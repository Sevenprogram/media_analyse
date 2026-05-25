# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/main.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

"""
MediaCrawler WebUI API Server
Start command: uvicorn api.main:app --port 8080 --reload
Or: python -m api.main
"""
import asyncio
import os
import subprocess
import sys
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from .routers import crawler_router, data_router, research as research_module, websocket_router
from .routers.accounts import router as accounts_router
from .routers.admin import router as admin_router
from .routers.auth import router as auth_router
from .routers.backtests import router as backtests_router
from .routers.background_tasks import router as background_tasks_router
from .routers.competitors import router as competitors_router
from .routers.content_tracking import router as content_tracking_router
from .routers.creator_search import router as creator_search_router
from .routers.keyword_opportunities import router as keyword_opportunities_router
from .routers.keyword_library import router as keyword_library_router
from .routers.orgs import router as orgs_router
from .routers.reports import router as reports_router
from .routers.research import router as research_router
from database.db_session import create_tables
from research.automation_daemon import (
    ensure_research_automation_daemon_started,
    stop_research_automation_daemon,
)
from research.database_guard import is_research_database_enabled


@asynccontextmanager
async def lifespan(app: FastAPI):
    if is_research_database_enabled():
        await create_tables()
        await ensure_research_automation_daemon_started(
            enqueue_job=lambda job_id, project_id: research_module.enqueue_research_collection_job(
                job_id,
                project_id=project_id,
            )
        )
    try:
        yield
    finally:
        await stop_research_automation_daemon()


app = FastAPI(
    title="MediaCrawler WebUI API",
    description="API for controlling MediaCrawler from WebUI",
    version="1.0.0",
    lifespan=lifespan,
)

# Get webui static files directory
WEBUI_DIR = os.path.join(os.path.dirname(__file__), "webui")
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# CORS configuration - allow frontend dev server access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Backup port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix="/api")
app.include_router(orgs_router, prefix="/api")
app.include_router(crawler_router, prefix="/api")
app.include_router(data_router, prefix="/api")
app.include_router(websocket_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(accounts_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(backtests_router, prefix="/api")
app.include_router(background_tasks_router, prefix="/api")
app.include_router(creator_search_router, prefix="/api")
app.include_router(competitors_router, prefix="/api")
app.include_router(keyword_opportunities_router, prefix="/api")
app.include_router(keyword_library_router, prefix="/api")
app.include_router(content_tracking_router, prefix="/api")
app.include_router(reports_router, prefix="/api")


@app.get("/")
async def serve_frontend():
    """Open the research console as the primary WebUI entry."""
    return RedirectResponse(url="/research", status_code=307)


@app.get("/crawler")
async def serve_crawler_console():
    """Return legacy crawler command center page."""
    crawler_path = os.path.join(WEBUI_DIR, "crawler.html")
    if os.path.exists(crawler_path):
        return FileResponse(crawler_path)
    return {
        "message": "MediaCrawler WebUI API",
        "version": "1.0.0",
        "docs": "/docs",
        "note": "WebUI not found, please build it first: cd webui && npm run build"
    }


@app.get("/research")
async def serve_research_console():
    """Return research console page"""
    return _serve_research_console_file()


@app.get("/login")
@app.get("/register")
async def serve_auth_console():
    """Return the React app for SaaS auth pages."""
    return _serve_research_console_file()


def _serve_research_console_file():
    built_research_path = os.path.join(WEBUI_DIR, "dist", "index.html")
    if os.path.exists(built_research_path):
        return FileResponse(built_research_path)
    research_path = os.path.join(WEBUI_DIR, "research.html")
    if os.path.exists(research_path):
        return FileResponse(research_path)
    return {"message": "Research console not found"}


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/env/check")
async def check_environment():
    """Check if MediaCrawler environment is configured correctly"""
    try:
        process = await asyncio.to_thread(_run_environment_check)

        if process.returncode == 0:
            return {
                "success": True,
                "message": "MediaCrawler environment configured correctly",
                "output": process.stdout[:500]  # Truncate to first 500 characters
            }
        else:
            error_msg = process.stderr or process.stdout
            return {
                "success": False,
                "message": "Environment check failed",
                "error": error_msg[:500]
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "Environment check timeout",
            "error": "Command execution exceeded 30 seconds"
        }
    except FileNotFoundError:
        return {
            "success": False,
            "message": "Python command not found",
            "error": "Please ensure the Python executable is available in system PATH"
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Environment check error",
            "error": f"{type(e).__name__}: {e}"
        }


def _run_environment_check() -> subprocess.CompletedProcess[str]:
    """Run the environment check in a worker thread.

    Windows uvicorn reload can run with a selector event loop, where
    asyncio subprocess APIs raise NotImplementedError. subprocess.run keeps
    this endpoint portable while the route itself remains async.
    """
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    return subprocess.run(
        [sys.executable, "main.py", "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=PROJECT_ROOT,
        env=env,
        timeout=30.0,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )


@app.get("/api/config/platforms")
async def get_platforms():
    """Get list of supported platforms"""
    return {
        "platforms": [
            {"value": "xhs", "label": "Xiaohongshu", "icon": "book-open"},
            {"value": "dy", "label": "Douyin", "icon": "music"},
            {"value": "ks", "label": "Kuaishou", "icon": "video"},
            {"value": "bili", "label": "Bilibili", "icon": "tv"},
            {"value": "wb", "label": "Weibo", "icon": "message-circle"},
            {"value": "tieba", "label": "Baidu Tieba", "icon": "messages-square"},
            {"value": "zhihu", "label": "Zhihu", "icon": "help-circle"},
        ]
    }


@app.get("/api/config/options")
async def get_config_options():
    """Get all configuration options"""
    return {
        "login_types": [
            {"value": "qrcode", "label": "QR Code Login"},
            {"value": "cookie", "label": "Cookie Login"},
        ],
        "crawler_types": [
            {"value": "search", "label": "Search Mode"},
            {"value": "detail", "label": "Detail Mode"},
            {"value": "creator", "label": "Creator Mode"},
        ],
        "save_options": [
            {"value": "jsonl", "label": "JSONL File"},
            {"value": "json", "label": "JSON File"},
            {"value": "csv", "label": "CSV File"},
            {"value": "excel", "label": "Excel File"},
            {"value": "sqlite", "label": "SQLite Database"},
            {"value": "db", "label": "MySQL Database"},
            {"value": "mongodb", "label": "MongoDB Database"},
        ],
    }


# Mount static resources - must be placed after all routes
if os.path.exists(WEBUI_DIR):
    assets_dir = os.path.join(WEBUI_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    # Mount logos directory
    logos_dir = os.path.join(WEBUI_DIR, "logos")
    if os.path.exists(logos_dir):
        app.mount("/logos", StaticFiles(directory=logos_dir), name="logos")
    # Mount other static files (e.g., vite.svg)
    app.mount("/static", StaticFiles(directory=WEBUI_DIR), name="webui-static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
