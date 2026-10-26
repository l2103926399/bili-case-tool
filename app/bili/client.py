"""B站接口客户端：搜索 + 详情，含频控、超时、失败重试。"""
import asyncio
import logging
import time

import httpx

from .. import config
from . import wbi

logger = logging.getLogger(__name__)


class BiliRequestError(Exception):
    """接口业务错误（code != 0 或重试耗尽）。"""


class Bili412Error(BiliRequestError):
    """风控拦截（HTTP 412）。"""


class BiliClient:
    def __init__(self, transport=None):
        self._client = httpx.AsyncClient(
            timeout=config.REQUEST_TIMEOUT,
            headers={
                "User-Agent": config.USER_AGENT,
                "Referer": config.REFERER,
            },
            transport=transport,
        )
        self._last_detail_ts = 0.0
        self._detail_lock = None
        self._wbi_keys = None
        self._cookies_ready = False

    async def _ensure_cookies(self):
        """获取匿名 buvid3/buvid4 cookie，使未登录可访问 view 接口。"""
        if self._cookies_ready:
            return
        try:
            r = await self._client.get("https://api.bilibili.com/x/frontend/finger/spi")
            data = (r.json() or {}).get("data", {}) or {}
            b3, b4 = data.get("b_3"), data.get("b_4")
            if b3:
                self._client.cookies.set("buvid3", b3, domain=".bilibili.com")
            if b4:
                self._client.cookies.set("buvid4", b4, domain=".bilibili.com")
        except Exception as exc:
            logger.warning("获取匿名 cookie 失败: %s", exc)
        self._cookies_ready = True

    async def close(self):
        await self._client.aclose()

    # ---------- 底层请求 ----------

    async def _request(self, url: str, params: dict):
        """统一请求：412 与业务错误不重试；网络错误退避重试。"""
        await self._ensure_cookies()
        last_exc = None
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = await self._client.get(url, params=params)
                if resp.status_code == 412:
                    raise Bili412Error(f"风控拦截(412): {url}")
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("code") != 0:
                    raise BiliRequestError(
                        f"接口错误 code={payload.get('code')}: {payload.get('message')}"
                    )
                return payload["data"]
            except Bili412Error:
                raise
            except BiliRequestError:
                raise
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "请求失败 %s（第 %d 次），%ds 后重试: %s",
                    url, attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)
        raise BiliRequestError(f"请求失败（重试 {config.MAX_RETRIES} 次）: {last_exc}")

    async def _rate_limit_detail(self):
        """串行安排详情请求的起点，保证相邻两次请求至少间隔 DETAIL_INTERVAL。

        并发抓取时多个协程会同时进入；用锁保证它们按间隔排队，避免瞬时冲击 B站。
        """
        if self._detail_lock is None:
            self._detail_lock = asyncio.Lock()
        async with self._detail_lock:
            elapsed = time.monotonic() - self._last_detail_ts
            wait = config.DETAIL_INTERVAL - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_detail_ts = time.monotonic()

    # ---------- 业务接口 ----------

    async def search_videos(self, keyword: str, page: int = 1, page_size: int = None,
                            limit: int = None):
        data = await self._request(
            config.BILI_SEARCH_URL,
            {
                "search_type": "video",
                "keyword": keyword,
                "page": page,
                "page_size": page_size or config.SEARCH_MAX_RESULTS,
            },
        )
        result = data.get("result") or []
        items = []
        for r in result:
            if not r.get("bvid"):
                continue
            items.append(self._normalize_search_item(r))
            if limit and len(items) >= limit:
                break
        return items

    async def _get_wbi_keys(self):
        """从 nav 接口取 wbi_img 的 img/sub key（带缓存）。
        注意：未登录时 nav 返回 code=-101，但 wbi_img 仍有效，故不做 code 校验。"""
        if self._wbi_keys:
            return self._wbi_keys
        await self._ensure_cookies()
        r = await self._client.get(config.BILI_NAV_URL)
        data = (r.json() or {}).get("data", {}) or {}
        wbi = data.get("wbi_img") or {}
        img_url = wbi.get("img_url", "")
        sub_url = wbi.get("sub_url", "")
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
        if not img_key or not sub_key:
            raise BiliRequestError("无法获取 wbi keys")
        self._wbi_keys = (img_key, sub_key)
        return self._wbi_keys

    async def get_video_detail(self, bvid: str):
        """返回详情字典；单条不可用返回 None。

        主链路是 view 接口（需匿名 cookie + WBI 签名）；机房 IP 常被 412 风控，
        这时降级到 archive/stat（只含互动数据，标题等沿用搜索结果）。
        """
        await self._rate_limit_detail()
        try:
            img_key, sub_key = await self._get_wbi_keys()
            signed = wbi.sign({"bvid": bvid}, img_key, sub_key)
            data = await self._request(config.BILI_VIEW_URL, signed)
            return self._map_view(data, bvid)
        except (Bili412Error, BiliRequestError) as exc:
            logger.warning("view 接口不可用，改走 archive/stat: %s (%s)", bvid, exc)

        try:
            stat = await self._request(config.BILI_STAT_URL, {"bvid": bvid})
            return self._map_stat(stat, bvid)
        except Exception as exc:
            logger.warning("archive/stat 也不可用: %s (%s)", bvid, exc)
            return None

    @staticmethod
    def _map_view(data: dict, bvid: str) -> dict:
        st = data.get("stat", {})
        owner = data.get("owner", {})
        pic = BiliClient._normalize_pic(data.get("pic", ""))
        return {
            "bvid": data.get("bvid", bvid),
            "title": data.get("title"),
            "author_name": owner.get("name"),
            "author_mid": str(owner.get("mid", "")),
            "cover_url": pic,
            "pubdate": int(data.get("pubdate", 0) or 0),
            "duration": int(data.get("duration", 0) or 0),
            "tname": data.get("tname"),
            "view": int(st.get("view", 0) or 0),
            "like": int(st.get("like", 0) or 0),
            "coin": int(st.get("coin", 0) or 0),
            "favorite": int(st.get("favorite", 0) or 0),
            "reply": int(st.get("reply", 0) or 0),
            "danmaku": int(st.get("danmaku", 0) or 0),
            "share": int(st.get("share", 0) or 0),
        }

    @staticmethod
    def _map_stat(data: dict, bvid: str) -> dict:
        """archive/stat 只返回互动数据，其余字段由搜索结果补齐。"""
        return {
            "bvid": data.get("bvid", bvid),
            "view": int(data.get("view", 0) or 0),
            "like": int(data.get("like", 0) or 0),
            "coin": int(data.get("coin", 0) or 0),
            "favorite": int(data.get("favorite", 0) or 0),
            "reply": int(data.get("reply", 0) or 0),
            "danmaku": int(data.get("danmaku", 0) or 0),
            "share": int(data.get("share", 0) or 0),
        }

    # ---------- 字段归一化 ----------

    @staticmethod
    def _normalize_pic(pic: str) -> str:
        if pic.startswith("//"):
            return "https:" + pic
        return pic

    @staticmethod
    def _strip_em(text: str) -> str:
        return (text or "").replace('<em class="keyword">', "").replace("</em>", "")

    @staticmethod
    def _parse_duration(d) -> int:
        try:
            parts = [int(x) for x in str(d).split(":")]
        except (ValueError, AttributeError):
            return 0
        sec = 0
        for p in parts:
            sec = sec * 60 + p
        return sec

    def _normalize_search_item(self, r: dict) -> dict:
        return {
            "bvid": r["bvid"],
            "title": self._strip_em(r.get("title")),
            "author_name": r.get("author"),
            "author_mid": str(r.get("mid", "") or ""),
            "cover_url": self._normalize_pic(r.get("pic", "")),
            "pubdate": int(r.get("pubdate", 0) or 0),
            "duration": self._parse_duration(r.get("duration", 0)),
            "tname": r.get("typename") or None,
            "view": int(r.get("play", 0) or 0),
            "like": int(r.get("like", 0) or 0),
            "coin": 0,
            "favorite": int(r.get("favorites", 0) or 0),
            "reply": int(r.get("review", 0) or 0),
            "danmaku": int(r.get("danmaku", 0) or 0),
            "share": 0,
        }
