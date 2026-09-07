from pathlib import Path
import types

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse


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
</style></head><body><main><div class=\"status\">Signed in</div><h1>Welcome, <span>Rochelle.</span></h1><p>GitHub verified your account and confirmed authorized access to RVS Admin.</p><div class=\"row\"><a href=\"/admin/editor\">Open blog</a><form method=\"post\" action=\"/logout\"><button type=\"submit\">Sign out</button></form></div></main></body></html>""",
        headers={"Cache-Control": "no-store"},
    )


# The admin route looks these functions up in the module namespace at request
# time, so replacing them here updates the interface without touching auth logic.
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


EDITOR_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta name="robots" content="noindex,nofollow,noarchive" />
<title>The Rochelle Edit Admin | Rochelle V. Silvestre</title>
<style>
:root{--ink:#11100f;--panel:#201b18;--paper:#faf7f2;--text:#f7f1ea;--muted:#b9aca1;--gold:#d1ab63;--blush:#cb8f96;--line:#3b312a;--dark:#2b2622}
*{box-sizing:border-box} body{margin:0;background:#0e0d0c;color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif} button,input,textarea{font:inherit}.shell{min-height:100vh;display:grid;grid-template-columns:240px 1fr}.sidebar{border-right:1px solid var(--line);background:#151311;padding:26px 18px;position:sticky;top:0;height:100vh}.brand{font-family:Georgia,"Times New Roman",serif;font-size:1.16rem;margin-bottom:5px}.sub{color:var(--gold);text-transform:uppercase;letter-spacing:.12em;font-size:.68rem}.nav{display:grid;gap:5px;margin-top:28px}.nav a{color:#c8bdb4;text-decoration:none;padding:10px 11px;border-radius:8px;font-size:.88rem}.nav a.active{background:#28211d;color:#fff}.account{position:absolute;left:18px;right:18px;bottom:20px;border-top:1px solid var(--line);padding-top:16px;font-size:.8rem;color:#b5a69b}.account strong{color:#f1e7de}.signout{margin-top:11px;border:1px solid #5a493c;background:transparent;color:#d8cbc1;border-radius:999px;padding:7px 11px;cursor:pointer;font-size:.76rem}.main{min-width:0}.topbar{min-height:68px;border-bottom:1px solid var(--line);background:#12100f;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 26px;position:sticky;top:0;z-index:5}.topbar strong{font-family:Georgia,"Times New Roman",serif;font-size:1.08rem}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:1px solid #5a493c;background:transparent;color:#eee4dc;border-radius:999px;padding:9px 14px;cursor:pointer;font-weight:750;font-size:.82rem}.btn.gold{background:var(--gold);border-color:var(--gold);color:#17110d}.workspace{display:grid;grid-template-columns:minmax(0,1fr) minmax(360px,.82fr);min-height:calc(100vh - 68px)}.editor{padding:28px;border-right:1px solid var(--line);background:#141210}.preview{padding:28px;background:#191613;overflow:auto}.section-label{text-transform:uppercase;letter-spacing:.14em;color:var(--blush);font-size:.68rem;font-weight:800;margin-bottom:18px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.field{display:grid;gap:7px;margin-bottom:15px}.field.full{grid-column:1/-1}.field label{font-size:.78rem;color:#cabdb4;font-weight:700}.field input,.field textarea{width:100%;border:1px solid #493c33;background:#1c1815;color:#fff;padding:11px 12px;border-radius:8px;outline:none}.field input:focus,.field textarea:focus{border-color:#9c7b4f}.field textarea{min-height:250px;resize:vertical;line-height:1.55}.help{font-size:.72rem;color:#8f8177}.upload{border:1px dashed #655044;border-radius:10px;padding:18px;background:#1a1614}.upload input{border:0;background:transparent;padding:0}.preview-card{background:var(--paper);color:var(--dark);border:1px solid #d8cec4;overflow:hidden}.preview-cover{aspect-ratio:16/9;background:linear-gradient(135deg,#1d1916,#3b2a24 60%,#8f6268);display:grid;place-items:center;color:#eadcd2;font-size:.82rem;background-size:cover;background-position:center}.preview-body{padding:24px}.preview-meta{text-transform:uppercase;letter-spacing:.1em;color:#8a7467;font-size:.7rem;font-weight:800}.preview-title{font:500 2rem/1.05 Georgia,"Times New Roman",serif;margin:10px 0 12px}.preview-excerpt{color:#685c54;line-height:1.6;font-size:.92rem}.preview-article{margin-top:18px;padding-top:18px;border-top:1px solid #ded3c8;color:#51463f;line-height:1.7;white-space:pre-wrap}.device-row{display:flex;gap:8px;margin-bottom:14px}.device{border:1px solid #524238;color:#c8bdb4;background:#171412;border-radius:999px;padding:7px 10px;font-size:.75rem}.device.active{border-color:var(--gold);color:var(--gold)}
@media(max-width:1080px){.workspace{grid-template-columns:1fr}.editor{border-right:0;border-bottom:1px solid var(--line)}.preview{min-height:560px}.sidebar{display:none}.shell{grid-template-columns:1fr}}
@media(max-width:620px){.topbar{padding:12px 14px;align-items:flex-start;flex-direction:column}.actions{width:100%}.actions .btn{flex:1}.editor,.preview{padding:18px}.grid{grid-template-columns:1fr}.field.full{grid-column:auto}.preview-title{font-size:1.65rem}}
</style>
</head>
<body>
<div class="shell">
<aside class="sidebar">
  <div class="brand">The Rochelle Edit</div><div class="sub">Admin</div>
  <nav class="nav"><a class="active" href="/admin/editor">New article</a><a href="__SITE_ORIGIN__/experiments/blog-cms-preview/">View blog</a><a href="__SITE_ORIGIN__/">Main website</a></nav>
  <div class="account">Signed in<br><strong>Rochelle V. Silvestre</strong><form method="post" action="/logout"><button class="signout" type="submit">Sign out</button></form></div>
</aside>
<main class="main">
  <div class="topbar"><strong>New article</strong><div class="actions"><button class="btn" type="button" onclick="alert('Draft saving will be connected after navigation QA.')">Save draft</button><button class="btn" type="button" onclick="document.getElementById('previewPane').scrollIntoView({behavior:'smooth'})">Preview</button><button class="btn gold" type="button" onclick="alert('Publishing will be connected after navigation QA.')">Publish</button></div></div>
  <div class="workspace">
    <section class="editor">
      <div class="section-label">Article details</div>
      <div class="grid">
        <div class="field full"><label for="title">Title</label><input id="title" value="Why Every Client Request Shouldn’t Become a Task" oninput="syncPreview()"></div>
        <div class="field"><label for="category">Category</label><input id="category" value="" placeholder="Add or create a category" oninput="syncPreview()"></div>
        <div class="field"><label for="date">Publish date</label><input id="date" type="date" value="2026-09-07" oninput="syncPreview()"></div>
        <div class="field full"><label for="slug">URL slug</label><input id="slug" value="why-every-client-request-shouldnt-become-a-task"><div class="help">This becomes the final part of the article URL, for example: /blog/your-article-title/</div></div>
        <div class="field full"><label for="excerpt">Excerpt</label><textarea id="excerpt" style="min-height:100px" oninput="syncPreview()">A request first needs context, ownership, priority, and a decision. Turning everything into a task too early creates noise instead of clarity.</textarea></div>
        <div class="field full"><label>Cover image</label><div class="upload"><input id="image" type="file" accept="image/*" onchange="loadImage(event)"><div class="help" style="margin-top:8px">Choose a cover image and check how it looks in the live preview.</div></div></div>
        <div class="field full"><label for="body">Article body</label><textarea id="body" oninput="syncPreview()">A client request may be actionable, but it may also be incomplete, duplicated, waiting on information, outside scope, or better handled as a quick answer instead of a formal task.

A separate request inbox gives you a place to review what came in before deciding what happens next.

Good intake protects the task system from becoming another inbox.</textarea><div class="help">The full editor can support headings, links, lists, images, and formatting.</div></div>
      </div>
    </section>
    <aside class="preview" id="previewPane">
      <div class="section-label">Live editor preview</div>
      <div class="device-row"><span class="device active">Desktop</span><span class="device">Tablet</span><span class="device">Phone</span></div>
      <article class="preview-card"><div class="preview-cover" id="coverPreview">Cover image preview</div><div class="preview-body"><div class="preview-meta" id="metaPreview"></div><h1 class="preview-title" id="titlePreview">Why Every Client Request Shouldn’t Become a Task</h1><p class="preview-excerpt" id="excerptPreview"></p><div class="preview-article" id="bodyPreview"></div></div></article>
    </aside>
  </div>
</main>
</div>
<script>
function formatDate(value){if(!value)return 'DRAFT';const d=new Date(value+'T00:00:00');return d.toLocaleDateString('en-US',{month:'long',day:'numeric',year:'numeric'}).toUpperCase();}
function syncPreview(){
  document.getElementById('titlePreview').textContent=document.getElementById('title').value || 'Untitled article';
  document.getElementById('excerptPreview').textContent=document.getElementById('excerpt').value;
  document.getElementById('bodyPreview').textContent=document.getElementById('body').value;
  const category=(document.getElementById('category').value || 'Uncategorized').toUpperCase();
  document.getElementById('metaPreview').textContent=category+' · '+formatDate(document.getElementById('date').value);
}
function loadImage(event){
  const file=event.target.files && event.target.files[0];
  if(!file)return;
  const reader=new FileReader();
  reader.onload=function(e){const el=document.getElementById('coverPreview');el.style.backgroundImage='url("'+e.target.result+'")';el.textContent='';};
  reader.readAsDataURL(file);
}
syncPreview();
</script>
</body>
</html>"""


def _admin_editor_page() -> HTMLResponse:
    html = EDITOR_HTML.replace("__SITE_ORIGIN__", module.SITE_ORIGIN)
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
    if not _authorized_admin_session(request):
        response = RedirectResponse("/admin", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        return response
    return _admin_editor_page()


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "rvs-website-inquiry-endpoint"})
