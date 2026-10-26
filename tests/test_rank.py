"""P2 排序单元测试。"""
import time

from app.services import rank

NOW = int(time.time())


def _score(view=100000, like=5000, coin=1000, fav=2000, reply=800, age_days=10):
    pubdate = NOW - age_days * 86400
    return rank.compute_quality_score(view, like, coin, fav, reply, pubdate, now=NOW)


def test_score_in_range():
    s = _score()
    assert 0 <= s <= 100


def test_score_none_when_zero_view():
    assert rank.compute_quality_score(0, 1, 1, 1, 1, NOW) is None
    assert rank.compute_quality_score(None, 1, 1, 1, 1, NOW) is None


def test_newer_scores_higher():
    new = _score(age_days=2)
    old = _score(age_days=150)
    assert new > old


def test_quality_sorted_desc_and_none_last():
    rows = [
        {"bvid": "A", "quality_score": 60.0, "view": 100},
        {"bvid": "B", "quality_score": None, "view": 1},
        {"bvid": "C", "quality_score": 90.0, "view": 100},
    ]
    out = rank.sort_videos(rows, "quality")
    assert [r["bvid"] for r in out] == ["C", "A", "B"]


def test_sort_view():
    rows = [
        {"bvid": "A", "view": 100},
        {"bvid": "B", "view": 9000},
        {"bvid": "C", "view": 500},
    ]
    out = rank.sort_videos(rows, "view")
    assert [r["bvid"] for r in out] == ["B", "C", "A"]


def test_sort_pubdate():
    rows = [
        {"bvid": "A", "pubdate": 1000},
        {"bvid": "B", "pubdate": 3000},
        {"bvid": "C", "pubdate": 2000},
    ]
    out = rank.sort_videos(rows, "pubdate")
    assert [r["bvid"] for r in out] == ["B", "C", "A"]
