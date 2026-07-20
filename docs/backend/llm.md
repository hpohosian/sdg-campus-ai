# LLM Layer & Translation

## Abstraction (`api/llm/base.py`)

`BaseLLM` is a minimal abstract interface with exactly two methods, both async:

```python
class BaseLLM(ABC):
    async def chat(self, messages: list[dict[str, str]], **kwargs) -> str: ...
    async def stream(self, messages: list[dict[str, str]], **kwargs) -> AsyncIterator[str]: ...
```

Every consumer in the codebase (`AIService`, `Translator`) depends only on this
interface, injected via `dependencies.get_llm()` — swapping the underlying provider means
writing one new `BaseLLM` subclass and changing `get_llm()`, with no changes needed
anywhere else.

## Mistral implementation (`api/llm/mistral.py`)

`MistralLLM(BaseLLM)` wraps the official `mistralai` Python SDK.

- Constructed with `api_key` (falls back to `settings.MISTRAL_API_KEY`) and `model`
  (falls back to `settings.MISTRAL_MODEL`); raises `ValueError` immediately if no API key
  is available at all.
- `chat(messages, **kwargs)` — calls `client.chat.complete(...)` (note: this is the
  **synchronous** SDK method, called from inside an `async def` — it blocks the event
  loop for the duration of the API call rather than truly yielding control; this matters
  under concurrent load, since a slow Mistral response would stall other requests being
  served by the same worker process). Raises `ValueError` if the API returns no choices
  or empty content.
- `stream(messages, **kwargs)` — calls `client.chat.stream_async(...)` (the actual async
  streaming method) and yields each non-empty `delta.content` as it arrives.

`**kwargs` is passed straight through to the Mistral SDK call in both methods, so any
Mistral-specific parameter (temperature, max_tokens, etc.) could be set by a caller today
without further backend changes — though no current caller in the codebase passes any.

## Where the LLM is called from

| Call site | Method | Purpose |
|---|---|---|
| `AIService.generate_response` | `chat()` | full (non-streaming) chat answer |
| `AIService.stream_response` | `stream()` | streaming chat answer |
| `AIService.generate_title` | `chat()` | short session title from the first exchange |
| `Translator.translate` | `chat()` | translating a stored message into a target language |

There is no caching or rate-limiting layer around any of these calls — every uncached
translation and every chat turn is a live Mistral API call.

## Translation (`api/translation/translator.py`)

`Translator` is a thin, single-purpose wrapper: it reuses `BaseLLM.chat()` as a
general-purpose translation engine rather than calling a dedicated translation API.

```python
_LANGUAGE_NAMES = {"en": "English", "de": "German", "ru": "Russian", "ua": "Ukrainian"}
```

> **Naming inconsistency to be aware of:** the translator's map uses the key `"ua"` for
> Ukrainian, while the Moodle frontend's language picker (and the session's stored
> `language` column) uses `"uk"` (the actual ISO 639-1 code for Ukrainian — see
> `templates/chatbot.mustache`, `data-language="uk"`). Because `_LANGUAGE_NAMES.get(code,
> code)` falls back to the raw code string when there's no match, selecting Ukrainian in
> the UI currently sends `target_language="uk"` to `Translator.translate`, which won't
> match the `"ua"` key — the system prompt ends up saying *"Translate the user's message
> into uk"* instead of *"...into Ukrainian"*. This still generally works because Mistral
> can usually infer the intent from the surrounding text and the "uk" ISO code, but it's
> a latent bug worth fixing by aligning the two key sets (recommend standardizing on
> `"uk"` everywhere, since it's the correct ISO code).

`translate(text, target_language)`:
- Returns the input unchanged if it's empty/whitespace-only (no wasted API call).
- Looks up a human-readable language name (or falls back to the raw code, per the note
  above).
- Sends a single system+user message pair instructing the model to translate, preserve
  markdown/links/code blocks exactly, and return only the translated text with no
  preamble or quotation marks.
- Returns the raw model output — **no post-processing or stripping** of the result
  (contrast with `AIService.generate_title`, which does strip quotes/whitespace on its
  output).

Translations are cached by the caller (`MessageService._translate_message`) in
`mdl_local_ai_system_message_translations`, keyed on `(message_id, language)` — the
`Translator` class itself has no awareness of caching; that's entirely the chatbot
module's responsibility.
