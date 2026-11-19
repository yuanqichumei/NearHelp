from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.main import create_app

TOPICS = "/api/communities/cityu-hackathon/topics"
ALICE = {"guest_id": str(uuid4()), "nickname": "访客甲"}
BOB = {"guest_id": str(uuid4()), "nickname": "访客乙"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "neartalk.sqlite3")) as session:
        yield session


def test_health_and_default_community(client):
    response = client.get("/api/health")
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
    assert client.get(TOPICS).json() == []


def test_independent_clients_share_posts_and_restart_persists(tmp_path):
    db = tmp_path / "neartalk.sqlite3"
    with TestClient(create_app(db)) as alice, TestClient(create_app(db)) as bob:
        response = alice.post(TOPICS, json={**ALICE, "title": "  午饭去哪里？ ", "content": "你好" * 90})
        assert response.status_code == 201
        topic_id = response.json()["id"]
        path = f"{TOPICS}/{topic_id}"
        [listed_topic] = bob.get(TOPICS).json()
        assert listed_topic["title"] == "午饭去哪里？"
        assert listed_topic["nickname"] == ALICE["nickname"]
        assert listed_topic["summary"] == "你好" * 70 + "…"
        assert listed_topic["comment_count"] == 0
        assert "guest_id" not in listed_topic
        content = "<b>去食堂</b>"
        response = bob.post(f"{path}/comments", json={**BOB, "content": content})
        assert response.status_code == 201
        assert alice.get(path).json()["comments"] == [response.json()]
        assert alice.get(TOPICS).json()[0]["comment_count"] == 1
    with TestClient(create_app(db)) as restarted:
        detail = restarted.get(path).json()
        assert detail["content"] == "你好" * 90
        assert detail["comments"][0]["nickname"] == BOB["nickname"]
        assert detail["comments"][0]["content"] == content


@pytest.mark.parametrize("invalid", [
    {"title": " "},
    {"title": "字" * 81},
    {"content": "字" * 2001},
    {"nickname": "字" * 25},
    {"guest_id": "bad-id"},
])
def test_invalid_topics_are_rejected(client, invalid):
    topic = {**ALICE, "title": "标题", "content": "正文", **invalid}
    assert client.post(TOPICS, json=topic).status_code == 422
    assert client.get(TOPICS).json() == []


def test_invalid_comments_and_unknown_community(client):
    response = client.post(TOPICS, json={**ALICE, "title": "标题", "content": "正文"})
    topic_id = response.json()["id"]
    comments = f"{TOPICS}/{topic_id}/comments"
    assert client.post(comments, json={**BOB, "content": "字" * 501}).status_code == 422
    assert client.post(comments, json={**BOB, "content": " "}).status_code == 422
    assert client.post(f"{TOPICS}/999/comments", json={**BOB, "content": "问好"}).status_code == 404
    assert client.get("/api/communities/unknown/topics").status_code == 404
    assert client.get(f"/api/communities/unknown/topics/{topic_id}").status_code == 404


def test_limits_apply_to_topic_and_comment_writes(client):
    topic = {**ALICE, "title": "标题", "content": "正文"}
    for _ in range(3):
        response = client.post(TOPICS, json=topic)
        assert response.status_code == 201
    comments = f"{TOPICS}/{response.json()['id']}/comments"
    throttled = client.post(TOPICS, json=topic)
    assert throttled.status_code == 429
    assert throttled.headers["retry-after"] == "60"
    assert client.post(TOPICS, json={**topic, **BOB}).status_code == 201
    for _ in range(12):
        assert client.post(comments, json={**BOB, "content": "回复"}).status_code == 201
    assert client.post(comments, json={**BOB, "content": "回复"}).status_code == 429
    assert client.get(TOPICS).json()[1]["comment_count"] == 12
