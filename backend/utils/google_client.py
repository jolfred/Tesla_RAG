import json
import re
from openai import OpenAI
from backend.config import GOOGLE_AI_STUDIO_KEY, GOOGLE_BASE_URL, GOOGLE_MODEL
from backend.utils.logger import setup_logger

logger = setup_logger("google_client")

_THOUGHT_RE = re.compile(r"<thought>.*?</thought>", re.DOTALL)


class GoogleClient:
    def __init__(self):
        self._client = None
        self._model = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        if not GOOGLE_AI_STUDIO_KEY:
            logger.warning("GOOGLE_AI_STUDIO_KEY is not set")
            return None

        try:
            self._client = OpenAI(
                base_url=GOOGLE_BASE_URL,
                api_key=GOOGLE_AI_STUDIO_KEY,
            )
            self._model = GOOGLE_MODEL
        except Exception as e:
            logger.warning(f"Google AI Studio client init failed: {e}")
            self._client = None

        return self._client

    def chat(self, messages: list[dict], **kwargs) -> str:
        client = self._get_client()
        if client is None or self._model is None:
            raise RuntimeError("Google AI Studio client is not available")

        model = kwargs.pop("model", self._model)
        max_completion_tokens = kwargs.pop("max_completion_tokens", None)
        kwargs.pop("max_tokens", None)
        completion_kwargs: dict = {}
        if max_completion_tokens is not None:
            completion_kwargs["max_completion_tokens"] = max_completion_tokens
        else:
            completion_kwargs["max_tokens"] = 8192
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kwargs.pop("temperature", 0.1),
            **completion_kwargs,
            **kwargs,
        )
        content = response.choices[0].message.content
        return _THOUGHT_RE.sub("", content or "").strip()

    def extract_json(self, system_prompt: str, text: str) -> dict:
        raw = self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
        )
        return _extract_json_object(raw)


def _extract_json_object(text: str) -> dict:
    content = _THOUGHT_RE.sub("", text or "")
    start = content.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in response: {text[:200]}...")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(content)):
        ch = content[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = content[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    break
    raise ValueError(f"Could not extract JSON object from response: {text[:200]}...")
