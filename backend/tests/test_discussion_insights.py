from contextlib import ExitStack
import time

from fastapi.testclient import TestClient

from app import discussion_insights
from app.create_admin import create_admin
from app.db import connect
from app.main import create_app


def test_admin_insights_uses_consent_and_discards_hidden_inputs(monkeypatch, tmp_path):
    monkeypatch.setenv("NEARHELP_DEMO_GUESTS", "true")
    monkeypatch.setenv("ZHIHU_RAG_ENABLED", "true")
    db_path = tmp_path / "insights.sqlite3"
    app = create_app(db_path)
    sample = {"id": "Z1", "title": "知乎参考回答", "author": "来源作者", "votes": 13,
              "url": "https://www.zhihu.com/question/1/answer/2?utm_medium=openapi_platform", "text": "外部摘要"}
    monkeypatch.setattr(discussion_insights, "search_answers", lambda query: [sample])
    invocations = []

    def generate(question, local, external=()):
        assert all(set(item) == {"id", "text"} for item in local)
        assert all("未授权" not in item["text"] for item in local)
        invocations.append(bool(external))
        return [{"text": "经核对的观点", "sources": [local[0]["id"]] + [item["id"] for item in external]}]

    monkeypatch.setattr(discussion_insights, "synthesize", generate)
    with ExitStack() as stack:
        admin, *guests = [stack.enter_context(TestClient(app)) for _ in range(5)]
        with connect(db_path) as db:
            venue = db.execute("SELECT topic_id,lat,lon FROM discussion_rounds").fetchone()
        path = f"/api/discussions/{venue['topic_id']}"
        fix = {"lat": venue["lat"], "lon": venue["lon"], "accuracy": 20, "timestamp": time.time()}
        for guest in guests:
            guest.post("/api/auth/session").raise_for_status()
        for index, guest in enumerate(guests):
            prompt = "同意整理的独立发言" if index < 3 else "未授权的独立发言"
            result = guest.post(path + "/answers", json={
                "content": prompt + str(index), "location": fix, **({"ai_consent": False} if index == 3 else {}),
            })
            result.raise_for_status()
            if index == 0:
                remove_id = result.json()["id"]
        query = {"query": "题目关键词"}
        assert guests[0].post(path + "/insights", json=query).status_code == 403
        password = "fixture-admin-password"
        create_admin(db_path, "insights_admin", password)
        admin.post("/api/auth/login", json={"username": "insights_admin", "password": password}).raise_for_status()
        admin.post(path + "/insights", json=query).raise_for_status()
        info = guests[0].get(path).json()["insights"]
        assert invocations == [False, True]
        assert info["local"] and info["comparison"]
        assert info["zhihu"][0]["url"] == sample["url"]
        assert info["zhihu"][0]["text"] == sample["text"]
        assert guests[0].get(path).json()["insights"] == info
        assert invocations == [False, True]
        monkeypatch.setenv("ZHIHU_RAG_ENABLED", "false")
        assert guests[0].get(path).json()["insights"]["comparison"] == []
        admin.post(f"/api/admin/discussion-answers/{remove_id}", json={"action": "hide"}).raise_for_status()
        after_hide = guests[0].get(path).json()["insights"]
        assert not after_hide["local"] and not after_hide["comparison"]
        assert after_hide["zhihu"] == info["zhihu"]
