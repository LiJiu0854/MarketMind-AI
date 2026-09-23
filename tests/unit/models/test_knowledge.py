from typing import cast

from sqlalchemy import CheckConstraint, Table, UniqueConstraint

from app.models.knowledge import (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeQuery,
    KnowledgeQueryStatus,
)


def test_knowledge_models_keep_the_database_contract() -> None:
    base_table = cast(Table, KnowledgeBase.__table__)
    document_table = cast(Table, KnowledgeDocument.__table__)
    query_table = cast(Table, KnowledgeQuery.__table__)

    assert base_table.name == "knowledge_bases"
    assert document_table.name == "knowledge_documents"
    assert query_table.name == "knowledge_queries"
    assert {item.value for item in KnowledgeDocumentStatus} == {
        "pending",
        "processing",
        "ready",
        "failure",
    }
    assert {item.value for item in KnowledgeQueryStatus} == {
        "success",
        "refused",
        "failure",
    }
    assert KnowledgeBase.created_by_id.property.columns[0].foreign_keys
    assert KnowledgeDocument.knowledge_base_id.property.columns[0].foreign_keys
    assert KnowledgeDocument.uploaded_by_id.property.columns[0].foreign_keys
    assert KnowledgeQuery.knowledge_base_id.property.columns[0].foreign_keys
    assert KnowledgeQuery.asked_by_id.property.columns[0].foreign_keys
    assert any(
        isinstance(item, UniqueConstraint) and item.name == "uq_knowledge_documents_base_sha256"
        for item in document_table.constraints
    )
    assert {
        item.name
        for table in (base_table, document_table, query_table)
        for item in table.constraints
        if isinstance(item, CheckConstraint)
    } >= {
        "ck_knowledge_bases_embedding_dimensions_positive",
        "ck_knowledge_documents_size_positive",
        "ck_knowledge_documents_chunk_count_non_negative",
        "ck_knowledge_documents_embedding_tokens_non_negative",
        "ck_knowledge_queries_token_counts_non_negative",
    }
