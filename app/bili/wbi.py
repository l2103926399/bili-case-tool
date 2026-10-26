"""WBI 签名工具（预留）。

当前 B站搜索/详情接口无需签名；若后续请求返回 412 风控，可在此基础上启用。
算法参考 bilibili-API-collect 公开整理：img_key + sub_key 按混淆表重排取前 32 位。
"""
import hashlib
import time
from urllib.parse import urlencode

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def sign(params: dict, img_key: str, sub_key: str) -> dict:
    """对请求参数附加 wts 与 w_rid，返回新参数字典。"""
    mixin_key = get_mixin_key(img_key + sub_key)
    signed = dict(params)
    signed["wts"] = int(time.time())
    signed = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in signed.items()
    }
    signed = dict(sorted(signed.items()))
    query = urlencode(signed)
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return signed
