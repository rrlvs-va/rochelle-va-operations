import time

from fastapi import Request
from fastapi.responses import JSONResponse

import app as blog_backend
from app_v2 import app


@app.post("/admin/api/articles/draft")
async def admin_article_save_draft(request: Request):
    _, error = await blog_backend._mutation_context(request)
    if error:
        return error

    body = await request.json()
    original_slug = blog_backend._safe_slug(body.get("original_slug"))
    requested_slug = blog_backend._safe_slug(body.get("slug"))
    slug = requested_slug or original_slug or f"draft-{int(time.time())}"

    requested_cover = str(body.get("cover_image", "") or "").strip()
    cover_image = blog_backend._safe_cover_path(requested_cover)
    if requested_cover and not cover_image:
        return JSONResponse({"detail": "Invalid cover image path."}, status_code=400)

    data = await blog_backend._read_manifest()
    articles = data.get("articles", [])
    original = next((a for a in articles if a.get("slug") == original_slug), None) if original_slug else None

    if original and original.get("status") != "draft":
        return JSONResponse(
            {"detail": "Only draft articles can be saved with Save draft. Use Publish to update an existing published or unpublished article."},
            status_code=409,
        )

    if original_slug and original_slug != slug:
        collision = next((a for a in articles if a.get("slug") == slug and a.get("slug") != original_slug), None)
        if collision:
            return JSONResponse({"detail": "That URL slug is already in use."}, status_code=409)
        articles = [a for a in articles if a.get("slug") != original_slug]

    item = next((a for a in articles if a.get("slug") == slug), None)
    if item and item.get("status") != "draft":
        return JSONResponse({"detail": "That URL slug is already in use."}, status_code=409)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "slug": slug,
        "title": str(body.get("title", "")).strip()[:240] or "Untitled draft",
        "category": str(body.get("category", "")).strip()[:100] or "Uncategorized",
        "publish_date": str(body.get("publish_date", "")).strip()[:10],
        "author": "Rochelle V. Silvestre",
        "excerpt": str(body.get("excerpt", "")).strip()[:700],
        "body": str(body.get("body", ""))[:30000],
        "cover_image": cover_image,
        "status": "draft",
        "updated_at": now,
    }
    if item:
        payload["created_at"] = item.get("created_at", now)
        item.update(payload)
    else:
        payload["created_at"] = now
        articles.append(payload)

    data["articles"] = articles
    ok, detail = await blog_backend._write_manifest(data, f"Blog: save draft {slug}")
    if not ok:
        return JSONResponse({"detail": detail}, status_code=502)
    return JSONResponse({"ok": True, "slug": slug})


@app.post("/admin/api/articles/{slug}/set-status")
async def admin_article_set_status(slug: str, request: Request):
    _, error = await blog_backend._mutation_context(request)
    if error:
        return error

    body = await request.json()
    new_status = str(body.get("status", ""))
    if new_status not in {"draft", "published", "unpublished", "trash"}:
        return JSONResponse({"detail": "Invalid article status."}, status_code=400)

    data = await blog_backend._read_manifest()
    match = next((a for a in data.get("articles", []) if a.get("slug") == slug), None)
    if not match:
        return JSONResponse({"detail": "Article not found."}, status_code=404)

    old_status = str(match.get("status", ""))
    if new_status == "trash" and old_status != "trash":
        match["trashed_from"] = old_status or "draft"
    elif old_status == "trash" and new_status != "trash":
        match.pop("trashed_from", None)

    match["status"] = new_status
    match["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ok, detail = await blog_backend._write_manifest(data, f"Blog: set {slug} to {new_status}")
    if not ok:
        return JSONResponse({"detail": detail}, status_code=502)
    return JSONResponse({"ok": True})
