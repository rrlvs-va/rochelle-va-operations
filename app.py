from pathlib import Path
import types

from fastapi.responses import HTMLResponse, JSONResponse


# Runtime compatibility shim for FastAPI on Wasmer/Python 3.13.
# The backend source uses a union return annotation on one route that this
# FastAPI build tries to interpret as a Pydantic response model at import time.
# Patch that annotation in memory before executing the module so the app can
# start without changing the OAuth or inquiry logic itself.
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


# Add the blog as a valid secure inquiry source without disturbing the
# existing website contact-form routes.
module.SOURCE_CONFIG["blog"] = {
    "label": "Website — Blog",
    "request_type": "Other",
    "page_url": f"{module.SITE_ORIGIN}/experiments/blog-cms-preview/article.html",
    "return_url": f"{module.SITE_ORIGIN}/experiments/blog-cms-preview/article.html#contact",
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
        f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<meta name=\"robots\" content=\"noindex,nofollow,noarchive\"><title>Admin Login | Rochelle V. Silvestre</title>
<style>
:root{{--ink:#11100f;--panel:#181512;--text:#f7f1ea;--muted:#b9aca1;--gold:#d1ab63;--blush:#cb8f96;--line:#4b3b30}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 18% 18%,rgba(203,143,150,.10),transparent 25%),radial-gradient(circle at 82% 78%,rgba(209,171,99,.10),transparent 28%),var(--ink);color:var(--text);font-family:Inter,system-ui,sans-serif;line-height:1.6}}
main{{width:min(640px,calc(100% - 34px));padding:46px 40px;border:1px solid var(--line);background:var(--panel);text-align:center}}.eyebrow{{text-transform:uppercase;letter-spacing:.14em;font-size:.72rem;font-weight:800;color:var(--blush)}}h1{{font:500 clamp(2.5rem,7vw,4rem)/1 Georgia,serif;margin:12px 0 18px}}h1 span{{color:var(--gold)}}p{{color:var(--muted);max-width:500px;margin:0 auto}}.button{{display:inline-flex;margin-top:22px;padding:11px 18px;border-radius:999px;background:var(--gold);color:#17110d;text-decoration:none;font-weight:800}}.button.disabled{{opacity:.45;cursor:not-allowed}}.notice{{margin-top:18px!important;padding:11px 13px;border-left:2px solid var(--blush);background:#211b18;text-align:left}}small{{display:block;margin-top:22px;color:#8f8178}}
</style></head><body><main><div class=\"eyebrow\">Admin Login Only</div><h1>Welcome to the <span>Admin Login.</span></h1><p>{detail}</p>{message_html}{button}<small>Access is intended only for the authorized owner of this website.</small></main></body></html>""",
        status_code=200 if configured else 503,
        headers={"Cache-Control": "no-store"},
    )


def _admin_success_page(login: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<meta name=\"robots\" content=\"noindex,nofollow,noarchive\"><title>Admin | Rochelle V. Silvestre</title>
<style>
:root{{--ink:#11100f;--panel:#181512;--text:#f7f1ea;--muted:#b9aca1;--gold:#d1ab63;--green:#9db79e;--line:#4b3b30}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--ink);color:var(--text);font-family:Inter,system-ui,sans-serif;line-height:1.6}}main{{width:min(680px,calc(100% - 34px));padding:44px 38px;border:1px solid var(--line);background:var(--panel);text-align:center}}.status{{color:var(--green);font-weight:800;text-transform:uppercase;letter-spacing:.12em;font-size:.72rem}}h1{{font:500 clamp(2.4rem,7vw,4rem)/1 Georgia,serif;margin:12px 0 18px}}h1 span{{color:var(--gold)}}p{{color:var(--muted);max-width:540px;margin:0 auto}}.row{{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin-top:26px}}a,button{{display:inline-flex;padding:10px 16px;border-radius:999px;text-decoration:none;font-weight:800;font:inherit;cursor:pointer}}a{{background:var(--gold);color:#17110d}}button{{background:transparent;color:#f7f1ea;border:1px solid #6d5846}}
</style></head><body><main><div class=\"status\">Signed in</div><h1>Welcome, <span>Rochelle.</span></h1><p>GitHub verified your account and confirmed authorized access to RVS Admin.</p><div class=\"row\"><a href=\"{module.SITE_ORIGIN}/experiments/blog-cms-preview/admin/\">Open blog</a><form method=\"post\" action=\"/logout\"><button type=\"submit\">Sign out</button></form></div></main></body></html>""",
        headers={"Cache-Control": "no-store"},
    )


# The admin route looks these functions up in the module namespace at request
# time, so replacing them here updates the interface without touching auth logic.
module._admin_login_page = _admin_login_page
module._admin_success_page = _admin_success_page


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "rvs-website-inquiry-endpoint"})
