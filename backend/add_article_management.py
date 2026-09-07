from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        '.nav{display:grid;gap:5px;margin-top:28px}.nav a{color:#c8bdb4;text-decoration:none;padding:10px 11px;border-radius:8px;font-size:.88rem}.nav a.active{background:#28211d;color:#fff}',
        '.nav{display:grid;gap:5px;margin-top:28px}.nav a{color:#c8bdb4;text-decoration:none;padding:10px 11px;border-radius:8px;font-size:.88rem;transition:background .18s ease,color .18s ease,transform .18s ease}.nav a.active{background:#28211d;color:#fff}.nav a:hover,.nav a:focus-visible{background:#28211d;color:#fff;outline:none;transform:translateX(2px)}',
    ),
    (
        '.signout{margin-top:11px;border:1px solid #5a493c;background:transparent;color:#d8cbc1;border-radius:999px;padding:7px 11px;cursor:pointer;font-size:.76rem}',
        '.signout{margin-top:11px;border:1px solid #5a493c;background:transparent;color:#d8cbc1;border-radius:999px;padding:7px 11px;cursor:pointer;font-size:.76rem;transition:background .18s ease,border-color .18s ease,color .18s ease,transform .18s ease}.signout:hover,.signout:focus-visible{background:#241d19;border-color:#cb8f96;color:#fff;transform:translateY(-1px);outline:none}',
    ),
    (
        '.btn{border:1px solid #5a493c;background:transparent;color:#eee4dc;border-radius:999px;padding:9px 14px;cursor:pointer;font-weight:750;font-size:.82rem}.btn.gold{background:var(--gold);border-color:var(--gold);color:#17110d}',
        '.btn{border:1px solid #5a493c;background:transparent;color:#eee4dc;border-radius:999px;padding:9px 14px;cursor:pointer;font-weight:750;font-size:.82rem;transition:background .18s ease,border-color .18s ease,color .18s ease,transform .18s ease,box-shadow .18s ease}.btn:hover,.btn:focus-visible{background:#28211d;border-color:#d1ab63;color:#fff;transform:translateY(-1px);outline:none}.btn.gold{background:var(--gold);border-color:var(--gold);color:#17110d}.btn.gold:hover,.btn.gold:focus-visible{background:#e0bc76;border-color:#e0bc76;color:#17110d;box-shadow:0 8px 22px rgba(209,171,99,.15)}',
    ),
    (
        '<nav class="nav"><a class="active" href="/admin/editor">New article</a><a href="__SITE_ORIGIN__/experiments/blog-cms-preview/">View blog</a><a href="__SITE_ORIGIN__/">Main website</a></nav>',
        '<nav class="nav"><a class="active" href="/admin/editor">New article</a><a href="/admin/articles">Articles</a><a href="__SITE_ORIGIN__/experiments/blog-cms-preview/">View blog</a><a href="__SITE_ORIGIN__/">Main website</a></nav>',
    ),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit(f"Expected editor fragment not found: {old[:80]}")
    text = text.replace(old, new, 1)

if '@app.get("/admin/articles")' not in text:
    marker = '\n\n@app.get("/")\nasync def root() -> JSONResponse:'
    if marker not in text:
        raise SystemExit("Root route marker not found")

    block = r'''

ARTICLES_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta name="robots" content="noindex,nofollow,noarchive" />
<title>Articles | The Rochelle Edit Admin</title>
<style>
:root{--ink:#11100f;--panel:#201b18;--text:#f7f1ea;--muted:#b9aca1;--gold:#d1ab63;--blush:#cb8f96;--line:#3b312a;--green:#9db79e}
*{box-sizing:border-box}body{margin:0;background:#0e0d0c;color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.6}button{font:inherit}.shell{min-height:100vh;display:grid;grid-template-columns:240px 1fr}.sidebar{border-right:1px solid var(--line);background:#151311;padding:26px 18px;position:sticky;top:0;height:100vh}.brand{font-family:Georgia,"Times New Roman",serif;font-size:1.16rem;margin-bottom:5px}.sub{color:var(--gold);text-transform:uppercase;letter-spacing:.12em;font-size:.68rem}.nav{display:grid;gap:5px;margin-top:28px}.nav a{color:#c8bdb4;text-decoration:none;padding:10px 11px;border-radius:8px;font-size:.88rem;transition:background .18s ease,color .18s ease,transform .18s ease}.nav a.active{background:#28211d;color:#fff}.nav a:hover,.nav a:focus-visible{background:#28211d;color:#fff;outline:none;transform:translateX(2px)}.account{position:absolute;left:18px;right:18px;bottom:20px;border-top:1px solid var(--line);padding-top:16px;font-size:.8rem;color:#b5a69b}.account strong{color:#f1e7de}.signout{margin-top:11px;border:1px solid #5a493c;background:transparent;color:#d8cbc1;border-radius:999px;padding:7px 11px;cursor:pointer;font-size:.76rem;transition:background .18s ease,border-color .18s ease,color .18s ease,transform .18s ease}.signout:hover,.signout:focus-visible{background:#241d19;border-color:var(--blush);color:#fff;transform:translateY(-1px);outline:none}.main{min-width:0}.topbar{min-height:68px;border-bottom:1px solid var(--line);background:#12100f;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 26px;position:sticky;top:0;z-index:5}.topbar strong{font-family:Georgia,"Times New Roman",serif;font-size:1.08rem}.new-link,.action{display:inline-flex;align-items:center;justify-content:center;text-decoration:none;border-radius:999px;padding:9px 14px;font-weight:750;font-size:.82rem;transition:background .18s ease,border-color .18s ease,color .18s ease,transform .18s ease}.new-link{background:var(--gold);color:#17110d}.new-link:hover,.new-link:focus-visible{background:#e0bc76;transform:translateY(-1px);outline:none}.content{padding:34px;max-width:1180px}.eyebrow{text-transform:uppercase;letter-spacing:.14em;color:var(--blush);font-size:.68rem;font-weight:800}.content h1{font:500 clamp(2.5rem,5vw,4rem)/1 Georgia,"Times New Roman",serif;margin:10px 0 10px}.lead{color:var(--muted);max-width:760px;margin:0 0 28px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.tab{border:1px solid #4d4036;border-radius:999px;padding:8px 12px;color:#c9bbb0;font-size:.78rem}.tab.active{border-color:var(--gold);color:var(--gold)}.article-list{border-top:1px solid var(--line)}.article-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;padding:22px 0;border-bottom:1px solid var(--line);align-items:center}.status{display:inline-block;color:var(--green);font-size:.7rem;text-transform:uppercase;letter-spacing:.11em;font-weight:800;margin-bottom:7px}.article-title{font:500 1.45rem/1.15 Georgia,"Times New Roman",serif;margin:0 0 6px}.meta{color:#9f9288;font-size:.78rem}.row-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.action{border:1px solid #5a493c;color:#eee4dc;background:transparent}.action:hover,.action:focus-visible{border-color:var(--gold);background:#28211d;color:#fff;transform:translateY(-1px);outline:none}.action.view{color:var(--gold)}button.action:disabled{opacity:.42;cursor:not-allowed;transform:none;background:transparent;border-color:#4a3d34;color:#968981}.notice{margin-top:24px;padding:18px 20px;border:1px solid #4c3e34;background:#171412;color:#b9aca1;font-size:.88rem}.notice strong{color:#f2e7df}.empty{padding:28px 0;color:#8f8177;font-size:.9rem;border-bottom:1px solid var(--line)}
@media(max-width:980px){.shell{grid-template-columns:1fr}.sidebar{display:none}.content{padding:26px}.article-row{grid-template-columns:1fr}.row-actions{justify-content:flex-start}}
@media(max-width:620px){.topbar{padding:12px 14px;align-items:flex-start;flex-direction:column}.content{padding:22px 16px}.row-actions{display:grid;grid-template-columns:1fr 1fr}.action{width:100%}}
</style>
</head>
<body>
<div class="shell">
<aside class="sidebar">
  <div class="brand">The Rochelle Edit</div><div class="sub">Admin</div>
  <nav class="nav"><a href="/admin/editor">New article</a><a class="active" href="/admin/articles">Articles</a><a href="__SITE_ORIGIN__/experiments/blog-cms-preview/">View blog</a><a href="__SITE_ORIGIN__/">Main website</a></nav>
  <div class="account">Signed in<br><strong>Rochelle V. Silvestre</strong><form method="post" action="/logout"><button class="signout" type="submit">Sign out</button></form></div>
</aside>
<main class="main">
  <div class="topbar"><strong>Articles</strong><a class="new-link" href="/admin/editor">New article</a></div>
  <div class="content">
    <div class="eyebrow">Manage content</div>
    <h1>Articles</h1>
    <p class="lead">Review published articles, drafts, and items moved to Trash from one place.</p>
    <div class="tabs"><span class="tab active">Published · 1</span><span class="tab">Drafts · 0</span><span class="tab">Trash · 0</span></div>
    <div class="article-list">
      <article class="article-row">
        <div><span class="status">Published</span><h2 class="article-title">Why Every Client Request Shouldn’t Become a Task</h2><div class="meta">September 7, 2026 · Rochelle V. Silvestre</div></div>
        <div class="row-actions"><a class="action" href="/admin/editor">Edit</a><a class="action view" href="__SITE_ORIGIN__/experiments/blog-cms-preview/article.html">View</a><button class="action" type="button" disabled title="Available when publishing storage is connected">Unpublish</button><button class="action" type="button" disabled title="Available when publishing storage is connected">Move to Trash</button></div>
      </article>
      <div class="empty"><strong>Trash:</strong> items moved to Trash will stay recoverable here before permanent deletion.</div>
    </div>
    <div class="notice"><strong>Deletion workflow is now accounted for in the admin design.</strong> Unpublish, Move to Trash, Restore, and Delete Permanently will become active together with real Save Draft/Publish storage. They are disabled for now so the interface does not pretend to delete something when no persistent article store exists yet.</div>
  </div>
</main>
</div>
</body>
</html>"""


def _admin_articles_page() -> HTMLResponse:
    html = ARTICLES_HTML.replace("__SITE_ORIGIN__", module.SITE_ORIGIN)
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


@app.get("/admin/articles")
async def admin_articles(request: Request):
    if not _authorized_admin_session(request):
        response = RedirectResponse("/admin", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        return response
    return _admin_articles_page()
'''
    text = text.replace(marker, block + marker, 1)

path.write_text(text, encoding="utf-8")
print("Article management and admin hover states added.")
