from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    Person = "Person"
    Organization = "Organization"
    Role = "Role"
    Award = "Award"
    Event = "Event"
    Project = "Project"
    Location = "Location"
    Profession = "Profession"


class OrgType(str, Enum):
    hq = "hq"
    lso = "lso"
    university = "university"
    external = "external"
    partner = "partner"


class RelationType(str, Enum):
    HOLDS_ROLE = "HOLDS_ROLE"
    WON_AWARD = "WON_AWARD"
    MEMBER_OF = "MEMBER_OF"
    PARTICIPATED_IN = "PARTICIPATED_IN"
    ORGANIZED = "ORGANIZED"
    PART_OF = "PART_OF"
    LOCATED_IN = "LOCATED_IN"
    HELD_AT = "HELD_AT"
    TRAINED_IN = "TRAINED_IN"
    SUPPORTED_BY = "SUPPORTED_BY"


class Entity(BaseModel):
    id: str
    type: EntityType
    org_type: Optional[OrgType] = None
    description: Optional[str] = None


class Relationship(BaseModel):
    source_id: str
    target_id: str
    relation: RelationType
    date: Optional[str] = None
    source_post_url: Optional[str] = None
    role_title: Optional[str] = None
    status: Optional[str] = "active"
    description: Optional[str] = None


class GraphExtractionResult(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
