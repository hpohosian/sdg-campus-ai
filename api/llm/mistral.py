import asyncio
from typing import Any, AsyncIterator
from mistralai.client import Mistral
from llm.base import BaseLLM, Message
from settings import settings

# Fallback if MISTRAL_VISION_MODEL isn't set in settings/.env yet — Pixtral
# as a standalone model line has been deprecated by Mistral; vision is now
# folded into their regular chat models. mistral-small-latest is Mistral's
# own default in their vision docs examples. Override via
# settings.MISTRAL_VISION_MODEL if you want mistral-medium-2508 /
# mistral-large-2512 for higher accuracy on harder images.
_DEFAULT_VISION_MODEL = "mistral-small-latest"


# Mistral answers 429 when the key's per-second / per-minute limit is hit
# (e.g. a second question right after the first, while the auto-title and
# translations of the first one are still running) and 429/503 when it is
# out of capacity. Both pass within a few seconds, so wait and retry
# instead of failing the student's question.
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RETRY_DELAYS = (1, 2, 4, 8)   # seconds; ~15 s in total at most


def _rate_limit_info(e: Exception) -> tuple[str, float | None]:
    """
    Mistral's x-ratelimit-* headers of a failed response, e.g.
    "req-minute 0/60, tokens-minute 120/500000", and Retry-After if sent.
    Tells WHICH limit is hit (requests or tokens) and how big it is.
    """
    headers = getattr(e, "headers", None)
    if headers is None:
        # mistralai: e.raw_response, openai (KI:connect): e.response
        raw = getattr(e, "raw_response", None) or getattr(e, "response", None)
        headers = getattr(raw, "headers", None)
    if not headers:
        return "", None
    parts = []
    for key, value in headers.items():
        k = key.lower()
        if k.startswith("x-ratelimit-limit-"):
            name = k[len("x-ratelimit-limit-"):]
            remaining = headers.get(f"x-ratelimit-remaining-{name}", "?")
            parts.append(f"{name} {remaining}/{value}")
    retry_after = None
    try:
        retry_after = float(headers.get("retry-after")) if headers.get("retry-after") else None
    except (TypeError, ValueError):
        pass
    return ", ".join(parts), retry_after


class _Throttle:
    """
    Spaces out request STARTS per model: at most `rps` requests per second
    leave this process; the rest wait their turn (FIFO). Waiting here costs
    a second or two, a 429 costs a whole retry cycle — or the answer.
    """
    _next_slot: dict[str, float] = {}
    _locks: dict[str, asyncio.Lock] = {}

    @classmethod
    async def wait(cls, model: str) -> None:
        rps = float(getattr(settings, "MISTRAL_MAX_RPS", 0) or 0)
        if rps <= 0:
            return
        interval = 1.0 / rps
        lock = cls._locks.setdefault(model, asyncio.Lock())
        async with lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            slot = max(now, cls._next_slot.get(model, 0.0))
            cls._next_slot[model] = slot + interval
        if slot > now:
            await asyncio.sleep(slot - now)


async def _with_retry(call, what: str, model: str | None = None):
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        if model:
            await _Throttle.wait(model)
        try:
            return await call()
        except Exception as e:
            status = getattr(e, "status_code", None)
            if delay is None or status not in _RETRY_STATUS:
                if status == 429:
                    info, _ = _rate_limit_info(e)
                    print(f"[mistral] {what}: HTTP 429, giving up | limits (remaining/limit): {info or 'no headers'}")
                raise
            info, retry_after = _rate_limit_info(e)
            if retry_after:
                delay = min(max(delay, retry_after), 20)
            print(f"[mistral] {what}: HTTP {status}, retry {attempt + 1}/{len(_RETRY_DELAYS)} in {delay}s"
                  + (f" | limits (remaining/limit): {info}" if info else ""))
            await asyncio.sleep(delay)


class MistralLLM(BaseLLM):
    """
    Mistral implementation of the BaseLLM interface.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None
    ):
        self.api_key = api_key or settings.MISTRAL_API_KEY

        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY is not set")

        self.model = model or settings.MISTRAL_MODEL
        self.vision_model = getattr(settings, "MISTRAL_VISION_MODEL", None) or _DEFAULT_VISION_MODEL

        self.client = Mistral(api_key=self.api_key)

    @staticmethod
    def _contains_image(messages: list[Message]) -> bool:
        """True if any message content includes an image_url block."""
        for m in messages:
            content = m.get("content") if isinstance(m, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    return True
        return False

    def _resolve_model(self, messages: list[Message], explicit_model: str | None) -> str:
        if explicit_model:
            return explicit_model
        if self._contains_image(messages):
            return self.vision_model
        return self.model

    async def chat(
        self,
        messages: list[Message],
        **kwargs: Any
    ) -> str:
        """
        Send a request to the Mistral API and return the full response text.

        Uses the SDK's async method: the sync variant would block the whole
        event loop (every other request) for the duration of the API call.
        """
        model = self._resolve_model(messages, kwargs.pop("model", None))

        response = await _with_retry(
            lambda: self.client.chat.complete_async(model=model, messages=messages, **kwargs),
            "chat",
            model,
        )

        if not response.choices:
            raise ValueError("No response choices returned from Mistral API")

        content = response.choices[0].message.content

        if not content:
            raise ValueError("Empty response content returned from Mistral API")

        return content

    async def stream(
        self,
        messages: list[Message],
        **kwargs: Any
    ) -> AsyncIterator[str]:

        model = self._resolve_model(messages, kwargs.pop("model", None))

        # Retried only while opening the stream (that is where 429 comes):
        # once tokens reach the student, a retry would duplicate text.
        stream = await _with_retry(
            lambda: self.client.chat.stream_async(model=model, messages=messages, **kwargs),
            "stream",
            model,
        )

        async for chunk in stream:
            if chunk.data.choices:
                delta = chunk.data.choices[0].delta.content
                if delta:
                    yield delta
                    