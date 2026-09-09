import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from html import escape
from typing import Iterable
from urllib.parse import quote

import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import app, module, _authorized_admin_session

VERIFY_TTL_SECONDS = 24 * 60 * 60
NOTION_PAGE_URL = "https://api.notion.com/v1/pages"
RESEND_API_URL = "https://api.resend.com/emails"
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Preserve the current production handler so the new flow can be disabled instantly
# with INQUIRY_V2_ENABLED=false.
LEGACY_INQUIRY_ENDPOINT = None
_kept_routes = []
for _route in app.router.routes:
    if (
        getattr(_route, "path", None) == "/api/inquiry"
        and "POST" in (getattr(_route, "methods", None) or set())
    ):
        LEGACY_INQUIRY_ENDPOINT = getattr(_route, "endpoint", None)
        continue
    _kept_routes.append(_route)
app.router.routes = _kept_routes


def _enabled() -> bool:
    return os.environ.get("INQUIRY_V2_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _reference_code() -> str:
    stamp = time.strftime("%y%m%d", time.gmtime())
    suffix = "".join(secrets.choice(REF_ALPHABET) for _ in range(6))
    return f"RVS-{stamp}-{suffix}"


def _verification_secret() -> str:
    return (
        os.environ.get("INQUIRY_VERIFICATION_SECRET", "").strip()
        or os.environ.get("ADMIN_SESSION_SECRET", "").strip()
    )


def _sign_verification(payload: dict) -> str:
    secret = _verification_secret()
    if len(secret) < 32:
        raise RuntimeError("Inquiry verification secret is not configured.")
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(body).rstrip(b"=").decode("ascii")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{encoded}.{sig}"


def _decode_b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))


def _verify_token(token: str) -> dict | None:
    secret = _verification_secret()
    if len(secret) < 32 or not token or "." not in token:
        return None
    try:
        encoded, supplied_sig = token.split(".", 1)
        expected = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        supplied = _decode_b64url(supplied_sig)
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(_decode_b64url(encoded).decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _verification_token(reference: str, page_id: str) -> str:
    now = int(time.time())
    return _sign_verification(
        {
            "kind": "inquiry-email",
            "ref": reference,
            "page_id": page_id,
            "iat": now,
            "exp": now + VERIFY_TTL_SECONDS,
        }
    )


def _verify_url(token: str) -> str:
    return f"{module.BACKEND_ORIGIN}/verify/inquiry?token={quote(token, safe='')}"


def _continue_url(token: str) -> str:
    return f"{module.BACKEND_ORIGIN}/continue/whatsapp?token={quote(token, safe='')}"


def _whatsapp_number() -> str:
    raw = os.environ.get("WHATSAPP_CONTACT_NUMBER", "").strip()
    return "".join(ch for ch in raw if ch.isdigit())


def _whatsapp_url(reference: str) -> str:
    number = _whatsapp_number()
    message = (
        "Hi Rochelle! I verified my website inquiry. "
        f"My reference is {reference}, and I'd like to continue here."
    )
    return f"https://wa.me/{number}?text={quote(message, safe='')}"


def _owner_emails() -> list[str]:
    raw = os.environ.get("OWNER_NOTIFICATION_EMAILS", "")
    parts = raw.replace(";", ",").split(",")
    values = []
    for part in parts:
        email = part.strip().lower()
        if email and module.EMAIL_RE.match(email) and email not in values:
            values.append(email)
    return values


def _notion_headers() -> dict:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": module.NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "RVS-Inquiry-Verification/1.0",
    }


async def _send_email(
    recipients: list[str],
    subject: str,
    text: str,
    html: str,
    reply_to: str = "",
) -> bool:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key or not recipients:
        return False

    sender = os.environ.get(
        "EMAIL_FROM", "RVS Website <onboarding@resend.dev>"
    ).strip()
    payload = {
        "from": sender,
        "to": recipients,
        "subject": subject[:200],
        "text": text,
        "html": html,
    }
    if reply_to and module.EMAIL_RE.match(reply_to):
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "RVS-Website-Inquiry/2.0",
                },
                json=payload,
            )
        return 200 <= response.status_code < 300
    except httpx.HTTPError:
        return False


def _page(
    title: str,
    body: str,
    button_url: str = "",
    button_text: str = "",
    secondary_url: str = "",
    secondary_text: str = "",
) -> HTMLResponse:
    button = ""
    secondary = ""
    if button_url and button_text:
        button = (
            f'<a class="button" href="{escape(button_url, quote=True)}">'
            f"{escape(button_text)}</a>"
        )
    if secondary_url and secondary_text:
        secondary = (
            f'<a class="secondary" href="{escape(secondary_url, quote=True)}">'
            f"{escape(secondary_text)}</a>"
        )
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{escape(title)}</title>
<style>
body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}
main{{width:min(680px,calc(100% - 36px));margin:10vh auto;padding:34px;border:1px solid #6d5846;background:radial-gradient(circle at 15% 18%,rgba(203,143,150,.12),transparent 28%),#181512}}
h1{{font-family:Georgia,serif;font-weight:500;color:#d1ab63}}
p{{color:#d8cbc1}}code{{color:#f5dfb9;font-size:1.05rem}}
label{{display:block;margin:14px 0 5px;color:#f7f1ea;font-weight:700}}
input,textarea{{width:100%;box-sizing:border-box;background:#11100f;color:#f7f1ea;border:1px solid #6d5846;padding:11px;border-radius:8px;font:inherit}}
textarea{{min-height:120px;resize:vertical}}
.button,button{{display:inline-block;margin-top:14px;color:#11100f;background:#d1ab63;padding:10px 16px;border:0;border-radius:999px;text-decoration:none;font-weight:800;cursor:pointer}}
.secondary{{display:inline-block;margin:14px 0 0 10px;color:#f5dfb9;text-decoration:none}}
.note{{font-size:.92rem;color:#b9aca1}}
</style>
</head>
<body><main><h1>{escape(title)}</h1>{body}{button}{secondary}</main></body></html>""",
        headers={"Cache-Control": "no-store"},
    )


def _submission_page(
    reference: str,
    return_url: str,
    verification_sent: bool,
) -> HTMLResponse:
    if verification_sent:
        body = (
            "<p>Your inquiry has been securely recorded.</p>"
            f"<p>Reference: <code>{escape(reference)}</code></p>"
            "<p>Please check your email and use the verification link. "
            "After verification, you can continue the conversation on WhatsApp without repeating your inquiry details.</p>"
        )
    else:
        body = (
            "<p>Your inquiry has been securely recorded, but the verification email could not be sent right now.</p>"
            f"<p>Keep this reference: <code>{escape(reference)}</code></p>"
            "<p>Your inquiry is still safely in the client requests inbox. "
            "You can return to the website and use the listed contact options if needed.</p>"
        )
    return _page(
        "Inquiry received",
        body,
        secondary_url=return_url,
        secondary_text="Return to the website",
    )


async def _notify_owner_new_inquiry(
    reference: str,
    name: str,
    company: str,
    email: str,
    source_label: str,
    notion_url: str,
) -> bool:
    recipients = _owner_emails()
    if not recipients:
        return False

    safe_ref = escape(reference)
    safe_name = escape(name)
    safe_company = escape(company)
    safe_email = escape(email)
    safe_source = escape(source_label)
    safe_url = escape(notion_url, quote=True)

    text = (
        f"New website inquiry: {reference}\n"
        f"Name: {name}\n"
        f"Company: {company}\n"
        f"Email: {email}\n"
        f"Source: {source_label}\n"
        "Email verification: Pending\n"
        f"Notion: {notion_url}\n"
    )
    html = (
        f"<h2>New website inquiry</h2>"
        f"<p><strong>Reference:</strong> {safe_ref}<br>"
        f"<strong>Name:</strong> {safe_name}<br>"
        f"<strong>Company:</strong> {safe_company}<br>"
        f"<strong>Email:</strong> {safe_email}<br>"
        f"<strong>Source:</strong> {safe_source}<br>"
        "<strong>Email verification:</strong> Pending</p>"
        f'<p><a href="{safe_url}">Open the inquiry in Notion</a></p>'
    )
    return await _send_email(
        recipients,
        f"New website inquiry — {reference}",
        text,
        html,
        reply_to=email,
    )


@app.post("/api/inquiry")
async def submit_inquiry_v2(request: Request):
    if not _enabled():
        if LEGACY_INQUIRY_ENDPOINT is None:
            return module.form_error(
                "The inquiry service is temporarily unavailable.",
                module.SITE_ORIGIN,
                503,
            )
        return await LEGACY_INQUIRY_ENDPOINT(request)

    if not module.request_is_from_site(request):
        return module.form_error(
            "This form submission was not accepted.", module.SITE_ORIGIN, 403
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > module.MAX_CONTENT_LENGTH:
                return module.form_error(
                    "The form submission was too large.", module.SITE_ORIGIN, 413
                )
        except ValueError:
            pass

    form = await request.form()
    source_key = module.clean(form.get("source"), 40).lower()
    source = module.SOURCE_CONFIG.get(source_key)
    if not source:
        return module.form_error(
            "The form source could not be verified.", module.SITE_ORIGIN
        )

    return_url = source["return_url"]
    if module.clean(form.get("website"), 200):
        return module.success_page(return_url)

    name = module.clean(form.get("name"), 120)
    company = module.clean(form.get("company"), 180)
    email = module.clean(form.get("email"), 254).lower()
    phone = module.clean(form.get("phone"), 80)
    message = module.clean_message(form.get("message"))
    preferred = module.clean(form.get("preferredContact"), 80)

    channels_raw: Iterable[str] = form.getlist("phoneChannel")
    channels = [module.clean(value, 40) for value in channels_raw]
    channels = [
        value for value in channels if value in module.ALLOWED_PHONE_CHANNELS
    ]

    if not name or not company or not email or not message or not preferred:
        return module.form_error("Please complete all required fields.", return_url)
    if not module.EMAIL_RE.match(email):
        return module.form_error("Please enter a valid email address.", return_url)
    if preferred not in module.ALLOWED_PREFERRED_CONTACT:
        return module.form_error(
            "Please select a valid preferred contact method.", return_url
        )
    if (preferred == "Phone" or channels) and not phone:
        return module.form_error(
            "Please add a phone number when selecting phone, Viber, WhatsApp, or mobile contact.",
            return_url,
        )

    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    data_source_id = os.environ.get(
        "NOTION_DATA_SOURCE_ID", module.DEFAULT_DATA_SOURCE_ID
    ).strip()
    if not notion_token:
        return module.form_error(
            "The secure form endpoint is not fully configured yet.",
            return_url,
            503,
        )
    if len(_verification_secret()) < 32:
        return module.form_error(
            "The inquiry verification service is not configured yet.",
            return_url,
            503,
        )

    reference = _reference_code()
    notion_channels = [
        "Mobile" if value == "Mobile call" else value for value in channels
    ]
    request_title = f"Website inquiry — {name}"
    if company:
        request_title += f" — {company}"

    properties = {
        "Request": module.title_text(request_title),
        "Requester Name": module.rich_text(name),
        "Requester Email": {"email": email},
        "Company / Client Name": module.rich_text(company),
        "Details": module.rich_text(message),
        "Request Type": {"select": {"name": source["request_type"]}},
        "Status": {"select": {"name": "New"}},
        "Source": {"select": {"name": source["label"]}},
        "Preferred Contact": {"select": {"name": preferred}},
        "Supporting Link": {"url": source["page_url"]},
        "Reference Code": module.rich_text(reference),
        "Email Verification": {"select": {"name": "Pending"}},
        "WhatsApp Continued": {"checkbox": False},
    }
    if phone:
        properties["Phone"] = {"phone_number": phone}
    if notion_channels:
        properties["Contact Channels"] = {
            "multi_select": [{"name": value} for value in notion_channels]
        }

    payload = {
        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
        "properties": properties,
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                module.NOTION_API_URL,
                headers=_notion_headers(),
                json=payload,
            )
    except httpx.HTTPError:
        return module.form_error(
            "There was a temporary connection problem. Please try again in a moment.",
            return_url,
            502,
        )

    if response.status_code not in (200, 201):
        return module.form_error(
            "The inquiry could not be saved right now. Please try again shortly.",
            return_url,
            502,
        )

    created = response.json()
    page_id = str(created.get("id", "")).strip()
    notion_url = str(created.get("url", "")).strip()
    if not page_id:
        return module.form_error(
            "The inquiry was saved, but the verification step could not be prepared.",
            return_url,
            502,
        )

    token = _verification_token(reference, page_id)
    verify_url = _verify_url(token)

    verify_text = (
        f"Hi {name},\n\n"
        "Please verify the email address used for your inquiry to Rochelle V. Silvestre.\n\n"
        f"Inquiry reference: {reference}\n"
        f"Verify your email: {verify_url}\n\n"
        "This link expires in 24 hours. If you did not submit this inquiry, you can ignore this email."
    )
    verify_html = (
        f"<p>Hi {escape(name)},</p>"
        "<p>Please verify the email address used for your inquiry to Rochelle V. Silvestre.</p>"
        f"<p><strong>Inquiry reference:</strong> {escape(reference)}</p>"
        f'<p><a href="{escape(verify_url, quote=True)}">Verify my email</a></p>'
        "<p>This link expires in 24 hours. If you did not submit this inquiry, you can ignore this email.</p>"
    )
    verification_sent = await _send_email(
        [email],
        f"Verify your inquiry — {reference}",
        verify_text,
        verify_html,
    )

    await _notify_owner_new_inquiry(
        reference,
        name,
        company,
        email,
        source["label"],
        notion_url,
    )

    return _submission_page(reference, return_url, verification_sent)


@app.get("/verify/inquiry")
async def verify_inquiry(request: Request):
    token = request.query_params.get("token", "")
    payload = _verify_token(token)
    if not payload or payload.get("kind") != "inquiry-email":
        return _page(
            "Verification link invalid",
            "<p>This verification link is invalid or has expired.</p>",
        )

    reference = str(payload.get("ref", "")).strip()
    page_id = str(payload.get("page_id", "")).strip()
    if not reference or not page_id:
        return _page(
            "Verification link invalid",
            "<p>The verification link is incomplete.</p>",
        )

    if not os.environ.get("NOTION_TOKEN", "").strip():
        return _page(
            "Verification unavailable",
            "<p>The inquiry service is temporarily unavailable.</p>",
        )

    verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    patch = {
        "properties": {
            "Email Verification": {"select": {"name": "Verified"}},
            "Verified At": {"date": {"start": verified_at}},
        }
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.patch(
                f"{NOTION_PAGE_URL}/{page_id}",
                headers=_notion_headers(),
                json=patch,
            )
    except httpx.HTTPError:
        return _page(
            "Verification unavailable",
            "<p>There was a temporary connection problem. Please try the link again.</p>",
        )

    if response.status_code != 200:
        return _page(
            "Verification unavailable",
            "<p>Your inquiry could not be verified right now. Please try again shortly.</p>",
        )

    body = (
        "<p>Your email verification is complete.</p>"
        f"<p>Your inquiry reference is <code>{escape(reference)}</code>.</p>"
        "<p>Your inquiry is already recorded, so you won't need to repeat the details when you continue on WhatsApp.</p>"
    )

    if _whatsapp_number():
        return _page(
            "Email verified",
            body,
            _continue_url(token),
            "Continue on WhatsApp",
            module.SITE_ORIGIN,
            "Return to the website",
        )
    return _page(
        "Email verified",
        body + "<p>WhatsApp continuation is not available right now.</p>",
        secondary_url=module.SITE_ORIGIN,
        secondary_text="Return to the website",
    )


@app.get("/continue/whatsapp")
async def continue_whatsapp(request: Request):
    token = request.query_params.get("token", "")
    payload = _verify_token(token)
    if not payload or payload.get("kind") != "inquiry-email":
        return _page(
            "Link invalid",
            "<p>This WhatsApp continuation link is invalid or has expired.</p>",
        )

    reference = str(payload.get("ref", "")).strip()
    page_id = str(payload.get("page_id", "")).strip()
    if not reference or not page_id or not _whatsapp_number():
        return _page(
            "WhatsApp unavailable",
            "<p>This WhatsApp continuation link is incomplete or unavailable.</p>",
        )

    if os.environ.get("NOTION_TOKEN", "").strip():
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.patch(
                    f"{NOTION_PAGE_URL}/{page_id}",
                    headers=_notion_headers(),
                    json={"properties": {"WhatsApp Continued": {"checkbox": True}}},
                )
        except httpx.HTTPError:
            pass

    return RedirectResponse(
        _whatsapp_url(reference),
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )


async def _create_test_inquiry(
    name: str, company: str, email: str, message: str
) -> tuple[str, str]:
    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    data_source_id = os.environ.get(
        "NOTION_DATA_SOURCE_ID", module.DEFAULT_DATA_SOURCE_ID
    ).strip()
    if not notion_token:
        raise RuntimeError("Notion is not configured.")

    reference = _reference_code()
    request_title = f"Website inquiry — {name}"
    if company:
        request_title += f" — {company}"

    properties = {
        "Request": module.title_text(request_title),
        "Requester Name": module.rich_text(name),
        "Requester Email": {"email": email},
        "Company / Client Name": module.rich_text(company),
        "Details": module.rich_text(message),
        "Request Type": {"select": {"name": "Other"}},
        "Status": {"select": {"name": "New"}},
        "Source": {"select": {"name": "Website — Homepage"}},
        "Preferred Contact": {"select": {"name": "Email"}},
        "Supporting Link": {"url": f"{module.SITE_ORIGIN}/"},
        "Reference Code": module.rich_text(reference),
        "Email Verification": {"select": {"name": "Pending"}},
        "WhatsApp Continued": {"checkbox": False},
        "Internal Notes": module.rich_text("Admin verification-flow test."),
    }
    payload = {
        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
        "properties": properties,
    }

    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            module.NOTION_API_URL,
            headers=_notion_headers(),
            json=payload,
        )
    if response.status_code not in (200, 201):
        raise RuntimeError("Notion rejected the test inquiry.")

    page_id = str(response.json().get("id", "")).strip()
    if not page_id:
        raise RuntimeError("Notion did not return the created record ID.")

    token = _verification_token(reference, page_id)
    return reference, _verify_url(token)


@app.get("/admin/inquiry-test")
async def inquiry_test_form(request: Request):
    if not _authorized_admin_session(request):
        return HTMLResponse(
            "Unauthorized",
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )
    body = """
<p>This creates a real test record in Client Requests Inbox and gives you the verification link directly.</p>
<form method="post" action="/admin/inquiry-test">
<label>Name</label><input name="name" required value="RVS Test">
<label>Company</label><input name="company" required value="RVS Internal Test">
<label>Email</label><input name="email" type="email" required>
<label>Message</label><textarea name="message" required>Testing the inquiry reference, verification, Notion update, and WhatsApp handoff.</textarea>
<button type="submit">Create test inquiry</button>
</form>
<p class="note">This admin-only route can test the verification and WhatsApp steps even before live website forms are enabled.</p>
"""
    return _page("Inquiry verification test", body)


@app.post("/admin/inquiry-test")
async def inquiry_test_submit(request: Request):
    if not _authorized_admin_session(request):
        return HTMLResponse(
            "Unauthorized",
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )
    form = await request.form()
    name = module.clean(form.get("name"), 120)
    company = module.clean(form.get("company"), 180)
    email = module.clean(form.get("email"), 254).lower()
    message = module.clean_message(form.get("message"))
    if (
        not name
        or not company
        or not email
        or not message
        or not module.EMAIL_RE.match(email)
    ):
        return _page(
            "Test could not be created",
            "<p>Please provide valid test details.</p>",
        )
    try:
        reference, verify_url = await _create_test_inquiry(
            name, company, email, message
        )
    except (RuntimeError, httpx.HTTPError):
        return _page(
            "Test could not be created",
            "<p>The test inquiry could not be saved to Notion.</p>",
        )
    body = (
        "<p>The test inquiry was created in Notion.</p>"
        f"<p>Reference: <code>{escape(reference)}</code></p>"
        "<p>Use the button below as the stand-in for the verification email.</p>"
    )
    return _page(
        "Test inquiry created",
        body,
        verify_url,
        "Verify test inquiry",
    )
