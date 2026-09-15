import os
import re
from html import escape
from typing import Iterable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="RVS Website Inquiry Endpoint", docs_url=None, redoc_url=None)

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2025-09-03"
DEFAULT_DATA_SOURCE_ID = "28ecfe15-bfb1-4265-abbe-c8c3e29a1a31"
RESEND_API_URL = "https://api.resend.com/emails"
SITE_ORIGIN = "https://rrlvsva.wasmer.app"
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
    "Asana",
    "monday.com",
    "Slack",
    "Atlassian / Jira",
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
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Form submission</title>
<style>body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 36px));margin:12vh auto;padding:34px;border:1px solid #6d5846;background:#181512}}h1{{font-family:Georgia,serif;font-weight:500;color:#d1ab63}}p{{color:#d8cbc1}}a{{display:inline-block;margin-top:12px;color:#11100f;background:#d1ab63;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:700}}</style></head>
<body><main><h1>We couldn’t send that yet.</h1><p>{safe_message}</p><a href="{safe_return}">Return to the form</a></main></body></html>""",
        status_code=status_code,
    )


def success_page(return_url: str) -> HTMLResponse:
    safe_return = return_url.replace('"', "%22")
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Inquiry received</title>
<style>body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 36px));margin:12vh auto;padding:34px;border:1px solid #6d5846;background:radial-gradient(circle at 15% 18%,rgba(203,143,150,.12),transparent 28%),#181512}}h1{{font-family:Georgia,serif;font-weight:500;color:#d1ab63}}p{{color:#d8cbc1}}a{{display:inline-block;margin-top:12px;color:#11100f;background:#d1ab63;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:700}}</style></head>
<body><main><h1>Thank you for reaching out.</h1><p>Your contact details have been received. I’ll be in touch with you shortly.</p><a href="{safe_return}">Return to the website</a></main></body></html>""",
        status_code=200,
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


def owner_notifications_enabled() -> bool:
    return os.environ.get("INQUIRY_NOTIFICATIONS_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def owner_emails() -> list[str]:
    raw = os.environ.get("OWNER_NOTIFICATION_EMAILS", "")
    recipients: list[str] = []
    for part in raw.replace(";", ",").split(","):
        email = part.strip().lower()
        if email and EMAIL_RE.match(email) and email not in recipients:
            recipients.append(email)
    return recipients


async def send_owner_notification(
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
    if not owner_notifications_enabled():
        return False

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    recipients = owner_emails()
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


@app.get("/health")
async def health() -> JSONResponse:
    notion_configured = bool(os.environ.get("NOTION_TOKEN"))
    notifications_configured = bool(
        owner_notifications_enabled()
        and os.environ.get("RESEND_API_KEY", "").strip()
        and owner_emails()
    )
    return JSONResponse(
        {
            "ok": True,
            "notion_configured": notion_configured,
            "owner_notifications_configured": notifications_configured,
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
    contact_details = clean(form.get("contactDetails"), 500)

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

    notion_channels = ["Mobile" if v == "Mobile call" else v for v in channels]
    request_title = f"Website inquiry — {name}"
    if company:
        request_title += f" — {company}"

    notion_details = message
    if contact_details:
        notion_details += f"\n\nPreferred platform / contact details: {contact_details}"

    properties = {
        "Request": title_text(request_title),
        "Requester Name": rich_text(name),
        "Requester Email": {"email": email},
        "Company / Client Name": rich_text(company),
        "Details": rich_text(notion_details),
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
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "RVS-Website-Inquiry/2.0",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(NOTION_API_URL, headers=headers, json=payload)
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

    created = response.json()
    notion_url = clean(created.get("url"), 1000)

    # Visitors do not receive an automated email. The website success page is
    # their acknowledgement; email delivery is only for the owner notification.
    await send_owner_notification(
        name=name,
        company=company,
        email=email,
        phone=phone,
        channels=channels,
        preferred=preferred,
        contact_details=contact_details,
        message=message,
        source_label=source["label"],
        notion_url=notion_url,
    )

    return success_page(return_url)
