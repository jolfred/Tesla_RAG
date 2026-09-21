import json
import re
import threading
import time

import httpx
from openai import OpenAI

from backend.config import GEMMA_BASE_URL, GEMMA_MODEL, GEMMA_RPM, GOOGLE_AI_STUDIO_KEY
from backend.utils.logger import setup_logger

logger = setup_logger("gemma_client")

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_DEFAULT_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "org_type": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                },
                "required": ["id", "type", "org_type", "description"],
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "relation": {"type": "string"},
                    "date": {"type": ["string", "null"]},
                    "source_post_url": {"type": ["string", "null"]},
                    "role_title": {"type": ["string", "null"]},
                    "status": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                },
                "required": [
                    "source_id",
                    "target_id",
                    "relation",
                    "date",
                    "source_post_url",
                    "role_title",
                    "status",
                    "description",
                ],
            },
        },
    },
    "required": ["entities", "relationships"],
}


class RateLimiter:
    def __init__(self, rpm: int):
        self._rpm = max(1, rpm)
        self._lock = threading.Lock()
        self._timestamps: list[float] = []

    def wait(self):
        while True:
            with self._lock:
                now = time.monotonic()
                cutoff = now - 60.0
                self._timestamps = [t for t in self._timestamps if t > cutoff]
                if len(self._timestamps) < self._rpm:
                    self._timestamps.append(now)
                    return
                sleep_for = self._timestamps[0] + 60.0 - now
            if sleep_for > 0:
                time.sleep(sleep_for)


class GemmaClient:
    def __init__(
        self,
        base_url: str = GEMMA_BASE_URL,
        model: str | None = None,
        rpm: int | None = None,
    ):
        from backend.admin.secrets import get_secret

        api_key = get_secret("GOOGLE_AI_STUDIO_KEY", GOOGLE_AI_STUDIO_KEY)
        if not api_key:
            raise RuntimeError("GOOGLE_AI_STUDIO_KEY is not set")
        self._base_url = base_url
        self._model = model or GEMMA_MODEL
        self._limiter = RateLimiter(rpm if rpm else GEMMA_RPM)
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=api_key,
            http_client=httpx.Client(),
        )

    def chat(self, messages: list[dict], **kwargs) -> str:
        self._limiter.wait()
        model = kwargs.pop("model", None) or self._model
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kwargs.pop("temperature", 0.1),
            max_tokens=kwargs.pop("max_tokens", 4096),
            **kwargs,
        )
        content = response.choices[0].message.content
        return (content or "").strip()

    def extract_json(
        self,
        system_prompt: str,
        text: str,
        schema: dict | None = None,
        model: str | None = None,
        max_retries: int = 2,
    ) -> dict:
        response_format = {"type": "json_object"}
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                raw = self.chat(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text},
                    ],
                    model=model,
                    response_format=response_format,
                )
                match = _JSON_OBJECT_RE.search(raw)
                if not match:
                    raise ValueError(
                        f"Could not extract JSON object from response: {raw[:200]}..."
                    )
                return json.loads(match.group(0))
            except Exception as e:
                last_error = e
                logger.warning(
                    "Gemma JSON parse failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
        raise last_error
