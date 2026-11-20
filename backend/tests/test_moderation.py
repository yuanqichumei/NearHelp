from contextlib import ExitStack
import secrets
import time

from fastapi.testclient import TestClient
import pytest

from app.create_admin import create_admin
from app.db import connect, initialize
from app.main import create_app
from app.moderation import PIN_SECONDS


@pytest.fixture
def clients(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("NEARHELP_DEMO_GUESTS", "true")
    app = create_app(path)
    with ExitStack() as stack:
        owner, helper, admin = [stack.enter_context(TestClient(app, base_url="https://local.test")) for _ in range(3)]
        password = secrets.token_urlsafe(20)
        create_admin(path, "moderator", password)
        for phone in [owner, helper, admin]:
            assert phone.post("/api/auth/session").json()["is_admin"] is False
        signed = admin.post("/api/auth/login", json={"username": "moderator", "password": password})
        assert signed.json()["is_admin"] and not signed.json()["is_demo"]
        yield path, owner, helper, admin


def publish(owner, title, longitude=0):
    response = owner.post("/api/help/requests", json={
        "title": title, "content": "测试正文", "location": {"lat": 0, "lon": longitude, "accuracy": 25},
        "minutes": 1440,
    })
    assert response.status_code == 201
    return response.json()["id"]


def moderate(admin, rid, action, **kwargs):
    return admin.post(f"/api/admin/requests/{rid}", json={"action": action}, **kwargs)


def nearby(phone):
    return phone.post("/api/help/nearby", json={"lat": 0, "lon": 0, "radius": 500}).json()["requests"]


def test_reversible_moderation_limited_to_public_requests(clients):
    path, owner, helper, admin = clients
    rid = publish(owner, "公开求助")
    detail = f"/api/help/requests/{rid}"
    chat = f"/api/help/chats/{rid}"
    helper_id = helper.get("/api/auth/me").json()["id"]
    assert helper.post(detail + "/replies", json={"content": "公开留言"}).status_code == 201
    assert helper.post(detail + "/offers").status_code == 204
    assert owner.get("/api/help/inbox").json()["pending"]
    assert helper.post(detail + "/reports/" + owner.get("/api/auth/me").json()["id"], json={"reason": "测试"}).status_code == 204
    assert moderate(admin, rid, "hide").status_code == 204
    assert moderate(admin, rid, "hide").status_code == 204
    assert nearby(owner) == [] and helper.get(detail).status_code == 404
    assert not helper.get("/api/help/mine").json()
    assert not owner.get("/api/help/inbox").json()["pending"]
    assert helper.post(detail + "/replies", json={"content": "被隐藏"}).status_code == 404
    assert owner.post(detail + "/offers/" + helper_id, json={"decision": "accepted"}).status_code == 404
    assert moderate(admin, rid, "pin").status_code == 409
    assert not admin.get("/api/admin/requests?visibility=visible").json()["items"]
    hidden, = admin.get("/api/admin/requests?visibility=hidden").json()["items"]
    assert hidden["is_hidden"] and hidden["report_count"] == 1
    assert moderate(admin, rid, "restore").status_code == 204
    assert helper.get(detail).json()["replies"][0]["content"] == "公开留言"
    assert owner.post(detail + "/offers/" + helper_id, json={"decision": "accepted"}).status_code == 204
    assert helper.post(chat + "/messages", json={"content": "仅双方可见"}).status_code == 201
    assert moderate(admin, rid, "hide").status_code == 204
    assert owner.get(chat).json()["messages"][0]["content"] == "仅双方可见"
    assert admin.get(chat).status_code == 404
    record, = admin.get("/api/admin/requests").json()["items"]
    assert set(record) == {"id","title","content","nickname","status","created_at","expires_at","is_pinned","pinned_until","is_hidden","report_count"}
    initialize(path)
    assert admin.get("/api/admin/requests").json()["items"][0]["is_hidden"]


def test_pin_preserves_radius_expiry_and_order(clients):
    path, owner, helper, admin = clients
    first = publish(owner, "较远", 0.002)
    second = publish(owner, "较近")
    outside = publish(owner, "范围以外", 0.04)
    assert [item["id"] for item in nearby(helper)] == [second, first]
    for rid in (outside, first):
        assert moderate(admin, rid, "pin").status_code == 204
    assert [(item["id"], item["is_pinned"]) for item in nearby(helper)] == [(first, True), (second, False)]
    row = next(item for item in admin.get("/api/admin/requests").json()["items"] if item["id"] == first)
    assert time.time() + PIN_SECONDS - 30 <= row["pinned_until"] <= time.time() + PIN_SECONDS
    assert moderate(admin, first, "hide").status_code == moderate(admin, first, "restore").status_code == 204
    assert not helper.get(f"/api/help/requests/{first}").json()["is_pinned"]
    assert moderate(admin, first, "pin").status_code == moderate(admin, first, "unpin").status_code == 204
    assert [item["id"] for item in nearby(helper)] == [second, first]
    assert moderate(admin, first, "pin").status_code == 204
    with connect(path) as db:
        db.execute("UPDATE help_requests SET pinned_until=0 WHERE topic_id=?", (first,))
        db.execute("UPDATE help_requests SET expires_at=0 WHERE topic_id=?", (outside,))
    assert not any(item["is_pinned"] for item in nearby(helper))
    assert moderate(admin, outside, "pin").status_code == 409
    assert moderate(admin, second, "pin").status_code == 204
    assert owner.post(f"/api/help/requests/{second}/state", json={"status":"resolved"}).status_code == 204
    assert not helper.get(f"/api/help/requests/{second}").json()["is_pinned"]
    assert moderate(admin, second, "pin").status_code == 409
    assert [item["id"] for item in admin.get(f"/api/admin/requests?before={second}").json()["items"]] == [first]


def test_credentials_and_permission_boundary(clients):
    path, owner, helper, admin = clients
    password = secrets.token_urlsafe(20)
    rid = publish(owner, "权限测试")
    assert moderate(admin, rid, "hide", headers={"Origin": "https://other.test"}).status_code == 403
    assert helper.get("/api/admin/requests").status_code == moderate(owner, rid, "hide").status_code == 403
    signed = helper.post("/api/auth/register", json={"username": "public", "nickname": "普通用户",
                        "password": password, "is_admin": True})
    assert signed.status_code == 201 and not signed.json()["is_admin"]
    assert moderate(helper, rid, "pin").status_code == 403
    with pytest.raises(ValueError, match="已被使用"):
        create_admin(path, "public", password)
    assert not helper.get("/api/auth/me").json()["is_admin"]
    assert admin.post("/api/auth/logout").status_code == 204
    assert moderate(admin, rid, "hide").status_code == 403
    admin.cookies.clear()
    assert admin.get("/api/admin/requests").status_code == 401
    assert moderate(admin, rid, "hide").status_code == 401
