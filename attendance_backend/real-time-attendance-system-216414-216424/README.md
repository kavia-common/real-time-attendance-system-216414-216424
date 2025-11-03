# real-time-attendance-system-216414-216424

## Realtime SSE for Attendance

The backend exposes a Server-Sent Events (SSE) endpoint to receive real-time attendance updates for a session.

- Endpoint: `GET /realtime/attendance?sessionId=<id>`
- Auth: Requires a valid Bearer JWT (same as other endpoints)
- Event name: `update`
- Data: JSON payload `{ "session_id": <int>, "changes": [ { row... } ] }`
- Headers: `text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`

Server behavior:
- Attempts to use PostgreSQL `LISTEN/NOTIFY` on the channel `attendance_events` (overridable via `ATTENDANCE_EVENTS_CHANNEL`).
- If `LISTEN/NOTIFY` is not available, falls back to polling with interval `REALTIME_POLL_INTERVAL_SEC` (default 2s).
- Sends periodic heartbeat comments to keep the connection alive.

Example (JavaScript):
```js
const url = new URL('/realtime/attendance', 'https://<backend-host>');
url.searchParams.set('sessionId', 123);

const es = new EventSource(url);
es.addEventListener('update', (ev) => {
  const payload = JSON.parse(ev.data);
  console.log('Attendance update:', payload);
});
es.onerror = (err) => console.error('SSE error', err);
```

Notify producers (optional):
If database triggers or application code send `NOTIFY attendance_events` with a JSON payload like `{"session_id": 123}`, listeners for different sessions will filter efficiently.

Environment variables (configure in .env, not checked into source):
- `POSTGRES_URL` (required): SQLAlchemy Postgres URL, e.g., `postgresql+psycopg2://USER:PASS@HOST:PORT/DBNAME`
- `CORS_ORIGINS` (optional): CORS allowed origins, default `*`
- `ATTENDANCE_EVENTS_CHANNEL` (optional): Channel name for LISTEN/NOTIFY, default `attendance_events`
- `REALTIME_POLL_INTERVAL_SEC` (optional): Polling interval seconds, default `2.0`
- `REALTIME_HEARTBEAT_INTERVAL_SEC` (optional): Heartbeat interval seconds, default `15.0`
