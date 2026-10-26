"""P4 前端测试：静态资源可达、首页关键控件、详情页跳转按钮。"""
import pytest
from fastapi.testclient import TestClient

from app import config, database
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "fe.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    database.init_db()
    with TestClient(app) as c:
        yield c


def test_static_assets_served(client):
    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert len(css.text) > 100
    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "doSearch" in js.text


def test_index_contains_search_controls(client):
    html = client.get("/").text
    assert 'id="keyword"' in html
    assert 'id="btn-search"' in html
    assert 'id="time_range"' in html
    assert 'id="sort"' in html
    assert "数据仅供个人分析参考" in html


def test_video_page_has_bilibili_link(client):
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO videos (bvid,title,author_name,author_mid,cover_url,pubdate,duration,tname,"
        "view,like,coin,favorite,reply,danmaku,share,quality_score,data_complete,fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("BVfe1", "前端测试", "UP", "1", "", 1700000000, 60, "科技",
         1000, 10, 1, 5, 2, 0, 0, 70.0, 1, 1700000000),
    )
    conn.commit()
    conn.close()

    html = client.get("/video/BVfe1").text
    assert "去B站观看" in html
    assert "https://www.bilibili.com/video/BVfe1" in html
    assert 'id="btn-fav"' in html
    assert 'id="note"' in html
