from enum import Enum


class NodeType(str, Enum):
    ORGANIZATION = "Organization"
    SQUAD = "Squad"
    PERSON = "Person"
    EVENT = "Event"
    PUBLICATION = "Publication"
    DOCUMENT = "Document"
    ACHIEVEMENT = "Achievement"
    PROJECT = "Project"
    DIRECTION = "Direction"
    TRADITION = "Tradition"
    LOCATION = "Location"


class RelationType(str, Enum):
    MEMBER_OF = "MEMBER_OF"
    COMMANDED = "COMMANDED"
    PARTICIPATED_IN = "PARTICIPATED_IN"
    ORGANIZED_BY = "ORGANIZED_BY"
    DESCRIBED_BY = "DESCRIBED_BY"
    DESCRIBES = "DESCRIBES"
    MENTIONS = "MENTIONS"
    HELD_AT = "HELD_AT"
    AWARDED = "AWARDED"
    INCLUDES = "INCLUDES"
    PART_OF = "PART_OF"
    HAS_TRADITION = "HAS_TRADITION"
    RELATES_TO = "RELATES_TO"


NODE_PROPS = {
    NodeType.ORGANIZATION: ["id", "name", "description"],
    NodeType.SQUAD: ["id", "name", "specialization", "description"],
    NodeType.PERSON: ["id", "name", "role"],
    NodeType.EVENT: ["id", "title", "date", "type", "description"],
    NodeType.PUBLICATION: ["id", "title", "date", "source", "url", "source_id"],
    NodeType.DOCUMENT: ["id", "title", "file_type", "source"],
    NodeType.ACHIEVEMENT: ["id", "title", "date", "level", "description"],
    NodeType.PROJECT: ["id", "name", "description", "period"],
    NodeType.DIRECTION: ["id", "name", "description"],
    NodeType.TRADITION: ["id", "name", "description"],
    NodeType.LOCATION: ["id", "name"],
}

REL_PROPS = {
    RelationType.MEMBER_OF: ["role"],
    RelationType.COMMANDED: ["year_start", "year_end"],
    RelationType.PARTICIPATED_IN: ["role"],
    RelationType.ORGANIZED_BY: [],
    RelationType.DESCRIBED_BY: [],
    RelationType.DESCRIBES: [],
    RelationType.MENTIONS: [],
    RelationType.HELD_AT: [],
    RelationType.AWARDED: ["year"],
    RelationType.INCLUDES: [],
    RelationType.PART_OF: [],
    RelationType.HAS_TRADITION: [],
    RelationType.RELATES_TO: [],
}
