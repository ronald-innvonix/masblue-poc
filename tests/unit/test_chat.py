"""Unit tests for the stubbed chat API."""

from fastapi.testclient import TestClient


def test_chat_returns_stubbed_response(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify authenticated chat calls return the expected placeholder shape."""
    response = client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={"message": "Hello"},
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"] is None
    assert response.json()["message"] == "This is a stubbed AI response."


def test_chat_requires_bearer_token(client: TestClient) -> None:
    """Verify the chat route does not accept unauthenticated requests."""
    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_chat_stream_returns_server_sent_events(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Verify the stub stream uses SSE token frames and a completion marker."""
    response = client.post(
        "/api/v1/chat/stream",
        headers=auth_headers,
        json={"message": "Hello"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"token": "This "}' in response.text
    assert "data: [DONE]" in response.text
