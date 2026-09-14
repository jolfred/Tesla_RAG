import json
import re
import time
import uuid

import httpx
from openai import OpenAI

from backend.config import GIGACHAT_AUTH_KEY, GIGACHAT_MODEL
from backend.utils.logger import setup_logger

logger = setup_logger("gigachat_client")

_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_API_BASE = "https://api.giga.chat/v1"
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


class GigaChatClient:
    def __init__(self, base_url: str = _API_BASE, model: str | None = None):
        self._base_url = base_url
        self._model = model or GIGACHAT_MODEL
        self._token = None
        self._token_expires_at = 0.0
        self._client = None

    def _fetch_token(self) -> str:
        if not GIGACHAT_AUTH_KEY:
            raise RuntimeError("GIGACHAT_AUTH_KEY is not set")

        rq_uid = str(uuid.uuid4())
        response = httpx.post(
            _OAUTH_URL,
            data="scope=GIGACHAT_API_PERS",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": rq_uid,
                "Authorization": f"Basic {GIGACHAT_AUTH_KEY}",
            },
            verify=False,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token", "")
        expires_at = data.get("expires_at", 0)
        self._token = token
        self._token_expires_at = expires_at / 1000.0 if expires_at else time.time() + 1700
        logger.info("GigaChat access token obtained, expires at %.0f", self._token_expires_at)
        return token

    def _get_token(self) -> str:
        if not self._token or time.time() >= self._token_expires_at - 60:
            return self._fetch_token()
        return self._token

    def _get_client(self) -> OpenAI:
        token = self._get_token()
        if self._client is None:
            self._client = OpenAI(
                base_url=self._base_url,
                api_key=token,
                http_client=httpx.Client(verify=False, timeout=120.0),
            )
        else:
            self._client.api_key = token
        return self._client

    def get_models(self) -> list[dict]:
        client = self._get_client()
        data = client.models.list()
        return [m.model_dump() for m in data.data]

    def chat(self, messages: list[dict], **kwargs) -> str:
        # trace_sink (панель «Рентген»): список, куда дописывается полный обмен
        # {"messages": [...], "response": str} каждого вызова. Локальный список
        # вызывающей стороны — параллельные запросы не перемешиваются.
        trace_sink = kwargs.pop("trace_sink", None)
        client = self._get_client()
        model = kwargs.pop("model", None) or self._model
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kwargs.pop("temperature", 0.1),
            max_tokens=kwargs.pop("max_tokens", 4096),
            **kwargs,
        )
        content = response.choices[0].message.content
        result = (content or "").strip()
        if trace_sink is not None:
            trace_sink.append(
                {
                    "messages": [dict(m) for m in messages],
                    "response": result,
                }
            )
        return result

    def extract_json(
        self,
        system_prompt: str,
        text: str,
        schema: dict | None = None,
        model: str | None = None,
        max_retries: int = 2,
        trace_sink: list | None = None,
    ) -> dict:
        response_format = {
            "type": "json_schema",
            "schema": schema or _DEFAULT_SCHEMA,
            "strict": True,
        }
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
                    trace_sink=trace_sink,
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
                    "GigaChat JSON parse failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
        raise last_error
