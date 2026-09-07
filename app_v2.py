import os
import secrets
import time
from html import escape
from urllib.parse import quote

import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import app, module, _authorized_admin_session

VERIFY_TTL_SECONDS = 24 * 60 * 60
NOTION_PAGE_URL = "https://api.notion.com/v1/pages"
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_CONTACT_NUMBER", "639686601851").strip()
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _reference_code() -> str:
    return "RVS-" + "".join(secrets.choice(REF_ALPHABET) for _ in range(8))


def _notion_headers() -> dict:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": module.NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "RVS-Inquiry-Verification/1.0",
    }


def _verification_token(reference: str, page_id: str, email: str) -> str:
    now = int(time.time())
    return module._sign_payload(
        {
            "kind": "inquiry-email",
            "ref": reference,
            "page_id": page_id,
            "email": email,
            "iat": now,
            "exp": now + VERIFY_TTL_SECONDS,
        }
    )


def _verify_url(token: str) -> str:
    return f"{module.BACKEND_ORIGIN}/verify/inquiry?token={quote(token, safe='')}"


def _continue_url(token: str) -> str:
    return f"{module.BACKEND_ORIGIN}/continue/whatsapp?token={quote(token, safe='')}"


def _whatsapp_url(reference: str) -> str:
    message = (
        "Hi Rochelle! I verified my website inquiry. "
        f"My reference is {reference}, and I'd like to continue here."
    )
    return f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(message, safe='')}"


def _page(title: str, body: str, button_url: str = "", button_text: str = "") -> HTMLResponse:
    button = ""
    if button_url and button_text:
        button = (
            f'<a class="button" href="{escape(button_url, quote=True)}" '
            f'rel="noopener noreferrer">{escape(button_text)}</a>'
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
.note{{font-size:.92rem;color:#b9aca1}}
</style>
</head>
<body><main><h1>{escape(title)}</h1>{body}{button}</main></body></html>""",
        headers={"Cache-Control": "no-store"},
    )


async def _create_test_inquiry(name: str, company: str, email: str, message: str) -> tuple[str, str]:
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

    token = _verification_token(reference, page_id, email)
    return reference, _verify_url(token)


@app.get("/admin/inquiry-test")
async def inquiry_test_form(request: Request):
    if not _authorized_admin_session(request):
        return HTMLResponse("Unauthorized", status_code=401, headers={"Cache-Control": "no-store"})
    body = """
<p>This creates a real test record in Client Requests Inbox and gives you the verification link directly. Existing website forms are untouched.</p>
<form method="post" action="/admin/inquiry-test">
<label>Name</label><input name="name" required value="RVS Test">
<label>Company</label><input name="company" required value="RVS Internal Test">
<label>Email</label><input name="email" type="email" required>
<label>Message</label><textarea name="message" required>Testing the inquiry reference, verification, Notion update, and WhatsApp handoff.</textarea>
<button type="submit">Create test inquiry</button>
</form>
<p class="note">No email is sent in this admin-only test. The verification link is shown directly so we can test the workflow before connecting an email provider.</p>
"""
    return _page("Inquiry verification test", body)


@app.post("/admin/inquiry-test")
async def inquiry_test_submit(request: Request):
    if not _authorized_admin_session(request):
        return HTMLResponse("Unauthorized", status_code=401, headers={"Cache-Control": "no-store"})
    form = await request.form()
    name = module.clean(form.get("name"), 120)
    company = module.clean(form.get("company"), 180)
    email = module.clean(form.get("email"), 254).lower()
    message = module.clean_message(form.get("message"))
    if not name or not company or not email or not message or not module.EMAIL_RE.match(email):
        return _page("Test could not be created", "<p>Please provide valid test details.</p>")
    try:
        reference, verify_url = await _create_test_inquiry(name, company, email, message)
    except (RuntimeError, httpx.HTTPError):
        return _page("Test could not be created", "<p>The test inquiry could not be saved to Notion.</p>")
    body = (
        "<p>The test inquiry was created in Notion.</p>"
        f"<p>Reference: <code>{escape(reference)}</code></p>"
        "<p>Use the button below as the stand-in for the verification email.</p>"
    )
    return _page("Test inquiry created", body, verify_url, "Verify test inquiry")


@app.get("/verify/inquiry")
async def verify_inquiry(request: Request):
    token = request.query_params.get("token", "")
    payload = module._verify_payload(token)
    if not payload or payload.get("kind") != "inquiry-email":
        return _page(
            "Verification link invalid",
            "<p>This verification link is invalid or has expired.</p>",
        )

    reference = str(payload.get("ref", "")).strip()
    page_id = str(payload.get("page_id", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    if not reference or not page_id or not email:
        return _page("Verification link invalid", "<p>The verification link is incomplete.</p>")

    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    if not notion_token:
        return _page("Verification unavailable", "<p>The inquiry service is temporarily unavailable.</p>")

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
        return _page("Verification unavailable", "<p>There was a temporary connection problem. Please try the link again.</p>")

    if response.status_code != 200:
        return _page("Verification unavailable", "<p>Your inquiry could not be verified right now. Please try again shortly.</p>")

    body = (
        "<p>Your email verification is complete.</p>"
        f"<p>Your inquiry reference is <code>{escape(reference)}</code>.</p>"
        "<p>Your inquiry is already recorded, so you won't need to repeat the details when you continue on WhatsApp.</p>"
    )
    return _page("Email verified", body, _continue_url(token), "Continue on WhatsApp")


@app.get("/continue/whatsapp")
async def continue_whatsapp(request: Request):
    token = request.query_params.get("token", "")
    payload = module._verify_payload(token)
    if not payload or payload.get("kind") != "inquiry-email":
        return _page("Link invalid", "<p>This WhatsApp continuation link is invalid or has expired.</p>")

    reference = str(payload.get("ref", "")).strip()
    page_id = str(payload.get("page_id", "")).strip()
    if not reference or not page_id:
        return _page("Link invalid", "<p>This WhatsApp continuation link is incomplete.</p>")

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

    return RedirectResponse(_whatsapp_url(reference), status_code=302, headers={"Cache-Control": "no-store"})
