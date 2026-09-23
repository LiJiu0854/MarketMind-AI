from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.core.errors import AppError
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.services.knowledge import ValidatedUpload, stage_knowledge_document, validate_upload


class RecordingBytesIO(BytesIO):
    last_read_size: int | None = None

    def read(self, size: int | None = -1) -> bytes:
        self.last_read_size = size
        return super().read(size)


def make_upload(name: str, data: bytes, media_type: str) -> UploadFile:
    return UploadFile(
        filename=name,
        file=RecordingBytesIO(data),
        headers=Headers({"content-type": media_type}),
    )


@pytest.mark.asyncio
async def test_validate_upload_rejects_pdf_without_pdf_header() -> None:
    upload = make_upload("manual.pdf", b"not a pdf", "application/pdf")
    with pytest.raises(AppError) as failure:
        await validate_upload(upload, 100)
    assert failure.value.code == "KNOWLEDGE_FILE_INVALID"
    assert upload.file.closed


@pytest.mark.asyncio
async def test_validate_upload_rejects_non_utf8_text() -> None:
    upload = make_upload("notes.txt", b"\xff", "text/plain")
    with pytest.raises(AppError) as failure:
        await validate_upload(upload, 100)
    assert failure.value.code == "KNOWLEDGE_FILE_INVALID"


@pytest.mark.asyncio
async def test_validate_upload_reads_only_limit_plus_one_bytes() -> None:
    upload = make_upload("notes.txt", b"x" * 200, "text/plain")
    with pytest.raises(AppError) as failure:
        await validate_upload(upload, 10)
    assert failure.value.code == "KNOWLEDGE_FILE_TOO_LARGE"
    assert isinstance(upload.file, RecordingBytesIO)
    assert upload.file.last_read_size == 11


@pytest.mark.asyncio
async def test_validate_upload_discards_traversal_components() -> None:
    upload = make_upload("../../secret.pdf", b"%PDF-test", "application/pdf")
    validated = await validate_upload(upload, 100)
    assert validated.original_name == "secret.pdf"


@pytest.mark.asyncio
async def test_stage_document_uses_generated_path_not_user_filename(tmp_path: Path) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [KnowledgeBase(id=3), None]

    async def assign_id() -> None:
        session.add.call_args.args[0].id = 7

    session.flush.side_effect = assign_id
    validated = ValidatedUpload(
        original_name="secret.pdf",
        suffix=".pdf",
        media_type="application/pdf",
        data=b"%PDF-test",
        sha256="a" * 64,
    )
    document = await stage_knowledge_document(session, 3, 2, validated, tmp_path)

    assert document.original_name == "secret.pdf"
    assert document.storage_path == "3/7.pdf"
    assert (tmp_path / document.storage_path).read_bytes() == validated.data
    assert (tmp_path / document.storage_path).resolve().is_relative_to((tmp_path / "3").resolve())


@pytest.mark.asyncio
async def test_failed_database_commit_removes_staged_file(tmp_path: Path) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [KnowledgeBase(id=3), None]

    async def assign_id() -> None:
        session.add.call_args.args[0].id = 8

    session.flush.side_effect = assign_id
    session.commit.side_effect = RuntimeError("database unavailable")
    validated = ValidatedUpload("notes.txt", ".txt", "text/plain", b"hello", "b" * 64)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await stage_knowledge_document(session, 3, 2, validated, tmp_path)

    assert not (tmp_path / "3" / "8.txt").exists()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_commit_error_has_stable_code_and_removes_file(tmp_path: Path) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = [KnowledgeBase(id=3), None]

    async def assign_id() -> None:
        session.add.call_args.args[0].id = 9

    session.flush.side_effect = assign_id
    session.commit.side_effect = IntegrityError("INSERT", {}, Exception("private driver detail"))
    validated = ValidatedUpload("notes.txt", ".txt", "text/plain", b"hello", "c" * 64)

    with pytest.raises(AppError) as failure:
        await stage_knowledge_document(session, 3, 2, validated, tmp_path)

    assert failure.value.code == "KNOWLEDGE_DOCUMENT_DUPLICATE"
    assert failure.value.status_code == 409
    assert "private" not in failure.value.message
    assert not (tmp_path / "3" / "9.txt").exists()


def test_document_model_has_no_file_path_in_public_response() -> None:
    assert "storage_path" in KnowledgeDocument.__table__.columns
