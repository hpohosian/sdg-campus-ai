from llm.base import BaseLLM

_LANGUAGE_NAMES = {
    "en": "English",
    "de": "German",
    "ru": "Russian",
    "ua": "Ukrainian"
}

_TRANSLATE_SYSTEM_PROMPT = (
    "You are a translation engine. Translate the user's message into {target_language}. "
    "Preserve markdown formatting, links, and code blocks exactly as they are. "
    "Return ONLY the translated text — no preamble, no explanations, no quotation marks."
)


class Translator:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    async def translate(self, text: str, target_language: str) -> str:
        if not text or not text.strip():
            return text

        target_name = _LANGUAGE_NAMES.get(target_language, target_language)

        messages = [
            {"role": "system", "content": _TRANSLATE_SYSTEM_PROMPT.format(target_language=target_name)},
            {"role": "user", "content": text},
        ]

        return await self.llm.chat(messages)