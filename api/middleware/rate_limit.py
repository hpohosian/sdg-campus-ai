"""
Rate limiting per Moodle user.

Every request to this backend comes from the Moodle server, so the client IP
says nothing about WHO is asking. The user id from the signed request
(request.state.auth, set by HMACAuthMiddleware) is the right key. This
middleware therefore has to sit INSIDE the auth middleware (added before it
in main.py).

Two budgets per user and minute:
  * "llm"     -- everything that makes the backend call the language model
                 (send / stream / edit / regenerate): expensive, strict.
  * "general" -- everything else (session list, messages, images, ...).

Sliding window, kept in memory: fine for the single uvicorn process this
backend runs as (see the Dockerfile). With several workers the counters would
have to move to Redis or the database.

Calls with user id 0 (system calls such as re-indexing) and /health are not
limited. A limit of 0 switches that budget off.
"""
import json
import math
import re
import time
from collections import deque

WINDOW_SECONDS = 60.0

# POST .../messages, .../messages/stream, .../messages/<id>/edit/stream,
# .../messages/<id>/regenerate/stream  (NOT .../messages/partial or /image)
_LLM_PATH = re.compile(
    r"^/sessions/[^/]+/messages(?:/stream)?$"
    r"|^/sessions/[^/]+/messages/\d+/(?:edit|regenerate)/stream$"
)


class SlidingWindowLimiter:
    def __init__(self, limit: int, window: float = WINDOW_SECONDS, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits: dict[str, deque] = {}
        self._calls = 0

    def check(self, key: str) -> float | None:
        """Counts this request. Returns None if allowed, else seconds until a slot frees up."""
        if self.limit <= 0:
            return None

        now = self.clock()
        cutoff = now - self.window
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= cutoff:
            hits.popleft()

        self._calls += 1
        if self._calls % 1000 == 0:
            self._drop_idle_keys(cutoff)

        if len(hits) >= self.limit:
            return max(hits[0] + self.window - now, 0.001)

        hits.append(now)
        return None

    def _drop_idle_keys(self, cutoff: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= cutoff]:
            del self._hits[key]


def _is_llm_request(method: str, path: str) -> bool:
    return method == "POST" and bool(_LLM_PATH.match(path))


class RateLimitMiddleware:
    def __init__(
        self,
        app,
        general_per_minute: int,
        llm_per_minute: int,
        exempt_paths: frozenset[str] = frozenset(),
        clock=time.monotonic,
    ):
        self.app = app
        self.exempt_paths = exempt_paths
        self.general = SlidingWindowLimiter(general_per_minute, clock=clock)
        self.llm = SlidingWindowLimiter(llm_per_minute, clock=clock)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        auth = scope.get("state", {}).get("auth")
        path = scope["path"]
        if auth is None or auth.user_id <= 0 or path in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        limiter = self.llm if _is_llm_request(scope["method"], path) else self.general
        retry_after = limiter.check(str(auth.user_id))
        if retry_after is not None:
            print(f"[rate-limit] user={auth.user_id} {scope['method']} {path} -> 429 (retry in {retry_after:.0f}s)", flush=True)
            body = json.dumps({"detail": "Too many requests, please slow down."}).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(max(1, math.ceil(retry_after))).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
