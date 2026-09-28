import time
import logging

log = logging.getLogger("timing")


class TimingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        start = time.perf_counter()
        first_byte = None
        status = None

        async def send_wrapper(message):
            nonlocal first_byte, status
            if message["type"] == "http.response.start":
                first_byte = time.perf_counter() - start
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            total = time.perf_counter() - start
            log.warning(
                "%s %s -> %s | first byte %.0f ms | total %.0f ms",
                scope["method"], scope["path"], status,
                (first_byte or 0) * 1000, total * 1000,
            )