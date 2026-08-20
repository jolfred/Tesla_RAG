def build_vk_post(
    id: int = 1,
    text: str = "Post text",
    owner_id: int = -12345,
    date: int = 1704067200,
    from_id: int | None = None,
) -> dict:
    return {
        "id": id,
        "owner_id": owner_id,
        "from_id": from_id or owner_id,
        "date": date,
        "text": text,
        "attachments": [],
        "comments": {"count": 0},
        "likes": {"count": 0},
        "reposts": {"count": 0},
        "views": {"count": 0},
    }
