from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.db.chroma import close_chroma_client, create_chroma_client, knowledge_collection_name


def test_collection_name_is_deterministic() -> None:
    assert knowledge_collection_name(42) == "marketmind_kb_42"
    with pytest.raises(ValueError):
        knowledge_collection_name(0)


@pytest.mark.asyncio
async def test_async_http_client_uses_all_connection_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = AsyncMock(return_value=object())
    monkeypatch.setattr("app.db.chroma.chromadb.AsyncHttpClient", constructor)
    settings = Settings(
        chroma_host="chroma.internal",
        chroma_port=8100,
        chroma_ssl=True,
        chroma_tenant="team",
        chroma_database="marketmind",
    )

    client = await create_chroma_client(settings)

    assert client is constructor.return_value
    constructor.assert_awaited_once_with(
        host="chroma.internal",
        port=8100,
        ssl=True,
        tenant="team",
        database="marketmind",
    )


@pytest.mark.asyncio
async def test_close_client_releases_http_connection() -> None:
    from types import SimpleNamespace
    from typing import cast

    from chromadb.api import AsyncClientAPI

    cleanup = AsyncMock()
    client = cast(AsyncClientAPI, SimpleNamespace(_server=SimpleNamespace(_cleanup=cleanup)))
    await close_chroma_client(client)
    cleanup.assert_awaited_once()
