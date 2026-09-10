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

from . import main as legacy

app = legacy.app
VERIFY_TTL_SECONDS = 24 * 60 * 60
WHATSAPP_TTL_SECONDS = 24 * 60 * 60
RESEND_API_URL = "https://api.resend.com/emails"
NOTION_PAGE_URL = "https://api.notion.com/v1/pages"
DEFAULT_BACKEND_ORIGIN = "https://rochelle-va-inquiries.wasmer.app"
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Replace only the POST /api/inquiry route in this test entrypoint. When the
# feature flag is off, requests are passed straight to the current handler.
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


def enabled() -> bool:
    return os.environ.get("INQUIRY_V2_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def backend_origin() -> str:
    return os.environ.get("BACKEND_ORIGIN", DEFAULT_BACKEND_ORIGIN).strip().rstrip("/")


def verification_secret() -> str:
    return os.environ.get("INQUIRY_VERIFICATION_SECRET", "").strip()


def reference_code() -> str:
    stamp = time.strftime("%y%m%d", time.gmtime())
    suffix = "".join(secrets.choice(REF_ALPHABET) for _ in range(6))
    return f"RVS-{stamp}-{suffix}"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))


def sign_token(kind: str, reference: str, page_id: str, ttl_seconds: int) -> str:
    secret = verification_secret()
    if len(secret) < 32:
        raise RuntimeError("Inquiry verification secret is not configured.")
    now = int(time.time())
    payload = {
        "kind": kind,
        "ref": reference,
        "page_id": page_id,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    encoded = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded}.{_b64url_encode(signature)}"


def verify_token(token: str, expected_kind: str) -> dict | None:
    secret = verification_secret()
    if len(secret) < 32 or not token or "." not in token:
        return None
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(supplied_signature)):
            return None
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("kind") != expected_kind:
            return None
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def owner_emails() -> list[str]:
    values: list[str] = []
    raw = os.environ.get("OWNER_NOTIFICATION_EMAILS", "")
    for part in raw.replace(";", ",").split(","):
        email = part.strip().lower()
        if email and legacy.EMAIL_RE.match(email) and email not in values:
            values.append(email)
    return values


def whatsapp_number() -> str:
    raw = os.environ.get("WHATSAPP_CONTACT_NUMBER", "").strip()
    return "".join(ch for ch in raw if ch.isdigit())


def notion_headers() -> dict:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": legacy.NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "RVS-Website-Inquiry/2.0",
    }


def result_page(
    title: str,
    body: str,
    button_url: str = "",
    button_text: str = "",
    secondary_url: str = "",
    secondary_text: str = "",
) -> HTMLResponse:
    button = (
        f'<a class="button" href="{escape(button_url, quote=True)}">{escape(button_text)}</a>'
        if button_url and button_text else ""
    )
    secondary = (
        f'<a class="secondary" href="{escape(secondary_url, quote=True)}">{escape(secondary_text)}</a>'
        if secondary_url and secondary_text else ""
    )
    return HTMLResponse(
        f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{escape(title)}</title><style>body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 36px));margin:10vh auto;padding:34px;border:1px solid #6d5846;background:radial-gradient(circle at 15% 18%,rgba(203,143,150,.12),transparent 28%),#181512}}h1{{font-family:Georgia,serif;font-weight:500;color:#d1ab63}}p{{color:#d8cbc1}}code{{color:#f5dfb9}}.button{{display:inline-block;margin-top:14px;color:#11100f;background:#d1ab63;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:800}}.secondary{{display:inline-block;margin:14px 0 0 10px;color:#f5dfb9;text-decoration:none}}</style></head><body><main><h1>{escape(title)}</h1>{body}{button}{secondary}</main></body></html>''',
        headers={"Cache-Control": "no-store"},
    )


async def send_email(
    recipients: list[str],
    subject: str,
    text: str,
    html: str,
    reply_to: str = "",
) -> bool:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key or not recipients:
        return False
    payload = {
        "from": os.environ.get(
            "EMAIL_FROM", "RVS Website <onboarding@resend.dev>"
        ).strip(),
        "to": recipients,
        "subject": subject[:200],
        "text": text,
        "html": html,
    }
    if reply_to and legacy.EMAIL_RE.match(reply_to):
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


async def notify_owner(
    reference: str,
    name: str,
    company: str,
    email: str,
    phone: str,
    preferred: str,
    source_label: str,
    message: str,
    notion_url: str,
) -> bool:
    recipients = owner_emails()
    if not recipients:
        return False
    phone_text = f"Phone: {phone}\n" if phone else ""
    text = (
        f"New website inquiry: {reference}\n"
        f"Name: {name}\nCompany: {company}\nEmail: {email}\n{phone_text}"
        f"Preferred contact: {preferred}\nSource: {source_label}\n"
        "Email verification: Pending\n\n"
        f"Message:\n{message}\n\nOpen in Notion: {notion_url}\n"
    )
    phone_html = f"<br><strong>Phone:</strong> {escape(phone)}" if phone else ""
    html = (
        f"<h2>New website inquiry</h2><p><strong>Reference:</strong> {escape(reference)}<br>"
        f"<strong>Name:</strong> {escape(name)}<br><strong>Company:</strong> {escape(company)}<br>"
        f"<strong>Email:</strong> {escape(email)}{phone_html}<br>"
        f"<strong>Preferred contact:</strong> {escape(preferred)}<br>"
        f"<strong>Source:</strong> {escape(source_label)}<br>"
        "<strong>Email verification:</strong> Pending</p>"
        f"<p><strong>Message:</strong><br>{escape(message).replace(chr(10), '<br>')}</p>"
        f'<p><a href="{escape(notion_url, quote=True)}">Open the inquiry in Notion</a></p>'
    )
    return await send_email(
        recipients,
        f"New website inquiry — {reference}",
        text,
        html,
        reply_to=email,
    )


async def send_verification(name: str, email: str, reference: str, page_id: str) -> bool:
    token = sign_token("inquiry-email", reference, page_id, VERIFY_TTL_SECONDS)
    url = f"{backend_origin()}/verify/inquiry?token={quote(token, safe='')}"
    text = (
        f"Hi {name},\n\nPlease verify the email address used for your inquiry to Rochelle V. Silvestre.\n\n"
        f"Inquiry reference: {reference}\nVerify your email: {url}\n\n"
        "This link expires in 24 hours. If you did not submit this inquiry, you can ignore this email."
    )
    html = (
        f"<p>Hi {escape(name)},</p>"
        "<p>Please verify the email address used for your inquiry to Rochelle V. Silvestre.</p>"
        f"<p><strong>Inquiry reference:</strong> {escape(reference)}</p>"
        f'<p><a href="{escape(url, quote=True)}">Verify my email</a></p>'
        "<p>This link expires in 24 hours. If you did not submit this inquiry, you can ignore this email.</p>"
    )
    return await send_email(
        [email], f"Verify your inquiry — {reference}", text, html
    )


@app.post("/api/inquiry")
async def submit_inquiry_v2(request: Request):
    if not enabled():
        if LEGACY_INQUIRY_ENDPOINT is None:
            return legacy.form_error(
                "The inquiry service is temporarily unavailable.", legacy.SITE_ORIGIN, 503
            )
        return await LEGACY_INQUIRY_ENDPOINT(request)

    if not legacy.request_is_from_site(request):
        return legacy.form_error("This form submission was not accepted.", legacy.SITE_ORIGIN, 403)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > legacy.MAX_CONTENT_LENGTH:
                return legacy.form_error("The form submission was too large.", legacy.SITE_ORIGIN, 413)
        except ValueError:
            pass

    form = await request.form()
    source = legacy.SOURCE_CONFIG.get(legacy.clean(form.get("source"), 40).lower())
    if not source:
        return legacy.form_error("The form source could not be verified.", legacy.SITE_ORIGIN)
    return_url = source["return_url"]

    if legacy.clean(form.get("website"), 200):
        return legacy.success_page(return_url)

    name = legacy.clean(form.get("name"), 120)
    company = legacy.clean(form.get("company"), 180)
    email = legacy.clean(form.get("email"), 254).lower()
    phone = legacy.clean(form.get("phone"), 80)
    message = legacy.clean_message(form.get("message"))
    preferred = legacy.clean(form.get("preferredContact"), 80)
    channels_raw: Iterable[str] = form.getlist("phoneChannel")
    channels = [legacy.clean(v, 40) for v in channels_raw]
    channels = [v for v in channels if v in legacy.ALLOWED_PHONE_CHANNELS]

    if not name or not company or not email or not message or not preferred:
        return legacy.form_error("Please complete all required fields.", return_url)
    if not legacy.EMAIL_RE.match(email):
        return legacy.form_error("Please enter a valid email address.", return_url)
    if preferred not in legacy.ALLOWED_PREFERRED_CONTACT:
        return legacy.form_error("Please select a valid preferred contact method.", return_url)
    if (preferred == "Phone" or channels) and not phone:
        return legacy.form_error(
            "Please add a phone number when selecting phone, Viber, WhatsApp, or mobile contact.",
            return_url,
        )

    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    data_source_id = os.environ.get(
        "NOTION_DATA_SOURCE_ID", legacy.DEFAULT_DATA_SOURCE_ID
    ).strip()
    if not notion_token:
        return legacy.form_error("The secure form endpoint is not fully configured yet.", return_url, 503)
    if len(verification_secret()) < 32:
        return legacy.form_error("The inquiry verification service is not configured yet.", return_url, 503)

    reference = reference_code()
    request_title = f"Website inquiry — {name}" + (f" — {company}" if company else "")
    properties = {
        "Request": legacy.title_text(request_title),
        "Requester Name": legacy.rich_text(name),
        "Requester Email": {"email": email},
        "Company / Client Name": legacy.rich_text(company),
        "Details": legacy.rich_text(message),
        "Request Type": {"select": {"name": source["request_type"]}},
        "Status": {"select": {"name": "New"}},
        "Source": {"select": {"name": source["label"]}},
        "Preferred Contact": {"select": {"name": preferred}},
        "Supporting Link": {"url": source["page_url"]},
        "Reference Code": legacy.rich_text(reference),
        "Email Verification": {"select": {"name": "Pending"}},
        "WhatsApp Continued": {"checkbox": False},
    }
    if phone:
        properties["Phone"] = {"phone_number": phone}
    notion_channels = ["Mobile" if v == "Mobile call" else v for v in channels]
    if notion_channels:
        properties["Contact Channels"] = {
            "multi_select": [{"name": value} for value in notion_channels]
        }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                legacy.NOTION_API_URL,
                headers=notion_headers(),
                json={
                    "parent": {"type": "data_source_id", "data_source_id": data_source_id},
                    "properties": properties,
                },
            )
    except httpx.HTTPError:
        return legacy.form_error(
            "There was a temporary connection problem. Please try again in a moment.",
            return_url,
            502,
        )
    if response.status_code not in (200, 201):
        return legacy.form_error("The inquiry could not be saved right now. Please try again shortly.", return_url, 502)

    created = response.json()
    page_id = str(created.get("id", "")).strip()
    notion_url = str(created.get("url", "")).strip()
    if not page_id:
        return result_page(
            "Inquiry received",
            f"<p>Your inquiry was recorded. Keep this reference: <code>{escape(reference)}</code>.</p>",
            secondary_url=return_url,
            secondary_text="Return to the website",
        )

    verification_sent = await send_verification(name, email, reference, page_id)
    await notify_owner(
        reference, name, company, email, phone, preferred, source["label"], message, notion_url
    )

    detail = (
        "Please check your email and use the verification link. After verification, you can continue on WhatsApp without repeating your inquiry details."
        if verification_sent
        else "Your inquiry is safely recorded, but the verification email could not be sent right now. Keep this reference and use the website contact options if needed."
    )
    return result_page(
        "Inquiry received",
        f"<p>Reference: <code>{escape(reference)}</code></p><p>{escape(detail)}</p>",
        secondary_url=return_url,
        secondary_text="Return to the website",
    )


@app.get("/verify/inquiry")
async def verify_inquiry(request: Request):
    payload = verify_token(request.query_params.get("token", ""), "inquiry-email")
    if not payload:
        return result_page("Verification link invalid", "<p>This verification link is invalid or has expired.</p>")

    reference = legacy.clean(payload.get("ref"), 80)
    page_id = legacy.clean(payload.get("page_id"), 80)
    if not reference or not page_id or not os.environ.get("NOTION_TOKEN", "").strip():
        return result_page("Verification unavailable", "<p>The inquiry service is temporarily unavailable.</p>")

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.patch(
                f"{NOTION_PAGE_URL}/{page_id}",
                headers=notion_headers(),
                json={"properties": {
                    "Email Verification": {"select": {"name": "Verified"}},
                    "Verified At": {"date": {"start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}},
                }},
            )
    except httpx.HTTPError:
        return result_page("Verification unavailable", "<p>There was a temporary connection problem. Please try the link again.</p>")
    if response.status_code != 200:
        return result_page("Verification unavailable", "<p>Your inquiry could not be verified right now. Please try again shortly.</p>")

    body = (
        "<p>Your email verification is complete.</p>"
        f"<p>Your inquiry reference is <code>{escape(reference)}</code>.</p>"
        "<p>Your inquiry is already recorded, so you won't need to repeat the details.</p>"
    )
    if not whatsapp_number():
        return result_page("Email verified", body + "<p>WhatsApp continuation is not available right now.</p>")

    whatsapp_token = sign_token("inquiry-whatsapp", reference, page_id, WHATSAPP_TTL_SECONDS)
    continue_url = f"{backend_origin()}/continue/whatsapp?token={quote(whatsapp_token, safe='')}"
    return result_page(
        "Email verified",
        body,
        continue_url,
        "Continue on WhatsApp",
        legacy.SITE_ORIGIN,
        "Return to the website",
    )


@app.get("/continue/whatsapp")
async def continue_whatsapp(request: Request):
    payload = verify_token(request.query_params.get("token", ""), "inquiry-whatsapp")
    if not payload:
        return result_page("Link invalid", "<p>This WhatsApp continuation link is invalid or has expired.</p>")

    reference = legacy.clean(payload.get("ref"), 80)
    page_id = legacy.clean(payload.get("page_id"), 80)
    number = whatsapp_number()
    if not reference or not page_id or not number:
        return result_page("WhatsApp unavailable", "<p>This WhatsApp continuation link is unavailable.</p>")

    if os.environ.get("NOTION_TOKEN", "").strip():
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.patch(
                    f"{NOTION_PAGE_URL}/{page_id}",
                    headers=notion_headers(),
                    json={"properties": {"WhatsApp Continued": {"checkbox": True}}},
                )
        except httpx.HTTPError:
            pass

    message = (
        "Hi Rochelle! I verified my website inquiry. "
        f"My reference is {reference}, and I'd like to continue here."
    )
    return RedirectResponse(
        f"https://wa.me/{number}?text={quote(message, safe='')}",
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )
