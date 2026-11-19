from contextlib import ExitStack
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app

HK = {"lat": 22.34, "lon": 114.17}
SZ = {"lat": 22.545, "lon": 114.06}
TOPICS = "/api/communities/cityu-hackathon/topics"


def test_home_feed_filters_radius_city_and_keeps_original_discussions(tmp_path):
    with TestClient(create_app(tmp_path / "geo.sqlite3")) as client:
        guest = {"guest_id": str(uuid4()), "nickname": "访客", "content": "在这里讨论"}

        def publish(title, point=None):
            return client.post(TOPICS, json={**guest, "title": title, "region": point}).json()["id"]

        legacy = publish("原有城大话题")
        farther = publish("距离约三公里", {"lat": 22.37, "lon": 114.17})
        shenzhen = publish("深圳话题", SZ)

        def titles(point, scope):
            return [item["id"] for item in client.get(
                "/api/regions/topics", params={**point, "scope": scope},
            ).json()]

        assert titles(HK, "1") == [legacy]
        assert titles(HK, "5") == [farther, legacy]
        assert titles(HK, "10") == [farther, legacy]
        assert titles(HK, "city") == [farther, legacy]
        assert titles(SZ, "city") == [shenzhen]
        detail = f"{TOPICS}/{shenzhen}"
        assert client.post(detail + "/comments", json={**guest, "content": "回复"}).status_code == 201
        assert len(client.get(detail).json()["comments"]) == 1


def test_regional_counts_are_available_to_nonparticipating_visitors(tmp_path):
    path = tmp_path / "geo.sqlite3"
    with ExitStack() as stack:
        clients = [stack.enter_context(TestClient(create_app(path))) for _ in range(4)]
        viewer = clients[0]

        def stats(point, scope):
            return viewer.get("/api/regions/stats", params={**point, "scope": scope})

        assert stats(HK, "5").status_code == 401
        for client in clients:
            assert client.post("/api/visitor/session").status_code == 204
        for count, client in enumerate(clients[1:], 1):
            assert client.post("/api/location/consent", json={"enabled": True}).status_code == 204
            assert client.post("/api/location/heartbeat", json={"lat": 22.37, "lon": 114.17}).status_code == 200
            if count < 3:
                assert stats(HK, "5").json() == {"city": "香港", "band": str(count)}
        assert stats(HK, "1").json() == {"city": "香港", "band": "0"}
        assert stats(HK, "5").json() == {"city": "香港", "band": "3–4"}
        assert stats(HK, "city").json() == {"city": "香港", "band": "3–4"}
        assert stats(SZ, "city").json() == {"city": "深圳", "band": "0"}
        assert stats({"lat": 0, "lon": 0}, "city").json() == {"city": None, "band": None}
        assert viewer.post("/api/location/heartbeat", json=HK).status_code == 403
        assert stats(HK, "5").status_code == 200
        assert stats(HK, "5").status_code == 429
