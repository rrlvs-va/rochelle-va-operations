from pathlib import Path
import types

from fastapi.responses import JSONResponse


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


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "rvs-website-inquiry-endpoint"})
