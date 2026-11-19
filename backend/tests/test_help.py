from contextlib import ExitStack
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import connect, initialize
from app.main import create_app

LOCATION = {"lat": 22.338, "lon": 114.172, "accuracy": 25}
REQUEST = {
    "title": "借一个充电器半小时",
    "content": "在校园公共区域交接。",
    "minutes": 30,
    "location": LOCATION,
}


def test_free_help_end_to_end_guest_permissions_and_archive(tmp_path, signup):
    path = tmp_path / "help.sqlite3"
    initialize(path)
    with connect(path) as db:
        old_id = db.execute(
            "INSERT INTO topics (community_slug,guest_id,nickname,title,content) VALUES (?,?,?,?,?)",
            ("cityu-hackathon", str(uuid4()), "旧访客", "历史讨论", "以前的内容"),
        ).lastrowid

    with ExitStack() as stack:
        owner, helper, stranger, guest = [stack.enter_context(TestClient(create_app(path))) for _ in range(4)]
        owner_profile = signup(owner, "owner", "发布者")
        helper_profile = signup(helper, "helper", "帮忙者")
        stranger_profile = signup(stranger, "stranger", "第三人")
        assert guest.get("/api/auth/me").json() is None
        assert guest.get(f"/api/communities/cityu-hackathon/topics/{old_id}").json()["title"] == "历史讨论"
        assert guest.post("/api/communities/cityu-hackathon/topics", json={
            "guest_id": str(uuid4()), "nickname": "冒名", "title": "主题", "content": "正文",
        }).status_code == 401
        assert guest.post("/api/help/requests", json=REQUEST).status_code == 401
        assert owner.post("/api/help/requests", json={**REQUEST, "location": None}).status_code == 422
        assert owner.post("/api/help/requests", json={**REQUEST, "location": {
            **LOCATION, "accuracy": 900,
        }}).status_code == 422
        creation = owner.post("/api/help/requests", json=REQUEST)
        assert creation.status_code == 201
        item = creation.json()
        assert item["author_id"] == owner_profile["id"]
        assert item["status"] == "open"
        assert not {"lat", "lon", "location"} & item.keys()
        item_id = item["id"]
        detail = f"/api/help/requests/{item_id}"
        chat = f"/api/help/chats/{item_id}"
        assert guest.post("/api/visitor/session").status_code == 204
        feed = guest.post("/api/help/nearby", json={**LOCATION, "radius": 500}).json()
        [card] = feed["requests"]
        assert card["id"] == item_id and card["distance_m"] == 100
        assert "lat" not in card
        assert guest.post("/api/help/nearby", json={"lat": 0, "lon": 0}).json()["requests"] == []
        assert guest.post(detail + "/replies", json={"content": "访客回复"}).status_code == 401
        assert guest.post(detail + "/offers").status_code == 401
        assert guest.get(f"/api/communities/neartalk-help/topics/{item_id}").status_code == 404
        for _ in range(2):
            assert helper.post(detail + "/offers").status_code == 204
        assert helper.post(detail + "/replies", json={"content": "我有充电器"}).status_code == 201
        assert guest.get(detail).json()["response_count"] == 1
        assert guest.get(detail).json()["offers"] == []
        assert helper.get(chat).status_code == 404
        assert owner.get("/api/help/inbox").json()["pending"][0]["offers"] == 1
        assert stranger.post(detail + "/offers").status_code == 204
        helper_offer = detail + "/offers/" + helper_profile["id"]
        assert stranger.post(helper_offer, json={"decision": "accepted"}).status_code == 403
        assert owner.post(helper_offer, json={"decision": "accepted"}).status_code == 204
        assert owner.post(detail + "/offers/" + stranger_profile["id"], json={
            "decision": "accepted",
        }).status_code == 409
        assert stranger.get(chat).status_code == 404
        assert guest.get(chat).status_code == 401
        assert helper.get(detail).json()["chat_id"] == item_id
        assert guest.get(detail).json()["chat_id"] is None
        assert guest.post("/api/help/nearby", json=LOCATION).json()["requests"] == []
        assert owner.post(chat + "/messages", json={"content": "在图书馆门口见。"}).status_code == 201
        assert helper.get("/api/help/inbox").json()["chats"][0]["unread"] == 1
        [message] = helper.get(chat).json()["messages"]
        assert message["content"] == "在图书馆门口见。" and not message["mine"]
        assert helper.post(chat + f"/read/{message['id']}").status_code == 204
        assert helper.get("/api/help/inbox").json()["chats"][0]["unread"] == 0
        assert helper.post(detail + "/state", json={"status": "resolved"}).status_code == 403
        assert owner.post(detail + "/state", json={"status": "resolved"}).status_code == 204
        assert guest.get(detail).json()["status"] == "resolved"
        assert helper.get(chat).json()["messages"] == [message]
        report = detail + "/reports/" + owner_profile["id"]
        assert helper.post(report, json={"reason": "本地举报验收"}).status_code == 204
        block = "/api/help/blocks/" + owner_profile["id"]
        assert helper.post(block, json={"blocked": True}).status_code == 204
        assert owner.post(chat + "/messages", json={"content": "被屏蔽内容"}).status_code == 404
        assert not helper.get("/api/help/inbox").json()["chats"]
        assert helper.post(block, json={"blocked": False}).status_code == 204
        assert helper.get(chat).json()["messages"] == [message]


def test_account_sessions_location_privacy_and_expiry(tmp_path, signup):
    path = tmp_path / "privacy.sqlite3"
    with ExitStack() as stack:
        clients = [stack.enter_context(TestClient(create_app(path))) for _ in range(5)]
        guest, first, second, third, same_user = clients
        assert guest.post("/api/visitor/session").status_code == 204
        assert guest.post("/api/help/presence", json=LOCATION).status_code == 401
        for index, account in enumerate([first, second, third]):
            signup(account, f"user_{index}", f"参与者 {index}")
            assert account.post("/api/help/presence", json=LOCATION).status_code == 403
            assert account.post("/api/help/preferences", json={
                "share_presence": True, "discoverable": index > 0,
            }).status_code == 200
            assert account.post("/api/help/presence", json=LOCATION).status_code == 204
        for _ in range(2):
            response = same_user.post("/api/auth/login", json={
                "username": "user_0", "password": "fixture-password-1234",
            })
            assert response.status_code == 200
            assert "HttpOnly" in response.headers["set-cookie"]
            assert same_user.post("/api/help/presence", json=LOCATION).status_code == 204
        assert guest.post("/api/help/nearby", json=LOCATION).json() == {
            "requests": [], "active_band": "3–4", "users": [],
        }
        assert first.post("/api/help/nearby", json=LOCATION).json()["users"] == []
        assert same_user.post("/api/auth/logout", headers={"origin": "https://other.example"}).status_code == 403
        assert same_user.post("/api/auth/logout").status_code == 204
        assert same_user.get("/api/auth/me").json() is None
        assert first.get("/api/auth/me").json()["username"] == "user_0"
        assert third.post("/api/help/preferences", json={
            "share_presence": False, "discoverable": False,
        }).status_code == 200
        assert guest.post("/api/help/nearby", json=LOCATION).json()["active_band"] == "hidden"
        item = first.post("/api/help/requests", json=REQUEST).json()
        with connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM help_presence").fetchone()[0] == 2
            db.execute("UPDATE help_presence SET seen_at=0")
            db.execute("UPDATE help_requests SET expires_at=0 WHERE topic_id=?", (item["id"],))
        detail = f"/api/help/requests/{item['id']}"
        assert guest.get(detail).json()["status"] == "expired"
        assert second.post(detail + "/offers").status_code == 409
        assert guest.post("/api/help/nearby", json=LOCATION).json()["requests"] == []
