from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.clean_demo import clean_request
from app.db import connect, initialize
from app.main import create_app


@pytest.fixture
def demo(tmp_path, monkeypatch):
    path = tmp_path / "demo.sqlite3"
    monkeypatch.setenv("NEARHELP_DEMO_GUESTS", "true")
    app = create_app(path)
    with ExitStack() as stack:
        phones = [stack.enter_context(TestClient(app, base_url="https://local.test")) for _ in range(3)]
        yield path, phones


def start(phone):
    return phone.post("/api/auth/session", json={})


def demand(cents=0):
    # Synthetic position generated for the test, never sent to a live service.
    return {"title": "借一个 Type-C 充电器半小时", "content": "希望附近有人可以借我使用。",
            "minutes": 60, "reward_cents": cents, "location": {"lat": 0, "lon": 0, "accuracy": 20}}


@pytest.mark.parametrize("cents", [0, 500])
def test_guest_flow_privacy_and_cleanup(demo, cents):
    path, (a, b, c) = demo
    owner, helper, other = [start(phone).json() for phone in (a, b, c)]
    assert len({owner["id"], helper["id"], other["id"]}) == 3
    assert all(person["is_demo"] for person in (owner, helper, other))
    assert all(person["share_presence"] and person["discoverable"] for person in (owner, helper, other))
    assert a.get("/api/auth/me").json() == start(a).json() == owner
    assert b.post("/api/auth/session", headers={"Origin": "https://elsewhere.test"}).status_code == 403
    created = a.post("/api/help/requests", json={**demand(cents), "author_id": other["id"]})
    assert created.status_code == 201 and created.json()["author_id"] == owner["id"]
    rid = created.json()["id"]
    url, chat = f"/api/help/requests/{rid}", f"/api/help/chats/{rid}"
    verdict = url + "/offers/" + helper["id"]
    location = demand()["location"]
    card, = b.post("/api/help/nearby", json=location).json()["requests"]
    edge = {**location, "lat": 0.007}
    assert b.post("/api/help/nearby", json=edge).json()["requests"][0]["id"] == rid
    assert not b.post("/api/help/nearby", json={**edge, "radius": 500}).json()["requests"]
    assert card["reward_cents"] == cents and card["comment_count"] == 0
    assert not {"lat", "lon", "accuracy", "location"} & card.keys()
    root = b.post(url + "/replies", json={"content": "我这里有充电器，可以借给你。"}).json()["id"]
    child = a.post(url + "/replies", json={"content": "好的，你在哪里？", "parent_id": root}).json()["id"]
    assert [msg["parent_id"] for msg in b.get(url).json()["replies"]] == [None, root]
    assert b.post(url + "/replies", json={"content": "多级", "parent_id": child}).status_code == 422
    second = a.post("/api/help/requests", json=demand()).json()["id"]
    assert b.post(f"/api/help/requests/{second}/replies", json={"content": "串帖", "parent_id": root}).status_code == 422
    assert a.get("/api/help/inbox").json()["pending"] == []
    assert b.get(chat).status_code == 404
    for _ in range(2):
        assert b.post(url + "/offers").status_code == 204
    assert a.get("/api/help/inbox").json()["pending"][0]["offers"] == 1
    card = next(item for item in b.post("/api/help/nearby", json=location).json()["requests"] if item["id"] == rid)
    assert card["comment_count"] == 2 and card["has_offered"]
    assert c.post(verdict, json={"decision": "accepted"}).status_code == 403
    assert c.post(url + "/offers").status_code == 204
    assert a.post(url + "/offers/" + other["id"], json={"decision": "declined"}).status_code == 204
    assert c.get(url).json()["offers"][0]["status"] == "declined"
    assert a.post(verdict, json={"decision": "accepted"}).status_code == 204
    assert a.get(url).json()["status"] == "in_progress"
    assert a.post(chat + "/messages", json={"content": "我们在图书馆门口见面吧。"}).status_code == 201
    assert b.get("/api/help/inbox").json()["chats"][0]["unread"] == 1
    assert b.post(chat + "/messages", json={"content": "好的，五分钟后到。"}).status_code == 201
    assert c.get(chat).status_code == 404
    assert c.post(chat + "/messages", json={"content": "他人私信"}).status_code == 404
    assert b.post(url + "/state", json={"status": "resolved"}).status_code == 403
    assert a.post(url + "/state", json={"status": "resolved"}).status_code == 204
    with TestClient(create_app(path), base_url="https://local.test") as restored:
        restored.cookies.update(a.cookies)
        assert start(restored).json() == owner
        assert restored.get(url).json()["status"] == "resolved"
        assert len(restored.get(url).json()["replies"]) == len(restored.get(chat).json()["messages"]) == 2
        assert all(row["id"] != rid for row in restored.post("/api/help/nearby", json=location).json()["requests"])
    assert clean_request(path, rid) == created.json()["title"]
    assert a.get(url).status_code == 200
    clean_request(path, rid, apply=True)
    assert a.get(url).status_code == 404 and a.get(chat).status_code == 404
    assert a.get(f"/api/help/requests/{second}").status_code == 200
    with connect(path) as db:
        assert not db.execute("PRAGMA foreign_key_check").fetchall()


def test_guest_switch_limits_and_registered_history(demo, monkeypatch, signup):
    path, (a, b, _) = demo
    session = start(a)
    assert {"Secure", "HttpOnly", "SameSite=strict"} <= set(session.headers["set-cookie"].split("; "))
    guest = session.json()
    assert b.post("/api/help/requests", json={**demand(), "guest_id": guest["id"]}).status_code == 401
    for invalid in (-1, 5.5, 1000001):
        assert a.post("/api/help/requests", json=demand(invalid)).status_code == 422
    for _ in range(3):
        assert a.post("/api/help/requests", json=demand()).status_code == 201
    assert a.post("/api/help/requests", json=demand()).status_code == 429
    assert a.post("/api/communities/cityu-hackathon/topics", json={
        "guest_id": guest["id"], "nickname": "访客", "title": "旧版", "content": "测试",
    }).status_code == 401
    reg = signup(a, "registered", "旧账号")
    assert not reg["is_demo"] and start(a).json() == reg
    registered_request = a.post("/api/help/requests", json=demand()).json()["id"]
    with pytest.raises(ValueError):
        clean_request(path, registered_request, apply=True)
    assert a.post("/api/auth/logout").status_code == 204 and start(a).json() == guest
    monkeypatch.setenv("NEARHELP_DEMO_GUESTS", "false")
    with TestClient(create_app(path), base_url="https://local.test") as normal:
        normal.cookies.update(a.cookies)
        assert start(normal).json() is None and normal.get("/api/auth/me").json() is None
        assert normal.post("/api/help/requests", json=demand()).status_code == 401
        assert normal.post("/api/auth/login", json={"username": "registered", "password": "fixture-password-1234"}).json() == reg
        assert normal.get("/api/help/mine").json()[0]["id"] == registered_request


def test_existing_database_upgrade_is_repeatable(tmp_path):
    path = tmp_path / "older.sqlite3"
    initialize(path)
    with connect(path) as db:
        db.execute("ALTER TABLE comments DROP COLUMN parent_id")
        db.execute("ALTER TABLE help_requests DROP COLUMN reward_cents")
        db.execute("ALTER TABLE accounts DROP COLUMN is_demo")
        db.execute("ALTER TABLE accounts DROP COLUMN is_admin")
        db.execute("ALTER TABLE help_requests DROP COLUMN hidden_at")
        db.execute("ALTER TABLE help_requests DROP COLUMN pinned_until")
        db.execute("INSERT INTO accounts(id,username,nickname,password_hash) VALUES('old','old','原昵称','hash')")
        old_id = db.execute("INSERT INTO topics(community_slug,guest_id,nickname,title,content) VALUES('cityu-hackathon','old','原昵称','旧帖','旧内容')").lastrowid
        db.execute("INSERT INTO help_requests(topic_id,author_id,expires_at) VALUES(?,'old',0)", (old_id,))
        db.execute("INSERT INTO comments(topic_id,guest_id,nickname,content) VALUES(?,'old','原昵称','旧评论')", (old_id,))
    initialize(path)
    initialize(path)
    with connect(path) as db:
        assert db.execute("SELECT is_demo FROM accounts").fetchone()[0] == 0
        assert db.execute("SELECT is_admin FROM accounts").fetchone()[0] == 0
        assert tuple(db.execute("SELECT hidden_at, pinned_until FROM help_requests").fetchone()) == (None, None)
        assert db.execute("SELECT reward_cents FROM help_requests").fetchone()[0] == 0
        assert tuple(db.execute("SELECT content, parent_id FROM comments").fetchone()) == ("旧评论", None)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
