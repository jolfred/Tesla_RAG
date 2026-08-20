import json
import re
import uuid
from openai import OpenAI
from backend.config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL, OLLAMA_MODEL,
    PROXYAPI_KEY, PROXYAPI_BASE_URL, PROXYAPI_MODEL,
    LLAMACPP_BASE_URL, LLAMACPP_MODEL,
    GIGACHAT_MODEL,
)
from backend.utils.gigachat_client import GigaChatClient, _DEFAULT_SCHEMA
from backend.utils.logger import setup_logger

logger = setup_logger("entity_extractor")

SYSTEM_PROMPT = """You are an expert Knowledge Graph Extraction Engine specializing in processing unstructured text from youth organization channels and student squad posts.

Your task is to analyze the input text and extract all entities (nodes) and relationships (edges) to construct a structured Knowledge Graph according to the strict Ontology specified below.

EXTENDED KNOWLEDGE GRAPH ONTOLOGY DEFINITION

1. ALLOWED ENTITY TYPES (NODES):
   - Person: Individuals, squad members, commanders, alumni, or guests.
   - Organization: HQ, student squads, universities, external partners, or grantors.
     * Required property for Organization: `org_type` ('hq', 'lso', 'university', 'external', 'partner').
   - Role: Official positions (e.g., Commander, Commissar, Master, Press Head).
   - Award: Contest nominations, titles, grand prix, or honors (e.g., "Номинация «Лучший командир ЛСО»").
   - Event: Competitions, rallies, forums, festivals, or celebrations.
   - Project: Seasonal labor projects, community campaigns, or grant projects (e.g., "Снежный десант", "ВСПрО «КАМАЗ»").
   - Location: Geographical places, cities, districts, venue halls, or university rooms (e.g., "Верхнеуслонский район", "г. Озёрск", "ДК им. Ленина", "Д-304 КГЭУ").
   - Profession: Working specialties and trades (e.g., "Электромонтажник 3-го разряда", "Рыбовод").

2. ALLOWED RELATIONSHIP TYPES (EDGES):
   - HOLDS_ROLE: Connects Person -> Organization/Role. Official leadership or operational position.
   - WON_AWARD: Connects Person/Organization -> Award. Winning a competition, nomination, or receiving official gratitude.
   - MEMBER_OF: Connects Person -> Organization. General squad or team membership.
   - PARTICIPATED_IN: Connects Person/Organization -> Event/Project. Participation in events, sports, or work projects.
   - ORGANIZED: Connects Organization -> Event/Project. Who hosted or organized the initiative.
   - PART_OF: Connects Organization -> Organization. Structural hierarchy (e.g., LSO -> HQ).
   - LOCATED_IN / HELD_AT: Connects Event/Project/Organization -> Location. Where an event took place or where a project operated.
   - TRAINED_IN: Connects Person/Organization -> Profession. Vocational training courses offered or completed.
   - SUPPORTED_BY: Connects Event/Project -> Organization. Financial or administrative backing.

3. REQUIRED EDGE PROPERTIES:
   - `date` (string or null): The precise date or period in ISO format (YYYY-MM-DD or YYYY-MM or YYYY).
   - `role_title` (string or null): Exact position title in Russian if relation == HOLDS_ROLE.
   - `status` (string): Role status if relation == HOLDS_ROLE ('active' or 'ex').
   - `description` (string or null): Short contextual summary of the relationship.

EXTRACTION RULES

1. Entity Canonization:
   - Use full canonical Russian names for entities.
   - Strip social media tags (e.g., "[id|Name]" -> "Name").

2. Roles vs. Contest Awards:
   - Do NOT confuse winning a contest award with holding an official organizational leadership position.
   - If a person wins a contest (e.g., "Лучший командир года"), use WON_AWARD pointing to an Award entity.
   - Use HOLDS_ROLE ONLY for actual operational leadership positions.

3. Dates & Timeline:
   - Map header post timestamps (e.g., "--- [ДАТА:04.03.2026 16:31] ---") to edge `date`.

4. Output Format:
   Output MUST be valid JSON strictly matching this structure:

{
  "entities": [
    {
      "id": "Canonical Entity Name",
      "type": "Person | Organization | Role | Award | Event | Project | Location | Profession",
      "org_type": "hq | lso | university | external | partner | null",
      "description": "Brief description"
    }
  ],
  "relationships": [
    {
      "source_id": "Canonical Entity Name",
      "target_id": "Canonical Entity Name",
      "relation": "HOLDS_ROLE | WON_AWARD | MEMBER_OF | PARTICIPATED_IN | ORGANIZED | PART_OF | LOCATED_IN | HELD_AT | TRAINED_IN | SUPPORTED_BY",
      "date": "2026-03-04",
      "role_title": "Position title or null",
      "status": "active | ex",
      "description": "Brief context"
    }
  ]
}"""


class EntityExtractor:
    def __init__(self):
        self._client = None
        self._model = None
        self._gigachat = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        provider = LLM_PROVIDER

        if provider == "gigachat":
            self._gigachat = GigaChatClient()
            self._client = self._gigachat
            self._model = GIGACHAT_MODEL
            return self._client

        if provider == "ollama":
            try:
                self._client = OpenAI(
                    base_url=OLLAMA_BASE_URL.rstrip("/") + "/v1",
                    api_key="ollama",
                )
                self._model = OLLAMA_MODEL
            except Exception as e:
                logger.warning(f"Ollama client init failed: {e}")
                self._client = None

        elif provider == "proxyapi":
            try:
                self._client = OpenAI(
                    base_url=PROXYAPI_BASE_URL,
                    api_key=PROXYAPI_KEY,
                )
                self._model = PROXYAPI_MODEL
            except Exception as e:
                logger.warning(f"ProxyAPI client init failed: {e}")
                self._client = None

        elif provider == "llamacpp":
            try:
                self._client = OpenAI(
                    base_url=LLAMACPP_BASE_URL,
                    api_key="no-key-required",
                )
                self._model = LLAMACPP_MODEL
            except Exception as e:
                logger.warning(f"llama.cpp client init failed: {e}")
                self._client = None

        else:
            logger.warning(f"Unknown LLM provider: {provider}")
            self._client = None

        return self._client

    def extract(self, chunk_text: str, source: str = "") -> dict:
        client = self._get_client()
        if client is None or self._model is None:
            return self._fallback_extract(chunk_text)

        try:
            if isinstance(client, GigaChatClient):
                parsed = client.extract_json(
                    SYSTEM_PROMPT, chunk_text, schema=_DEFAULT_SCHEMA
                )
            else:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": chunk_text},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=16384,
                )
                raw = response.choices[0].message.content.strip()
                raw = re.sub(r'^```json\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw)
                parsed = json.loads(raw)

            entities = parsed.get("entities", [])
            relationships = parsed.get("relationships", [])

            for e in entities:
                if "id" not in e or "type" not in e:
                    raise ValueError(f"Entity missing id or type: {e}")
            for r in relationships:
                if "source_id" not in r or "target_id" not in r or "relation" not in r:
                    raise ValueError(f"Relationship missing required fields: {r}")

            return {"entities": entities, "relationships": relationships}
        except Exception as e:
            logger.error(f"Entity extraction failed for '{source}': {e}")
            return self._fallback_extract(chunk_text)

    def _fallback_extract(self, text: str) -> dict:
        return {"entities": [], "relationships": []}
