import logging
import re

import emoji


logger = logging.getLogger("scraper.cleaners.text_cleaner")


def remove_emojis(text: str) -> str:
    return emoji.replace_emoji(text, replace="")


def extract_hashtags(text: str) -> tuple[str, list[str]]:
    hashtags = re.findall(r"#(\w+)", text)
    clean = re.sub(r"#\w+", "", text)
    return clean.strip(), hashtags


def process_mentions(text: str) -> tuple[str, list[dict]]:
    # Паттерн для VK-упоминаний: [id123|Имя] или [club456|Название]
    pattern = r"\[(id|club)(\d+)\|([^\]]+)\]"
    mentions = []
    for m in re.finditer(pattern, text):
        prefix, uid, name = m.groups()
        mentions.append({
            "id": f"{prefix}{uid}",
            "name": name.strip(),
            "raw": m.group(0),
        })
    clean = re.sub(pattern, r"\3", text)
    return clean.strip(), mentions


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: str) -> tuple[str, list[str], list[dict]]:
    text = remove_emojis(text)
    text, hashtags = extract_hashtags(text)
    text, mentions = process_mentions(text)
    text = normalize_whitespace(text)
    logger.debug("Очищено: %d хэштегов, %d упоминаний", len(hashtags), len(mentions))
    return text, hashtags, mentions
