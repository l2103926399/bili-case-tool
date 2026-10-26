"""质量分计算与排序。

质量分 = 互动率×35% + 收藏率×25% + 播放量分×25% + 时效因子×15%
比率按经验基准归一化到 0-100；数据来自 B站 搜索结果，不依赖详情接口
（详情接口对机房 IP 有风控）。投币数搜索接口不提供，不计入。
"""
import math
import time

IR_FULL = 0.10   # 互动率满分基准：10%
FR_FULL = 0.05   # 收藏率满分基准：5%

W_INTERACTION = 0.35
W_FAVORITE = 0.25
W_PLAY = 0.25
W_RECENCY = 0.15


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
    play_score = min(100.0, math.log10(max(view, 1)) / math.log10(1_000_000) * 100.0)
    age_days = max(0.0, (now - (pubdate or 0)) / 86400.0)
    recency = max(0.0, min(100.0, 100.0 * (1 - age_days / 180.0)))
    score = (
        _rate_score(ir, IR_FULL) * W_INTERACTION
        + _rate_score(fr, FR_FULL) * W_FAVORITE
        + play_score * W_PLAY
        + recency * W_RECENCY
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
