import logging
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, current_app, g, jsonify, request
from werkzeug.exceptions import HTTPException


DEMO_OPERATOR_ID = "demo-operator-1"
DEMO_RENEWAL_ID = "demo-renewal-1"
MAX_MESSAGE_LENGTH = 2000
DEFAULT_DATABASE = Path(__file__).parent / "instance" / "renewals.sqlite"


def get_db():
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def initialise_database(app):
    with app.app_context():
        database = get_db()
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS operators (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                operator_id TEXT NOT NULL REFERENCES operators(id),
                number TEXT NOT NULL UNIQUE,
                card_type TEXT NOT NULL,
                expiry_date TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS renewals (
                id TEXT PRIMARY KEY,
                reference TEXT NOT NULL UNIQUE,
                operator_id TEXT NOT NULL REFERENCES operators(id),
                card_id TEXT NOT NULL REFERENCES cards(id),
                status TEXT NOT NULL,
                status_explanation TEXT NOT NULL,
                status_updated_at TEXT NOT NULL,
                next_action_title TEXT NOT NULL,
                next_action_description TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS progress_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                renewal_id TEXT NOT NULL REFERENCES renewals(id),
                stage TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('complete', 'current', 'upcoming')),
                event_date TEXT,
                description TEXT NOT NULL,
                position INTEGER NOT NULL,
                UNIQUE (renewal_id, position)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                renewal_id TEXT NOT NULL REFERENCES renewals(id),
                request_id TEXT NOT NULL,
                content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 2000),
                sender TEXT NOT NULL CHECK (sender IN ('operator', 'support')),
                sender_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (renewal_id, request_id)
            );
            """
        )
        database.commit()

        if database.execute(
            "SELECT 1 FROM operators WHERE id = ?", (DEMO_OPERATOR_ID,)
        ).fetchone():
            return

        today = datetime.now(timezone.utc).date()
        expiry_date = (today + timedelta(days=21)).isoformat()
        status_updated_at = utc_now()
        seeded_messages = (
            (
                "seed-operator-message",
                "operator",
                "Alex Morgan",
                "I have seen the renewal request. Where can I send the requested evidence?",
                today.isoformat() + "T09:00:00Z",
            ),
            (
                "seed-support-message",
                "support",
                "Demo support",
                "Example response",
                today.isoformat() + "T09:05:00Z",
            ),
        )
        with database:
            database.execute(
                "INSERT INTO operators (id, name) VALUES (?, ?)",
                (DEMO_OPERATOR_ID, "Alex Morgan"),
            )
            database.execute(
                """INSERT INTO cards (id, operator_id, number, card_type, expiry_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    "demo-card-1",
                    DEMO_OPERATOR_ID,
                    "CPCS-4821-7306",
                    "Plant Operator — 360° Excavator",
                    expiry_date,
                ),
            )
            database.execute(
                """INSERT INTO renewals
                   (id, reference, operator_id, card_id, status, status_explanation,
                    status_updated_at, next_action_title, next_action_description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    DEMO_RENEWAL_ID,
                    "RN-2026-00482",
                    DEMO_OPERATOR_ID,
                    "demo-card-1",
                    "Action needed",
                    "The demo renewal is waiting for a sample item of evidence before it can move forward.",
                    status_updated_at,
                    "Provide an example of recent experience",
                    "For this demo, ask about the evidence using the message form.",
                ),
            )
            database.executemany(
                """INSERT INTO progress_events
                   (renewal_id, stage, state, event_date, description, position)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    (
                        DEMO_RENEWAL_ID,
                        "Renewal started",
                        "complete",
                        today.isoformat(),
                        "A renewal record was created for this demo.",
                        1,
                    ),
                    (
                        DEMO_RENEWAL_ID,
                        "Evidence requested",
                        "current",
                        today.isoformat(),
                        "The example renewal is waiting for the operator to provide information.",
                        2,
                    ),
                    (
                        DEMO_RENEWAL_ID,
                        "Review and decision",
                        "upcoming",
                        None,
                        "This stage has not started and has no demo date.",
                        3,
                    ),
                ),
            )
            database.executemany(
                """INSERT INTO messages
                   (id, renewal_id, request_id, content, sender, sender_name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    (
                        message_id,
                        DEMO_RENEWAL_ID,
                        message_id,
                        content,
                        sender,
                        sender_name,
                        created_at,
                    )
                    for message_id, sender, sender_name, content, created_at in seeded_messages
                ),
            )


def error_response(message, status):
    return jsonify({"error": message}), status


def get_accessible_renewal(renewal_id):
    return get_db().execute(
        """SELECT r.*, o.name AS operator_name, c.number AS card_number,
                  c.card_type, c.expiry_date
           FROM renewals r
           JOIN operators o ON o.id = r.operator_id
           JOIN cards c ON c.id = r.card_id
           WHERE r.id = ? AND r.operator_id = ?""",
        (renewal_id, DEMO_OPERATOR_ID),
    ).fetchone()


def message_dict(row):
    return {
        "id": row["id"],
        "text": row["content"],
        "sender": row["sender"],
        "sender_name": row["sender_name"],
        "created_at": row["created_at"],
    }


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(DATABASE=os.environ.get("DATABASE_PATH", str(DEFAULT_DATABASE)))
    if test_config:
        app.config.update(test_config)
    app.logger.setLevel(logging.INFO)
    app.teardown_appcontext(close_db)
    initialise_database(app)

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unexpected API error")
        return error_response("An unexpected error occurred.", 500)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/renewals/<renewal_id>")
    def renewal_details(renewal_id):
        renewal = get_accessible_renewal(renewal_id)
        if renewal is None:
            return error_response("Renewal not found.", 404)

        today = datetime.now(timezone.utc).date()
        expiry_date = date.fromisoformat(renewal["expiry_date"])
        days_remaining = (expiry_date - today).days
        events = get_db().execute(
            """SELECT stage, state, event_date, description
               FROM progress_events WHERE renewal_id = ? ORDER BY position""",
            (renewal_id,),
        ).fetchall()
        return jsonify(
            {
                "id": renewal["id"],
                "reference": renewal["reference"],
                "operator_name": renewal["operator_name"],
                "card": {
                    "number": renewal["card_number"],
                    "type": renewal["card_type"],
                    "expiry_date": renewal["expiry_date"],
                    "days_remaining": days_remaining,
                    "validity": "Valid" if days_remaining >= 0 else "Expired",
                },
                "status": {
                    "label": renewal["status"],
                    "explanation": renewal["status_explanation"],
                    "updated_at": renewal["status_updated_at"],
                },
                "next_action": {
                    "title": renewal["next_action_title"],
                    "description": renewal["next_action_description"],
                    "is_demo_assumption": True,
                },
                "timeline": [
                    {
                        "stage": event["stage"],
                        "state": event["state"],
                        "date": event["event_date"],
                        "description": event["description"],
                    }
                    for event in events
                ],
            }
        )

    @app.get("/api/renewals/<renewal_id>/messages")
    def get_messages(renewal_id):
        if get_accessible_renewal(renewal_id) is None:
            return error_response("Renewal not found.", 404)
        rows = get_db().execute(
            """SELECT id, content, sender, sender_name, created_at
               FROM messages WHERE renewal_id = ?
               ORDER BY created_at, id""",
            (renewal_id,),
        ).fetchall()
        return jsonify({"messages": [message_dict(row) for row in rows]})

    @app.post("/api/renewals/<renewal_id>/messages")
    def post_message(renewal_id):
        if get_accessible_renewal(renewal_id) is None:
            return error_response("Renewal not found.", 404)
        if not request.is_json:
            return error_response("Request body must be JSON.", 400)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error_response("Request body must be a JSON object.", 400)
        if set(body) != {"text", "request_id"}:
            return error_response("Provide only text and request_id.", 400)
        content = body["text"]
        request_id = body["request_id"]
        if not isinstance(content, str) or not isinstance(request_id, str):
            return error_response("text and request_id must be strings.", 400)
        content = content.strip()
        if not content:
            return error_response("Enter a message before sending.", 400)
        if len(content) > MAX_MESSAGE_LENGTH:
            return error_response(
                f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer.", 400
            )
        try:
            parsed_request_id = uuid.UUID(request_id)
        except (ValueError, AttributeError):
            return error_response("request_id must be a valid UUID.", 400)
        if str(parsed_request_id) != request_id.lower():
            return error_response("request_id must be a valid UUID.", 400)

        database = get_db()
        try:
            database.execute("BEGIN IMMEDIATE")
            existing = database.execute(
                """SELECT id, content, sender, sender_name, created_at
                   FROM messages WHERE renewal_id = ? AND request_id = ?""",
                (renewal_id, request_id),
            ).fetchone()
            if existing is not None:
                database.commit()
                if existing["content"] != content:
                    return error_response(
                        "This request identifier was already used for a different message.",
                        409,
                    )
                return jsonify({"message": message_dict(existing)}), 200

            message_id = str(uuid.uuid4())
            created_at = utc_now()
            database.execute(
                """INSERT INTO messages
                   (id, renewal_id, request_id, content, sender, sender_name, created_at)
                   VALUES (?, ?, ?, ?, 'operator', ?, ?)""",
                (
                    message_id,
                    renewal_id,
                    request_id,
                    content,
                    get_accessible_renewal(renewal_id)["operator_name"],
                    created_at,
                ),
            )
            saved_message = database.execute(
                """SELECT id, content, sender, sender_name, created_at
                   FROM messages WHERE id = ?""",
                (message_id,),
            ).fetchone()
            database.commit()
        except sqlite3.Error:
            database.rollback()
            raise
        return jsonify({"message": message_dict(saved_message)}), 201

    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
