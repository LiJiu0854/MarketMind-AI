"""Knowledge-base management and RBAC HTTP tests."""

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from kombu.exceptions import (  # type: ignore[import-untyped]
    OperationalError as BrokerOperationalError,
)
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app
from app.models.knowledge import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeQuery,
    KnowledgeQueryStatus,
)
from app.models.user import Role, User
from app.schemas.knowledge import KnowledgeCitation, RetrievedChunk
from app.schemas.user import UserCreate
from app.services.document_ingestion import DocumentIngestionError, EmbeddingCompletion
from app.services.knowledge import ValidatedUpload, create_query_history, stage_knowledge_document
from app.services.rag import RAGCallError, RAGCompletion
from app.services.users import create_user

JWT_SECRET = "rag-api-test-secret-with-32-bytes"


@pytest.fixture(autouse=True)
def jwt_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


@pytest_asyncio.fixture
async def client(session: AsyncSession, tmp_path: Path) -> AsyncIterator[AsyncClient]:
    app = create_app(
        Settings(
            embedding_provider="test",
            embedding_base_url="https://provider.invalid/v1",
            embedding_model="embedding-test",
            embedding_api_key=SecretStr("test-only-key"),
            llm_provider="test-chat",
            llm_base_url="https://chat.invalid/v1",
            llm_model="chat-test",
            llm_api_key=SecretStr("test-chat-key"),
            knowledge_file_root=tmp_path,
            knowledge_max_file_bytes=16,
        )
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def make_actor(session: AsyncSession, role: Role, suffix: str) -> User:
    return await create_user(
        session,
        UserCreate(
            email=f"rag-api-{suffix}@example.com",
            full_name="RAG API",
            password="correct-horse-battery-staple",
            role=role,
        ),
    )


def auth_headers(actor: User) -> dict[str, str]:
    token = create_access_token(actor.id, SecretStr(JWT_SECRET), 30)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_creates_knowledge_base_and_receives_201(
    client: AsyncClient, session: AsyncSession
) -> None:
    actor = await make_actor(session, Role.ADMIN, "admin")
    response = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "  Policies  ", "description": "  Team docs  "},
        headers=auth_headers(actor),
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Policies"
    assert response.json()["embedding_model"] == "embedding-test"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ANALYST])
async def test_non_admin_cannot_create_knowledge_base(
    client: AsyncClient, session: AsyncSession, role: Role
) -> None:
    actor = await make_actor(session, role, role.value)
    response = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Forbidden"},
        headers=auth_headers(actor),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(Role))
async def test_all_roles_can_list_and_read_knowledge_bases(
    client: AsyncClient, session: AsyncSession, role: Role
) -> None:
    admin = await make_actor(session, Role.ADMIN, f"create-{role.value}")
    created = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": f"Policy {role.value}"},
        headers=auth_headers(admin),
    )
    actor = await make_actor(session, role, f"read-{role.value}")
    base_id = created.json()["id"]

    listing = await client.get("/api/v1/knowledge-bases", headers=auth_headers(actor))
    detail = await client.get(f"/api/v1/knowledge-bases/{base_id}", headers=auth_headers(actor))
    documents = await client.get(
        f"/api/v1/knowledge-bases/{base_id}/documents", headers=auth_headers(actor)
    )

    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == base_id
    assert detail.status_code == 200
    assert detail.json()["id"] == base_id
    assert documents.status_code == 200
    assert documents.json()["total"] == 0


@pytest.mark.asyncio
async def test_duplicate_name_returns_stable_409(
    client: AsyncClient, session: AsyncSession
) -> None:
    actor = await make_actor(session, Role.ADMIN, "duplicate")
    headers = auth_headers(actor)
    first = await client.post("/api/v1/knowledge-bases", json={"name": "Same"}, headers=headers)
    second = await client.post("/api/v1/knowledge-bases", json={"name": "Same"}, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "KNOWLEDGE_BASE_NAME_EXISTS"


@pytest.mark.asyncio
async def test_missing_base_returns_stable_404(client: AsyncClient, session: AsyncSession) -> None:
    actor = await make_actor(session, Role.ANALYST, "missing")
    response = await client.get("/api/v1/knowledge-bases/999999", headers=auth_headers(actor))
    assert response.status_code == 404
    assert response.json()["code"] == "KNOWLEDGE_BASE_NOT_FOUND"


@pytest.mark.asyncio
async def test_unauthenticated_management_request_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/knowledge-bases")).status_code == 401


async def make_base(client: AsyncClient, actor: User, name: str = "Upload base") -> int:
    response = await client.post(
        "/api/v1/knowledge-bases", json={"name": name}, headers=auth_headers(actor)
    )
    assert response.status_code == 201
    return int(response.json()["id"])


@pytest.mark.asyncio
async def test_admin_upload_returns_202_document_task_and_pending_status(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    actor = await make_actor(session, Role.ADMIN, "upload")
    base_id = await make_base(client, actor)
    delay = Mock(return_value=SimpleNamespace(id="task-123"))
    embedding_client = Mock(side_effect=AssertionError("upload must not call Embedding"))
    monkeypatch.setattr("app.api.v1.knowledge_bases.index_knowledge_document.delay", delay)
    monkeypatch.setattr("app.services.document_ingestion.AsyncOpenAI", embedding_client)

    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files={"file": ("../../notes.txt", b"hello", "text/plain")},
        headers=auth_headers(actor),
    )

    assert response.status_code == 202
    assert response.json()["task_id"] == "task-123"
    assert response.json()["status"] == "pending"
    document = await session.get_one(KnowledgeDocument, response.json()["document_id"])
    assert document.original_name == "notes.txt"
    assert document.status is KnowledgeDocumentStatus.PENDING
    assert (tmp_path / document.storage_path).read_bytes() == b"hello"
    delay.assert_called_once_with(document.id)
    embedding_client.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ANALYST])
async def test_non_admin_upload_is_forbidden(
    client: AsyncClient, session: AsyncSession, role: Role
) -> None:
    admin = await make_actor(session, Role.ADMIN, f"owner-{role.value}")
    base_id = await make_base(client, admin)
    actor = await make_actor(session, role, f"upload-{role.value}")
    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=auth_headers(actor),
    )
    assert response.status_code == 403
    assert (await session.scalars(select(KnowledgeDocument))).all() == []


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file_with_413(
    client: AsyncClient, session: AsyncSession
) -> None:
    actor = await make_actor(session, Role.ADMIN, "too-large")
    base_id = await make_base(client, actor)
    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files={"file": ("notes.txt", b"x" * 17, "text/plain")},
        headers=auth_headers(actor),
    )
    assert response.status_code == 413
    assert response.json()["code"] == "KNOWLEDGE_FILE_TOO_LARGE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file",
    [
        ("notes.exe", b"hello", "text/plain"),
        ("notes.pdf", b"hello", "application/pdf"),
        ("notes.txt", b"hello", "application/pdf"),
        ("notes.txt", b"\xff", "text/plain"),
    ],
)
async def test_upload_rejects_invalid_extension_content_type_or_bytes_with_422(
    client: AsyncClient, session: AsyncSession, file: tuple[str, bytes, str]
) -> None:
    actor = await make_actor(session, Role.ADMIN, "invalid")
    base_id = await make_base(client, actor)
    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files={"file": file},
        headers=auth_headers(actor),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "KNOWLEDGE_FILE_INVALID"


@pytest.mark.asyncio
async def test_duplicate_file_returns_409(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_actor(session, Role.ADMIN, "duplicate-file")
    base_id = await make_base(client, actor)
    monkeypatch.setattr(
        "app.api.v1.knowledge_bases.index_knowledge_document.delay",
        Mock(return_value=SimpleNamespace(id="task-duplicate")),
    )
    url = f"/api/v1/knowledge-bases/{base_id}/documents"
    files = {"file": ("notes.txt", b"hello", "text/plain")}
    assert (await client.post(url, files=files, headers=auth_headers(actor))).status_code == 202
    second = await client.post(url, files=files, headers=auth_headers(actor))
    assert second.status_code == 409
    assert second.json()["code"] == "KNOWLEDGE_DOCUMENT_DUPLICATE"


@pytest.mark.asyncio
async def test_broker_failure_marks_document_failure_and_returns_503(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = await make_actor(session, Role.ADMIN, "broker-fail")
    base_id = await make_base(client, actor)
    monkeypatch.setattr(
        "app.api.v1.knowledge_bases.index_knowledge_document.delay",
        Mock(side_effect=BrokerOperationalError("private broker URL")),
    )
    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=auth_headers(actor),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "KNOWLEDGE_DOCUMENT_DISPATCH_FAILED"
    assert "private" not in response.text
    document = (await session.scalars(select(KnowledgeDocument))).one()
    assert document.status is KnowledgeDocumentStatus.FAILURE
    assert document.error_code == "DOCUMENT_INTERNAL_ERROR"


async def make_ready_document(
    client: AsyncClient, session: AsyncSession, tmp_path: Path, suffix: str
) -> tuple[int, int]:
    admin = await make_actor(session, Role.ADMIN, f"ready-{suffix}")
    base_id = await make_base(client, admin, f"Ready {suffix}")
    document = await stage_knowledge_document(
        session,
        base_id,
        admin.id,
        ValidatedUpload("policy.txt", ".txt", "text/plain", b"Returns in 30 days", "d" * 64),
        tmp_path,
    )
    document.status = KnowledgeDocumentStatus.READY
    await session.commit()
    return base_id, document.id


def mock_question_pipeline(
    monkeypatch: pytest.MonkeyPatch, document_id: int, *, weak: bool = False
) -> Mock:
    monkeypatch.setattr(
        "app.services.rag.request_embeddings",
        AsyncMock(return_value=EmbeddingCompletion([[0.1, 0.2]], 3, 2)),
    )
    monkeypatch.setattr("app.services.rag.create_chroma_client", AsyncMock(return_value=object()))
    monkeypatch.setattr("app.services.rag.close_chroma_client", AsyncMock())
    chunks = (
        []
        if weak
        else [
            RetrievedChunk(
                document_id=document_id,
                original_name="policy.txt",
                chunk_id=f"document:{document_id}:chunk:0",
                chunk_index=0,
                text="Returns in 30 days",
                distance=0.1,
            )
        ]
    )
    monkeypatch.setattr("app.services.rag.retrieve_chunks", AsyncMock(return_value=chunks))
    citation = KnowledgeCitation(
        document_id=document_id,
        original_name="policy.txt",
        chunk_id=f"document:{document_id}:chunk:0",
        chunk_index=0,
        excerpt="Returns in 30 days",
        distance=0.1,
    )
    chat = AsyncMock(
        return_value=RAGCompletion(
            "30 days", KnowledgeQueryStatus.SUCCESS, [citation], None, 10, 4, 14
        )
    )
    monkeypatch.setattr("app.services.rag.request_rag_answer", chat)
    return chat


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(Role))
async def test_all_roles_can_ask_and_receive_verified_citations(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    base_id, document_id = await make_ready_document(client, session, tmp_path, f"ask-{role.value}")
    actor = await make_actor(session, role, f"ask-{role.value}")
    chat = mock_question_pipeline(monkeypatch, document_id)

    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/questions",
        json={"question": " Return period? "},
        headers=auth_headers(actor),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["citations"][0]["document_id"] == document_id
    assert response.json()["total_tokens"] == 17
    chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_base_returns_409_without_model_call(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await make_actor(session, Role.ADMIN, "empty-ask")
    base_id = await make_base(client, actor)
    embed = AsyncMock()
    monkeypatch.setattr("app.services.rag.request_embeddings", embed)
    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/questions",
        json={"question": "Anything?"},
        headers=auth_headers(actor),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "KNOWLEDGE_BASE_EMPTY"
    embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_weak_retrieval_returns_refused_and_empty_citations(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_id, document_id = await make_ready_document(client, session, tmp_path, "weak-ask")
    actor = await make_actor(session, Role.ANALYST, "weak-ask")
    chat = mock_question_pipeline(monkeypatch, document_id, weak=True)
    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/questions",
        json={"question": "Unknown?"},
        headers=auth_headers(actor),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "refused"
    assert response.json()["citations"] == []
    chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_unavailable_returns_503_and_persists_failure(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_id, _ = await make_ready_document(client, session, tmp_path, "provider-error")
    actor = await make_actor(session, Role.ANALYST, "provider-error")
    monkeypatch.setattr(
        "app.services.rag.request_embeddings",
        AsyncMock(
            side_effect=DocumentIngestionError(
                "EMBEDDING_UNAVAILABLE", "Embedding 服务暂时不可用", retryable=True
            )
        ),
    )
    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/questions",
        json={"question": "Return period?"},
        headers=auth_headers(actor),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "RAG_PROVIDER_UNAVAILABLE"
    history = (await session.scalars(select(KnowledgeQuery))).one()
    assert history.status is KnowledgeQueryStatus.FAILURE


@pytest.mark.asyncio
async def test_invalid_provider_response_returns_502_and_persists_failure(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_id, document_id = await make_ready_document(client, session, tmp_path, "invalid-chat")
    actor = await make_actor(session, Role.ANALYST, "invalid-chat")
    chat = mock_question_pipeline(monkeypatch, document_id)
    chat.side_effect = RAGCallError("RAG_INVALID_RESPONSE", "模型回答格式无效", status_code=502)
    response = await client.post(
        f"/api/v1/knowledge-bases/{base_id}/questions",
        json={"question": "Return period?"},
        headers=auth_headers(actor),
    )
    assert response.status_code == 502
    assert response.json()["code"] == "RAG_INVALID_RESPONSE"
    history = (await session.scalars(select(KnowledgeQuery))).one()
    assert history.error_code == "RAG_INVALID_RESPONSE"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(Role))
async def test_all_roles_can_list_and_read_query_history(
    client: AsyncClient, session: AsyncSession, role: Role
) -> None:
    admin = await make_actor(session, Role.ADMIN, f"history-owner-{role.value}")
    base_id = await make_base(client, admin, f"History {role.value}")
    query = await create_query_history(
        session,
        base_id,
        admin.id,
        "Question?",
        "test-chat",
        "chat-test",
        RAGCompletion("No basis", KnowledgeQueryStatus.REFUSED, [], 2, None, None, 2),
    )
    actor = await make_actor(session, role, f"history-read-{role.value}")
    listing = await client.get(
        f"/api/v1/knowledge-bases/{base_id}/questions", headers=auth_headers(actor)
    )
    detail = await client.get(
        f"/api/v1/knowledge-bases/{base_id}/questions/{query.id}", headers=auth_headers(actor)
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == query.id
    assert detail.status_code == 200
    assert detail.json()["id"] == query.id


@pytest.mark.asyncio
async def test_query_from_other_base_returns_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    actor = await make_actor(session, Role.ADMIN, "history-other")
    first = await make_base(client, actor, "History first")
    second = await make_base(client, actor, "History second")
    query = await create_query_history(
        session,
        first,
        actor.id,
        "Question?",
        "test-chat",
        "chat-test",
        RAGCompletion("No basis", KnowledgeQueryStatus.REFUSED, [], 2, None, None, 2),
    )
    response = await client.get(
        f"/api/v1/knowledge-bases/{second}/questions/{query.id}", headers=auth_headers(actor)
    )
    assert response.status_code == 404
    assert response.json()["code"] == "KNOWLEDGE_QUERY_NOT_FOUND"
