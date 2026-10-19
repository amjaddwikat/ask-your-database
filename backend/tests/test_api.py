from fastapi.testclient import TestClient

from tests.fakes import FakeLLM


def test_health_needs_no_auth(client: TestClient) -> None:
    assert client.get("/health", headers={"X-API-Key": ""}).json() == {"status": "ok"}


def test_readiness(client: TestClient) -> None:
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_rejects_missing_api_key(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": "hi"}, headers={"X-API-Key": ""})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "http_error"


def test_rejects_wrong_api_key(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": "hi"}, headers={"X-API-Key": "nope"})
    assert response.status_code == 401


def test_chat_starts_a_session(client: TestClient, llm: FakeLLM) -> None:
    llm.reply("router", {"action": "general", "message": "Hello!"})

    response = client.post("/api/v1/chat", json={"message": "hi"})

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "general"
    assert body["message"] == "Hello!"
    assert len(body["session_id"]) == 32
    assert response.headers["X-Request-ID"]


def test_chat_reuses_session_and_history_endpoint(client: TestClient, llm: FakeLLM) -> None:
    llm.reply("router", {"action": "general", "message": "Hello!"})
    client.post("/api/v1/chat", json={"message": "hi", "session_id": "my-session-01"})

    history = client.get("/api/v1/sessions/my-session-01/messages").json()

    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "hi"),
        ("assistant", "Hello!"),
    ]


def test_validation_errors_use_the_error_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_invalid_session_id_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": "hi", "session_id": "../etc"})
    assert response.status_code == 422


def test_llm_outage_returns_502(client: TestClient, llm: FakeLLM) -> None:
    llm.reply("router", "not json", "still not json")

    response = client.post("/api/v1/chat", json={"message": "hi"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_unavailable"


def test_schema_endpoint_lists_tables(client: TestClient) -> None:
    tables = client.get("/api/v1/schema").json()
    assert {t["name"] for t in tables} == {"telecom_dw.dimcustomer", "telecom_dw.factbilling"}
