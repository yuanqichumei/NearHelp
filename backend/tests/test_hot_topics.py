from uuid import uuid4

from fastapi.testclient import TestClient

from app import hot_topics
from app.db import DEFAULT_COMMUNITY, connect
from app.main import create_app
from app.zhihu import ZhihuError, ZhihuHotList, ZhihuItem


def test_hot_topics_cache_and_discussion(tmp_path, monkeypatch, signup):
    path = tmp_path / "near.sqlite3"
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "server-only-test-secret")
    monkeypatch.setenv("ZHIHU_CACHE_TTL", "1800")
    now = [10000]
    monkeypatch.setattr(hot_topics, "time", type("Clock", (), {"time": staticmethod(lambda: now[0])}))
    original = "https://www.zhihu.com/question/1?utm_source=first"
    duplicate = "https://www.zhihu.com/question/1?utm_source=second"
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) == 2:
            raise ZhihuError("temporary failure")
        url = original if len(calls) == 1 else duplicate
        return ZhihuHotList(1, (ZhihuItem("热点", url, None, None),))

    monkeypatch.setattr(hot_topics, "fetch_hot_list", fetch)
    with TestClient(create_app(path)) as client:
        signup(client, "reader", "访客")
        response = client.get("/api/hot-topics")
        assert "server-only-test-secret" not in response.text
        [topic] = response.json()
        assert topic["original_url"] == original
        assert client.get("/api/hot-topics").json() == [topic]
        assert len(calls) == 1
        detail = f"/api/communities/{DEFAULT_COMMUNITY}/topics/{topic['topic_id']}"
        assert client.get(detail).json()["hot_topic"]["original_url"] == original
        assert client.post(detail + "/comments", json={
            "guest_id": str(uuid4()), "nickname": "访客", "content": "讨论",
        }).status_code == 201
        now[0] += 1801
        [cached] = client.get("/api/hot-topics").json()
        assert cached["comment_count"] == 1
        assert client.get("/api/hot-topics").json() == [cached]
        assert len(calls) == 2
        now[0] += 121
        [refreshed] = client.get("/api/hot-topics").json()
        assert refreshed["topic_id"] == topic["topic_id"]
        assert refreshed["original_url"] == duplicate
        assert refreshed["comment_count"] == 1
        assert client.get(f"/api/communities/{DEFAULT_COMMUNITY}/topics").json() == []


def test_manual_hot_topic_and_empty_state_without_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("ZHIHU_ACCESS_SECRET", raising=False)
    path = tmp_path / "near.sqlite3"
    with TestClient(create_app(path)) as client:
        assert client.get("/api/hot-topics").json() == []
        with connect(path) as connection:
            topic_id = hot_topics.save_hot_topic(connection, DEFAULT_COMMUNITY, hot_topics.MANUAL,
                                                "人工收录", "https://example.org/news")
        [topic] = client.get("/api/hot-topics").json()
        assert topic["topic_id"] == topic_id
        assert topic["source"] == "manual"
