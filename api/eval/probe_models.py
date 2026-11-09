"""
Which Mistral chat models can THIS API key actually use, and with which limits?

The Limits page in the Mistral console also lists models the plan has no
access to (they answer 403 "not available in your subscription tier").
This sends one tiny request (a few tokens) per model, one per ~1.5 s, and
prints the result plus the rate-limit headers Mistral sends back.

Run from the api/ folder:
    python -m eval.probe_models
    python -m eval.probe_models mistral-small-2603 glm-5-2     # only these
"""

import asyncio
import sys

from eval.run_eval import load_env_file

CANDIDATES = [
    "ministral-8b-2512",
    "ministral-14b-2512",
    "ministral-3b-2512",
    "mistral-small-2603",
    "mistral-small-latest",
    "mistral-medium-latest",
    "mistral-large-2512",
    "mistral-large-4",
    "deepseek-v4-1-flash-1017",
    "glm-5-2",
    "zai-glm-5-3",
    "zai-glm-5-3-flash",
]


async def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    load_env_file()
    from mistralai.client import Mistral
    from settings import settings
    from llm.mistral import _rate_limit_info

    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    models = sys.argv[1:] or CANDIDATES
    messages = [{"role": "user", "content": "Antworte nur mit: ok"}]

    print(f"{'model':<28} result")
    for model in models:
        try:
            resp = await client.chat.complete_async(model=model, messages=messages, max_tokens=5)
            text = (resp.choices[0].message.content or "").strip()
            print(f"{model:<28} OK  answer={text!r}")
        except Exception as e:
            status = getattr(e, "status_code", "?")
            info, _ = _rate_limit_info(e)
            body = str(getattr(e, "body", "") or e)
            reason = (
                "no access on this plan" if status == 403
                else "rate limited" if status == 429
                else "unknown model" if status in (400, 404, 422)
                else "error"
            )
            print(f"{model:<28} HTTP {status} ({reason})"
                  + (f" | limits: {info}" if info else "")
                  + ("" if status in (403, 429) else f" | {body[:120]}"))
        await asyncio.sleep(1.5)


if __name__ == "__main__":
    asyncio.run(main())
    