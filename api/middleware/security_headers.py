"""
Security headers on every response (also on 401 / 429 / 413 answers, so this
middleware sits OUTSIDE the auth middleware).

  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Cache-Control: no-store            (only if the endpoint set none itself)
  Strict-Transport-Security          only when the request came in over HTTPS
                                     (directly, or via a proxy that says so in
                                     X-Forwarded-Proto). The proxy (nginx) sets
                                     it as well; here it is a safety net.
  X-Accel-Buffering: no              on Server-Sent-Events responses, so that an
                                     nginx in front streams the chat answer
                                     token by token instead of buffering it.
"""

HSTS_VALUE = b"max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        forwarded_proto = dict(scope["headers"]).get(b"x-forwarded-proto", b"").split(b",")[0].strip().lower()
        is_https = scope.get("scheme") == "https" or forwarded_proto == b"https"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}

                def add(name: bytes, value: bytes) -> None:
                    if name not in present:
                        headers.append((name, value))
                        present.add(name)

                add(b"x-content-type-options", b"nosniff")
                add(b"x-frame-options", b"DENY")
                add(b"referrer-policy", b"no-referrer")
                add(b"cache-control", b"no-store")
                if is_https:
                    add(b"strict-transport-security", HSTS_VALUE)

                content_type = next((v for n, v in headers if n.lower() == b"content-type"), b"")
                if content_type.startswith(b"text/event-stream"):
                    add(b"x-accel-buffering", b"no")

                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
