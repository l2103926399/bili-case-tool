"""搜索编排：缓存判断 → 并发抓取详情 → 入库 → 排序。"""
import asyncio
import hashlib
import json
import logging
import time

from .. import config, database
from ..bili.client import BiliClient
from . import rank

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
INSERT INTO videos (bvid,title,author_name,author_mid,cover_url,pubdate,duration,tname,
 view,like,coin,favorite,reply,danmaku,share,quality_score,data_complete,fetched_at)
VALUES (:bvid,:title,:author_name,:author_mid,:cover_url,:pubdate,:duration,:tname,
 :view,:like,:coin,:favorite,:reply,:danmaku,:share,:quality_score,:data_complete,:fetched_at)
ON CONFLICT(bvid) DO UPDATE SET
 title=excluded.title, author_name=excluded.author_name, author_mid=excluded.author_mid,
 cover_url=excluded.cover_url, pubdate=excluded.pubdate, duration=excluded.duration,
 tname=excluded.tname, view=excluded.view, like=excluded.like, coin=excluded.coin,
 favorite=excluded.favorite, reply=excluded.reply, danmaku=excluded.danmaku,
 share=excluded.share, quality_score=excluded.quality_score,
 data_complete=excluded.data_complete, fetched_at=excluded.fetched_at
"""


def _cache_key(keyword: str, time_range: str) -> str:
    return hashlib.md5(f"{keyword}|{time_range}".encode("utf-8")).hexdigest()


def _filter_by_time(rows, time_range: str):
    days = config.TIME_RANGES.get(time_range)
    if not days:
        return rows
    cutoff = int(time.time()) - days * 86400
    return [r for r in rows if (r.get("pubdate") or 0) >= cutoff]


def _load_rows(conn, bvids):
    if not bvids:
        return []
    placeholders = ",".join("?" * len(bvids))
    db_rows = {
        r["bvid"]: dict(r)
        for r in conn.execute(
            f"SELECT * FROM videos WHERE bvid IN ({placeholders})", bvids
        ).fetchall()
    }
    return [db_rows[b] for b in bvids if b in db_rows]


def _upsert(conn, record: dict):
    conn.execute(_UPSERT_SQL, record)


async def _fetch_details(client, items):
    """并发抓详情：信号量控制并发，客户端内部保证请求间隔。"""
    sem = asyncio.Semaphore(max(1, config.DETAIL_CONCURRENCY))

    async def one(base):
        async with sem:
            try:
                detail = await client.get_video_detail(base["bvid"])
            except Exception:
                logger.warning("详情获取异常，按不全处理: %s", base["bvid"])
                detail = None
            return base, detail

    return await asyncio.gather(*(one(b) for b in items))


async def search_and_store(keyword, time_range="all", sort="quality", client=None):
    """返回 (rows, cached)。rows 为 dict 列表，已按 sort 排序。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return [], False
    ck = _cache_key(keyword, time_range)

    # 1) 尝试缓存
    conn = database.get_conn()
    try:
        cached = conn.execute(
            "SELECT bvids, fetched_at FROM search_cache WHERE cache_key=?", (ck,)
        ).fetchone()
        if cached and (int(time.time()) - cached["fetched_at"]) < config.CACHE_TTL_SECONDS:
            bvids = json.loads(cached["bvids"])
            rows = _filter_by_time(_load_rows(conn, bvids), time_range)
            return rank.sort_videos(rows, sort), True
    finally:
        conn.close()

    # 2) 未命中：抓取
    owns_client = client is None
    client = client or BiliClient()
    rows = []
    try:
        search_items = await client.search_videos(keyword)
        search_items = list(search_items)[: config.SEARCH_MAX_RESULTS]
        if config.ENRICH_DETAIL:
            pairs = await _fetch_details(client, search_items)
        else:
            pairs = [(base, None) for base in search_items]

        conn = database.get_conn()
        try:
            fetched_at = int(time.time())
            for base, detail in pairs:
                record = dict(base)
                if detail:
                    # view 或 archive/stat 的结果覆盖搜索摘要，缺失字段沿用 base
                    record.update({k: v for k, v in detail.items() if v is not None})
                complete = 1 if (detail or not config.ENRICH_DETAIL) else 0

                record["quality_score"] = rank.compute_quality_score(
                    record.get("view", 0), record.get("like", 0),
                    record.get("coin", 0), record.get("favorite", 0),
                    record.get("reply", 0), record.get("pubdate", 0),
                )
                record["data_complete"] = complete
                record["fetched_at"] = fetched_at
                _upsert(conn, record)
                rows.append(record)

            conn.commit()
            bvids = [r["bvid"] for r in rows]
            conn.execute(
                "INSERT OR REPLACE INTO search_cache "
                "(cache_key,keyword,time_range,bvids,fetched_at) VALUES (?,?,?,?,?)",
                (ck, keyword, time_range, json.dumps(bvids), fetched_at),
            )
            conn.commit()
        finally:
            conn.close()
    finally:
        if owns_client:
            await client.close()

    rows = _filter_by_time(rows, time_range)
    return rank.sort_videos(rows, sort), False
