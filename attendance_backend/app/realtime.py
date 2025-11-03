import json
import os
import time
from contextlib import contextmanager
from typing import Iterable, Optional

from flask import Response, request
from flask.views import MethodView
from flask_smorest import Blueprint
from flask_jwt_extended import jwt_required
from sqlalchemy import text

from . import sse_stream
from .db import _get_engine, session_scope

blp = Blueprint(
    "Realtime",
    "realtime",
    url_prefix="/realtime",
    description="Realtime streaming endpoints (SSE)",
)


def _format_sse(data: dict, event: str = "update", id: Optional[str] = None) -> str:
    """
    Format data as an SSE string.

    Example:
      event: update
      data: {"foo": "bar"}

    Always ends with a double newline as per SSE spec.
    """
    lines = []
    if event:
        lines.append(f"event: {event}")
    if id is not None:
        lines.append(f"id: {id}")
    # Note: ensure the JSON is a single-line string
    lines.append(f"data: {json.dumps(data, default=str)}")
    return "\n".join(lines) + "\n\n"


@contextmanager
def _pg_listen_cursor(channel: str):
    """
    Try to open a raw psycopg connection via SQLAlchemy engine and issue LISTEN.

    Yields a tuple (conn, cursor) where cursor.connection is a psycopg connection
    that supports .poll() and .notifies. If any step fails, yields (None, None).
    """
    conn = None
    cursor = None
    try:
        # Use raw connection from SQLAlchemy for LISTEN/NOTIFY
        engine = _get_engine()
        raw = engine.raw_connection()  # returns a psycopg2 connection
        conn = raw
        cursor = conn.cursor()
        cursor.execute(f"LISTEN {channel};")
        conn.commit()
        yield conn, cursor
    except Exception:
        # Fallback will be used by caller
        yield None, None
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def _poll_attendance_changes(session_id: int, since_ts: Optional[str]) -> list[dict]:
    """
    Query recent attendance rows for a given session.
    If since_ts provided (ISO timestamp string), only return rows updated after it.
    """
    with session_scope() as db:
        where = "attendance.session_id = :sid"
        params = {"sid": session_id}
        if since_ts:
            where += " AND attendance.updated_at > :since_ts"
            params["since_ts"] = since_ts

        # Direct SQL for portability and to return updated_at as well
        sql = text(
            f"""
            SELECT id, session_id, student_id, status, marked_at, updated_at
            FROM attendance
            WHERE {where}
            ORDER BY updated_at DESC
            LIMIT 100
            """
        )
        rows = db.execute(sql, params).mappings().all()
        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "student_id": r["student_id"],
                "status": r["status"],
                "marked_at": r["marked_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]


def _attendance_events_stream(session_id: int) -> Iterable[str]:
    """
    Generator that yields SSE events for attendance changes for a given session.

    Strategy:
    - Attempt to LISTEN on 'attendance_events' channel. When notified, query and emit changes.
    - If LISTEN is not available, fallback to short-interval polling of attendance table.
    - Heartbeat comments sent periodically to keep connection alive.
    """
    channel = os.getenv("ATTENDANCE_EVENTS_CHANNEL", "attendance_events")
    poll_interval = float(os.getenv("REALTIME_POLL_INTERVAL_SEC", "2.0"))
    heartbeat_interval = float(os.getenv("REALTIME_HEARTBEAT_INTERVAL_SEC", "15.0"))

    last_heartbeat = time.time()
    # Optional watermark for updated_at, as ISO string
    since_ts: Optional[str] = None

    # Send an initial comment to establish the stream quickly
    yield ": stream-started\n\n"

    # Try LISTEN/NOTIFY path
    with _pg_listen_cursor(channel) as (conn, cursor):
        if conn is not None and cursor is not None:
            # LISTEN is active
            while True:
                try:
                    # Non-blocking wait for notifications
                    conn.poll()
                    # Deliver any queued notifications
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        # The payload is expected to be JSON; if present, we can filter
                        try:
                            payload = json.loads(getattr(notify, "payload", "{}") or "{}")
                        except Exception:
                            payload = {}

                        # If payload contains session_id and it doesn't match, skip
                        if payload.get("session_id") and int(payload.get("session_id")) != int(session_id):
                            continue

                        # Query recent changes and emit
                        changes = _poll_attendance_changes(session_id, since_ts)
                        if changes:
                            # Update watermark
                            latest = max(c.get("updated_at") for c in changes if c.get("updated_at"))
                            if latest is not None:
                                since_ts = str(latest)
                            yield _format_sse({"session_id": session_id, "changes": changes})

                    # Heartbeat to keep connection open
                    now = time.time()
                    if now - last_heartbeat >= heartbeat_interval:
                        last_heartbeat = now
                        yield ": heartbeat\n\n"

                    time.sleep(poll_interval)
                except GeneratorExit:
                    break
                except Exception:
                    # If listen loop breaks due to error, fall back to polling
                    break

        # Fallback to polling only
        while True:
            try:
                changes = _poll_attendance_changes(session_id, since_ts)
                if changes:
                    latest = max(c.get("updated_at") for c in changes if c.get("updated_at"))
                    if latest is not None:
                        since_ts = str(latest)
                    yield _format_sse({"session_id": session_id, "changes": changes})
                # Heartbeat
                now = time.time()
                if now - last_heartbeat >= heartbeat_interval:
                    last_heartbeat = now
                    yield ": heartbeat\n\n"
                time.sleep(poll_interval)
            except GeneratorExit:
                break
            except Exception:
                # On repeated failures, slow down slightly to avoid hot loop.
                time.sleep(max(poll_interval, 2.0))


@blp.route("/attendance", methods=["GET"])
class RealtimeAttendance(MethodView):
    """
    Server-Sent Events stream of attendance updates for a given session.

    Query parameters:
      - sessionId (int, required): The session ID to subscribe to.

    Returns:
      - text/event-stream stream with events named "update".
        Each event "data" is JSON: { "session_id": <int>, "changes": [ ...rows... ] }

    Usage example (JavaScript):
      const token = "<JWT>";
      const url = new URL("/realtime/attendance", baseUrl);
      url.searchParams.set("sessionId", 123);

      const es = new EventSource(url, { withCredentials: false });
      es.onmessage = (ev) => {
        const payload = JSON.parse(ev.data);
        console.log("Attendance update:", payload);
      };
      es.addEventListener("update", (ev) => {
        const payload = JSON.parse(ev.data);
        console.log("Named event update:", payload);
      });
      es.onerror = (err) => console.error("SSE error", err);

    Notes:
      - The backend uses PostgreSQL LISTEN/NOTIFY on channel 'attendance_events' when available.
        Payloads should be JSON and may include {"session_id": <id>} to optimize filtering.
      - If NOTIFY isn't available, the endpoint falls back to short-interval polling.
    """

    # PUBLIC_INTERFACE
    @jwt_required()
    def get(self) -> Response:
        """
        Start an SSE stream for attendance changes of a given session.

        Returns an HTTP Response with the appropriate SSE headers and a streaming body.
        """
        session_id_raw = request.args.get("sessionId")
        if not session_id_raw:
            # 400 Bad Request if sessionId missing
            return Response(
                json.dumps({"message": "Missing required query parameter: sessionId"}),
                status=400,
                mimetype="application/json",
            )

        try:
            session_id = int(session_id_raw)
        except ValueError:
            return Response(
                json.dumps({"message": "sessionId must be an integer"}),
                status=400,
                mimetype="application/json",
            )

        # Ensure response has proper SSE headers; CORS handled at app level via flask-cors
        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable proxy buffering where supported
        }
        generator: Iterable[str] = _attendance_events_stream(session_id)
        resp = sse_stream(generator)
        # Update headers for SSE explicitly
        for k, v in headers.items():
            resp.headers[k] = v
        return resp
