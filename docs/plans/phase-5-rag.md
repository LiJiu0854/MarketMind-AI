# Phase 5 RAG Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-shaped knowledge-base RAG flow that asynchronously indexes PDF, Markdown, and TXT files, answers only from retrieved evidence with verified citations, and persists operational history in MySQL.

**Architecture:** MySQL owns knowledge-base, document, and query state; files live under a controlled local root; Celery parses and embeds documents; a server-backed Chroma collection per knowledge base owns the derived vector index. FastAPI performs authenticated management and synchronous cited question answering through OpenAI-compatible Embedding and Chat endpoints.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy asyncio, Alembic, MySQL 8, Redis, Celery 5.6, OpenAI Python SDK 2.x, Chroma thin HTTP client 1.5.x, pypdf 6.x, pytest, Ruff, mypy.

**Spec:** `docs/plans/phase-5-rag-design.md`

## Global Constraints

- Work only on branch `phase/5-rag`; do not merge, push, or delete the branch before user acceptance.
- Add only `chromadb-client>=1.5,<2.0` and `pypdf>=6.17,<7.0`; do not add LangChain, LlamaIndex, a second model SDK, or OCR.
- Use one cosine-distance Chroma collection named `marketmind_kb_{knowledge_base_id}` per knowledge base.
- Store business state, audit history, verified citations, and Token usage in MySQL; Chroma is a rebuildable derived index.
- Accept only `.pdf`, `.md`, and `.txt`; maximum upload size is 10 MiB; text must be UTF-8; PDF bytes must start with `%PDF-`.
- Defaults: 1000-character chunks, 150-character overlap, top K 5, maximum cosine distance 0.35, maximum 2000 chunks per document, Embedding batch size 64.
- Snapshot `embedding_provider`, `embedding_base_url`, and `embedding_model` per knowledge base; reject later configuration drift.
- Keep API keys in `SecretStr`; never put secrets in MySQL, logs, responses, tests, examples, or Git.
- Automated tests use mocks/fakes and never access real model endpoints or an external Chroma service.
- Real paid model acceptance requires a separate explicit user approval.
- Preserve every existing modified/untracked learning or practice file; never stage it.
- Create four local Chinese learning documents under `docs/learning/` and keep them untracked.
- Use exact `git add -- <files>` commands; never use `git add .` or `git add -A`.
- Every unit follows RED → GREEN → focused Ruff/mypy; every Task ends with focused regression and `git diff --check`.

## Review Focus

1. A traversal filename such as `../../secret.pdf` must not influence the stored path; Task 1 pins generated paths.
2. Concurrent identical uploads to one knowledge base must produce one row plus stable 409 behavior, not an uncaught integrity error; Task 1 pins the database constraint and error mapping.
3. A Chroma write followed by a failed MySQL ready commit must converge on retry without duplicate chunks; Task 2 pins deterministic IDs and delete/upsert.
4. Provider vectors with mixed dimensions or non-finite values must be rejected before Chroma; Task 2 pins both cases.
5. Chroma hits for missing or non-ready MySQL documents must not reach the prompt or citations; Task 3 pins readiness post-filtering.

---

## File Map

### New production files

- `backend/app/models/knowledge.py` — ORM models and document/query status enums.
- `backend/app/schemas/knowledge.py` — requests, responses, pages, chunks, citations, and provider output.
- `backend/app/db/chroma.py` — async Chroma client and collection naming.
- `backend/app/services/knowledge.py` — MySQL CRUD, file staging, pagination, status, and compensation.
- `backend/app/services/document_ingestion.py` — parsing, chunking, Embedding, validation, and Chroma indexing.
- `backend/app/services/rag.py` — retrieval, refusal, Prompt, Chat validation, citations, and query history.
- `backend/app/services/rag_evaluation.py` — JSONL validation and RAG metrics.
- `backend/app/tasks/knowledge.py` — Celery indexing lifecycle, lock, retry, and resource cleanup.
- `backend/app/api/v1/knowledge_bases.py` — management, document, upload, question, and history API.
- `alembic/versions/0004_create_rag_tables.py` — three RAG tables and constraints.
- `scripts/evaluate_rag.py` — guarded evaluation CLI.

### New tests

- `tests/unit/models/test_knowledge.py`
- `tests/unit/schemas/test_knowledge.py`
- `tests/unit/services/test_knowledge.py`
- `tests/unit/services/test_document_ingestion.py`
- `tests/unit/services/test_rag.py`
- `tests/unit/services/test_rag_evaluation.py`
- `tests/unit/db/test_chroma.py`
- `tests/unit/tasks/test_knowledge.py`
- `tests/integration/db/test_knowledge.py`
- `tests/api/test_knowledge_bases.py`

### Modified files

- `pyproject.toml`, `.env.example`, `.gitignore`, `README.md`
- `backend/app/core/config.py`, `backend/app/models/__init__.py`
- `backend/app/celery_app.py`, `backend/app/main.py`, `alembic/env.py`
- `tests/conftest.py`, `tests/unit/core/test_config.py`

---

### Task 1: Knowledge-base persistence, safe file staging, and management API

**Deliverable:** Admin can create/list/read knowledge bases; the service safely stages a validated file and creates a pending document; MySQL owns all three Phase 5 tables and enforces duplicate protection.

**Files:**
- Create: `backend/app/models/knowledge.py`
- Create: `backend/app/schemas/knowledge.py`
- Create: `backend/app/services/knowledge.py`
- Create: `backend/app/api/v1/knowledge_bases.py`
- Create: `alembic/versions/0004_create_rag_tables.py`
- Create: `tests/unit/models/test_knowledge.py`
- Create: `tests/unit/schemas/test_knowledge.py`
- Create: `tests/unit/services/test_knowledge.py`
- Create: `tests/integration/db/test_knowledge.py`
- Create: `tests/api/test_knowledge_bases.py`
- Modify: `backend/app/core/config.py`, `backend/app/models/__init__.py`, `backend/app/main.py`
- Modify: `alembic/env.py`, `tests/conftest.py`, `tests/unit/core/test_config.py`, `.gitignore`
- Local only: `docs/learning/phase-5-task-1-knowledge-upload.md`

**Interfaces:**
- Consumes: `Base`, `Settings`, `AppError`, `get_db_session()`, `get_current_user()`, `require_roles()`, `Role`, `AsyncSession`, and existing pagination/error conventions.
- Produces: `KnowledgeBase`, `KnowledgeDocument`, `KnowledgeQuery`, `KnowledgeDocumentStatus`, `KnowledgeQueryStatus`; schemas and service signatures below; router `/api/v1/knowledge-bases`; pending documents for Task 2.

- [ ] **Step 1: Write failing configuration tests**

Append to `tests/unit/core/test_config.py`:

```python
def test_rag_config_has_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.knowledge_file_root == Path("data/knowledge")
    assert settings.knowledge_max_file_bytes == 10 * 1024 * 1024
    assert settings.rag_chunk_size == 1_000
    assert settings.rag_chunk_overlap == 150
    assert settings.rag_top_k == 5
    assert settings.rag_max_distance == 0.35
    assert settings.embedding_api_key is None


def test_chunk_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_chunk_size=100, rag_chunk_overlap=100)
```

- [ ] **Step 2: Run configuration tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/core/test_config.py -q`

Expected: FAIL because RAG fields and the cross-field validator do not exist.

- [ ] **Step 3: Add typed configuration**

Add these exact fields to `Settings`:

```python
knowledge_file_root: Path = Path("data/knowledge")
knowledge_max_file_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
rag_chunk_size: int = Field(default=1_000, gt=0)
rag_chunk_overlap: int = Field(default=150, ge=0)
rag_top_k: int = Field(default=5, ge=1, le=10)
rag_max_distance: float = Field(default=0.35, ge=0, le=2)
chroma_host: str = "127.0.0.1"
chroma_port: int = Field(default=8_000, ge=1, le=65_535)
chroma_ssl: bool = False
chroma_tenant: str = "default_tenant"
chroma_database: str = "default_database"
embedding_provider: str = "openai"
embedding_base_url: str = "https://api.openai.com/v1"
embedding_model: str | None = None
embedding_api_key: SecretStr | None = None
embedding_timeout_seconds: int = Field(default=60, gt=0)
embedding_batch_size: int = Field(default=64, gt=0, le=2_048)
```

Use `model_validator(mode="after")` to reject `rag_chunk_overlap >= rag_chunk_size`. Reuse existing optional text/secret normalization for `embedding_model` and `embedding_api_key`. Validate nonblank provider, base URL, Chroma host, tenant, and database.

- [ ] **Step 4: Run configuration tests GREEN and static checks**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/core/test_config.py -q
.venv\Scripts\ruff.exe check backend/app/core/config.py tests/unit/core/test_config.py
.venv\Scripts\mypy.exe backend/app/core/config.py tests/unit/core/test_config.py
```

Expected: all commands exit 0.

- [ ] **Step 5: Write failing ORM and schema tests**

Create `test_knowledge.py` model tests for exact table names, foreign keys, enum values, positive/non-negative checks, and unique `(knowledge_base_id, sha256)`. Create schema tests including:

```python
def test_create_name_and_description_are_trimmed() -> None:
    payload = KnowledgeBaseCreate(name="  Policies  ", description="  Team docs  ")
    assert payload.name == "Policies"
    assert payload.description == "Team docs"


@pytest.mark.parametrize("question", ["", "   ", "x" * 2_001])
def test_question_rejects_empty_or_oversized_text(question: str) -> None:
    with pytest.raises(ValidationError):
        KnowledgeQuestionCreate(question=question)


def test_citation_requires_source_coordinates() -> None:
    citation = KnowledgeCitation(
        document_id=7,
        original_name="policy.pdf",
        chunk_id="document:7:chunk:0",
        chunk_index=0,
        page_number=1,
        excerpt="Return window is 30 days.",
        distance=0.12,
    )
    assert citation.page_number == 1
```

- [ ] **Step 6: Run ORM/schema tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/models/test_knowledge.py tests/unit/schemas/test_knowledge.py -q`

Expected: import failure because the model and schema modules do not exist.

- [ ] **Step 7: Implement the three ORM models**

Public enums:

```python
class KnowledgeDocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILURE = "failure"


class KnowledgeQueryStatus(StrEnum):
    SUCCESS = "success"
    REFUSED = "refused"
    FAILURE = "failure"
```

Implement `KnowledgeBase`, `KnowledgeDocument`, and `KnowledgeQuery` exactly as design section 5. Use string-backed SQLAlchemy enums and named checks. Add:

```python
UniqueConstraint(
    "knowledge_base_id",
    "sha256",
    name="uq_knowledge_documents_base_sha256",
)
```

Do not add ORM relationships. Export models/enums from `models/__init__.py`; import models in `alembic/env.py`.

- [ ] **Step 8: Implement strict schemas**

Create these public schemas with `extra="forbid"` for input/provider data and `from_attributes=True` for ORM reads:

```python
class KnowledgeBaseCreate(BaseModel): ...
class KnowledgeBaseRead(BaseModel): ...
class KnowledgeBasePage(BaseModel): ...
class KnowledgeDocumentRead(BaseModel): ...
class KnowledgeDocumentPage(BaseModel): ...
class KnowledgeDocumentCreated(BaseModel):
    document_id: int
    task_id: str
    status: KnowledgeDocumentStatus

class KnowledgeQuestionCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    top_k: int | None = Field(default=None, ge=1, le=10)

class RetrievedChunk(BaseModel): ...
class RAGModelResult(BaseModel): ...
class KnowledgeCitation(BaseModel): ...
class KnowledgeAnswerRead(BaseModel): ...
class KnowledgeQueryRead(BaseModel): ...
class KnowledgeQueryPage(BaseModel): ...
```

Trim name, description, and question. `RetrievedChunk.distance` is 0..2; citation excerpt is at most 300 characters; RAG answer is at most 5000 characters; citations are at most 10.

- [ ] **Step 9: Create migration and test cleanup**

Create revision `0004`, down revision `0003`, containing all three tables, indexes, foreign keys, checks, and unique constraints. Downgrade in dependency order: queries, documents, bases.

Update `tests/conftest.py` cleanup order:

```python
await connection.execute(delete(KnowledgeQuery))
await connection.execute(delete(KnowledgeDocument))
await connection.execute(delete(KnowledgeBase))
await connection.execute(delete(SemanticReview))
await connection.execute(delete(Product))
await connection.execute(delete(User))
```

- [ ] **Step 10: Run ORM/schema/migration-focused GREEN checks**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/models/test_knowledge.py tests/unit/schemas/test_knowledge.py -q
.venv\Scripts\ruff.exe check backend/app/models/knowledge.py backend/app/schemas/knowledge.py alembic/versions/0004_create_rag_tables.py tests/unit/models/test_knowledge.py tests/unit/schemas/test_knowledge.py
.venv\Scripts\mypy.exe backend/app/models/knowledge.py backend/app/schemas/knowledge.py tests/unit/models/test_knowledge.py tests/unit/schemas/test_knowledge.py
```

- [ ] **Step 11: Write failing safe-storage and persistence tests**

Required unit cases:

```python
def test_validate_upload_rejects_pdf_without_pdf_header() -> None: ...
def test_validate_upload_rejects_non_utf8_text() -> None: ...
def test_validate_upload_reads_only_limit_plus_one_bytes() -> None: ...
def test_stage_document_uses_generated_path_not_user_filename(tmp_path: Path) -> None: ...
def test_failed_database_commit_removes_staged_file(tmp_path: Path) -> None: ...
```

The traversal case supplies `../../secret.pdf`, expects display name `secret.pdf`, and asserts the resolved storage path stays under `<root>/<knowledge_base_id>/`.

Required integration cases:

```python
async def test_create_base_snapshots_embedding_contract(session) -> None: ...
async def test_same_hash_in_same_base_is_unique(session) -> None: ...
async def test_same_hash_in_different_bases_is_allowed(session) -> None: ...
async def test_duplicate_integrity_error_maps_to_stable_conflict(session) -> None: ...
async def test_document_and_query_must_belong_to_path_base(session) -> None: ...
async def test_history_pages_are_descending(session) -> None: ...
```

- [ ] **Step 12: Run storage/persistence tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_knowledge.py tests/integration/db/test_knowledge.py -q`

Expected: FAIL because service functions do not exist.

- [ ] **Step 13: Implement safe-file and knowledge services**

Public surface:

```python
@dataclass(frozen=True)
class ValidatedUpload:
    original_name: str
    suffix: Literal[".pdf", ".md", ".txt"]
    media_type: str
    data: bytes
    sha256: str


async def validate_upload(upload: UploadFile, max_bytes: int) -> ValidatedUpload: ...
async def create_knowledge_base(session, payload, creator_id, settings) -> KnowledgeBase: ...
async def get_knowledge_base(session, knowledge_base_id) -> KnowledgeBase: ...
async def list_knowledge_bases(session, page, page_size) -> tuple[list[KnowledgeBase], int]: ...
async def stage_knowledge_document(
    session, knowledge_base_id, uploader_id, upload, file_root
) -> KnowledgeDocument: ...
async def mark_document_dispatch_failure(session, document_id) -> None: ...
async def attach_document_task_id(session, document_id, task_id) -> KnowledgeDocument: ...
async def get_knowledge_document(session, knowledge_base_id, document_id) -> KnowledgeDocument: ...
async def list_knowledge_documents(
    session, knowledge_base_id, page, page_size
) -> tuple[list[KnowledgeDocument], int]: ...
```

Read at most `max_bytes + 1`, close `UploadFile` in `finally`, use `Path(filename).name`, and never use user directories. Resolve and verify containment, write a temporary sibling, then `Path.replace()` atomically. Delete the file if DB commit fails. Catch duplicate `IntegrityError`, rollback, and raise stable `KNOWLEDGE_DOCUMENT_DUPLICATE` 409 without driver text. Ignore `data/knowledge/` in Git.

- [ ] **Step 14: Run storage/persistence tests GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_knowledge.py tests/integration/db/test_knowledge.py -q`

Expected: all tests pass; database tests only use configured `marketmind_test`.

- [ ] **Step 15: Write failing management API tests**

```python
def test_admin_creates_knowledge_base_and_receives_201() -> None: ...
@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ANALYST])
def test_non_admin_cannot_create_knowledge_base(role: Role) -> None: ...
@pytest.mark.parametrize("role", list(Role))
def test_all_roles_can_list_and_read_knowledge_bases(role: Role) -> None: ...
def test_duplicate_name_returns_stable_409() -> None: ...
def test_missing_base_returns_stable_404() -> None: ...
def test_unauthenticated_management_request_returns_401() -> None: ...
```

- [ ] **Step 16: Run API tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_knowledge_bases.py -q`

Expected: FAIL because the router is not mounted.

- [ ] **Step 17: Implement and mount management/read endpoints**

Implement POST collection (201, Admin only), GET collection, GET base, GET documents page, and GET one document under `/knowledge-bases`. Read endpoints require any authenticated user. Always verify nested IDs belong to the path base. Mount under `/api/v1` in `main.py`.

- [ ] **Step 18: Run complete Task 1 verification**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/core/test_config.py tests/unit/models/test_knowledge.py tests/unit/schemas/test_knowledge.py tests/unit/services/test_knowledge.py tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py -q
.venv\Scripts\ruff.exe check backend/app/core/config.py backend/app/models/knowledge.py backend/app/schemas/knowledge.py backend/app/services/knowledge.py backend/app/api/v1/knowledge_bases.py alembic/versions/0004_create_rag_tables.py tests/unit/core/test_config.py tests/unit/models/test_knowledge.py tests/unit/schemas/test_knowledge.py tests/unit/services/test_knowledge.py tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py
.venv\Scripts\mypy.exe backend/app/core/config.py backend/app/models/knowledge.py backend/app/schemas/knowledge.py backend/app/services/knowledge.py backend/app/api/v1/knowledge_bases.py tests/unit/models/test_knowledge.py tests/unit/schemas/test_knowledge.py tests/unit/services/test_knowledge.py tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py
git diff --check
```

- [ ] **Step 19: Write Task 1 learning document**

Write local `docs/learning/phase-5-task-1-knowledge-upload.md`: actual RED/GREEN outputs, file responsibilities, imports, model constraints, migration order, generated paths, UploadFile ownership, atomic replace, DB/file compensation, RBAC, errors, final code by focused section, and line-by-line explanation of execution-affecting code. Keep it untracked.

- [ ] **Step 20: Commit Task 1 exactly**

```powershell
git add -- .gitignore backend/app/core/config.py backend/app/models/__init__.py backend/app/models/knowledge.py backend/app/schemas/knowledge.py backend/app/services/knowledge.py backend/app/api/v1/knowledge_bases.py backend/app/main.py alembic/env.py alembic/versions/0004_create_rag_tables.py tests/conftest.py tests/unit/core/test_config.py tests/unit/models/test_knowledge.py tests/unit/schemas/test_knowledge.py tests/unit/services/test_knowledge.py tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py
git diff --cached --name-status
git diff --cached --check
git commit -m "feat: add RAG knowledge base persistence"
```

Expected: learning and pre-existing local files are absent from the staged list.

---

### Task 2: Parsing, chunking, Embedding, Chroma, and asynchronous indexing

**Deliverable:** Admin upload returns 202; Celery turns pending into ready/failure using safe parsing, deterministic chunks, validated embeddings, Chroma upsert, Redis locking, and bounded retries.

**Files:**
- Create: `backend/app/db/chroma.py`
- Create: `backend/app/services/document_ingestion.py`
- Create: `backend/app/tasks/knowledge.py`
- Create: `tests/unit/db/test_chroma.py`
- Create: `tests/unit/services/test_document_ingestion.py`
- Create: `tests/unit/tasks/test_knowledge.py`
- Modify: `pyproject.toml`, `.env.example`
- Modify: `backend/app/services/knowledge.py`, `backend/app/api/v1/knowledge_bases.py`, `backend/app/celery_app.py`
- Modify: `tests/api/test_knowledge_bases.py`
- Local only: `docs/learning/phase-5-task-2-document-indexing.md`

**Interfaces:**
- Consumes: Task 1 models and document helpers, `redis_lock()`, `create_engine()`, and `create_session_factory()`.
- Produces: `ParsedSection`, `DocumentChunk`, `EmbeddingCompletion`, `DocumentIngestionError`, parsing/chunking/Embedding/index functions, `run_document_index_attempt()`, and Celery task `index_knowledge_document`.

- [ ] **Step 1: Write failing parser/chunker tests**

```python
def test_parse_txt_normalizes_newlines_and_preserves_text_source() -> None: ...
def test_parse_markdown_requires_utf8() -> None: ...
def test_parse_pdf_returns_one_section_per_nonempty_page() -> None: ...
def test_encrypted_or_malformed_pdf_maps_to_safe_parse_error() -> None: ...
def test_scanned_pdf_without_text_is_rejected() -> None: ...
def test_split_prefers_paragraph_or_sentence_boundary() -> None: ...
def test_split_uses_exact_overlap_without_infinite_loop() -> None: ...
def test_pdf_chunks_never_cross_page_boundary() -> None: ...
def test_more_than_2000_chunks_is_rejected_before_embedding() -> None: ...
```

For a forced hard split, compare the final 150 characters of chunk N with the first 150 of chunk N+1.

- [ ] **Step 2: Run parser/chunker tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_document_ingestion.py -q`

Expected: import failure because the service does not exist.

- [ ] **Step 3: Install only approved dependencies**

Add to `pyproject.toml`:

```toml
"chromadb-client>=1.5,<2.0",
"pypdf>=6.17,<7.0",
```

Run: `uv pip install --python .venv\Scripts\python.exe -e ".[dev]"`

Expected: editable install succeeds on Python 3.12. Record resolved versions in the learning document; do not add another framework.

- [ ] **Step 4: Implement parsing/chunking minimally**

```python
MAX_CHUNKS_PER_DOCUMENT = 2_000

@dataclass(frozen=True)
class ParsedSection:
    text: str
    page_number: int | None


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: int
    chunk_index: int
    text: str
    page_number: int | None


class DocumentIngestionError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None: ...


def parse_document(path: Path, suffix: str) -> list[ParsedSection]: ...
def split_sections(
    document_id: int,
    sections: Sequence[ParsedSection],
    chunk_size: int,
    overlap: int,
) -> list[DocumentChunk]: ...
```

Use `PdfReader(path)` and `page.extract_text()`. Normalize CRLF/CR and repeated horizontal whitespace. Search backward from the size limit for paragraph, newline, Chinese sentence punctuation, then `. `; otherwise hard split. Advance by `end - overlap` and require progress. PDF sections never combine pages.

The only permanent parsing codes are `DOCUMENT_PARSE_ERROR` and
`DOCUMENT_TOO_MANY_CHUNKS`; use their predefined Chinese messages and never include the
path, extracted text, or parser exception text.

- [ ] **Step 5: Run parser/chunker tests GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_document_ingestion.py -q`

- [ ] **Step 6: Write failing Chroma and Embedding tests**

`tests/unit/db/test_chroma.py`:

```python
def test_collection_name_is_deterministic() -> None:
    assert knowledge_collection_name(42) == "marketmind_kb_42"


@pytest.mark.asyncio
async def test_async_http_client_uses_all_connection_settings(monkeypatch) -> None: ...
```

Embedding/index cases:

```python
async def test_embedding_batches_preserve_provider_index_order() -> None: ...
async def test_embedding_usage_is_summed_across_batches() -> None: ...
async def test_embedding_count_mismatch_is_rejected() -> None: ...
async def test_mixed_embedding_dimensions_are_rejected() -> None: ...
async def test_nan_or_infinite_embedding_value_is_rejected() -> None: ...
async def test_index_deletes_document_then_upserts_deterministic_ids() -> None: ...
async def test_retry_after_partial_write_converges_without_duplicate_ids() -> None: ...
```

- [ ] **Step 7: Run Chroma/Embedding tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/db/test_chroma.py tests/unit/services/test_document_ingestion.py -q`

Expected: new functions are absent.

- [ ] **Step 8: Implement Chroma client boundary**

```python
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
```

Keep external construction in one patchable function; do not create a VectorStore interface.

- [ ] **Step 9: Implement validated Embedding and index writes**

```python
@dataclass(frozen=True)
class EmbeddingCompletion:
    vectors: list[list[float]]
    total_tokens: int | None
    dimensions: int


async def request_embeddings(
    texts: Sequence[str], settings: Settings
) -> EmbeddingCompletion: ...


async def index_document_vectors(
    client: AsyncClientAPI,
    knowledge_base: KnowledgeBase,
    document: KnowledgeDocument,
    chunks: Sequence[DocumentChunk],
    embeddings: EmbeddingCompletion,
) -> None: ...
```

Use `AsyncOpenAI(..., max_retries=0)`, batch by configured size, call `embeddings.create(model=..., input=list(batch))`, sort response by `index`, require exact `0..n-1`, one positive dimension, and all `math.isfinite` values. Map SDK errors to safe codes.

The complete Embedding/index error set is `DOCUMENT_CONFIG_ERROR`,
`EMBEDDING_AUTH_ERROR`, `EMBEDDING_REQUEST_ERROR`, `EMBEDDING_UNAVAILABLE`,
`EMBEDDING_INVALID_RESPONSE`, `CHROMA_UNAVAILABLE`, and `DOCUMENT_INTERNAL_ERROR`.
Only unavailable errors are retryable.

Create/get Collection with `{"hnsw:space": "cosine"}`; delete `where={"document_id": document.id}` then upsert explicit IDs, vectors, documents, and scalar metadata. Never ask Chroma to embed.

- [ ] **Step 10: Run Chroma/Embedding GREEN checks**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/db/test_chroma.py tests/unit/services/test_document_ingestion.py -q
.venv\Scripts\ruff.exe check backend/app/db/chroma.py backend/app/services/document_ingestion.py tests/unit/db/test_chroma.py tests/unit/services/test_document_ingestion.py
.venv\Scripts\mypy.exe backend/app/db/chroma.py backend/app/services/document_ingestion.py tests/unit/db/test_chroma.py tests/unit/services/test_document_ingestion.py
```

- [ ] **Step 11: Write failing Worker state-machine tests**

```python
async def test_no_redis_lock_skips_parse_embedding_and_chroma() -> None: ...
async def test_terminal_document_is_ignored() -> None: ...
async def test_pending_moves_processing_then_ready() -> None: ...
async def test_ready_is_written_only_after_chroma_upsert() -> None: ...
async def test_embedding_contract_drift_fails_before_provider_call() -> None: ...
async def test_first_success_saves_embedding_dimensions() -> None: ...
async def test_transient_provider_or_chroma_error_retries_with_backoff() -> None: ...
async def test_permanent_parse_error_is_persisted_without_retry() -> None: ...
async def test_worker_always_closes_engine_redis_and_chroma() -> None: ...
def test_celery_registers_knowledge_task_module() -> None: ...
```

- [ ] **Step 12: Run Worker tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/tasks/test_knowledge.py -q`

- [ ] **Step 13: Implement state helpers and Celery task**

Service helpers:

```python
async def mark_document_processing(
    session, document_id
) -> tuple[KnowledgeDocument, KnowledgeBase] | None: ...
async def mark_document_ready(
    session, document_id, chunk_count, embedding_tokens, embedding_dimensions
) -> KnowledgeDocument | None: ...
async def mark_document_failure(
    session, document_id, code, message
) -> KnowledgeDocument | None: ...
```

Task module:

```python
DOCUMENT_LOCK_PREFIX = "marketmind:lock:knowledge-document"
MAX_DOCUMENT_RETRIES = 3

async def run_document_index_attempt(document_id: int) -> dict[str, int | str]: ...
async def persist_document_failure(document_id: int, code: str, message: str) -> None: ...
def run_document_index_task(task: Task, document_id: int) -> dict[str, int | str]: ...

@celery_app.task(
    bind=True,
    name="app.tasks.knowledge.index_knowledge_document",
    max_retries=MAX_DOCUMENT_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
def index_knowledge_document(self: Task, document_id: int) -> dict[str, int | str]: ...
```

Order: validate config → create Redis/Engine/Chroma → lock → short Session marks processing/detaches state → parse → split → Embed → delete/upsert → new Session marks ready. Close owned resources in `finally`. Retry connection/timeout/limit/5xx/Redis/MySQL/Chroma availability with `2**retries`; persist safe permanent/exhausted failure. Add module to Celery `include`.

- [ ] **Step 14: Run Worker tests GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/tasks/test_knowledge.py -q`

- [ ] **Step 15: Write failing upload API tests**

```python
def test_admin_upload_returns_202_document_task_and_pending_status() -> None: ...
@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ANALYST])
def test_non_admin_upload_is_forbidden(role: Role) -> None: ...
def test_upload_rejects_oversized_file_with_413() -> None: ...
def test_upload_rejects_invalid_extension_content_type_or_bytes_with_422() -> None: ...
def test_duplicate_file_returns_409() -> None: ...
def test_broker_failure_marks_document_failure_and_returns_503() -> None: ...
def test_upload_uses_no_real_embedding_or_chroma_call() -> None: ...
```

- [ ] **Step 16: Run upload API RED**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_knowledge_bases.py -q`

Expected: upload cases return 404/405.

- [ ] **Step 17: Implement upload and dispatch compensation**

Add Admin-only multipart POST `/{knowledge_base_id}/documents`, response `KnowledgeDocumentCreated`, status 202. Validate and stage, call `index_knowledge_document.delay(document.id)`, attach task ID, and return pending row. Broker failure saves `DOCUMENT_INTERNAL_ERROR` / `文档任务投递失败` then raises `KNOWLEDGE_DOCUMENT_DISPATCH_FAILED` 503. Keep the staged file for diagnosis/retry.

- [ ] **Step 18: Run complete Task 2 verification**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/db/test_chroma.py tests/unit/services/test_document_ingestion.py tests/unit/tasks/test_knowledge.py tests/api/test_knowledge_bases.py -q
.venv\Scripts\ruff.exe check backend/app/db/chroma.py backend/app/services/document_ingestion.py backend/app/services/knowledge.py backend/app/tasks/knowledge.py backend/app/api/v1/knowledge_bases.py backend/app/celery_app.py tests/unit/db/test_chroma.py tests/unit/services/test_document_ingestion.py tests/unit/tasks/test_knowledge.py tests/api/test_knowledge_bases.py
.venv\Scripts\mypy.exe backend/app/db/chroma.py backend/app/services/document_ingestion.py backend/app/services/knowledge.py backend/app/tasks/knowledge.py backend/app/api/v1/knowledge_bases.py tests/unit/db/test_chroma.py tests/unit/services/test_document_ingestion.py tests/unit/tasks/test_knowledge.py tests/api/test_knowledge_bases.py
git diff --check
```

- [ ] **Step 19: Write Task 2 learning document**

Write local `docs/learning/phase-5-task-2-document-indexing.md`: pypdf limitations, character chunking, overlap progress, Embedding response order, finite/dimension validation, thin-client explicit embeddings, cosine distance, delete/upsert idempotency, at-least-once costs, resource ownership, retries, actual RED/GREEN failures, and final code explanation. Keep it untracked.

- [ ] **Step 20: Commit Task 2 exactly**

```powershell
git add -- pyproject.toml .env.example backend/app/db/chroma.py backend/app/services/document_ingestion.py backend/app/services/knowledge.py backend/app/tasks/knowledge.py backend/app/api/v1/knowledge_bases.py backend/app/celery_app.py tests/unit/db/test_chroma.py tests/unit/services/test_document_ingestion.py tests/unit/tasks/test_knowledge.py tests/api/test_knowledge_bases.py
git diff --cached --name-status
git diff --cached --check
git commit -m "feat: index knowledge documents in Chroma"
```

---

### Task 3: Evidence-filtered RAG answering, verified citations, and MySQL history

**Deliverable:** Every authenticated role can ask one knowledge base a question; weak evidence refuses without Chat, while strong evidence produces a validated answer with program-generated citations and persisted Token usage.

**Files:**
- Create: `backend/app/services/rag.py`
- Create: `tests/unit/services/test_rag.py`
- Modify: `backend/app/services/knowledge.py`, `backend/app/schemas/knowledge.py`
- Modify: `backend/app/api/v1/knowledge_bases.py`
- Modify: `tests/integration/db/test_knowledge.py`, `tests/api/test_knowledge_bases.py`
- Local only: `docs/learning/phase-5-task-3-rag-question-answering.md`

**Interfaces:**
- Consumes: `request_embeddings()`, `create_chroma_client()`, `knowledge_collection_name()`, Task 1 ORM/history services, current `LLM_*` settings, and Chroma `ids/documents/metadatas/distances`.
- Produces: `RAGCallError`, `RAGCompletion`, `retrieve_chunks()`, `build_rag_messages()`, `request_rag_answer()`, `answer_knowledge_question()`, plus question/history endpoints; Task 4 evaluation reuses retrieval and citation validation.

- [ ] **Step 1: Write failing retrieval/readiness tests**

Create a fake async Collection and pin:

```python
async def test_retrieve_queries_only_requested_collection() -> None: ...
async def test_retrieve_discards_distance_above_threshold() -> None: ...
async def test_retrieve_discards_nan_distance_and_malformed_metadata() -> None: ...
async def test_retrieve_discards_missing_or_non_ready_document() -> None: ...
async def test_retrieve_keeps_rank_order_after_ready_filter() -> None: ...
async def test_embedding_contract_drift_stops_before_embedding() -> None: ...
async def test_embedding_dimension_mismatch_stops_before_chroma() -> None: ...
```

The readiness case returns a missing ID, one processing document, and one ready document; only the ready hit survives.

- [ ] **Step 2: Run retrieval tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag.py -q`

Expected: import failure because `app.services.rag` does not exist.

- [ ] **Step 3: Implement retrieval normalization**

```python
RAG_PROMPT_VERSION = "rag-answer-v1"
REFUSAL_ANSWER = "当前知识库中没有足够依据回答这个问题。"


class RAGCallError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int) -> None: ...


async def retrieve_chunks(
    session: AsyncSession,
    client: AsyncClientAPI,
    knowledge_base: KnowledgeBase,
    question_vector: Sequence[float],
    top_k: int,
    max_distance: float,
) -> list[RetrievedChunk]: ...
```

Query the collection with explicit question vector and include documents, metadatas, distances. Validate the three parallel lists, scalar metadata, base ID, finite distance, and threshold. Query MySQL once for all candidate IDs with `status == READY`; discard all others while preserving Chroma rank order.

- [ ] **Step 4: Run retrieval tests GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag.py -q`

- [ ] **Step 5: Write failing Prompt/output/citation tests**

```python
def test_prompt_keeps_question_and_chunks_out_of_system_instructions() -> None: ...
async def test_no_reliable_chunks_refuses_without_chat_call() -> None: ...
async def test_chat_uses_json_mode_and_configured_model() -> None: ...
@pytest.mark.parametrize("payload", [None, "", "not-json", '{"answer": 1}'])
async def test_empty_malformed_or_schema_invalid_output_is_rejected(payload) -> None: ...
async def test_fabricated_or_zero_citation_number_is_rejected() -> None: ...
async def test_success_maps_only_real_chunk_numbers_to_citations() -> None: ...
async def test_refused_output_cannot_carry_citations() -> None: ...
async def test_answer_and_embedding_token_usage_are_combined() -> None: ...
async def test_provider_errors_map_to_safe_status_without_secret_text() -> None: ...
```

- [ ] **Step 6: Run Prompt/answer tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag.py -q`

Expected: new cases fail because Prompt and Chat functions are absent.

- [ ] **Step 7: Implement Prompt, Chat, and citation mapping**

```python
@dataclass(frozen=True)
class RAGCompletion:
    answer: str
    status: KnowledgeQueryStatus
    citations: list[KnowledgeCitation]
    embedding_tokens: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


def build_rag_messages(
    question: str, chunks: Sequence[RetrievedChunk]
) -> list[ChatCompletionMessageParam]: ...


async def request_rag_answer(
    question: str,
    chunks: Sequence[RetrievedChunk],
    settings: Settings,
) -> RAGCompletion: ...
```

System instructions state that question/chunks are untrusted, only numbered evidence may be used, tools/network are unavailable, and output is JSON with `answer`, `cited_chunk_numbers`, `refused`. Put untrusted payload in the user message as JSON.

Use `AsyncOpenAI(..., max_retries=0)` and Chat Completions JSON Mode. Parse with `RAGModelResult.model_validate(..., strict=True)`. A non-refusal needs at least one unique integer in `1..len(chunks)`; a refusal needs none. Map citations only from selected `RetrievedChunk` objects, never model source text.

Map missing/drifted configuration to `RAG_CONFIG_MISSING`/503, transient provider or
Chroma failure to `RAG_PROVIDER_UNAVAILABLE`/503, and malformed or unverifiable model
output to `RAG_INVALID_RESPONSE`/502. Persist only these stable codes and messages.

- [ ] **Step 8: Run RAG unit tests GREEN and static checks**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag.py -q
.venv\Scripts\ruff.exe check backend/app/services/rag.py tests/unit/services/test_rag.py
.venv\Scripts\mypy.exe backend/app/services/rag.py tests/unit/services/test_rag.py
```

- [ ] **Step 9: Write failing history/orchestration integration tests**

```python
async def test_success_query_persists_verified_citations_and_usage(session) -> None: ...
async def test_refused_query_persists_empty_citations(session) -> None: ...
async def test_provider_failure_persists_safe_failure_without_secret(session) -> None: ...
async def test_query_detail_requires_matching_knowledge_base(session) -> None: ...
async def test_query_history_is_descending_and_paginated(session) -> None: ...
async def test_external_calls_run_without_open_database_transaction() -> None: ...
```

- [ ] **Step 10: Implement query history and orchestration**

Add to `knowledge.py`:

```python
async def create_query_history(
    session, knowledge_base_id, asked_by_id, question, provider, model, completion
) -> KnowledgeQuery: ...
async def create_query_failure(
    session, knowledge_base_id, asked_by_id, question, provider, model, code, message
) -> KnowledgeQuery: ...
async def get_knowledge_query(session, knowledge_base_id, query_id) -> KnowledgeQuery: ...
async def list_knowledge_queries(
    session, knowledge_base_id, page, page_size
) -> tuple[list[KnowledgeQuery], int]: ...
```

Add to `rag.py`:

```python
async def answer_knowledge_question(
    session: AsyncSession,
    knowledge_base_id: int,
    asked_by_id: int,
    payload: KnowledgeQuestionCreate,
    settings: Settings,
) -> KnowledgeQuery: ...
```

Load base and ready-document existence, end the read transaction, call question Embedding, create Chroma, retrieve, close Chroma, refuse without Chat for no hits, otherwise call Chat, and persist one terminal query in a new short transaction. On provider/Chroma errors persist stable code/message before raising `AppError`. Do not store raw responses.

- [ ] **Step 11: Run history integration GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/db/test_knowledge.py tests/unit/services/test_rag.py -q`

- [ ] **Step 12: Write failing question API/RBAC tests**

```python
@pytest.mark.parametrize("role", list(Role))
def test_all_roles_can_ask_and_receive_verified_citations(role: Role) -> None: ...
def test_empty_base_returns_409_without_model_call() -> None: ...
def test_weak_retrieval_returns_refused_and_empty_citations() -> None: ...
def test_provider_unavailable_returns_503_and_persists_failure() -> None: ...
def test_invalid_provider_response_returns_502_and_persists_failure() -> None: ...
@pytest.mark.parametrize("role", list(Role))
def test_all_roles_can_list_and_read_query_history(role: Role) -> None: ...
def test_query_from_other_base_returns_404() -> None: ...
```

- [ ] **Step 13: Run question API RED**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_knowledge_bases.py -q`

- [ ] **Step 14: Implement question/history endpoints**

Add authenticated POST `/{knowledge_base_id}/questions`, GET question page, and GET one query. All roles use `get_current_user`. Create `Settings()` only at the API boundary and pass it to the service. Return the persisted row so immediate response equals later history.

- [ ] **Step 15: Run complete Task 3 verification**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag.py tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py -q
.venv\Scripts\ruff.exe check backend/app/schemas/knowledge.py backend/app/services/knowledge.py backend/app/services/rag.py backend/app/api/v1/knowledge_bases.py tests/unit/services/test_rag.py tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py
.venv\Scripts\mypy.exe backend/app/schemas/knowledge.py backend/app/services/knowledge.py backend/app/services/rag.py backend/app/api/v1/knowledge_bases.py tests/unit/services/test_rag.py tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py
git diff --check
```

- [ ] **Step 16: Write Task 3 learning document**

Write local `docs/learning/phase-5-task-3-rag-question-answering.md`: query Embedding, collection isolation, cosine distance, ready post-filtering, injection boundary, JSON Mode versus schema validation, citation provenance, refusal cost saving, AsyncOpenAI, transaction boundaries, failure history, Token accounting, model switching, actual failures, and final code explanation. Keep it untracked.

- [ ] **Step 17: Commit Task 3 exactly**

```powershell
git add -- backend/app/schemas/knowledge.py backend/app/services/knowledge.py backend/app/services/rag.py backend/app/api/v1/knowledge_bases.py tests/unit/services/test_rag.py tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py
git diff --cached --name-status
git diff --cached --check
git commit -m "feat: add cited RAG question answering"
```

---

### Task 4: RAG evaluation, operations documentation, and full acceptance

**Deliverable:** A deterministic evaluation service and CLI report Hit@K, MRR, citation validity, refusal accuracy, failures, and latency; documentation explains Chroma/providers; the complete repository passes regression checks.

**Files:**
- Create: `backend/app/services/rag_evaluation.py`
- Create: `scripts/evaluate_rag.py`
- Create: `tests/unit/services/test_rag_evaluation.py`
- Modify: `.env.example`, `README.md`
- Modify existing tests only when a Phase 5 behavior legitimately changes their fixture/import expectations
- Local only: `docs/learning/phase-5-task-4-evaluation-acceptance.md`

**Interfaces:**
- Consumes: `RetrievedChunk`, verified `KnowledgeCitation`, `retrieve_chunks()`, and Task 3 answer results.
- Produces: `EvaluationCase`, `CaseEvaluation`, `EvaluationReport`, `reciprocal_rank()`, `evaluate_case()`, `summarize_evaluations()`, and CLI JSON output.

- [ ] **Step 1: Write failing metric and JSONL tests**

```python
def test_reciprocal_rank_uses_first_relevant_document() -> None:
    assert reciprocal_rank([8, 3, 5], {3, 9}) == 0.5


def test_no_relevant_hit_has_zero_reciprocal_rank() -> None:
    assert reciprocal_rank([8, 3, 5], {9}) == 0.0


def test_hit_at_k_is_one_when_any_relevant_document_is_retrieved() -> None: ...
def test_citation_validity_requires_every_citation_from_retrieval() -> None: ...
def test_refusal_accuracy_matches_expected_boolean() -> None: ...
def test_summary_averages_metrics_and_counts_failures() -> None: ...
@pytest.mark.parametrize("bad_line", ["not-json", "{}", '{"question":""}'])
def test_invalid_jsonl_reports_line_number_without_full_content(bad_line: str) -> None: ...
```

- [ ] **Step 2: Run evaluation tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag_evaluation.py -q`

Expected: import failure because the service does not exist.

- [ ] **Step 3: Implement typed cases and pure metrics**

```python
class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2_000)
    relevant_document_ids: set[int] = Field(default_factory=set)
    should_refuse: bool


class CaseEvaluation(BaseModel):
    question: str
    hit_at_k: float = Field(ge=0, le=1)
    reciprocal_rank: float = Field(ge=0, le=1)
    citation_valid: float = Field(ge=0, le=1)
    refusal_correct: float = Field(ge=0, le=1)
    latency_ms: float = Field(ge=0)
    error_code: str | None = None


class EvaluationReport(BaseModel):
    case_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    hit_at_k: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    citation_valid_rate: float = Field(ge=0, le=1)
    refusal_accuracy: float = Field(ge=0, le=1)
    average_latency_ms: float = Field(ge=0)
    cases: list[CaseEvaluation]


def load_evaluation_cases(path: Path) -> list[EvaluationCase]: ...
def reciprocal_rank(retrieved_document_ids: Sequence[int], relevant: set[int]) -> float: ...
def evaluate_case(...) -> CaseEvaluation: ...
def summarize_evaluations(cases: Sequence[CaseEvaluation]) -> EvaluationReport: ...
```

Use stdlib JSON/Path/statistics plus Pydantic. Reject an empty file. Include the 1-based line number in validation errors without echoing the full invalid line.

- [ ] **Step 4: Run pure metric tests GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag_evaluation.py -q`

- [ ] **Step 5: Write failing CLI/orchestration tests**

```python
async def test_evaluation_runner_reuses_production_rag_path() -> None: ...
def test_cli_writes_utf8_json_report_to_requested_path() -> None: ...
def test_cli_does_not_run_without_explicit_live_flag() -> None: ...
def test_case_failure_is_counted_and_does_not_abort_remaining_cases() -> None: ...
```

Without `--live`, the CLI must exit non-zero before creating OpenAI or Chroma clients.

- [ ] **Step 6: Run CLI tests RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag_evaluation.py -q`

- [ ] **Step 7: Implement evaluation runner and guarded CLI**

The async runner measures each case using `time.perf_counter()`, calls production retrieval/answer boundaries, records one safe error code on a failed case, and continues. Keep formulas pure.

Create argparse CLI:

```text
--knowledge-base-id INTEGER  required and positive
--cases PATH                 required
--output PATH                required
--live                       mandatory external-call guard
```

Write UTF-8 JSON using `json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)`. Do not print questions, chunks, credentials, or raw provider errors.

- [ ] **Step 8: Run evaluation GREEN and static checks**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/services/test_rag_evaluation.py -q
.venv\Scripts\ruff.exe check backend/app/services/rag_evaluation.py scripts/evaluate_rag.py tests/unit/services/test_rag_evaluation.py
.venv\Scripts\mypy.exe backend/app/services/rag_evaluation.py scripts/evaluate_rag.py tests/unit/services/test_rag_evaluation.py
```

- [ ] **Step 9: Update configuration and operations documentation**

Append every Phase 5 variable from the design to `.env.example`, leaving keys empty. Update README with feature/endpoints, MySQL-versus-Chroma ownership, official Chroma container startup with persistent volume, migration/Worker commands, file restrictions, provider configuration locations, mandatory reindex/new base after changing Embedding, guarded evaluation usage/cost warning, scanned-PDF limitation, and no-paid-call automation statement.

- [ ] **Step 10: Run migration-chain and focused API acceptance**

```powershell
.venv\Scripts\alembic.exe -x database=test upgrade head
.venv\Scripts\python.exe -m pytest tests/integration/db/test_knowledge.py tests/api/test_knowledge_bases.py -q
```

Expected: migration reaches `0004`; RAG integration/API tests pass against `marketmind_test`.

- [ ] **Step 11: Run full repository quality gate**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests scripts
git diff --check
```

Expected: zero pytest failures; Ruff, mypy, and Git checks exit 0. Record exact counts and real repairs.

- [ ] **Step 12: Run secrets and accidental-network audit**

Do not open `.env`. Search tracked implementation surfaces for credential-shaped literals and test constructors. Confirm every test external client is patched or fake-controlled before invocation. The audit must not output actual environment values.

- [ ] **Step 13: Write Task 4 tutorial and finalize all Phase 5 tutorials**

Write local `docs/learning/phase-5-task-4-evaluation-acceptance.md`: formulas with worked examples, JSONL, CLI guard, model-switch table, Chroma operations, migration/full-test evidence, actual failures/fixes, complete data/transaction/task sequence, security/cost limitations, resume-ready summary, interview questions, and manual acceptance checklist marked unexecuted unless approved.

Re-open the other three Phase 5 tutorials and ensure they include final code, file/line responsibilities, import provenance, writing order, framework mechanisms, evidence, and debugging history. Keep all four untracked.

- [ ] **Step 14: Commit Task 4 exactly**

```powershell
git add -- .env.example README.md backend/app/services/rag_evaluation.py scripts/evaluate_rag.py tests/unit/services/test_rag_evaluation.py
git diff --cached --name-status
git diff --cached --check
git commit -m "feat: add RAG evaluation and operations guide"
```

- [ ] **Step 15: Prepare final review evidence**

```powershell
git merge-base main HEAD
git rev-parse HEAD
git log --oneline --decorate main..HEAD
git diff --stat main...HEAD
git status --short
```

Use `superpowers:requesting-code-review` for one independent whole-branch review. Explicit review focus: the five items above, MySQL/file/Chroma compensation, async resource ownership, provider error secrecy, migration downgrade order, and mocked external calls. Every Critical/Important finding gets a new failing test, observed RED, GREEN fix, full quality gate, and fix commit. Record Minor findings without silently expanding scope.

## Manual acceptance excluded from automated completion

Mocked deterministic tests can complete engineering. A paid live acceptance needs separate explicit approval. When approved, index one small document and ask one answerable plus one unanswerable question; verify MySQL rows and Chroma citations without printing `.env` or credentials.
