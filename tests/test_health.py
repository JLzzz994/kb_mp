"""Health 端点冒烟测试。"""

from fastapi.testclient import TestClient

from app.api.app import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_name"] == "kb-mp"
