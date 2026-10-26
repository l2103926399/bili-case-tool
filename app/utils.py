"""展示层工具：数字格式化、比率计算、卡片数据组装。"""
import time


def fmt_num(n) -> str:
    n = int(n or 0)
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def fmt_ts(ts) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(int(ts)))


def fmt_duration(seconds) -> str:
    """秒数 → mm:ss / h:mm:ss。"""
    try:
        total = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def bili_url(bvid: str) -> str:
    return f"https://www.bilibili.com/video/{bvid}"


def ratios(row: dict) -> dict:
    view = row.get("view") or 0
    if view <= 0:
        return {"interaction": None, "favorite": None, "coin": None}
    ir = (row.get("like", 0) + row.get("coin", 0) + row.get("favorite", 0) + row.get("reply", 0)) / view
    return {
        "interaction": round(ir * 100, 2),
        "favorite": round((row.get("favorite", 0) / view) * 100, 2),
        "coin": round((row.get("coin", 0) / view) * 100, 2),
    }


def card_dict(r: dict) -> dict:
    return {
        "bvid": r["bvid"],
        "title": r["title"],
        "author_name": r.get("author_name") or "未知UP主",
        "cover_url": r.get("cover_url") or "",
        "pubdate": r.get("pubdate") or 0,
        "pubdate_str": fmt_ts(r.get("pubdate")),
        "duration_str": fmt_duration(r.get("duration")),
        "view": r.get("view") or 0,
        "view_str": fmt_num(r.get("view")),
        "like": r.get("like") or 0,
        "like_str": fmt_num(r.get("like")),
        "favorite": r.get("favorite") or 0,
        "favorite_str": fmt_num(r.get("favorite")),
        "reply": r.get("reply") or 0,
        "reply_str": fmt_num(r.get("reply")),
        "quality_score": r.get("quality_score"),
        "data_complete": r.get("data_complete", 1),
        "bili_url": bili_url(r["bvid"]),
    }
