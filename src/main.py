import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Iterable
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

app = FastAPI(title="RVS Website Backend", docs_url=None, redoc_url=None)

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2025-09-03"
DEFAULT_DATA_SOURCE_ID = "28ecfe15-bfb1-4265-abbe-c8c3e29a1a31"
SITE_ORIGIN = "https://rrlvsva.wasmer.app"
BACKEND_ORIGIN = "https://rochelle-va-inquiries.wasmer.app"
MAX_CONTENT_LENGTH = 32_768
MAX_MESSAGE_LENGTH = 6_000
MAX_SHORT_LENGTH = 300

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_API_VERSION = "2026-03-10"
DEFAULT_GITHUB_USER = "rrlvs-va"
DEFAULT_GITHUB_ID = "253043442"
DEFAULT_CALLBACK_URL = f"{BACKEND_ORIGIN}/oauth2/callback"
OAUTH_COOKIE = "__Host-rvsva_oauth"
SESSION_COOKIE = "__Host-rvsva_admin"
OAUTH_TTL_SECONDS = 600
DEFAULT_SESSION_TTL_SECONDS = 3600

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


def request_is_from_site(request: Request) -> bool:
    origin = (request.headers.get("origin") or "").rstrip("/")
    referer = request.headers.get("referer") or ""
    if origin:
        return origin == SITE_ORIGIN
    if referer:
        return referer.startswith(SITE_ORIGIN + "/") or referer == SITE_ORIGIN
    return True


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _session_secret() -> str:
    return os.environ.get("ADMIN_SESSION_SECRET", "").strip()


def _oauth_config() -> dict:
    return {
        "client_id": os.environ.get("GITHUB_OAUTH_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "").strip(),
        "callback_url": os.environ.get(
            "GITHUB_OAUTH_CALLBACK_URL", DEFAULT_CALLBACK_URL
        ).strip(),
        "authorized_user": os.environ.get(
            "AUTHORIZED_GITHUB_USER", DEFAULT_GITHUB_USER
        ).strip(),
        "authorized_id": os.environ.get(
            "AUTHORIZED_GITHUB_ID", DEFAULT_GITHUB_ID
        ).strip(),
    }


def _oauth_ready() -> bool:
    config = _oauth_config()
    return bool(
        config["client_id"]
        and config["client_secret"]
        and len(_session_secret()) >= 32
        and config["callback_url"].startswith("https://")
    )


def _session_ttl() -> int:
    raw = os.environ.get("ADMIN_SESSION_TTL", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_SESSION_TTL_SECONDS
    except ValueError:
        value = DEFAULT_SESSION_TTL_SECONDS
    return min(max(value, 300), 14_400)


def _sign_payload(payload: dict) -> str:
    secret = _session_secret().encode("utf-8")
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = _b64url_encode(body)
    signature = hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64url_encode(signature)}"


def _verify_payload(token: str) -> dict | None:
    secret = _session_secret()
    if len(secret) < 32 or not token or "." not in token:
        return None
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        supplied = _b64url_decode(supplied_signature)
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _admin_login_page(message: str = "") -> HTMLResponse:
    configured = _oauth_ready()
    detail = (
        "GitHub authentication is configured and ready for a login test."
        if configured
        else "GitHub authentication is not configured yet. Add the OAuth Client ID, Client Secret, and admin session secret in Wasmer environment variables first."
    )
    message_html = f'<p class="notice">{message}</p>' if message else ""
    button = (
        '<a class="button" href="/auth/github">Sign in with GitHub</a>'
        if configured
        else '<span class="button disabled">Sign in unavailable</span>'
    )
    return HTMLResponse(
        f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<meta name=\"robots\" content=\"noindex,nofollow,noarchive\"><title>RVS Insights Admin</title>
<style>
:root{{--ink:#11100f;--panel:#181512;--text:#f7f1ea;--muted:#b9aca1;--gold:#d1ab63;--blush:#cb8f96;--line:#4b3b30}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 18% 18%,rgba(203,143,150,.10),transparent 25%),radial-gradient(circle at 82% 78%,rgba(209,171,99,.10),transparent 28%),var(--ink);color:var(--text);font-family:Inter,system-ui,sans-serif;line-height:1.6}}
main{{width:min(620px,calc(100% - 34px));padding:42px 38px;border:1px solid var(--line);background:var(--panel)}}.eyebrow{{text-transform:uppercase;letter-spacing:.14em;font-size:.72rem;font-weight:800;color:var(--blush)}}h1{{font:500 clamp(2.5rem,7vw,4.2rem)/.98 Georgia,serif;margin:12px 0 18px}}h1 span{{color:var(--gold)}}p{{color:var(--muted)}}.button{{display:inline-flex;margin-top:12px;padding:11px 18px;border-radius:999px;background:var(--gold);color:#17110d;text-decoration:none;font-weight:800}}.button.disabled{{opacity:.45;cursor:not-allowed}}.notice{{padding:11px 13px;border-left:2px solid var(--blush);background:#211b18}}small{{display:block;margin-top:22px;color:#8f8178}}
</style></head><body><main><div class=\"eyebrow\">Private publishing area</div><h1>RVS Insights <span>Admin</span></h1><p>{detail}</p>{message_html}{button}<small>Access is intended only for the authorized GitHub account. Publishing remains disabled during this authentication test.</small></main></body></html>""",
        status_code=200 if configured else 503,
        headers={"Cache-Control": "no-store"},
    )


def _admin_success_page(login: str) -> HTMLResponse:
    safe_login = re.sub(r"[^A-Za-z0-9_-]", "", login)[:80]
    return HTMLResponse(
        f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<meta name=\"robots\" content=\"noindex,nofollow,noarchive\"><title>RVS Insights Admin — Authenticated</title>
<style>
:root{{--ink:#11100f;--panel:#181512;--text:#f7f1ea;--muted:#b9aca1;--gold:#d1ab63;--green:#9db79e;--line:#4b3b30}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--ink);color:var(--text);font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 34px));padding:42px 38px;border:1px solid var(--line);background:var(--panel)}}.status{{color:var(--green);font-weight:800;text-transform:uppercase;letter-spacing:.12em;font-size:.72rem}}h1{{font:500 clamp(2.4rem,7vw,4rem)/1 Georgia,serif;margin:12px 0 18px}}h1 span{{color:var(--gold)}}p{{color:var(--muted)}}code{{color:#f5dfb9}}.row{{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}}a,button{{display:inline-flex;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:800;font:inherit;cursor:pointer}}a{{background:var(--gold);color:#17110d}}button{{background:transparent;color:#f7f1ea;border:1px solid #6d5846}}
</style></head><body><main><div class=\"status\">Authentication test passed</div><h1>Welcome, <span>@{safe_login}</span>.</h1><p>GitHub verified the account and the backend accepted it as the authorized RVS Insights administrator.</p><p>No publishing permissions are connected yet. This page proves only the login and protected-session layer.</p><div class=\"row\"><a href=\"{SITE_ORIGIN}/experiments/blog-cms-preview/admin/\">Open editor prototype</a><form method=\"post\" action=\"/logout\"><button type=\"submit\">Sign out</button></form></div></main></body></html>""",
        headers={"Cache-Control": "no-store"},
    )


def _oauth_error_page(message: str, status_code: int = 400) -> HTMLResponse:
    safe_message = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return HTMLResponse(
        f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"robots\" content=\"noindex,nofollow,noarchive\"><title>Admin sign-in</title><style>body{{margin:0;background:#11100f;color:#f7f1ea;font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(650px,calc(100% - 34px));margin:12vh auto;padding:36px;border:1px solid #6d5846;background:#181512}}h1{{font-family:Georgia,serif;color:#d1ab63;font-weight:500}}p{{color:#d8cbc1}}a{{display:inline-block;margin-top:10px;background:#d1ab63;color:#17110d;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:800}}</style></head><body><main><h1>Admin sign-in could not be completed.</h1><p>{safe_message}</p><a href=\"/admin\">Return to admin sign-in</a></main></body></html>""",
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health")
async def health() -> JSONResponse:
    notion_configured = bool(os.environ.get("NOTION_TOKEN"))
    return JSONResponse(
        {
            "ok": True,
            "notion_configured": notion_configured,
            "github_oauth_configured": _oauth_ready(),
        }
    )


@app.get("/admin")
async def admin(request: Request) -> HTMLResponse:
    session = _verify_payload(request.cookies.get(SESSION_COOKIE, ""))
    if session and session.get("kind") == "admin":
        config = _oauth_config()
        if (
            str(session.get("login", "")).lower()
            == config["authorized_user"].lower()
            and str(session.get("id", "")) == config["authorized_id"]
        ):
            return _admin_success_page(str(session.get("login", "")))
    return _admin_login_page()


@app.get("/auth/github")
async def github_login() -> RedirectResponse | HTMLResponse:
    if not _oauth_ready():
        return _admin_login_page("OAuth configuration is incomplete.")

    config = _oauth_config()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())
    now = int(time.time())
    oauth_cookie = _sign_payload(
        {
            "kind": "oauth",
            "state": state,
            "verifier": verifier,
            "iat": now,
            "exp": now + OAUTH_TTL_SECONDS,
        }
    )

    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["callback_url"],
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "login": config["authorized_user"],
            "allow_signup": "false",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{query}", status_code=302)
    response.set_cookie(
        OAUTH_COOKIE,
        oauth_cookie,
        max_age=OAUTH_TTL_SECONDS,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/oauth2/callback")
async def github_callback(request: Request):
    if not _oauth_ready():
        return _oauth_error_page("OAuth configuration is incomplete.", 503)

    if request.query_params.get("error"):
        return _oauth_error_page("GitHub authorization was cancelled or denied.")

    code = request.query_params.get("code", "")
    returned_state = request.query_params.get("state", "")
    oauth_state = _verify_payload(request.cookies.get(OAUTH_COOKIE, ""))
    if not code or not returned_state or not oauth_state:
        return _oauth_error_page("The authorization response was incomplete or expired.")
    if oauth_state.get("kind") != "oauth" or not hmac.compare_digest(
        str(oauth_state.get("state", "")), returned_state
    ):
        return _oauth_error_page("The authorization state did not match. Please try again.", 403)

    config = _oauth_config()
    token_payload = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "redirect_uri": config["callback_url"],
        "code_verifier": str(oauth_state.get("verifier", "")),
    }

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
            token_response = await client.post(
                GITHUB_TOKEN_URL,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "RVS-Insights-Admin/1.0",
                },
                data=token_payload,
            )
            token_data = token_response.json()
            access_token = str(token_data.get("access_token", ""))
            if token_response.status_code != 200 or not access_token:
                return _oauth_error_page("GitHub did not issue a usable login token.", 502)

            user_response = await client.get(
                GITHUB_USER_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                    "User-Agent": "RVS-Insights-Admin/1.0",
                },
            )
    except (httpx.HTTPError, ValueError):
        return _oauth_error_page(
            "There was a temporary problem communicating with GitHub. Please try again.",
            502,
        )

    if user_response.status_code != 200:
        return _oauth_error_page("GitHub could not verify the signed-in account.", 502)

    user = user_response.json()
    login = str(user.get("login", ""))
    github_id = str(user.get("id", ""))
    if (
        login.lower() != config["authorized_user"].lower()
        or github_id != config["authorized_id"]
    ):
        denied = _oauth_error_page(
            "This GitHub account is not authorized to access RVS Insights Admin.",
            403,
        )
        denied.delete_cookie(OAUTH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return denied

    now = int(time.time())
    ttl = _session_ttl()
    session_token = _sign_payload(
        {
            "kind": "admin",
            "login": login,
            "id": github_id,
            "iat": now,
            "exp": now + ttl,
        }
    )
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=ttl,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(OAUTH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/admin", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.delete_cookie(OAUTH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return response


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

    notion_channels = ["Mobile" if v == "Mobile call" else v for v in channels]
    request_title = f"Website inquiry — {name}"
    if company:
        request_title += f" — {company}"

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
        "User-Agent": "RVS-Website-Inquiry/1.0",
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
        return form_error(
            "The inquiry could not be saved right now. Please try again shortly or use the email contact option.",
            return_url,
            502,
        )

    return success_page(return_url)
