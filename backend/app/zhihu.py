"""Client for the official Zhihu hot-list API."""

from collections.abc import Mapping
from dataclasses import dataclass
import http.client
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dotenv import load_dotenv

from .config import BACKEND

HOT_LIST_URL = "https://developer.zhihu.com/api/v1/content/hot_list"


class ZhihuError(Exception):
    """An upstream error safe to show in the command-line verification output."""


@dataclass(frozen=True)
class ZhihuItem:
    title: str
    url: str
    thumbnail_url: str | None
    summary: str | None


@dataclass(frozen=True)
class ZhihuHotList:
    total: int
    items: tuple[ZhihuItem, ...]


class NoRedirects(HTTPRedirectHandler):
    # Keep the authorization header on the configured endpoint.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _error(status: int, payload: object, secret: str) -> ZhihuError:
    body = payload if isinstance(payload, Mapping) else {}
    code = body.get("Code")
    message = body.get("Message")
    safe_message = ""
    if isinstance(message, str):
        safe_message = " ".join(message.replace(secret, "[已隐藏]").split())[:240]
        safe_message = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", safe_message)

    if status == 401 or code == 20001:
        reason = "知乎鉴权失败，请检查 Access Secret 和系统时间"
    elif status == 402 or re.search(r"额度|余额|quota|insufficient balance", safe_message, re.I):
        reason = "知乎额度或余额异常，请检查用量统计"
    elif status == 429 or code == 30001:
        reason = "知乎请求超过频率限制，请稍后重试"
    elif status == 403:
        reason = "知乎拒绝访问，请检查热榜 API 权限"
    else:
        reason = "知乎热榜接口返回错误"
    details = [f"HTTP {status}"]
    if type(code) is int:
        details.append(f"Code={code}")
    if safe_message:
        details.append(safe_message)
    return ZhihuError(f"{reason}（{'，'.join(details)}）".replace(secret, "[已隐藏]"))


def _parse_hot_list(payload: object) -> ZhihuHotList:
    try:
        if not isinstance(payload, dict) or type(payload.get("Code")) is not int:
            raise ValueError
        data = payload["Data"]
        total, items = data["Total"], data["Items"]
        if type(total) is not int or total < 0 or not isinstance(items, list):
            raise ValueError
        parsed = []
        for item in items:
            title, url = item["Title"], item["Url"]
            thumbnail, summary = item.get("ThumbnailUrl"), item.get("Summary")
            if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
                raise ValueError
            link = urlsplit(url)
            if (link.scheme not in {"https", "http"} or not link.hostname or link.username is not None
                    or any(character.isspace() or ord(character) < 32 for character in url)):
                raise ValueError
            if any(value is not None and not isinstance(value, str) for value in (thumbnail, summary)):
                raise ValueError
            parsed.append(ZhihuItem(title.strip(), url, thumbnail, summary))
        return ZhihuHotList(total, tuple(parsed))
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ZhihuError("知乎热榜返回格式错误，请核对 Code、Data.Total 和 Data.Items 字段") from None


def fetch_hot_list() -> ZhihuHotList:
    load_dotenv(BACKEND.parent / ".env")
    secret = os.environ.get("ZHIHU_ACCESS_SECRET", "").strip()
    if not secret:
        raise ZhihuError("缺少 ZHIHU_ACCESS_SECRET，请在项目根目录 .env 或后端进程环境中配置")
    if any(not 33 <= ord(character) <= 126 for character in secret):
        raise ZhihuError("ZHIHU_ACCESS_SECRET 格式无效，请重新复制 Access Secret")
    try:
        limit = int(os.environ.get("ZHIHU_HOT_LIMIT", "10"))
        if limit < 1:
            raise ValueError
    except ValueError:
        raise ZhihuError("ZHIHU_HOT_LIMIT 必须为正整数") from None

    request = Request(
        f"{HOT_LIST_URL}?{urlencode({'Limit': limit})}",
        headers={
            "Authorization": f"Bearer {secret}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        },
    )
    try:
        try:
            response = build_opener(NoRedirects()).open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            status = response.code
            raw = response.read()
    except TimeoutError:
        raise ZhihuError("请求知乎热榜超时") from None
    except URLError as error:
        message = "请求知乎热榜超时" if isinstance(error.reason, TimeoutError) else "无法连接知乎热榜接口"
        raise ZhihuError(message) from None
    except (OSError, http.client.HTTPException):
        raise ZhihuError("与知乎热榜接口的连接中断") from None

    try:
        payload = json.loads(raw)
    except (UnicodeError, ValueError):
        if not 200 <= status < 300:
            raise _error(status, None, secret) from None
        raise ZhihuError("知乎热榜返回格式错误，响应不是有效 JSON") from None
    if not 200 <= status < 300 or (
        isinstance(payload, dict) and type(payload.get("Code")) is int and payload["Code"] != 0
    ):
        raise _error(status, payload, secret)
    return _parse_hot_list(payload)
