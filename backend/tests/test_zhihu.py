import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from app import zhihu

SECRET = "test-secret"


class Response(io.BytesIO):
    code = 200


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setattr(zhihu, "load_dotenv", lambda _: None)
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", SECRET)
    monkeypatch.delenv("ZHIHU_HOT_LIMIT", raising=False)


def use_response(monkeypatch, callback):
    monkeypatch.setattr(zhihu, "build_opener", lambda _: SimpleNamespace(open=callback))


def test_official_request_and_parsing(monkeypatch):
    def open_response(request, timeout):
        assert request.full_url == zhihu.HOT_LIST_URL + "?Limit=10"
        assert request.get_header("Authorization") == "Bearer " + SECRET
        assert request.get_header("Content-type") == "application/json"
        assert request.get_header("X-request-timestamp").isdigit()
        assert timeout == 10
        return Response(json.dumps({"Code": 0, "Data": {"Total": 1, "Items": [
            {"Title": "测试标题", "Url": "https://www.zhihu.com/question/1"},
        ]}}).encode())

    use_response(monkeypatch, open_response)
    result = zhihu.fetch_hot_list()
    assert result.total == 1
    assert result.items[0].title == "测试标题"
    assert result.items[0].url == "https://www.zhihu.com/question/1"


@pytest.mark.parametrize(("status", "code", "message", "expected"), [
    (401, 20001, "invalid secret", "鉴权失败"),
    (403, 123, "permission denied", "拒绝访问"),
    (200, 123, "quota exceeded", "额度或余额"),
    (429, 30001, "rate limited", "频率限制"),
])
def test_errors_keep_diagnostics_without_secret(monkeypatch, status, code, message, expected):
    def open_response(request, timeout):
        body = json.dumps({"Code": code, "Message": f"{message} {SECRET}"}).encode()
        if status == 200:
            return Response(body)
        raise HTTPError(request.full_url, status, "error", {}, io.BytesIO(body))

    use_response(monkeypatch, open_response)
    with pytest.raises(zhihu.ZhihuError, match=expected) as error:
        zhihu.fetch_hot_list()
    assert f"HTTP {status}" in str(error.value)
    assert f"Code={code}" in str(error.value)
    assert message in str(error.value)
    assert SECRET not in str(error.value)


def test_missing_secret_stops_before_network(monkeypatch):
    monkeypatch.delenv("ZHIHU_ACCESS_SECRET")
    use_response(monkeypatch, lambda *args, **kwargs: pytest.fail("Unexpected network call"))
    with pytest.raises(zhihu.ZhihuError, match="缺少 ZHIHU_ACCESS_SECRET"):
        zhihu.fetch_hot_list()


def test_timeout(monkeypatch):
    def open_response(request, timeout):
        raise TimeoutError()

    use_response(monkeypatch, open_response)
    with pytest.raises(zhihu.ZhihuError, match="超时"):
        zhihu.fetch_hot_list()


@pytest.mark.parametrize("raw", [
    b"invalid json",
    b'{"Code":0,"Data":{"Total":1,"Items":[{"Title":"Test","Url":"javascript:alert(1)"}]}}',
    b'{"Code":0,"Data":{"Total":1,"Items":{}}}',
])
def test_malformed_response(monkeypatch, raw):
    use_response(monkeypatch, lambda request, timeout: Response(raw))
    with pytest.raises(zhihu.ZhihuError, match="返回格式错误"):
        zhihu.fetch_hot_list()
