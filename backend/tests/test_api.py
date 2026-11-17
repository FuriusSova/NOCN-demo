import sqlite3
import json
import uuid

import pytest

from app import DEMO_RENEWAL_ID, create_app


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "renewals.sqlite"),
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def test_loads_seeded_renewal(client):
    response = client.get(f"/api/renewals/{DEMO_RENEWAL_ID}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["operator_name"] == "Alex Morgan"
    assert data["status"]["label"] == "Action needed"
    assert data["card"]["days_remaining"] == 21
    assert data["next_action"]["description"] == (
        "For this demo, ask about the evidence using the message form."
    )
    assert [event["state"] for event in data["timeline"]] == [
        "complete",
        "current",
        "upcoming",
    ]


def test_creates_and_retrieves_message(client):
    request_id = str(uuid.uuid4())
    response = client.post(
        f"/api/renewals/{DEMO_RENEWAL_ID}/messages",
        json={"text": "  I have a question.  ", "request_id": request_id},
    )

    assert response.status_code == 201
    saved = response.get_json()["message"]
    assert saved["text"] == "I have a question."
    assert saved["sender"] == "operator"
    assert saved["sender_name"] == "Alex Morgan"
    assert saved["created_at"].endswith("Z")

    messages = client.get(
        f"/api/renewals/{DEMO_RENEWAL_ID}/messages"
    ).get_json()["messages"]
    assert saved in messages


def test_message_persists_across_app_instances(tmp_path):
    database = str(tmp_path / "persistent.sqlite")
    first_client = create_app({"TESTING": True, "DATABASE": database}).test_client()
    request_id = str(uuid.uuid4())
    first_client.post(
        f"/api/renewals/{DEMO_RENEWAL_ID}/messages",
        json={"text": "Please clarify the request.", "request_id": request_id},
    )

    second_client = create_app(
        {"TESTING": True, "DATABASE": database}
    ).test_client()
    messages = second_client.get(
        f"/api/renewals/{DEMO_RENEWAL_ID}/messages"
    ).get_json()["messages"]
    assert any(message["text"] == "Please clarify the request." for message in messages)


@pytest.mark.parametrize(
    ("text", "expected_error"),
    [
        ("", "Enter a message"),
        ("   \t ", "Enter a message"),
        ("x" * 2001, "2000 characters"),
        (42, "must be strings"),
        (None, "must be strings"),
    ],
)
def test_rejects_invalid_messages(client, text, expected_error):
    response = client.post(
        f"/api/renewals/{DEMO_RENEWAL_ID}/messages",
        json={"text": text, "request_id": str(uuid.uuid4())},
    )

    assert response.status_code == 400
    assert expected_error in response.get_json()["error"]


@pytest.mark.parametrize(
    "body",
    [
        "not-json",
        "[]",
        '{"text":',
        '{"text":"hello"}',
        '{"text":"hello","request_id":"not-a-uuid"}',
        '{"text":"hello","request_id":"00000000-0000-0000-0000-000000000000","role":"support"}',
    ],
)
def test_rejects_malformed_requests(client, body):
    response = client.post(
        f"/api/renewals/{DEMO_RENEWAL_ID}/messages",
        data=body,
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_rejects_missing_or_inaccessible_renewals(app, client):
    with sqlite3.connect(app.config["DATABASE"]) as database:
        database.execute(
            "INSERT INTO operators (id, name) VALUES (?, ?)",
            ("other-operator", "Other fictional operator"),
        )
        database.execute(
            """INSERT INTO cards (id, operator_id, number, card_type, expiry_date)
               VALUES (?, ?, ?, ?, ?)""",
            ("other-card", "other-operator", "OTHER-123", "Demo card", "2027-01-01"),
        )
        database.execute(
            """INSERT INTO renewals
               (id, reference, operator_id, card_id, status, status_explanation,
                status_updated_at, next_action_title, next_action_description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "other-renewal",
                "RN-OTHER",
                "other-operator",
                "other-card",
                "Action needed",
                "Private to another operator.",
                "2026-01-01T00:00:00Z",
                "No action",
                "No action.",
            ),
        )

    assert client.get("/api/renewals/missing").status_code == 404
    assert client.get("/api/renewals/missing/messages").status_code == 404
    assert client.get("/api/renewals/other-renewal").status_code == 404
    assert client.get("/api/renewals/other-renewal/messages").status_code == 404
    response = client.post(
        "/api/renewals/missing/messages",
        json={"text": "Hello", "request_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_identical_request_id_returns_original_message(client):
    request_id = str(uuid.uuid4())
    body = {"text": "Same message", "request_id": request_id}
    first = client.post(f"/api/renewals/{DEMO_RENEWAL_ID}/messages", json=body)
    repeated = client.post(f"/api/renewals/{DEMO_RENEWAL_ID}/messages", json=body)

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.get_json() == first.get_json()


def test_reused_request_id_with_different_content_conflicts(client):
    request_id = str(uuid.uuid4())
    path = f"/api/renewals/{DEMO_RENEWAL_ID}/messages"
    client.post(path, json={"text": "First", "request_id": request_id})

    response = client.post(
        path, json={"text": "Different", "request_id": request_id}
    )

    assert response.status_code == 409
    assert "already used" in response.get_json()["error"]


def test_sending_message_does_not_change_renewal_status(client):
    path = f"/api/renewals/{DEMO_RENEWAL_ID}"
    before = client.get(path).get_json()["status"]
    client.post(
        f"{path}/messages",
        json={"text": "A support question", "request_id": str(uuid.uuid4())},
    )
    after = client.get(path).get_json()["status"]

    assert after == before


def test_health_response_is_small(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
