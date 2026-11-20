from contextlib import ExitStack
import secrets
import time

from fastapi.testclient import TestClient
import pytest

from app.create_admin import create_admin
from app.db import connect, initialize
from app.main import create_app

BASE = "/api/discussions"
VENUE = {"lat": 22.338, "lon": 114.172}


def test_moderator_hiding_restores_thread_and_recalculates_summary(forum):
    db, (a, b, c, admin) = forum
    route = "/api/admin/discussion-answers"
    tid = a.post(BASE + "/nearby", json=VENUE).json()[0]["id"]
    detail = f"{BASE}/{tid}"
    fix = {**VENUE, "accuracy": 20, "timestamp": time.time()}
    published = []
    for phone, content in ((a, "设计和验证都是重要贡献。"), (b, "手写代码有助于学习。"), (c, "我想了解实际测试的过程。")):
        answer = phone.post(detail + "/answers", json={"content": content, "location": fix})
        answer.raise_for_status()
        published.append(answer.json()["id"])
    parent = published[0]
    payload = {"content": "能详细讲讲吗？", "parent_id": parent}
    child = b.post(detail + "/answers", json=payload).json()["id"]
    assert a.get(route).status_code == 403
    assert b.post(f"{route}/{parent}", json={"action": "hide"}).status_code == 403
    assert a.get(detail).json()["summary"]["contributors"] == 3
    pwd = secrets.token_urlsafe(20)
    create_admin(db, "discussionmod", pwd)
    admin.post("/api/auth/login", json={"username": "discussionmod", "password": pwd}).raise_for_status()
    with connect(db) as connection:
        topic = connection.execute("""INSERT INTO topics(community_slug,guest_id,nickname,title,content)
            VALUES ('cityu-hackathon','test','test','test','test')""").lastrowid
        legacy = connection.execute("INSERT INTO comments(topic_id,guest_id,nickname,content) VALUES (?,'test','test','test')",
                                    (topic,)).lastrowid
    assert admin.post(f"{route}/{legacy}", json={"action": "hide"}).status_code == 404
    assert admin.post(f"{route}/{parent}", json={"action": "hide"},
                      headers={"Origin": "https://other.example"}).status_code == 403
    admin.post(f"{route}/{parent}", json={"action": "hide"}).raise_for_status()
    rows = admin.get(route, params={"visibility": "hidden"}).json()["items"]
    assert {row["id"] for row in rows} == {parent, child}
    assert next(row for row in rows if row["id"] == child)["parent_hidden"]
    data = a.get(detail).json()
    assert len(data["answers"]) == 2 and data["summary"]["extracts"] == []
    assert a.post(BASE + "/nearby", json=VENUE).json()[0]["count"] == 2
    assert b.post(detail + "/answers", json=payload).status_code == 422
    admin.post(f"{route}/{child}", json={"action": "hide"}).raise_for_status()
    admin.post(f"{route}/{parent}", json={"action": "restore"}).raise_for_status()
    assert len(a.get(detail).json()["answers"]) == 3
    assert a.get(detail).json()["summary"]["contributors"] == 3
    admin.post(f"{route}/{child}", json={"action": "restore"}).raise_for_status()
    assert a.post(BASE + "/nearby", json=VENUE).json()[0]["count"] == 4


@pytest.fixture
def forum(tmp_path, monkeypatch):
    db = tmp_path / "venue.sqlite3"
    monkeypatch.setenv("NEARHELP_DEMO_GUESTS", "true")
    app = create_app(db)
    with ExitStack() as stack:
        phones = [stack.enter_context(TestClient(app)) for _ in range(4)]
        for phone in phones:
            assert phone.post("/api/auth/session").status_code == 200
        yield db, phones


def test_one_feature_per_venue_and_archived_source_links(forum):
    db, (admin, guest, _, _) = forum
    tid = guest.post(BASE + "/nearby", json=VENUE).json()[0]["id"]
    config = {**VENUE, "venue": "香港城市大学", "question": "learning", "zhihu_url": ""}
    assert guest.post(BASE + "/feature", json=config).status_code == 403
    assert guest.get(BASE + "/catalog").status_code == 403
    pwd = secrets.token_urlsafe(16)
    create_admin(db, "editor", pwd)
    admin.post("/api/auth/login", json={"username": "editor", "password": pwd}).raise_for_status()
    assert {"authorship", "learning", "tools", "teamwork"} <= {q["key"] for q in admin.get(BASE + "/catalog").json()["questions"]}
    assert admin.post(BASE + "/feature", json={**config, "zhihu_url": "https://example.com"}).status_code == 422
    assert admin.post(BASE + "/feature", json=config).status_code == 409
    config["expected_topic_id"] = tid
    updated = admin.post(BASE + "/feature", json=config).json()["id"]
    assert updated != tid
    assert admin.post(BASE + "/feature", json=config).status_code == 409
    assert admin.post(BASE + "/feature", json={**config, "expected_topic_id": updated}).json()["id"] == updated
    initialize(db)
    cards = guest.post(BASE + "/nearby", json=VENUE).json()
    assert [c["id"] for c in cards] == [updated] and cards[0]["count"] == 0
    assert guest.post(BASE + "/nearby", json={"lat": 0, "lon": 0}).json() == []
    assert guest.get(f"{BASE}/{tid}").json()["active"] is False
    assert guest.post(f"{BASE}/{tid}/answers", json={"content": "往期"}).status_code == 409
    assert guest.get(f"/api/communities/nearhelp-discussions/topics/{updated}").status_code == 404


def test_authentic_local_summary_and_replies(forum):
    db, (a, b, c, remote) = forum
    tid = a.post(BASE + "/nearby", json=VENUE).json()[0]["id"]
    topic = f"{BASE}/{tid}"
    def send(phone, text, **extra):
        response = phone.post(topic + "/answers", json={"content": text, **extra})
        response.raise_for_status()
        return response.json()["id"]

    assert TestClient(create_app(db)).post(topic + "/answers", json={"content": "无身份"}).status_code == 401
    fix = {**VENUE, "accuracy": 30, "timestamp": time.time()}
    send(a, "我想先看懂生成的每一行代码。", location=fix)
    aid = send(a, "关键是作者能解释自己的设计取舍。", location=fix, theme="设计决策")
    send(b, "作品交付之后要能维护和修复它。", location=fix, theme="对成品负责")
    send(remote, "异地的读者也可以留下看法。")
    send(remote, "手动切到这个会场也能浏览。", location={**fix, "lat": 0})
    send(remote, "昨天在会场发表的看法。", location={**fix, "timestamp": time.time()-600})
    assert a.get(topic).json()["summary"]["extracts"] == []
    cid = send(c, "我更想了解测试和责任由谁承担。", location=fix, theme="对成品负责")
    rid = send(b, "你能举个例子吗？", parent_id=aid)
    assert a.post(topic+"/answers", json={"content": "跨楼回复", "parent_id": rid}).status_code == 422
    data = remote.get(topic).json()
    assert data["answers"][0]["parent_id"] == aid
    assert data["summary"]["contributors"] == 3
    assert {e["people"] for e in data["summary"]["themes"]} == {1, 2}
    originals = {r["id"]: r["content"] for r in data["answers"]}
    assert cid in [e["comment_id"] for e in data["summary"]["extracts"]]
    assert all(e["text"] in originals[e["comment_id"]] for e in data["summary"]["extracts"])
    assert all("location" not in r and "guest_id" not in r for r in data["answers"])
    with connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM discussion_local").fetchone()[0] == 4
    assert len(remote.get(topic, params={"before": cid}).json()["answers"]) < len(data["answers"])
