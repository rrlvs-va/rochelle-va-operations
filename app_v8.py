import os
from html import escape
from typing import Iterable

import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

import app_v2 as inquiry_backend
from app_v7 import app

module = inquiry_backend.module
RESEND_API_URL = "https://api.resend.com/emails"

ALLOWED_PREFERRED_CONTACT = {
    "Email",
    "Phone",
    "Google Meet / Chat",
    "Zoom",
    "MS Teams",
    "Asana",
    "monday.com",
    "Slack",
    "Atlassian / Jira",
}
module.ALLOWED_PREFERRED_CONTACT = ALLOWED_PREFERRED_CONTACT

# app_v2 contains the superseded email-verification / WhatsApp handoff flow.
# Remove those public routes and install the corrected owner-notification flow
# while preserving the existing admin/blog route chain from app_v7.
_REMOVED_PATHS = {"/api/inquiry", "/verify/inquiry", "/continue/whatsapp"}
app.router.routes = [
    route
    for route in app.router.routes
    if getattr(route, "path", None) not in _REMOVED_PATHS
]


def _owner_notifications_enabled() -> bool:
    return os.environ.get("INQUIRY_NOTIFICATIONS_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _owner_emails() -> list[str]:
    raw = os.environ.get("OWNER_NOTIFICATION_EMAILS", "")
    recipients: list[str] = []
    for part in raw.replace(";", ",").split(","):
        email = part.strip().lower()
        if email and module.EMAIL_RE.match(email) and email not in recipients:
            recipients.append(email)
    return recipients


def _success_page(return_url: str) -> HTMLResponse:
    safe_return = return_url.replace('"', "%22")
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Inquiry received</title>
<style>body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 36px));margin:12vh auto;padding:34px;border:1px solid #6d5846;background:radial-gradient(circle at 15% 18%,rgba(203,143,150,.12),transparent 28%),#181512}}h1{{font-family:Georgia,serif;font-weight:500;color:#d1ab63}}p{{color:#d8cbc1}}a{{display:inline-block;margin-top:12px;color:#11100f;background:#d1ab63;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:700}}</style></head>
<body><main><h1>Thank you for reaching out.</h1><p>Your contact details have been received. I’ll be in touch with you shortly.</p><a href="{safe_return}">Return to the website</a></main></body></html>""",
        status_code=200,
        headers={"Cache-Control": "no-store"},
    )


async def _send_owner_notification(
    *,
    name: str,
    company: str,
    email: str,
    phone: str,
    channels: list[str],
    preferred: str,
    contact_details: str,
    message: str,
    source_label: str,
    notion_url: str,
) -> bool:
    if not _owner_notifications_enabled():
        return False

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    recipients = _owner_emails()
    if not api_key or not recipients:
        return False

    sender = os.environ.get(
        "EMAIL_FROM", "RVS Website <onboarding@resend.dev>"
    ).strip()

    channel_text = ", ".join(channels) if channels else "Not specified"
    phone_text = phone or "Not provided"
    contact_details_text = contact_details or "Not provided"
    notion_text = notion_url or "Not available"

    text = (
        "New website inquiry\n\n"
        f"Name: {name}\n"
        f"Company / business: {company}\n"
        f"Email: {email}\n"
        f"Phone: {phone_text}\n"
        f"Number works with: {channel_text}\n"
        f"Preferred method: {preferred}\n"
        f"Platform / contact details: {contact_details_text}\n"
        f"Source: {source_label}\n\n"
        f"Message:\n{message}\n\n"
        f"Notion: {notion_text}\n"
    )

    html = (
        "<h2>New website inquiry</h2>"
        f"<p><strong>Name:</strong> {escape(name)}<br>"
        f"<strong>Company / business:</strong> {escape(company)}<br>"
        f"<strong>Email:</strong> {escape(email)}<br>"
        f"<strong>Phone:</strong> {escape(phone_text)}<br>"
        f"<strong>Number works with:</strong> {escape(channel_text)}<br>"
        f"<strong>Preferred method:</strong> {escape(preferred)}<br>"
        f"<strong>Platform / contact details:</strong> {escape(contact_details_text)}<br>"
        f"<strong>Source:</strong> {escape(source_label)}</p>"
        f"<p><strong>Message:</strong><br>{escape(message).replace(chr(10), '<br>')}</p>"
    )
    if notion_url:
        html += (
            f'<p><a href="{escape(notion_url, quote=True)}">'
            "Open this inquiry in Notion</a></p>"
        )

    payload = {
        "from": sender,
        "to": recipients,
        "subject": f"New website inquiry — {name}"[:200],
        "text": text,
        "html": html,
        "reply_to": email,
    }

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


@app.get("/health/notifications")
async def notification_health() -> JSONResponse:
    enabled = _owner_notifications_enabled()
    api_key_configured = bool(os.environ.get("RESEND_API_KEY", "").strip())
    recipients_configured = bool(_owner_emails())
    sender_configured = bool(os.environ.get("EMAIL_FROM", "").strip())
    return JSONResponse(
        {
            "ok": True,
            "notifications_enabled": enabled,
            "resend_api_key_configured": api_key_configured,
            "owner_notification_emails_configured": recipients_configured,
            "email_from_configured": sender_configured,
            "owner_notifications_configured": bool(
                enabled and api_key_configured and recipients_configured
            ),
        }
    )


@app.post("/api/inquiry")
async def submit_inquiry(request: Request):
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

    # Honeypot: legitimate visitors never see or fill this field.
    if module.clean(form.get("website"), 200):
        return _success_page(return_url)

    name = module.clean(form.get("name"), 120)
    company = module.clean(form.get("company"), 180)
    email = module.clean(form.get("email"), 254).lower()
    phone = module.clean(form.get("phone"), 80)
    message = module.clean_message(form.get("message"))
    preferred = module.clean(form.get("preferredContact"), 80)
    contact_details = module.clean(form.get("contactDetails"), 500)

    channels_raw: Iterable[str] = form.getlist("phoneChannel")
    channels = [module.clean(value, 40) for value in channels_raw]
    channels = [
        value for value in channels if value in module.ALLOWED_PHONE_CHANNELS
    ]

    if not name or not company or not email or not message or not preferred:
        return module.form_error("Please complete all required fields.", return_url)
    if not module.EMAIL_RE.match(email):
        return module.form_error("Please enter a valid email address.", return_url)
    if preferred not in ALLOWED_PREFERRED_CONTACT:
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
            "The secure form endpoint is not fully configured yet. Please use the email contact option for now.",
            return_url,
            503,
        )

    notion_channels = [
        "Mobile" if value == "Mobile call" else value for value in channels
    ]
    request_title = f"Website inquiry — {name}"
    if company:
        request_title += f" — {company}"

    notion_details = message
    if contact_details:
        notion_details += (
            f"\n\nPreferred platform / contact details: {contact_details}"
        )

    properties = {
        "Request": module.title_text(request_title),
        "Requester Name": module.rich_text(name),
        "Requester Email": {"email": email},
        "Company / Client Name": module.rich_text(company),
        "Details": module.rich_text(notion_details),
        "Request Type": {"select": {"name": source["request_type"]}},
        "Status": {"select": {"name": "New"}},
        "Source": {"select": {"name": source["label"]}},
        "Preferred Contact": {"select": {"name": preferred}},
        "Supporting Link": {"url": source["page_url"]},
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

    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": module.NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "RVS-Website-Inquiry/2.0",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                module.NOTION_API_URL,
                headers=headers,
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
            "The inquiry could not be saved right now. Please try again shortly or use the email contact option.",
            return_url,
            502,
        )

    notion_url = ""
    try:
        notion_url = str(response.json().get("url", "")).strip()
    except (ValueError, AttributeError):
        pass

    sent = await _send_owner_notification(
        name=name,
        company=company,
        email=email,
        phone=phone,
        channels=notion_channels,
        preferred=preferred,
        contact_details=contact_details,
        message=message,
        source_label=source["label"],
        notion_url=notion_url,
    )
    if _owner_notifications_enabled() and not sent:
        print("Owner inquiry notification was not sent.")

    return _success_page(return_url)
