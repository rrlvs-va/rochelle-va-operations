import os

import httpx

import app_v2 as inquiry_backend
from app_v7 import app

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


async def _send_email_brevo(
    recipients: list[str],
    subject: str,
    text: str,
    html: str,
    reply_to: str = "",
) -> bool:
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender_email = os.environ.get("EMAIL_FROM_ADDRESS", "").strip().lower()
    sender_name = os.environ.get(
        "EMAIL_FROM_NAME", "Rochelle V. Silvestre"
    ).strip() or "Rochelle V. Silvestre"

    if (
        not api_key
        or not recipients
        or not sender_email
        or not inquiry_backend.module.EMAIL_RE.match(sender_email)
    ):
        return False

    payload = {
        "sender": {"email": sender_email, "name": sender_name},
        "to": [{"email": email} for email in recipients],
        "subject": subject[:200],
        "textContent": text,
        "htmlContent": html,
    }
    if reply_to and inquiry_backend.module.EMAIL_RE.match(reply_to):
        payload["replyTo"] = {"email": reply_to}

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                BREVO_API_URL,
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "RVS-Website-Inquiry/2.0",
                },
                json=payload,
            )
        return 200 <= response.status_code < 300
    except httpx.HTTPError:
        return False


# app_v2's inquiry and owner-notification routes resolve _send_email from the
# module at request time, so this swaps the delivery provider without changing
# the existing blog/admin chain.
inquiry_backend._send_email = _send_email_brevo
