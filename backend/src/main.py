import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from html import escape
from typing import Iterable
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

app = FastAPI(title="RVS Website Inquiry Endpoint", docs_url=None, redoc_url=None)

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2025-09-03"
DEFAULT_DATA_SOURCE_ID = "28ecfe15-bfb1-4265-abbe-c8c3e29a1a31"
SITE_ORIGIN = "https://rrlvsva.wasmer.app"
DEFAULT_BACKEND_ORIGIN = "https://rochelle-va-inquiries.wasmer.app"
RESEND_API_URL = "https://api.resend.com/emails"
VERIFY_TTL_SECONDS = 24 * 60 * 60
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_CONTENT_LENGTH = 32_768
MAX_MESSAGE_LENGTH = 6_000
MAX_SHORT_LENGTH = 300

SOURCE_CONFIG = {
    "homepage": {
        "label": "Website — Homepage",
        "request_type": "Other",
        "page_url": f"{SITE_ORIGIN}/",
        "return_url": f"{SITE_ORIGIN}/#contact",
    },
    "about": {
        "label": "Website — About",
        "request_type": "Other",
        "page_url": f"{SITE_ORIGIN}/about.html",
        "return_url": f"{SITE_ORIGIN}/about.html#contact",
    },
    "faq": {
        "label": "Website — FAQ",
        "request_type": "Question",
        "page_url": f"{SITE_ORIGIN}/faq.html",
        "return_url": f"{SITE_ORIGIN}/faq.html#contact",
    },
    "service-policies": {
        "label": "Website — Service Policies",
        "request_type": "Question",
        "page_url": f"{SITE_ORIGIN}/service-policies.html",
        "return_url": f"{SITE_ORIGIN}/service-policies.html#contact",
    },
    "privacy": {
        "label": "Website — Privacy",
        "request_type": "Question",
        "page_url": f"{SITE_ORIGIN}/privacy.html",
        "return_url": f"{SITE_ORIGIN}/privacy.html#contact-privacy",
    },
}

ALLOWED_PREFERRED_CONTACT = {
    "Email",
    "Phone",
    "Google Meet / Chat",
    "Zoom",
    "MS Teams",
}
ALLOWED_PHONE_CHANNELS = {"Viber", "WhatsApp", "Mobile call"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def clean(value: object, limit: int = MAX_SHORT_LENGTH) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]


def clean_message(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:MAX_MESSAGE_LENGTH]


def rich_text(value: str) -> dict:
    chunks = [value[i : i + 1900] for i in range(0, len(value), 1900)] or [""]
    return {
        "rich_text": [
            {"type": "text", "text": {"content": chunk}}
            for chunk in chunks
            if chunk
        ]
    }


def title_text(value: str) -> dict:
    return {
        "title": [
            {"type": "text", "text": {"content": value[:300]}}
        ]
    }


def form_error(message: str, return_url: str, status_code: int = 400) -> HTMLResponse:
    safe_message = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    safe_return = return_url.replace('"', "%22")
    return HTMLResponse(
        f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<meta name=\"robots\" content=\"noindex,nofollow\"><title>Form submission</title>
<style>body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 36px));margin:12vh auto;padding:34px;border:1px solid #6d5846;background:#181512}}h1{{font-family:Georgia,serif;font-weight:500;color:#d1ab63}}p{{color:#d8cbc1}}a{{display:inline-block;margin-top:12px;color:#11100f;background:#d1ab63;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:700}}</style></head>
<body><main><h1>We couldn’t send that yet.</h1><p>{safe_message}</p><a href=\"{safe_return}\">Return to the form</a></main></body></html>""",
        status_code=status_code,
    )


def success_page(return_url: str) -> HTMLResponse:
    safe_return = return_url.replace('"', "%22")
    return HTMLResponse(
        f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<meta name=\"robots\" content=\"noindex,nofollow\"><title>Inquiry received</title>
<style>body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 36px));margin:12vh auto;padding:34px;border:1px solid #6d5846;background:radial-gradient(circle at 15% 18%,rgba(203,143,150,.12),transparent 28%),#181512}}h1{{font-family:Georgia,serif;font-weight:500;color:#d1ab63}}p{{color:#d8cbc1}}a{{display:inline-block;margin-top:12px;color:#11100f;background:#d1ab63;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:700}}</style></head>
<body><main><h1>Thank you. Your inquiry has been received.</h1><p>Your message was sent securely to my client requests inbox for review.</p><a href=\"{safe_return}\">Return to the website</a></main></body></html>""",
        status_code=200,
    )


def flow_page(
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
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{escape(title)}</title>
<style>body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 36px));margin:10vh auto;padding:34px;border:1px solid #6d5846;background:radial-gradient(circle at 15% 18%,rgba(203,143,150,.12),transparent 28%),#181512}}h1{{font-family:Georgia,serif;font-weight:500;color:#d1ab63}}p{{color:#d8cbc1}}code{{color:#f5dfb9;font-size:1.05rem}}.button{{display:inline-block;margin-top:14px;color:#11100f;background:#d1ab63;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:800}}.secondary{{display:inline-block;margin:14px 0 0 10px;color:#f5dfb9;text-decoration:none}}</style></head>
<body><main><h1>{escape(title)}</h1>{body}{button}{secondary}</main></body></html>""",
        headers={"Cache-Control": "no-store"},
    )


def request_is_from_site(request: Request) -> bool:
    origin = (request.headers.get("origin") or "").rstrip("/")
    referer = request.headers.get("referer") or ""
    if origin:
        return origin == SITE_ORIGIN
    if referer:
        return referer.startswith(SITE_ORIGIN + "/") or referer == SITE_ORIGIN
    # Some privacy-focused clients omit both headers. Other validation still applies.
    return True


def inquiry_v2_enabled() -> bool:
    return os.environ.get("INQUIRY_V2_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def backend_origin() -> str:
    return os.environ.get("BACKEND_ORIGIN", DEFAULT_BACKEND_ORIGIN).strip().rstrip("/")


def verification_secret() -> str:
    return os.environ.get("INQUIRY_VERIFICATION_SECRET", "").strip()


def reference_code() -> str:
    stamp = time.strftime("%y%m%d", time.gmtime())
    suffix = "".join(secrets.choice(REF_ALPHABET) for _ in range(6))
    return f"RVS-{stamp}-{suffix}"


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def sign_verification(payload: dict) -> str:
    secret = verification_secret()
    if len(secret) < 32:
        raise RuntimeError("Inquiry verification secret is not configured.")
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = b64url_encode(body)
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{b64url_encode(signature)}"


def verify_token(token: str) -> dict | None:
    secret = verification_secret()
    if len(secret) < 32 or not token or "." not in token:
        return None
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        supplied = b64url_decode(supplied_signature)
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(b64url_decode(encoded).decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def verification_token(reference: str, page_id: str) -> str:
    now = int(time.time())
    return sign_verification(
        {
            "kind": "inquiry-email",
            "ref": reference,
            "page_id": page_id,
            "iat": now,
            "exp": now + VERIFY_TTL_SECONDS,
        }
    )


def verify_url(token: str) -> str:
    return f"{backend_origin()}/verify/inquiry?token={quote(token, safe='')}"


def continue_url(token: str) -> str:
    return f"{backend_origin()}/continue/whatsapp?token={quote(token, safe='')}"


def whatsapp_number() -> str:
    raw = os.environ.get("WHATSAPP_CONTACT_NUMBER", "").strip()
    return "".join(ch for ch in raw if ch.isdigit())


def whatsapp_url(reference: str) -> str:
    message = (
        "Hi Rochelle! I verified my website inquiry. "
        f"My reference is {reference}, and I'd like to continue here."
    )
    return f"https://wa.me/{whatsapp_number()}?text={quote(message, safe='')}"


def owner_emails() -> list[str]:
    raw = os.environ.get("OWNER_NOTIFICATION_EMAILS", "")
    parts = raw.replace(";", ",").split(",")
    values: list[str] = []
    for part in parts:
        email = part.strip().lower()
        if email and EMAIL_RE.match(email) and email not in values:
            values.append(email)
    return values


def notion_headers(notion_token: str) -> dict:
    return {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "RVS-Website-Inquiry/2.0",
    }


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
    if reply_to and EMAIL_RE.match(reply_to):
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


async def notify_owner_new_inquiry(
    reference: str,
    name: str,
    company: str,
    email: str,
    source_label: str,
    preferred: str,
    message: str,
    notion_url: str,
) -> bool:
    recipients = owner_emails()
    if not recipients:
        return False

    safe_url = escape(notion_url, quote=True)
    text = (
        f"New website inquiry: {reference}\n"
        f"Name: {name}\n"
        f"Company: {company}\n"
        f"Email: {email}\n"
        f"Preferred contact: {preferred}\n"
        f"Source: {source_label}\n"
        "Email verification: Pending\n\n"
        f"Message:\n{message}\n\n"
        f"Notion: {notion_url}\n"
    )
    html = (
        "<h2>New website inquiry</h2>"
        f"<p><strong>Reference:</strong> {escape(reference)}<br>"
        f"<strong>Name:</strong> {escape(name)}<br>"
        f"<strong>Company:</strong> {escape(company)}<br>"
        f"<strong>Email:</strong> {escape(email)}<br>"
        f"<strong>Preferred contact:</strong> {escape(preferred)}<br>"
        f"<strong>Source:</strong> {escape(source_label)}<br>"
        "<strong>Email verification:</strong> Pending</p>"
        f"<p><strong>Message:</strong><br>{escape(message).replace(chr(10), '<br>')}</p>"
        f'<p><a href="{safe_url}">Open the inquiry in Notion</a></p>'
    )
    return await send_email(
        recipients,
        f"New website inquiry — {reference}",
        text,
        html,
        reply_to=email,
    )


async def send_verification_email(name: str, email: str, reference: str, url: str) -> bool:
    text = (
        f"Hi {name},\n\n"
        "Please verify the email address used for your inquiry to Rochelle V. Silvestre.\n\n"
        f"Inquiry reference: {reference}\n"
        f"Verify your email: {url}\n\n"
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
        [email],
        f"Verify your inquiry — {reference}",
        text,
        html,
    )


def submission_page(reference: str, return_url: str, verification_sent: bool) -> HTMLResponse:
    if verification_sent:
        body = (
            "<p>Your inquiry has been securely recorded.</p>"
            f"<p>Reference: <code>{escape(reference)}</code></p>"
            "<p>Please check your email and use the verification link. "
            "After verification, you can continue on WhatsApp without repeating your inquiry details.</p>"
        )
    else:
        body = (
            "<p>Your inquiry has been securely recorded, but the verification email could not be sent right now.</p>"
            f"<p>Keep this reference: <code>{escape(reference)}</code></p>"
            "<p>Your inquiry is still safely in the client requests inbox.</p>"
        )
    return flow_page(
        "Inquiry received",
        body,
        secondary_url=return_url,
        secondary_text="Return to the website",
    )


@app.get("/health")
async def health() -> JSONResponse:
    notion_configured = bool(os.environ.get("NOTION_TOKEN"))
    v2_enabled = inquiry_v2_enabled()
    v2_configured = bool(
        len(verification_secret()) >= 32
        and os.environ.get("RESEND_API_KEY", "").strip()
        and owner_emails()
    )
    return JSONResponse(
        {
            "ok": True,
            "notion_configured": notion_configured,
            "inquiry_v2_enabled": v2_enabled,
            "inquiry_v2_configured": v2_configured,
        }
    )


@app.post("/api/inquiry")
async def submit_inquiry(request: Request):
    if not request_is_from_site(request):
        return form_error("This form submission was not accepted.", SITE_ORIGIN, 403)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_CONTENT_LENGTH:
                return form_error("The form submission was too large.", SITE_ORIGIN, 413)
        except ValueError:
            pass

    form = await request.form()

    source_key = clean(form.get("source"), 40).lower()
    source = SOURCE_CONFIG.get(source_key)
    if not source:
        return form_error("The form source could not be verified.", SITE_ORIGIN)

    return_url = source["return_url"]

    # Honeypot: legitimate visitors never see or fill this field.
    if clean(form.get("website"), 200):
        return success_page(return_url)

    name = clean(form.get("name"), 120)
    company = clean(form.get("company"), 180)
    email = clean(form.get("email"), 254).lower()
    phone = clean(form.get("phone"), 80)
    message = clean_message(form.get("message"))
    preferred = clean(form.get("preferredContact"), 80)

    channels_raw: Iterable[str] = form.getlist("phoneChannel")
    channels = [clean(v, 40) for v in channels_raw]
    channels = [v for v in channels if v in ALLOWED_PHONE_CHANNELS]

    if not name or not company or not email or not message or not preferred:
        return form_error("Please complete all required fields.", return_url)
    if not EMAIL_RE.match(email):
        return form_error("Please enter a valid email address.", return_url)
    if preferred not in ALLOWED_PREFERRED_CONTACT:
        return form_error("Please select a valid preferred contact method.", return_url)
    if (preferred == "Phone" or channels) and not phone:
        return form_error(
            "Please add a phone number when selecting phone, Viber, WhatsApp, or mobile contact.",
            return_url,
        )

    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    data_source_id = os.environ.get(
        "NOTION_DATA_SOURCE_ID", DEFAULT_DATA_SOURCE_ID
    ).strip()
    if not notion_token:
        return form_error(
            "The secure form endpoint is not fully configured yet. Please use the email contact option for now.",
            return_url,
            503,
        )

    use_v2 = inquiry_v2_enabled()
    if use_v2:
        if len(verification_secret()) < 32:
            return form_error(
                "The inquiry verification service is not configured yet.",
                return_url,
                503,
            )
        if not os.environ.get("RESEND_API_KEY", "").strip():
            return form_error(
                "The inquiry email service is not configured yet.",
                return_url,
                503,
            )

    notion_channels = ["Mobile" if v == "Mobile call" else v for v in channels]
    request_title = f"Website inquiry — {name}"
    if company:
        request_title += f" — {company}"

    reference = reference_code() if use_v2 else ""
    properties = {
        "Request": title_text(request_title),
        "Requester Name": rich_text(name),
        "Requester Email": {"email": email},
        "Company / Client Name": rich_text(company),
        "Details": rich_text(message),
        "Request Type": {"select": {"name": source["request_type"]}},
        "Status": {"select": {"name": "New"}},
        "Source": {"select": {"name": source["label"]}},
        "Preferred Contact": {"select": {"name": preferred}},
        "Supporting Link": {"url": source["page_url"]},
    }
    if use_v2:
        properties["Reference Code"] = rich_text(reference)
        properties["Email Verification"] = {"select": {"name": "Pending"}}
        properties["WhatsApp Continued"] = {"checkbox": False}
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
                NOTION_API_URL,
                headers=notion_headers(notion_token),
                json=payload,
            )
    except httpx.HTTPError:
        return form_error(
            "There was a temporary connection problem. Please try again in a moment.",
            return_url,
            502,
        )

    if response.status_code not in (200, 201):
        # Do not expose Notion response bodies or secrets to public visitors.
        return form_error(
            "The inquiry could not be saved right now. Please try again shortly or use the email contact option.",
            return_url,
            502,
        )

    if not use_v2:
        return success_page(return_url)

    created = response.json()
    page_id = str(created.get("id", "")).strip()
    notion_url = str(created.get("url", "")).strip()
    if not page_id:
        return form_error(
            "The inquiry was saved, but the verification step could not be prepared.",
            return_url,
            502,
        )

    token = verification_token(reference, page_id)
    url = verify_url(token)

    verification_sent = await send_verification_email(name, email, reference, url)
    await notify_owner_new_inquiry(
        reference,
        name,
        company,
        email,
        source["label"],
        preferred,
        message,
        notion_url,
    )

    return submission_page(reference, return_url, verification_sent)


@app.get("/verify/inquiry")
async def verify_inquiry(request: Request):
    token = request.query_params.get("token", "")
    payload = verify_token(token)
    if not payload or payload.get("kind") != "inquiry-email":
        return flow_page(
            "Verification link invalid",
            "<p>This verification link is invalid or has expired.</p>",
        )

    reference = str(payload.get("ref", "")).strip()
    page_id = str(payload.get("page_id", "")).strip()
    if not reference or not page_id:
        return flow_page(
            "Verification link invalid",
            "<p>The verification link is incomplete.</p>",
        )

    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    if not notion_token:
        return flow_page(
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
                f"{NOTION_API_URL}/{page_id}",
                headers=notion_headers(notion_token),
                json=patch,
            )
    except httpx.HTTPError:
        return flow_page(
            "Verification unavailable",
            "<p>There was a temporary connection problem. Please try the link again.</p>",
        )

    if response.status_code != 200:
        return flow_page(
            "Verification unavailable",
            "<p>Your inquiry could not be verified right now. Please try again shortly.</p>",
        )

    body = (
        "<p>Your email verification is complete.</p>"
        f"<p>Your inquiry reference is <code>{escape(reference)}</code>.</p>"
        "<p>Your inquiry is already recorded, so you won’t need to repeat the details if you continue on WhatsApp.</p>"
    )

    if whatsapp_number():
        return flow_page(
            "Email verified",
            body,
            continue_url(token),
            "Continue on WhatsApp",
            SITE_ORIGIN,
            "Return to the website",
        )
    return flow_page(
        "Email verified",
        body + "<p>WhatsApp continuation is not available right now.</p>",
        secondary_url=SITE_ORIGIN,
        secondary_text="Return to the website",
    )


@app.get("/continue/whatsapp")
async def continue_whatsapp(request: Request):
    token = request.query_params.get("token", "")
    payload = verify_token(token)
    if not payload or payload.get("kind") != "inquiry-email":
        return flow_page(
            "Link invalid",
            "<p>This WhatsApp continuation link is invalid or has expired.</p>",
        )

    reference = str(payload.get("ref", "")).strip()
    page_id = str(payload.get("page_id", "")).strip()
    if not reference or not page_id or not whatsapp_number():
        return flow_page(
            "WhatsApp unavailable",
            "<p>This WhatsApp continuation link is incomplete or unavailable.</p>",
        )

    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    if notion_token:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.patch(
                    f"{NOTION_API_URL}/{page_id}",
                    headers=notion_headers(notion_token),
                    json={"properties": {"WhatsApp Continued": {"checkbox": True}}},
                )
        except httpx.HTTPError:
            pass

    return RedirectResponse(
        whatsapp_url(reference),
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )
