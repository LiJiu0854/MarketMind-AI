"""Thin, server-backed Chroma client boundary."""

import chromadb
from chromadb.api import AsyncClientAPI

from app.core.config import Settings


def knowledge_collection_name(knowledge_base_id: int) -> str:
    if knowledge_base_id <= 0:
        raise ValueError("knowledge_base_id 必须为正整数")
    return f"marketmind_kb_{knowledge_base_id}"


async def create_chroma_client(settings: Settings) -> AsyncClientAPI:
    return await chromadb.AsyncHttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
        ssl=settings.chroma_ssl,
        tenant=settings.chroma_tenant,
        database=settings.chroma_database,
    )


async def close_chroma_client(client: AsyncClientAPI) -> None:
    # ponytail: chromadb-client 1.5 has no public async close; use its HTTP cleanup until it does.
    server = getattr(client, "_server", None)
    cleanup = getattr(server, "_cleanup", None)
    if cleanup is not None:
        await cleanup()
