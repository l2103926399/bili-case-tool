"""P2 缓存与搜索编排测试（使用临时数据库，mock 客户端）。"""
import asyncio
import time

import pytest

from app import config, database
from app.services import search as search_svc


class FakeClient:
    """记录调用次数的假客户端。"""

    def __init__(self, items, details=None):
        self.items = items
        self.details = details or {}
        self.search_calls = 0

    async def search_videos(self, keyword):
        self.search_calls += 1
        return list(self.items)

    async def get_video_detail(self, bvid):
        return self.details.get(bvid)

    async def close(self):
        pass


def make_search_item(bvid, view=50000, age_days=5):
    return {
        "bvid": bvid,
        "title": f"视频{bvid}",
        "author_name": "UP",
        "author_mid": "1",
        "cover_url": "https://x/a.jpg",
        "pubdate": int(time.time()) - age_days * 86400,
        "duration": 100,
        "tname": None,
        "view": view,
        "like": 100, "coin": 10, "favorite": 50,
        "reply": 20, "danmaku": 5, "share": 1,
    }


def make_detail(bvid, view=50000, like=500, coin=100, fav=200, reply=50, age_days=5):
    return {
        "bvid": bvid, "title": f"视频{bvid}", "author_name": "UP", "author_mid": "1",
        "cover_url": "https://x/a.jpg", "pubdate": int(time.time()) - age_days * 86400,
        "duration": 100, "tname": "科技",
        "view": view, "like": like, "coin": coin, "favorite": fav,
        "reply": reply, "danmaku": 10, "share": 5,
    }


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    database.init_db()
    return tmp_path


def test_first_search_hits_network(tmp_db):
    items = [make_search_item("BV1")]
    details = {"BV1": make_detail("BV1")}
    client = FakeClient(items, details)

    rows, cached = asyncio.run(search_svc.search_and_store("AI数字人", client=client))

    assert cached is False
    assert client.search_calls == 1
    assert len(rows) == 1
    assert rows[0]["data_complete"] == 1
    assert rows[0]["quality_score"] is not None


def test_second_search_uses_cache(tmp_db):
    items = [make_search_item("BV1")]
    details = {"BV1": make_detail("BV1")}
    client = FakeClient(items, details)

    rows1, cached1 = asyncio.run(search_svc.search_and_store("关键词A", client=client))
    rows2, cached2 = asyncio.run(search_svc.search_and_store("关键词A", client=client))

    assert cached1 is False
    assert cached2 is True          # 第二次命中缓存
    assert client.search_calls == 1  # 没有再次请求网络
    assert len(rows1) == len(rows2) == 1


def test_different_keyword_not_cached(tmp_db):
    items = [make_search_item("BV1")]
    details = {"BV1": make_detail("BV1")}
    client = FakeClient(items, details)

    asyncio.run(search_svc.search_and_store("关键词甲", client=client))
    asyncio.run(search_svc.search_and_store("关键词乙", client=client))

    assert client.search_calls == 2


def test_cache_expired_refetches(tmp_db, monkeypatch):
    items = [make_search_item("BV1")]
    details = {"BV1": make_detail("BV1")}
    client = FakeClient(items, details)

    asyncio.run(search_svc.search_and_store("过期测试", client=client))
    # 把缓存时间改到很久以前
    conn = database.get_conn()
    conn.execute("UPDATE search_cache SET fetched_at=?", (int(time.time()) - 999999,))
    conn.commit()
    conn.close()

    rows, cached = asyncio.run(search_svc.search_and_store("过期测试", client=client))
    assert cached is False
    assert client.search_calls == 2


def test_time_range_filters_old_videos(tmp_db):
    items = [
        make_search_item("BVnew", age_days=2),
        make_search_item("BVold", age_days=120),
    ]
    details = {"BVnew": make_detail("BVnew"), "BVold": make_detail("BVold", age_days=120)}
    client = FakeClient(items, details)

    rows, cached = asyncio.run(
        search_svc.search_and_store("时间过滤", time_range="7d", client=client)
    )
    bvids = [r["bvid"] for r in rows]
    assert "BVnew" in bvids
    assert "BVold" not in bvids
