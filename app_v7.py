from pathlib import Path
import time

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import app as blog_backend
import app_v6 as previous_backend
from app_v6 import app


_original_template = blog_backend._template


def _template_with_article_photo(name: str, session: dict) -> HTMLResponse:
    if name != "admin_editor.html":
        return _original_template(name, session)

    html = (Path(__file__).parent / name).read_text(encoding="utf-8")
    html = html.replace("__SITE_ORIGIN__", blog_backend.module.SITE_ORIGIN).replace(
        "__CSRF__", blog_backend._csrf_for(session)
    )
    html = html.replace(
        "</body>",
        '<script src="/admin/article-photo.js?v=20260908-1"></script></body>',
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


blog_backend._template = _template_with_article_photo


@app.get("/admin/article-photo.js")
async def admin_article_photo_script(request: Request):
    if not blog_backend._authorized_admin_session(request):
        return Response("// Unauthorized", status_code=401, media_type="application/javascript")
    script = (Path(__file__).parent / "admin_article_photo.js").read_text(encoding="utf-8")
    return Response(
        script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


async def _save_article_with_photo(request: Request, status: str):
    _, error = await blog_backend._mutation_context(request)
    if error:
        return error

    body = await request.json()
    original_slug = blog_backend._safe_slug(body.get("original_slug"))
    requested_slug = blog_backend._safe_slug(body.get("slug"))
    slug = requested_slug or original_slug or (f"draft-{int(time.time())}" if status == "draft" else "")

    title = str(body.get("title", "")).strip()[:240]
    article_body = str(body.get("body", ""))[:30000]
    if status == "published" and (not slug or not title or not article_body.strip()):
        return JSONResponse(
            {"detail": "Title, URL slug, and article body are required."},
            status_code=400,
        )

    requested_cover = str(body.get("cover_image", "") or "").strip()
    requested_article = str(body.get("article_image", "") or "").strip()
    requested_photo = str(body.get("article_photo", "") or "").strip()
    cover_image = previous_backend._safe_image(requested_cover)
    article_image = previous_backend._safe_image(requested_article)
    article_photo = previous_backend._safe_image(requested_photo)

    if requested_cover and not cover_image:
        return JSONResponse({"detail": "Invalid blog cover image path."}, status_code=400)
    if requested_article and not article_image:
        return JSONResponse({"detail": "Invalid article header image path."}, status_code=400)
    if requested_photo and not article_photo:
        return JSONResponse({"detail": "Invalid article photo path."}, status_code=400)

    data = await blog_backend._read_manifest()
    articles = data.get("articles", [])
    original = next((a for a in articles if a.get("slug") == original_slug), None) if original_slug else None

    if status == "draft" and original and original.get("status") != "draft":
        return JSONResponse(
            {"detail": "Only draft articles can be saved with Save draft. Use Publish to update an existing published or unpublished article."},
            status_code=409,
        )

    if original_slug and original_slug != slug:
        collision = next(
            (a for a in articles if a.get("slug") == slug and a.get("slug") != original_slug),
            None,
        )
        if collision:
            return JSONResponse({"detail": "That URL slug is already in use."}, status_code=409)
        articles = [a for a in articles if a.get("slug") != original_slug]

    item = next((a for a in articles if a.get("slug") == slug), None)
    if item and status == "draft" and item.get("status") != "draft":
        return JSONResponse({"detail": "That URL slug is already in use."}, status_code=409)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "slug": slug,
        "title": title or "Untitled draft",
        "category": str(body.get("category", "")).strip()[:100] or "Uncategorized",
        "publish_date": str(body.get("publish_date", "")).strip()[:10]
        or ("" if status == "draft" else time.strftime("%Y-%m-%d", time.gmtime())),
        "author": "Rochelle V. Silvestre",
        "excerpt": str(body.get("excerpt", "")).strip()[:700],
        "body": article_body,
        "cover_image": cover_image,
        "cover_position_x": previous_backend._position(body.get("cover_position_x")),
        "cover_position_y": previous_backend._position(body.get("cover_position_y")),
        "article_image": article_image,
        "article_position_x": previous_backend._position(body.get("article_position_x")),
        "article_position_y": previous_backend._position(body.get("article_position_y")),
        "article_photo": article_photo,
        "status": status,
        "updated_at": now,
    }

    if item:
        if status == "draft":
            payload["created_at"] = item.get("created_at", now)
        item.update(payload)
    else:
        if status == "draft":
            payload["created_at"] = now
        articles.append(payload)

    data["articles"] = articles
    action = "save draft" if status == "draft" else "publish"
    ok, detail = await blog_backend._write_manifest(data, f"Blog: {action} {slug}")
    if not ok:
        return JSONResponse({"detail": detail}, status_code=502)

    return JSONResponse({"ok": True, "slug": slug, "status": status, "article": payload})


# The existing v6 routes call this function by name at request time, so replacing
# it lets the current editor endpoints gain article-photo support without adding
# another pair of public mutation URLs.
previous_backend._save_article_v2 = _save_article_with_photo
