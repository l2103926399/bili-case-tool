"""P1 抓取模块测试：mock B站接口，不依赖真实网络。

新流程：spi(取匿名cookie) → nav(取wbi keys) → view(详情，带签名)。
mock handler 需同时处理这三类 URL。
"""
import asyncio

import httpx
import pytest

from app import config
from app.bili.client import BiliClient, Bili412Error


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(config, "DETAIL_INTERVAL", 0.0)

    async def _fake_sleep(_sec):
        pass

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)


def _search_payload(items):
    return {"code": 0, "data": {"result": items, "numResults": len(items)}}


def _search_item(bvid="BV1xx411c7m9"):
    return {
        "bvid": bvid,
        "title": 'AI<em class="keyword">数字人</em>教程',
        "author": "UP甲",
        "mid": 111,
        "pubdate": "1700000000",
        "duration": "2:03",
        "pic": "//i0.hdslb.com/bfs/archive/a.jpg",
        "play": 50000,
        "like": 1234,
        "favorites": 456,
        "review": 20,
        "video_review": 20,
        "danmaku": 8,
        "typename": "科技",
    }


def _detail_payload(bvid="BV1xx411c7m9"):
    return {
        "code": 0,
        "data": {
            "bvid": bvid,
            "title": "测试视频",
            "pic": "//i0.hdslb.com/bfs/archive/test.jpg",
            "pubdate": 1700000000,
            "duration": 123,
            "tname": "科技",
            "owner": {"mid": 12345, "name": "测试UP主"},
            "stat": {
                "view": 10000, "danmaku": 10, "reply": 30,
                "favorite": 100, "coin": 50, "share": 5, "like": 200,
            },
        },
    }


def make_handler(
    search_json=None,
    detail_status=200,
    detail_json=None,
    detail_raises=None,
    search_override=None,
):
    """统一 handler：自动响应 spi/nav，按需覆盖 search/view。"""

    def handler(request):
        url = str(request.url)
        if "finger/spi" in url:
            return httpx.Response(200, json={"code": 0, "data": {"b_3": "b3", "b_4": "b4"}})
        if "web-interface/nav" in url:
            return httpx.Response(200, json={
                "code": -101,
                "data": {"wbi_img": {
                    "img_url": "https://i0.hdslb.com/bfs/wbi/" + "a" * 32 + ".png",
                    "sub_url": "https://i0.hdslb.com/bfs/wbi/" + "b" * 32 + ".png",
                }},
            })
        if "search/type" in url:
            if search_override is not None:
                return search_override(request)
            return httpx.Response(200, json=search_json or {"code": 0, "data": {"result": []}})
        if "view" in url:
            if detail_raises is not None:
                raise detail_raises
            if detail_status != 200:
                return httpx.Response(detail_status, json={})
            return httpx.Response(200, json=detail_json or _detail_payload())
        return httpx.Response(404)

    return handler


def make_client(handler):
    return BiliClient(transport=httpx.MockTransport(handler))


def test_search_normalizes_fields():
    handler = make_handler(search_json=_search_payload([_search_item()]))
    client = make_client(handler)
    try:
        items = asyncio.run(client.search_videos("AI数字人"))
    finally:
        asyncio.run(client.close())

    assert len(items) == 1
    it = items[0]
    assert it["bvid"] == "BV1xx411c7m9"
    assert it["title"] == "AI数字人教程"
    assert it["cover_url"].startswith("https://")
    assert it["view"] == 50000
    assert it["like"] == 1234
    assert it["favorite"] == 456
    assert it["reply"] == 20
    assert it["tname"] == "科技"
    assert it["duration"] == 123
    assert it["pubdate"] == 1700000000


def test_detail_maps_stat():
    handler = make_handler()
    client = make_client(handler)
    try:
        d = asyncio.run(client.get_video_detail("BV1xx411c7m9"))
    finally:
        asyncio.run(client.close())

    assert d["view"] == 10000
    assert d["like"] == 200
    assert d["coin"] == 50
    assert d["favorite"] == 100
    assert d["reply"] == 30
    assert d["author_name"] == "测试UP主"
    assert d["tname"] == "科技"
    assert d["cover_url"].startswith("https://")


def test_detail_failure_returns_none():
    handler = make_handler(detail_status=500)
    client = make_client(handler)
    try:
        d = asyncio.run(client.get_video_detail("BV1xx411c7m9"))
    finally:
        asyncio.run(client.close())
    assert d is None


def test_api_code_error_raises():
    def search_override(request):
        return httpx.Response(200, json={"code": -401, "message": "报错了"})

    handler = make_handler(search_override=search_override)
    client = make_client(handler)
    try:
        with pytest.raises(Exception):
            asyncio.run(client.search_videos("x"))
    finally:
        asyncio.run(client.close())


def test_412_raises_bili412():
    def search_override(request):
        return httpx.Response(412, text="risk control")

    handler = make_handler(search_override=search_override)
    client = make_client(handler)
    try:
        with pytest.raises(Bili412Error):
            asyncio.run(client.search_videos("x"))
    finally:
        asyncio.run(client.close())


def test_retries_on_transport_error(monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRIES", 3)
    calls = {"n": 0}

    def view_raise_once(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TransportError("boom")
        return httpx.Response(200, json=_detail_payload())

    def handler(request):
        url = str(request.url)
        if "finger/spi" in url:
            return httpx.Response(200, json={"code": 0, "data": {"b_3": "b3", "b_4": "b4"}})
        if "web-interface/nav" in url:
            return httpx.Response(200, json={"code": -101, "data": {"wbi_img": {
                "img_url": "https://x/" + "a" * 32 + ".png",
                "sub_url": "https://x/" + "b" * 32 + ".png"}}})
        if "view" in url:
            return view_raise_once(request)
        return httpx.Response(404)

    client = make_client(handler)
    try:
        d = asyncio.run(client.get_video_detail("BV1xx411c7m9"))
    finally:
        asyncio.run(client.close())

    # spi(1) + nav(1) + view 第一次失败重试(2次view) = 至少 3 次 view 尝试
    assert calls["n"] == 2
    assert d is not None
    assert d["view"] == 10000
