import time

from fastapi import Request
from fastapi.responses import JSONResponse

import app as blog_backend
from app_v3 import app


def _position(value: object):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 50
    number = min(max(number, 0), 100)
    # Existing public templates historically use a falsy fallback for zero.
    # Keep an intentional far-edge crop effectively at zero rather than
    # allowing it to be interpreted as the 50% default.
    return 0.01 if number == 0 else number


async def _save_article(request: Request, status: str):
    _, error = await blog_backend._mutation_context(request)
    if error:
        return error

    body = await request.json()
    original_slug = blog_backend._safe_slug(body.get("original_slug"))
    requested_slug = blog_backend._safe_slug(body.get("slug"))
    if status == "draft":
        slug = requested_slug or original_slug or f"draft-{int(time.time())}"
    else:
        slug = requested_slug

    title = str(body.get("title", "")).strip()[:240]
    article_body = str(body.get("body", ""))[:30000]
    if status == "published" and (not slug or not title or not article_body.strip()):
        return JSONResponse(
            {"detail": "Title, URL slug, and article body are required."},
            status_code=400,
        )

    requested_cover = str(body.get("cover_image", "") or "").strip()
    cover_image = blog_backend._safe_cover_path(requested_cover)
    if requested_cover and not cover_image:
        return JSONResponse({"detail": "Invalid cover image path."}, status_code=400)

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
        "cover_position_x": _position(body.get("cover_position_x")),
        "cover_position_y": _position(body.get("cover_position_y")),
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
    return JSONResponse({"ok": True, "slug": slug})


@app.post("/admin/api/articles/save-draft")
async def admin_article_save_draft_v4(request: Request):
    return await _save_article(request, "draft")


@app.post("/admin/api/articles/save-publish")
async def admin_article_publish_v4(request: Request):
    return await _save_article(request, "published")
