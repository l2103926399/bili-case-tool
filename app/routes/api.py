"""JSON API。"""
import asyncio
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import config, database, utils
from ..services import search as search_svc

router = APIRouter()

# 单 IP 搜索频控（滑动窗口）。多 worker 部署时各自计数，作为缓冲够用。
_ip_hits: dict[str, list[float]] = {}
_gates: dict[object, asyncio.Semaphore] = {}


def _search_gate() -> asyncio.Semaphore:
    """每个事件循环一个信号量，避免跨 loop 复用时绑定冲突。"""
    loop = asyncio.get_running_loop()
    gate = _gates.get(loop)
    if gate is None:
        if len(_gates) > 8:
            _gates.clear()
        gate = _gates[loop] = asyncio.Semaphore(max(1, config.GLOBAL_SEARCH_CONCURRENCY))
    return gate


def get_video_row(bvid: str):
    conn = database.get_conn()
    try:
        r = conn.execute("SELECT * FROM videos WHERE bvid=?", (bvid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    now = time.time()
    hits = [t for t in _ip_hits.get(ip, []) if now - t < 60]
    if len(hits) >= config.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="搜索太频繁了，请休息一会儿再试")
    hits.append(now)
    _ip_hits[ip] = hits
    if len(_ip_hits) > 2048:  # 防止内存无限增长
        stale = [k for k, v in _ip_hits.items() if not v or now - v[-1] > 120]
        for k in stale[:512]:
            _ip_hits.pop(k, None)


class SearchBody(BaseModel):
    keyword: str
    time_range: str = "all"
    sort: str = "quality"


@router.post("/api/search")
async def api_search(body: SearchBody, request: Request):
    _check_rate_limit(request)
    keyword = (body.keyword or "").strip()
    if not keyword:
        return {"ok": True, "items": [], "cached": False, "total": 0}
    time_range = body.time_range if body.time_range in config.TIME_RANGES else "all"
    sort = body.sort if body.sort in {"quality", "view", "pubdate"} else "quality"
    try:
        async with _search_gate():
            rows, cached = await search_svc.search_and_store(keyword, time_range, sort)
    except Exception as e:  # 抓取异常 → 友好返回，不白屏
        return {"ok": False, "error": f"抓取失败：{e}", "items": [], "cached": False, "total": 0}
    items = [utils.card_dict(r) for r in rows]
    return {"ok": True, "items": items, "cached": cached, "total": len(items)}


@router.get("/api/video/{bvid}")
def api_video(bvid: str):
    row = get_video_row(bvid)
    if not row:
        return {"ok": False, "error": "未找到该视频，请先搜索"}
    return {
        "ok": True,
        "video": utils.card_dict(row),
        "full": row,
        "ratios": utils.ratios(row),
        "bili_url": utils.bili_url(bvid),
    }
