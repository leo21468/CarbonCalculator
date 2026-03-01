"""
FastAPI 后端：产品碳足迹查询 API + 自定义数据管理。
路由按功能拆分至 backend/routers/ 子模块。
"""
from __future__ import annotations
import os
import sys
import time
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.routers.products import router as products_router
from backend.routers.match import router as match_router
from backend.routers.invoices import router as invoices_router

logger = logging.getLogger("carbon_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# CORS 允许源从环境变量读取，多个源用逗号分隔，默认允许 localhost
_raw_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000",
)
_ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app = FastAPI(title="碳足迹 Agent API", version="1.0.0")

# ---------- CORS 中间件 ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 请求日志中间件 ----------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    logger.info("%s %s %.1fms %s", request.method, request.url.path, elapsed, response.status_code)
    return response

# ---------- 全局异常处理器 ----------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("未捕获异常: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "内部服务器错误", "detail": "服务器处理请求时发生错误，请稍后重试"},
    )

# ---------- 注册路由 ----------
app.include_router(products_router)
app.include_router(match_router)
app.include_router(invoices_router)

# ---------- 静态文件 ----------
frontend_dir = ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

# ---------- 健康检查 ----------
@app.get("/api/health", tags=["health"], summary="健康检查")
def health():
    """服务健康检查，用于前端判断接口可用性"""
    return {"status": "ok", "service": "碳足迹 Agent API"}

# ---------- 根路由 ----------
@app.get("/", include_in_schema=False)
def index():
    """返回前端 Agent 页面"""
    front = ROOT / "frontend" / "index.html"
    if front.exists():
        return FileResponse(str(front))
    return {"msg": "请放置 frontend/index.html"}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
