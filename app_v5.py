import base64
import json

import httpx

import app as blog_backend
from app_v4 import app


_original_read_manifest = blog_backend._read_manifest


async def _read_manifest_fresh() -> dict:
    """Read the manifest from GitHub's contents API to avoid raw-CDN propagation lag."""
    try:
        params = {"ref": blog_backend.PUBLISH_BRANCH}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                blog_backend.GITHUB_CONTENTS_URL,
                headers=blog_backend._github_headers(True),
                params=params,
            )
        if response.status_code == 200:
            payload = response.json()
            encoded = str(payload.get("content", "")).replace("\n", "")
            if encoded:
                decoded = base64.b64decode(encoded).decode("utf-8")
                data = json.loads(decoded)
                if isinstance(data, dict) and isinstance(data.get("articles"), list):
                    return data
    except (httpx.HTTPError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        pass

    # Keep the old raw-file reader as a fallback if GitHub's contents API is unavailable.
    return await _original_read_manifest()


blog_backend._read_manifest = _read_manifest_fresh
