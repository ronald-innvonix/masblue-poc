"""Integration tests for the liveness endpoint."""

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    """Verify the liveness endpoint is available without database access."""
    response = client.get("/api/v1/health", headers={"X-Request-ID": "health-test-1"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "health-test-1"
