"""
Request authentication between the Moodle plugin and this backend.

Every request must be signed by the plugin with the shared secret
(MOODLE_SECRET here, "api_secret" in the plugin settings). The signature
covers everything the backend trusts:

    HMAC-SHA256(secret,
        "v2\\n" + timestamp + "\\n" + METHOD + "\\n" + path + "\\n"
        + user_id + "\\n" + enrolled_courses + "\\n" + sha256(body))

so none of these can be changed without the secret: not the user, not the
list of courses the user is enrolled in, not the endpoint, not the body.

Headers sent by the plugin:
    X-Timestamp         unix seconds
    X-Signature         hex HMAC (see above)
    X-User-Id           Moodle user id ("0" = system call, e.g. re-indexing)
    X-Enrolled-Courses  optional, base64url(JSON {"<course id>": "<full name>"})

On success the verified identity is put on the request
(request.state.auth -> AuthContext); endpoints must take the user id and the
course list from there and never from anything else.

This is a plain ASGI middleware (not BaseHTTPMiddleware) on purpose: it must
not interfere with Server-Sent-Events streaming responses.
"""
import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field

SIGNATURE_VERSION = "v2"
MAX_CLOCK_SKEW_SECONDS = 300          # replay protection window
MAX_BODY_BYTES = 20 * 1024 * 1024     # ~8 MB image as base64 is ~11 MB


@dataclass(frozen=True)
class AuthContext:
    """The verified identity of the caller, as stated (and signed) by Moodle."""
    user_id: int
    enrolled_courses: dict[int, str] = field(default_factory=dict)


def compute_signature(
    secret: str,
    timestamp: str,
    method: str,
    path: str,
    user_id: str,
    enrolled_courses: str,
    body: bytes,
) -> str:
    message = "\n".join([
        SIGNATURE_VERSION,
        timestamp,
        method.upper(),
        path,
        user_id,
        enrolled_courses,
        hashlib.sha256(body).hexdigest(),
    ])
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def decode_enrolled_courses(value: str) -> dict[int, str]:
    """base64url(JSON object) -> {course_id: full name}. Empty -> {}."""
    if not value:
        return {}
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("enrolled courses must be a JSON object")
    return {int(course_id): str(name) for course_id, name in data.items()}


def _log_reject(scope, detail: str, headers: dict | None = None) -> None:
    """Server-side reason for a rejected request (never the secret or the signature)."""
    present = sorted(k for k in (headers or {}) if k.startswith("x-"))
    print(f"[auth] {scope['method']} {scope['path']} rejected: {detail} | x-headers present: {present}", flush=True)


async def _send_json(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body})


class HMACAuthMiddleware:
    def __init__(self, app, secret: str, exempt_paths: frozenset[str] = frozenset()):
        if not secret:
            raise RuntimeError("MOODLE_SECRET is empty: refusing to start without request signing")
        self.app = app
        self.secret = secret
        self.exempt_paths = exempt_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_path = scope.get("raw_path")
        path = raw_path.decode("latin-1") if raw_path else scope["path"]
        # Some servers include the query string in raw_path; the signature never does.
        path = path.split("?", 1)[0]

        if path in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        # --- read the whole body (needed for the signature) -----------------
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            if len(body) > MAX_BODY_BYTES:
                await _send_json(send, 413, "Request body too large")
                return
            more_body = message.get("more_body", False)

        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        timestamp = headers.get("x-timestamp", "")
        signature = headers.get("x-signature", "")
        user_id_raw = headers.get("x-user-id", "")
        courses_raw = headers.get("x-enrolled-courses", "")

        if not timestamp or not signature or not user_id_raw:
            _log_reject(scope, "missing authentication headers", headers)
            await _send_json(send, 401, "Missing authentication headers")
            return

        expected = compute_signature(
            self.secret, timestamp, scope["method"], path,
            user_id_raw, courses_raw, body,
        )
        if not hmac.compare_digest(signature, expected):
            _log_reject(scope, f"invalid signature (user={user_id_raw!r}, courses_header_len={len(courses_raw)}, body_len={len(body)})", headers)
            await _send_json(send, 401, "Invalid signature")
            return

        # Signature is valid -> the values below are exactly what Moodle sent.
        try:
            if abs(time.time() - int(timestamp)) > MAX_CLOCK_SKEW_SECONDS:
                _log_reject(scope, f"request expired (clock skew {int(time.time()) - int(timestamp)}s)", headers)
                await _send_json(send, 401, "Request expired")
                return
            user_id = int(user_id_raw)
            if user_id < 0:
                raise ValueError("negative user id")
            enrolled = decode_enrolled_courses(courses_raw)
        except (ValueError, binascii.Error, UnicodeDecodeError):
            await _send_json(send, 400, "Malformed authentication headers")
            return

        scope.setdefault("state", {})["auth"] = AuthContext(
            user_id=user_id, enrolled_courses=enrolled,
        )

        # Hand the already-read body to the application, then pass on whatever
        # the server sends afterwards (e.g. the client-disconnect message).
        body_sent = False

        async def replay_receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)
