from pathlib import Path
import base64
import hashlib
import json
import os
import time
import types

import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# Load the existing inquiry + OAuth backend while keeping the Python 3.13
# FastAPI compatibility shim that is already proven on Wasmer.
source_path = Path(__file__).parent / "src" / "main.py"
source = source_path.read_text(encoding="utf-8")
source = source.replace(
    "async def github_login() -> RedirectResponse | HTMLResponse:",
    "async def github_login():",
)
module = types.ModuleType("rvs_backend_main")
module.__file__ = str(source_path)
exec(compile(source, str(source_path), "exec"), module.__dict__)
app = module.app

module.SOURCE_CONFIG["blog"] = {
    "label": "Website — Blog",
    "request_type": "Other",
    "page_url": f"{module.SITE_ORIGIN}/blog/article.html",
    "return_url": f"{module.SITE_ORIGIN}/blog/article.html#contact",
}

PUBLISH_REPO = "rrlvs-va/rochelle-va-operations"
PUBLISH_BRANCH = "main"
MANIFEST_PATH = "blog/articles.json"
MANIFEST_RAW_URL = (
    f"https://raw.githubusercontent.com/{PUBLISH_REPO}/{PUBLISH_BRANCH}/{MANIFEST_PATH}"
)
GITHUB_CONTENTS_URL = (
    f"https://api.github.com/repos/{PUBLISH_REPO}/contents/{MANIFEST_PATH}"
)
UPLOAD_DIR = "blog/uploads"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", b"RIFF"),
}


def _admin_login_page(message: str = "") -> HTMLResponse:
    configured = module._oauth_ready()
    detail = (
        "GitHub authentication is needed. Sign in with GitHub."
        if configured
        else "GitHub authentication is not available right now."
    )
    message_html = f'<p class="notice">{message}</p>' if message else ""
    button = (
        '<a class="button" href="/auth/github">Sign in with GitHub</a>'
        if configured
        else '<span class="button disabled">Sign in unavailable</span>'
    )
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><title>Admin Login | Rochelle V. Silvestre</title><style>:root{{--ink:#11100f;--panel:#181512;--text:#f7f1ea;--muted:#b9aca1;--gold:#d1ab63;--blush:#cb8f96;--line:#4b3b30}}*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 18% 18%,rgba(203,143,150,.10),transparent 25%),var(--ink);color:var(--text);font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(640px,calc(100% - 34px));padding:46px 40px;border:1px solid var(--line);background:var(--panel);text-align:center}}.eyebrow{{text-transform:uppercase;letter-spacing:.14em;font-size:.72rem;font-weight:800;color:var(--blush)}}h1{{font:500 clamp(2.5rem,7vw,4rem)/1 Georgia,serif;margin:12px 0 18px}}h1 span{{color:var(--gold)}}p{{color:var(--muted)}}.button{{display:inline-flex;margin-top:22px;padding:11px 18px;border-radius:999px;background:var(--gold);color:#17110d;text-decoration:none;font-weight:800}}.button.disabled{{opacity:.45}}.notice{{margin-top:18px!important;padding:11px 13px;border-left:2px solid var(--blush);background:#211b18}}small{{display:block;margin-top:22px;color:#8f8178}}</style></head><body><main><div class="eyebrow">Admin Login Only</div><h1>Welcome to the <span>Admin Login.</span></h1><p>{detail}</p>{message_html}{button}<small>Access is intended only for the authorized owner of this website.</small></main></body></html>""",
        status_code=200 if configured else 503,
        headers={"Cache-Control": "no-store"},
    )


def _admin_success_page(login: str) -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive"><title>Admin | Rochelle V. Silvestre</title><style>:root{--ink:#11100f;--panel:#181512;--text:#f7f1ea;--muted:#b9aca1;--gold:#d1ab63;--green:#9db79e;--line:#4b3b30}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--ink);color:var(--text);font-family:Inter,system-ui,sans-serif}main{width:min(680px,calc(100% - 34px));padding:44px 38px;border:1px solid var(--line);background:var(--panel);text-align:center}.status{color:var(--green);font-weight:800;text-transform:uppercase;letter-spacing:.12em;font-size:.72rem}h1{font:500 clamp(2.4rem,7vw,4rem)/1 Georgia,serif;margin:12px 0 18px}h1 span{color:var(--gold)}p{color:var(--muted)}.row{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin-top:26px}a,button{display:inline-flex;padding:10px 16px;border-radius:999px;text-decoration:none;font:inherit;cursor:pointer}a{background:var(--gold);color:#17110d}button{background:transparent;color:#f7f1ea;border:1px solid #6d5846}</style></head><body><main><div class="status">Signed in</div><h1>Welcome, <span>Rochelle.</span></h1><p>GitHub verified your account and confirmed authorized access to RVS Admin.</p><div class="row"><a href="/admin/editor">Open blog</a><form method="post" action="/logout"><button type="submit">Sign out</button></form></div></main></body></html>""",
        headers={"Cache-Control": "no-store"},
    )


module._admin_login_page = _admin_login_page
module._admin_success_page = _admin_success_page


def _authorized_admin_session(request: Request):
    session = module._verify_payload(request.cookies.get(module.SESSION_COOKIE, ""))
    if not session or session.get("kind") != "admin":
        return None
    config = module._oauth_config()
    if (
        str(session.get("login", "")).lower() != config["authorized_user"].lower()
        or str(session.get("id", "")) != config["authorized_id"]
    ):
        return None
    return session


def _csrf_for(session: dict) -> str:
    return module._sign_payload(
        {
            "kind": "csrf",
            "login": str(session.get("login", "")),
            "id": str(session.get("id", "")),
            "exp": min(int(session.get("exp", 0)), int(time.time()) + 3600),
        }
    )


def _valid_csrf(session: dict, token: str) -> bool:
    payload = module._verify_payload(token or "")
    return bool(
        payload
        and payload.get("kind") == "csrf"
        and str(payload.get("login", "")) == str(session.get("login", ""))
        and str(payload.get("id", "")) == str(session.get("id", ""))
    )


def _valid_admin_origin(request: Request) -> bool:
    origin = (request.headers.get("origin") or "").rstrip("/")
    referer = request.headers.get("referer") or ""
    return origin == module.BACKEND_ORIGIN or referer.startswith(
        module.BACKEND_ORIGIN + "/"
    )


def _publish_token() -> str:
    return os.environ.get("GITHUB_PUBLISH_TOKEN", "").strip()


def _write_ready() -> bool:
    return bool(_publish_token())


def _github_headers(with_auth: bool = False) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "RVS-Blog-Admin",
    }
    if with_auth and _publish_token():
        headers["Authorization"] = f"Bearer {_publish_token()}"
    return headers


async def _read_manifest() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                MANIFEST_RAW_URL,
                headers={"User-Agent": "RVS-Blog-Admin"},
                params={"cb": str(int(time.time()))},
            )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and isinstance(data.get("articles"), list):
                return data
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        pass
    return {"version": 1, "articles": []}


async def _write_manifest(data: dict, message: str) -> tuple[bool, str]:
    token = _publish_token()
    if not token:
        return False, "GitHub publishing credential is not configured."
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            current = await client.get(
                GITHUB_CONTENTS_URL,
                headers=_github_headers(True),
                params={"ref": PUBLISH_BRANCH},
            )
            sha = current.json().get("sha") if current.status_code == 200 else None
            payload = {
                "message": message,
                "content": base64.b64encode(
                    (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode(
                        "utf-8"
                    )
                ).decode("ascii"),
                "branch": PUBLISH_BRANCH,
            }
            if sha:
                payload["sha"] = sha
            response = await client.put(
                GITHUB_CONTENTS_URL, headers=_github_headers(True), json=payload
            )
        if response.status_code in (200, 201):
            return True, ""
        detail = (
            response.json().get("message", "GitHub rejected the publishing change.")
            if response.headers.get("content-type", "").startswith("application/json")
            else "GitHub rejected the publishing change."
        )
        return False, detail
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return False, "Could not reach GitHub publishing storage."


async def _write_image_file(path: str, data: bytes, message: str) -> tuple[bool, str]:
    if not _publish_token():
        return False, "GitHub publishing credential is not configured."
    url = f"https://api.github.com/repos/{PUBLISH_REPO}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": PUBLISH_BRANCH,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                url, headers=_github_headers(True), json=payload
            )
        if response.status_code in (200, 201):
            return True, ""
        detail = (
            response.json().get("message", "GitHub rejected the image upload.")
            if response.headers.get("content-type", "").startswith("application/json")
            else "GitHub rejected the image upload."
        )
        return False, detail
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return False, "Could not reach GitHub image storage."


def _safe_slug(value: object) -> str:
    raw = str(value or "").strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:120]


def _safe_cover_path(value: object) -> str:
    path = str(value or "").strip()
    if not path.startswith("uploads/") or "/" in path[len("uploads/") :]:
        return ""
    name = path[len("uploads/") :]
    if not name or len(name) > 220:
        return ""
    if not all(ch.isalnum() or ch in "._-" for ch in name):
        return ""
    if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return ""
    return path


def _image_extension(content_type: str, data: bytes) -> str:
    spec = ALLOWED_IMAGE_TYPES.get((content_type or "").lower())
    if not spec:
        return ""
    ext, signature = spec
    if not data.startswith(signature):
        return ""
    if ext == "webp" and (len(data) < 12 or data[8:12] != b"WEBP"):
        return ""
    return ext


def _template(name: str, session: dict) -> HTMLResponse:
    html = (Path(__file__).parent / name).read_text(encoding="utf-8")
    html = html.replace("__SITE_ORIGIN__", module.SITE_ORIGIN).replace(
        "__CSRF__", _csrf_for(session)
    )
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
        },
    )


@app.get("/admin/editor")
async def admin_editor(request: Request):
    session = _authorized_admin_session(request)
    if not session:
        return RedirectResponse(
            "/admin", status_code=303, headers={"Cache-Control": "no-store"}
        )
    return _template("admin_editor.html", session)


@app.get("/admin/articles")
async def admin_articles(request: Request):
    session = _authorized_admin_session(request)
    if not session:
        return RedirectResponse(
            "/admin", status_code=303, headers={"Cache-Control": "no-store"}
        )
    return _template("admin_articles.html", session)


@app.get("/admin/api/articles")
async def admin_api_articles(request: Request):
    if not _authorized_admin_session(request):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    data = await _read_manifest()
    return JSONResponse(
        {"articles": data.get("articles", []), "write_ready": _write_ready()},
        headers={"Cache-Control": "no-store"},
    )


async def _mutation_context(request: Request):
    session = _authorized_admin_session(request)
    if not session:
        return None, JSONResponse({"detail": "Unauthorized"}, status_code=401)
    if not _valid_admin_origin(request):
        return None, JSONResponse(
            {"detail": "Invalid request origin."}, status_code=403
        )
    if not _valid_csrf(session, request.headers.get("x-csrf-token", "")):
        return None, JSONResponse(
            {
                "detail": "Security token expired. Refresh the admin page and try again."
            },
            status_code=403,
        )
    if not _write_ready():
        return None, JSONResponse(
            {"detail": "GitHub publishing credential is not configured."},
            status_code=503,
        )
    return session, None


@app.post("/admin/api/images/upload")
async def admin_image_upload(request: Request):
    _, error = await _mutation_context(request)
    if error:
        return error

    form = await request.form()
    upload = form.get("image")
    slug = _safe_slug(form.get("slug")) or "article"
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"detail": "Choose an image to upload."}, status_code=400)

    content_type = str(getattr(upload, "content_type", "") or "").lower()
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if not data:
        return JSONResponse({"detail": "The selected image is empty."}, status_code=400)
    if len(data) > MAX_IMAGE_BYTES:
        return JSONResponse(
            {"detail": "Cover images must be 5 MB or smaller."}, status_code=413
        )

    ext = _image_extension(content_type, data)
    if not ext:
        return JSONResponse(
            {"detail": "Use a JPEG, PNG, or WebP image."}, status_code=400
        )

    digest = hashlib.sha256(data).hexdigest()[:12]
    stamp = int(time.time())
    filename = f"{slug}-{stamp}-{digest}.{ext}"
    repo_path = f"{UPLOAD_DIR}/{filename}"
    ok, detail = await _write_image_file(
        repo_path, data, f"Blog: upload cover image for {slug}"
    )
    if not ok:
        return JSONResponse({"detail": detail}, status_code=502)

    relative_path = f"uploads/{filename}"
    return JSONResponse(
        {
            "ok": True,
            "path": relative_path,
            "url": f"{module.SITE_ORIGIN}/blog/{relative_path}",
        }
    )


@app.post("/admin/api/articles/{slug}/status")
async def admin_article_status(slug: str, request: Request):
    _, error = await _mutation_context(request)
    if error:
        return error
    body = await request.json()
    new_status = str(body.get("status", ""))
    if new_status not in {"published", "unpublished", "trash"}:
        return JSONResponse({"detail": "Invalid article status."}, status_code=400)
    data = await _read_manifest()
    match = next(
        (a for a in data.get("articles", []) if a.get("slug") == slug), None
    )
    if not match:
        return JSONResponse({"detail": "Article not found."}, status_code=404)
    match["status"] = new_status
    match["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ok, detail = await _write_manifest(data, f"Blog: set {slug} to {new_status}")
    return (
        JSONResponse({"ok": True})
        if ok
        else JSONResponse({"detail": detail}, status_code=502)
    )


@app.delete("/admin/api/articles/{slug}")
async def admin_article_delete(slug: str, request: Request):
    _, error = await _mutation_context(request)
    if error:
        return error
    data = await _read_manifest()
    match = next(
        (a for a in data.get("articles", []) if a.get("slug") == slug), None
    )
    if not match:
        return JSONResponse({"detail": "Article not found."}, status_code=404)
    if match.get("status") != "trash":
        return JSONResponse(
            {"detail": "Move the article to Trash before deleting it permanently."},
            status_code=409,
        )
    data["articles"] = [
        a for a in data.get("articles", []) if a.get("slug") != slug
    ]
    ok, detail = await _write_manifest(data, f"Blog: permanently delete {slug}")
    return (
        JSONResponse({"ok": True})
        if ok
        else JSONResponse({"detail": detail}, status_code=502)
    )


@app.post("/admin/api/articles/publish")
async def admin_article_publish(request: Request):
    _, error = await _mutation_context(request)
    if error:
        return error

    body = await request.json()
    slug = _safe_slug(body.get("slug"))
    title = str(body.get("title", "")).strip()[:240]
    article_body = str(body.get("body", "")).strip()[:30000]
    if not slug or not title or not article_body:
        return JSONResponse(
            {"detail": "Title, URL slug, and article body are required."},
            status_code=400,
        )

    requested_cover = str(body.get("cover_image", "") or "").strip()
    cover_image = _safe_cover_path(requested_cover)
    if requested_cover and not cover_image:
        return JSONResponse({"detail": "Invalid cover image path."}, status_code=400)

    original_slug = _safe_slug(body.get("original_slug"))
    data = await _read_manifest()
    articles = data.get("articles", [])
    if original_slug and original_slug != slug:
        articles = [a for a in articles if a.get("slug") != original_slug]

    item = next((a for a in articles if a.get("slug") == slug), None)
    payload = {
        "slug": slug,
        "title": title,
        "category": str(body.get("category", "")).strip()[:100] or "Uncategorized",
        "publish_date": str(body.get("publish_date", "")).strip()[:10]
        or time.strftime("%Y-%m-%d", time.gmtime()),
        "author": "Rochelle V. Silvestre",
        "excerpt": str(body.get("excerpt", "")).strip()[:700],
        "body": article_body,
        "cover_image": cover_image,
        "status": "published",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if item:
        item.update(payload)
    else:
        articles.append(payload)
    data["articles"] = articles

    ok, detail = await _write_manifest(data, f"Blog: publish {slug}")
    return (
        JSONResponse({"ok": True, "slug": slug})
        if ok
        else JSONResponse({"detail": detail}, status_code=502)
    )


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "rvs-website-inquiry-endpoint"})
