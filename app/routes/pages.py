"""页面路由：首页 / 详情页 / 我的案例页。"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import database, utils

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def get_video_row(bvid: str):
    conn = database.get_conn()
    try:
        r = conn.execute("SELECT * FROM videos WHERE bvid=?", (bvid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"keyword": "", "results": [], "cached": None}
    )


@router.get("/video/{bvid}", response_class=HTMLResponse)
def video_page(request: Request, bvid: str):
    v = get_video_row(bvid)
    if not v:
        return templates.TemplateResponse(
            request, "video.html",
            {"v": None, "bvid": bvid, "bili_url": utils.bili_url(bvid)},
        )
    display = dict(v)
    display["pubdate_str"] = utils.fmt_ts(v["pubdate"])
    for key in ("view", "like", "coin", "favorite", "reply", "danmaku"):
        display[key + "_str"] = utils.fmt_num(v[key])
    display["duration_str"] = utils.fmt_duration(v.get("duration"))
    return templates.TemplateResponse(
        request, "video.html",
        {"v": display, "bvid": bvid, "bili_url": utils.bili_url(bvid),
         "ratios": utils.ratios(v)},
    )


@router.get("/favorites", response_class=HTMLResponse)
def favorites_page(request: Request):
    # 收藏存在浏览器 localStorage，这里只返回页面骨架，由前端渲染。
    return templates.TemplateResponse(request, "favorites.html", {})
