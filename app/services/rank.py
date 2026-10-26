"""质量分计算与排序。

质量分 = 互动率×30% + 收藏率×20% + 播放量分×20% + 投币率×15% + 时效因子×15%
各比率按经验基准归一化到 0-100。
"""
import math
import time

IR_FULL = 0.10   # 互动率满分基准：10%
FR_FULL = 0.05   # 收藏率满分基准：5%
CR_FULL = 0.02   # 投币率满分基准：2%


def _rate_score(rate: float, full: float) -> float:
    if full <= 0:
        return 0.0
    return max(0.0, min(100.0, rate / full * 100.0))


def compute_quality_score(view, like, coin, favorite, reply, pubdate, now=None):
    """返回 0-100 分；数据不足（播放量<=0）返回 None。"""
    if view is None or view <= 0:
        return None
    now = now or int(time.time())
    ir = (like + coin + favorite + reply) / view
    fr = favorite / view
    cr = coin / view
    play_score = min(100.0, math.log10(max(view, 1)) / math.log10(1_000_000) * 100.0)
    age_days = max(0.0, (now - (pubdate or 0)) / 86400.0)
    recency = max(0.0, min(100.0, 100.0 * (1 - age_days / 180.0)))
    score = (
        _rate_score(ir, IR_FULL) * 0.30
        + _rate_score(fr, FR_FULL) * 0.20
        + play_score * 0.20
        + _rate_score(cr, CR_FULL) * 0.15
        + recency * 0.15
    )
    return round(score, 2)


def sort_videos(rows, sort: str = "quality"):
    """rows 为 dict 或 sqlite3.Row 列表。quality_score 为 None 时按 quality 排序置底。"""

    def key(r):
        d = r if isinstance(r, dict) else dict(r)
        if sort == "view":
            return d.get("view", 0) or 0
        if sort == "pubdate":
            return d.get("pubdate", 0) or 0
        s = d.get("quality_score")
        return s if s is not None else -1

    return sorted(rows, key=key, reverse=True)
