"""P0 冒烟测试：建表与健康检查。"""
from fastapi.testclient import TestClient

from app import config, database
from app.main import app


def test_init_db_creates_tables():
    database.init_db()
    assert config.DB_PATH.exists()
    conn = database.get_conn()
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert {"videos", "favorites", "video_notes", "search_cache"} <= tables


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["db_exists"] is True
