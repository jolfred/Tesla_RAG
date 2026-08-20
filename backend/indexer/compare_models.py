import json
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from backend.indexer.indexer import _build_post_prompt, filter_posts, SYSTEM_PROMPT
from backend.utils.gemma_client import GemmaClient
from backend.utils.google_client import GoogleClient
from backend.utils.gigachat_client import GigaChatClient, _DEFAULT_SCHEMA

load_dotenv()

client = OpenAI(
    base_url=os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1"),
    api_key=os.getenv("PROXYAPI_KEY", ""),
)

client_openrouter = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_KEY", ""),
)

client_tokenrouter = OpenAI(
    base_url="https://api.tokenrouter.com/v1",
    api_key=os.getenv("tokenrouter_KEY", ""),
    timeout=180,
)

client_google = GoogleClient()

client_gigachat = GigaChatClient()

client_gemma = GemmaClient()

MODELS = [
    ("GigaChat-2-Pro",                         client_gigachat,     False),
    ("GigaChat-2",                             client_gigachat,     False),
    ("GigaChat-3-Ultra",                       client_gigachat,     False),
    ("Gemma-4-31b-it",                         client_gemma,        False),
]


def _call_model(model_name: str, model_client, kwargs: dict) -> str:
    if isinstance(model_client, GoogleClient):
        messages = kwargs.pop("messages")
        temperature = kwargs.pop("temperature", 0.1)
        max_tokens = kwargs.pop("max_tokens", 4096)
        kwargs.pop("response_format", None)
        kwargs.pop("model", None)
        return model_client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model_name,
            **kwargs,
        )
    if isinstance(model_client, GigaChatClient):
        messages = kwargs.pop("messages")
        temperature = kwargs.pop("temperature", 0.1)
        max_tokens = kwargs.pop("max_tokens", 4096)
        kwargs.pop("response_format", None)
        data = model_client.extract_json(
            messages[0]["content"],
            messages[1]["content"],
            schema=_DEFAULT_SCHEMA,
            model=model_name,
        )
        return json.dumps(data, ensure_ascii=False)
    if isinstance(model_client, GemmaClient):
        messages = kwargs.pop("messages")
        temperature = kwargs.pop("temperature", 0.1)
        max_tokens = kwargs.pop("max_tokens", 4096)
        kwargs.pop("response_format", None)
        data = model_client.extract_json(
            messages[0]["content"],
            messages[1]["content"],
            model=model_name,
        )
        return json.dumps(data, ensure_ascii=False)
    if "tokenrouter" in str(model_client.base_url):
        stream = model_client.chat.completions.create(
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        parts = []
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    parts.append(delta.content)
        return "".join(parts)
    response = model_client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()

JSONL_PATH = "storage/posts/posts_rso_tesla.jsonl"


def main() -> None:
    path = Path(JSONL_PATH)
    if not path.exists():
        print(f"File not found: {JSONL_PATH}")
        return

    posts_raw = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                posts_raw.append(json.loads(line))

    filtered = filter_posts(posts_raw)
    if len(filtered) < 3:
        print(f"Need at least 3 posts after filter, got {len(filtered)}")
        return

    sample = random.sample(filtered, 3)

    results = {m[0]: {"entities": 0, "relationships": 0, "times": []} for m in MODELS}

    for idx, post in enumerate(sample, 1):
        print(f"\n{'=' * 72}")
        print(f"===== POST {idx} =====")
        print(f"Group: {post.get('group_name', 'N/A')}")
        print(f"Published: {post.get('published_at', 'N/A')}")
        print(f"URL: {post.get('post_url', 'N/A')}")
        text_preview = (post.get("text_clean", "") or "")[:200]
        print(f"Text: {text_preview}...")
        print()

        prompt = _build_post_prompt(post)

        for model_name, model_client, use_json in MODELS:
            try:
                start = time.perf_counter()
                kwargs = dict(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                )
                if "gpt-5" in model_name:
                    kwargs["max_completion_tokens"] = 4096
                else:
                    kwargs["response_format"] = {"type": "json_object"}
                    kwargs["temperature"] = 0.1
                    kwargs["max_tokens"] = 4096
                raw = _call_model(model_name, model_client, kwargs)
                elapsed = time.perf_counter() - start

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    print(f"--- {model_name} ({elapsed:.2f}s) ---")
                    print(f"  RAW (non-JSON): {raw[:500]}")
                    print()
                    continue
                n_ent = len(data.get("entities", []))
                n_rel = len(data.get("relationships", []))

                results[model_name]["entities"] += n_ent
                results[model_name]["relationships"] += n_rel
                results[model_name]["times"].append(elapsed)

                print(f"--- {model_name} ({elapsed:.2f}s) ---")
                print(f"  entities: {n_ent}  relationships: {n_rel}")
                print(f"  response: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
                print()
            except Exception as e:
                print(f"--- {model_name} ---")
                print(f"  ERROR: {e}")
                print()

    print(f"\n{'=' * 72}")
    print("===== SUMMARY =====")
    print(f"{'Model':<40} {'Entities':>10} {'Relations':>10} {'Avg time':>10}")
    print("-" * 72)
    for model_name, *_ in MODELS:
        r = results[model_name]
        avg = sum(r["times"]) / len(r["times"]) if r["times"] else 0
        print(f"{model_name:<40} {r['entities']:>10} {r['relationships']:>10} {avg:>8.2f}s")
    print()


if __name__ == "__main__":
    main()
