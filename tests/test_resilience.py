"""P5 韧性测试：412、单条详情失败降级、搜索失败友好返回。"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.bili.client import Bili412Error
from app.main import app
from app.services import search as search_svc


class PartialClient:
    """搜索成功，但指定视频详情失败的假客户端。"""

    def __init__(self, items, fail_bvid="BVfail"):
        self.items = items
        self.fail_bvid = fail_bvid
        self.search_calls = 0

    async def search_videos(self, keyword):
        self.search_calls += 1
        return list(self.items)

    async def get_video_detail(self, bvid):
        if bvid == self.fail_bvid:
            return None
        return {
            "bvid": bvid, "title": "ok", "author_name": "UP", "author_mid": "1",
            "cover_url": "", "pubdate": 1700000000, "duration": 60, "tname": "科技",
            "view": 10000, "like": 100, "coin": 10, "favorite": 50, "reply": 20,
            "danmaku": 5, "share": 1,
        }

    async def close(self):
        pass


def _search_item(bvid, view=1000):
    return {
        "bvid": bvid, "title": bvid, "author_name": "UP", "author_mid": "1",
        "cover_url": "", "pubdate": 1700000000, "duration": 60, "tname": None,
        "view": view, "like": 0, "coin": 0, "favorite": 0, "reply": 0,
        "danmaku": 0, "share": 0,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "r.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "b")
    database.init_db()
    with TestClient(app) as c:
        yield c


def test_detail_failure_marks_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "r.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DETAIL_INTERVAL", 0.0)
    monkeypatch.setattr(config, "ENRICH_DETAIL", True)
    database.init_db()

    items = [_search_item("BVok"), _search_item("BVfail")]
    fc = PartialClient(items)
    rows, cached = asyncio.run(search_svc.search_and_store("降级测试", client=fc))

    assert cached is False
    by = {r["bvid"]: r for r in rows}
    assert "BVok" in by
    assert "BVfail" in by                       # 单条失败不中断整体
    assert by["BVok"]["data_complete"] == 1
    assert by["BVfail"]["data_complete"] == 0  # 详情失败标记不全


def test_412_returns_friendly_error(client, monkeypatch):
    async def boom(*a, **kw):
        raise Bili412Error("412 risk control")

    monkeypatch.setattr(search_svc, "search_and_store", boom)
    r = client.post("/api/search", json={"keyword": "AI"})
    body = r.json()
    assert body["ok"] is False
    assert "抓取失败" in body["error"]


def test_network_down_returns_friendly_error(client, monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(search_svc, "search_and_store", boom)
    body = client.post("/api/search", json={"keyword": "AI"}).json()
    assert body["ok"] is False
    assert "抓取失败" in body["error"]
