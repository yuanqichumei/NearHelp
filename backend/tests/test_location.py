from contextlib import ExitStack

from fastapi.testclient import TestClient

from app import location
from app.db import connect
from app.main import create_app


def test_nearby_identity_consent_privacy_and_expiry(tmp_path):
    path = tmp_path / "geo.sqlite3"
    point = {"lat": 22.33761, "lon": 114.17142}
    with ExitStack() as stack:
        clients = [stack.enter_context(TestClient(create_app(path))) for _ in range(4)]
        assert clients[0].post("/api/location/heartbeat", json=point).status_code == 401
        for client in clients:
            response = client.post("/api/visitor/session")
            assert response.status_code == 204
            assert "HttpOnly" in response.headers["set-cookie"]
            assert client.post("/api/location/heartbeat", json=point).status_code == 403
            assert client.post("/api/location/consent", json={"enabled": True}).status_code == 204
        assert clients[0].post("/api/location/heartbeat", json=point).json() == {
            "radius_m": 500, "band": "1",
        }
        clients[0].post("/api/visitor/session")
        clients[0].post("/api/location/heartbeat", json={"lat": 0, "lon": 0})
        assert clients[1].post("/api/location/heartbeat", json=point).json()["band"] == "2"
        assert clients[2].post("/api/location/heartbeat", json={"lat": 23, "lon": 114}).json()["band"] == "1"
        assert clients[3].post("/api/location/heartbeat", json=point).json()["band"] == "3–4"
        with connect(path) as connection:
            assert location.nearby_count(connection, 22.338, 114.171, location.time.time()) == 3
            assert connection.execute("SELECT COUNT(*) FROM geo_presence").fetchone()[0] == 4
            assert connection.execute("SELECT COUNT(*) FROM geo_presence WHERE lat = 22.338").fetchone()[0] == 3
        clients[1].post("/api/location/consent", json={"enabled": False})
        assert clients[1].post("/api/location/heartbeat", json=point).status_code == 403
        with connect(path) as connection:
            assert location.nearby_count(connection, 22.338, 114.171, location.time.time()) == 2
            timestamp = location.time.time() + 301
            assert location.nearby_count(connection, 22.338, 114.171, timestamp) == 0
            location.cleanup(connection, timestamp)
            assert connection.execute("SELECT COUNT(*) FROM geo_presence").fetchone()[0] == 0
