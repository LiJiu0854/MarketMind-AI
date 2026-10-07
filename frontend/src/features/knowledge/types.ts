export interface KnowledgeBase { id: number; name: string; description: string | null; embedding_provider: string; embedding_model: string; embedding_dimensions: number | null; created_at: string }
export interface KnowledgeBaseCreate { name: string; description: string | null }
export interface KnowledgeDocument { id: number; original_name: string; size_bytes: number; status: 'pending' | 'processing' | 'ready' | 'failure'; chunk_count: number; error_code: string | null; error_message: string | null; created_at: string }
export interface KnowledgeDocumentCreated { document_id: number; task_id: string; status: KnowledgeDocument['status'] }
export interface KnowledgeCitation { document_id: number; original_name: string; chunk_id: string; chunk_index: number; page_number: number | null; excerpt: string; distance: number }
export interface KnowledgeQuery { id: number; question: string; status: 'success' | 'refused' | 'failure'; answer: string | null; citations: KnowledgeCitation[]; total_tokens: number | null; error_message: string | null; created_at: string }
