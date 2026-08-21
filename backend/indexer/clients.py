import os

from neo4j import GraphDatabase
from openai import OpenAI
from qdrant_client import QdrantClient

from backend.indexer.logger import setup_indexer_logger

logger = setup_indexer_logger()


def init_clients() -> tuple[OpenAI, GraphDatabase.driver, QdrantClient]:
    openai_client = OpenAI(
        base_url=os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1"),
        api_key=os.getenv("PROXYAPI_KEY", ""),
    )
    openai_client.models.list()

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASS", "tesla_neo4j")
    neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    with neo4j_driver.session() as session:
        session.run("RETURN 1")

    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant_api_key = os.getenv("QDRANT_API_KEY", None)
    qdrant_client = QdrantClient(
        host=qdrant_host,
        port=qdrant_port,
        api_key=qdrant_api_key if qdrant_api_key else None,
    )
    qdrant_client.get_collections()

    logger.info("All clients initialized and connected successfully")
    return openai_client, neo4j_driver, qdrant_client
