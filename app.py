from fastapi.responses import JSONResponse

from src.main import app


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "rvs-website-inquiry-endpoint"})
