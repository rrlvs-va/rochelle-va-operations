import time

from fastapi import Request
from fastapi.responses import JSONResponse

import app as blog_backend
from app_v5 import app


def _position(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 50.0
    return min(max(number, 0.0), 100.0)


def _safe_image(value: object) -> str:
    requested = str(value or "").strip()
    if not requested:
        return ""
    return blog_backend._safe_cover_path(requested)


async def _save_article_v2(request: Request, status: str):
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
    cover_image = _safe_image(requested_cover)
    article_image = _safe_image(requested_article)
    if requested_cover and not cover_image:
        return JSONResponse({"detail": "Invalid blog cover image path."}, status_code=400)
    if requested_article and not article_image:
        return JSONResponse({"detail": "Invalid article header image path."}, status_code=400)

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
        "article_image": article_image,
        "article_position_x": _position(body.get("article_position_x")),
        "article_position_y": _position(body.get("article_position_y")),
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


@app.post("/admin/api/articles/save-draft-v2")
async def admin_article_save_draft_v6(request: Request):
    return await _save_article_v2(request, "draft")


@app.post("/admin/api/articles/save-publish-v2")
async def admin_article_publish_v6(request: Request):
    return await _save_article_v2(request, "published")


@app.post("/admin/api/articles/{slug}/safe-status")
async def admin_article_safe_status(slug: str, request: Request):
    _, error = await blog_backend._mutation_context(request)
    if error:
        return error

    body = await request.json()
    expected = str(body.get("expected_status", ""))
    new_status = str(body.get("status", ""))
    allowed = {"draft", "published", "unpublished", "trash"}
    if expected not in allowed or new_status not in allowed:
        return JSONResponse({"detail": "Invalid article status."}, status_code=400)

    data = await blog_backend._read_manifest()
    match = next((a for a in data.get("articles", []) if a.get("slug") == slug), None)
    if not match:
        return JSONResponse({"detail": "Article not found. The list may be out of date."}, status_code=404)

    current = str(match.get("status", ""))
    if current != expected:
        return JSONResponse(
            {
                "detail": f"This screen showed the article as {expected}, but the latest saved state is {current}. Nothing was changed; the list will refresh.",
                "current_status": current,
            },
            status_code=409,
        )

    if new_status == "trash" and current != "trash":
        match["trashed_from"] = current
    elif current == "trash" and new_status != "trash":
        match.pop("trashed_from", None)

    match["status"] = new_status
    match["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ok, detail = await blog_backend._write_manifest(data, f"Blog: set {slug} to {new_status}")
    if not ok:
        return JSONResponse({"detail": detail}, status_code=502)
    return JSONResponse({"ok": True, "slug": slug, "status": new_status})
