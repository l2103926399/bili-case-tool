"""FastAPI 入口：启动时建表，挂载路由。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import database
from .routes import api, pages


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="B站优质视频案例库", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)
app.include_router(pages.router)
app.include_router(api.router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "db_exists": database.db_readable(),
        "db_path": str(database.config.DB_PATH),
    }
