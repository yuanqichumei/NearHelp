import pytest


@pytest.fixture
def signup():
    def register(client, username, nickname):
        response = client.post("/api/auth/register", json={
            "username": username, "nickname": nickname, "password": "fixture-password-1234",
        })
        assert response.status_code == 201, response.text
        return response.json()

    return register
