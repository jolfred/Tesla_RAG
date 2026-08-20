from pydantic import BaseModel


class StatusResponse(BaseModel):
    status: str
    qdrant_points: int = 0
    neo4j_nodes: int = 0
    neo4j_relations: int = 0
    documents_count: int = 0
    ollama_available: bool = False
    errors: list[str] = []


class IndexResponse(BaseModel):
    status: str
    processed: list[dict] = []
    errors: list[dict] = []
    total_processed: int = 0
    total_errors: int = 0
