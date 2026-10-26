"""P3 后端 API 测试（临时数据库，mock 搜索编排）。"""
import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.main import app
from app.routes import api as api_mod
from app.services import search as search_svc


def insert_video(bvid="BVtest1"):
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO videos (bvid,title,author_name,author_mid,cover_url,pubdate,duration,tname,"
        "view,like,coin,favorite,reply,danmaku,share,quality_score,data_complete,fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (bvid, "测试视频", "UP", "1", "https://x/a.jpg", 1700000000, 100, "科技",
         10000, 500, 100, 200, 30, 10, 5, 75.0, 1, 1700000000),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    database.init_db()
    with TestClient(app) as c:
        yield c


def test_pages_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/favorites").status_code == 200
    assert client.get("/video/BVnotexist").status_code == 200


def test_search_api(client, monkeypatch):
    async def fake_search(keyword, time_range="all", sort="quality", client=None):
        return [{
            "bvid": "BVx", "title": "视频", "author_name": "UP", "cover_url": "https://x/c.jpg",
            "pubdate": 1700000000, "duration": 60, "tname": "科技",
            "view": 50000, "like": 100, "coin": 10, "favorite": 50, "reply": 20,
            "danmaku": 5, "share": 1, "quality_score": 80.0, "data_complete": 1,
            "fetched_at": 1700000000,
        }], True

    monkeypatch.setattr(search_svc, "search_and_store", fake_search)
    r = client.post("/api/search", json={"keyword": "AI", "time_range": "30d", "sort": "quality"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["total"] == 1
    assert body["cached"] is True
    assert body["items"][0]["bvid"] == "BVx"
    assert body["items"][0]["bili_url"].startswith("https://www.bilibili.com/video/")


def test_detail_not_found(client):
    assert client.get("/api/video/BVnope").json()["ok"] is False


def test_search_error_handled(client, monkeypatch):
    async def boom(keyword, time_range="all", sort="quality", client=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(search_svc, "search_and_store", boom)
    r = client.post("/api/search", json={"keyword": "AI"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "抓取失败" in body["error"]


def test_rate_limit_blocks_burst(client):
    """空关键词也会计入频控，连续请求超过阈值应返回 429。"""
    api_mod._ip_hits.clear()
    try:
        codes = []
        for _ in range(config.RATE_LIMIT_PER_MINUTE + 1):
            codes.append(client.post("/api/search", json={"keyword": ""}).status_code)
        assert codes[-1] == 429
        assert 429 not in codes[:-1]
    finally:
        api_mod._ip_hits.clear()
