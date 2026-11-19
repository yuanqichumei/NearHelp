from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app import places
from app.db import connect
from app.main import create_app


def test_real_catalog_place_is_created_on_first_visit_and_reuses_topics(tmp_path, monkeypatch, signup):
    monkeypatch.delenv("GEOAPIFY_PLACES_KEY", raising=False)
    now = [datetime(2026, 1, 1, 15, 59, tzinfo=timezone.utc).timestamp()]
    monkeypatch.setattr(places, "time", SimpleNamespace(time=lambda: now[0]))
    path = tmp_path / "places.sqlite3"
    guest = {"guest_id": str(uuid4()), "nickname": "访客"}
    with TestClient(create_app(path)) as a, TestClient(create_app(path)) as b:
        signup(a, "alice", "访客甲")
        signup(b, "bob", "访客乙")
        assert a.get("/api/places/nearby?lat=-88&lon=0").json()["places"] == []
        results = a.get("/api/places/nearby?lat=22.337&lon=114.172").json()["places"]
        library = next(place for place in results if place["name"] == "邵逸夫图书馆")
        slug = library["slug"]
        url = f"/api/communities/{slug}"
        assert a.get(url).json()["source_id"] == "run-run-shaw-library"
        assert a.get(url + "/topics").status_code == 404
        assert a.post(url + "/visit").status_code == 401
        for visitor in (a, b):
            assert visitor.post("/api/visitor/session").status_code == 204
        assert a.post("/api/communities/place-fiction/visit").status_code == 404
        assert a.post(url + "/visit").json() == {
            "recent_visitors": 1, "today_visitors": 1, "active_topics": 0, "timezone": "Asia/Hong_Kong",
        }
        assert a.post(url + "/visit").json()["today_visitors"] == 1
        assert b.post(url + "/visit").json()["today_visitors"] == 2
        topic = a.post(url + "/topics", json={**guest, "title": "附近活动", "content": "一起讨论。"})
        assert topic.status_code == 201
        detail = url + "/topics/" + str(topic.json()["id"])
        assert b.post(detail + "/comments", json={**guest, "content": "你好"}).status_code == 201
        assert len(a.get(detail).json()["comments"]) == 1
        assert a.get("/api/communities/cityu-hackathon/topics").json() == []
        now[0] += 120  # After midnight in Hong Kong, same UTC day.
        assert a.post(url + "/visit").json() == {
            "recent_visitors": 2, "today_visitors": 1, "active_topics": 1, "timezone": "Asia/Hong_Kong",
        }
        assert b.post(url + "/visit").json()["recent_visitors"] == 2
        now[0] += 301
        assert a.post(url + "/visit").json()["recent_visitors"] == 1
        with connect(path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM geo_presence").fetchone()[0] == 0


def test_provider_catalog_reuses_place_id_and_resolves_timezone(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOAPIFY_PLACES_KEY", "test-key")
    calls = []

    def provider(endpoint, parameters, key):
        calls.append(endpoint)
        assert key == "test-key"
        if endpoint == "/v2/places":
            feature = {"properties": {"name": "Provider café", "place_id": "provider-id",
                                      "lat": 0, "lon": 0, "categories": ["catering.cafe"]}}
            return {"features": [feature, feature]}
        assert "apiKey" not in parameters
        return {"features": [{"properties": {"timezone": {"name": "Africa/Accra"}}}]}

    monkeypatch.setattr(places, "provider_json", provider)
    places.provider_places.cache_clear()
    with TestClient(create_app(tmp_path / "provider.sqlite3")) as client:
        search = "/api/places/nearby?lat=0&lon=0"
        [place] = client.get(search).json()["places"]
        assert client.get(search).json()["places"] == [place]
        assert place["source_id"] == "provider-id"
        assert client.post("/api/visitor/session").status_code == 204
        url = f"/api/communities/{place['slug']}/visit"
        assert client.post(url).json()["timezone"] == "Africa/Accra"
        assert client.post(url).json()["today_visitors"] == 1
        assert calls == ["/v2/places", "/v1/geocode/reverse"]
