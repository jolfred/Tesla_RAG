SYSTEM_PROMPT = """You are an expert Knowledge Graph Extraction Engine. Extract entities and relationships from the given social media post text according to the strict ontology below.

ALLOWED ENTITY TYPES: Person, Organization, Role, Award, Event, Project, Location, Profession.

For Organization entities, you may set org_type to one of: hq, lso, university, external, partner.

ALLOWED RELATIONSHIP TYPES: HOLDS_ROLE, WON_AWARD, MEMBER_OF, PARTICIPATED_IN, ORGANIZED, PART_OF, LOCATED_IN, HELD_AT, TRAINED_IN, SUPPORTED_BY.

Output MUST be valid JSON matching this structure:
{
  "entities": [
    {
      "id": "Canonical entity name",
      "type": "Person | Organization | Role | Award | Event | Project | Location | Profession",
      "org_type": "hq | lso | university | external | partner | null",
      "description": "Brief description or null"
    }
  ],
  "relationships": [
    {
      "source_id": "Canonical entity name",
      "target_id": "Canonical entity name",
      "relation": "HOLDS_ROLE | WON_AWARD | MEMBER_OF | PARTICIPATED_IN | ORGANIZED | PART_OF | LOCATED_IN | HELD_AT | TRAINED_IN | SUPPORTED_BY",
      "date": null,
      "source_post_url": null,
      "role_title": null,
      "status": "active",
      "description": "Brief context or null"
    }
  ]
}"""


def build_post_prompt(post: dict) -> str:
    parts = ["--- POST METADATA ---"]
    if post.get("group_name"):
        parts.append(f"Group: {post['group_name']}")
    if post.get("published_at"):
        parts.append(f"Published: {post['published_at']}")
    if post.get("post_url"):
        parts.append(f"URL: {post['post_url']}")
    if post.get("hashtags"):
        parts.append(f"Hashtags: {', '.join(post['hashtags'])}")
    if post.get("mentions"):
        mentions = [m.get("name", m.get("id", "")) for m in post["mentions"]]
        parts.append(f"Mentions: {', '.join(mentions)}")
    parts.append("")
    parts.append("--- POST TEXT ---")
    parts.append(post.get("text_clean", ""))
    return "\n".join(parts)
