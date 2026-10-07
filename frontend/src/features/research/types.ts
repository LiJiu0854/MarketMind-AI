export type ResearchStatus = 'pending' | 'running' | 'success' | 'failure'
export type ReviewStatus = 'not_ready' | 'not_reviewable' | 'pending_review' | 'approved' | 'rejected'
export interface ResearchEvidence {
  source_id: string; source_type: 'product' | 'knowledge'; text: string; original_name: string | null
  page_number: number | null; document_id: number | null; knowledge_base_id: number | null
}
export interface ResearchReport {
  outcome: 'supported' | 'insufficient_evidence'; summary: string
  findings: { claim: string; source_ids: string[] }[]
  recommendations: { action: string; reason: string; source_ids: string[] }[]
  evidence_gaps: string[]
}
export interface ResearchReview { id: number; run_id: number; reviewed_by_id: number; decision: 'approved' | 'rejected'; comment: string | null; reviewed_at: string }
export interface ResearchStep {
  number: number; action: { action: 'read_product' | 'search_knowledge' | 'finish'; knowledge_base_id?: number; query?: string }
  source_ids: string[]; prompt_tokens: number | null; completion_tokens: number | null
  embedding_tokens: number | null; at: string
}
export interface ResearchRun {
  id: number; product_id: number; goal: string; knowledge_base_ids: number[]; status: ResearchStatus
  product_snapshot: Record<string, unknown>; steps: ResearchStep[]; evidence: ResearchEvidence[]
  report: ResearchReport | null; provider: string; model: string; total_tokens: number | null
  prompt_tokens: number | null; completion_tokens: number | null; embedding_tokens: number | null
  error_code: string | null; error_message: string | null; review_status: ReviewStatus; review: ResearchReview | null
  created_at: string; completed_at: string | null
}
export interface ResearchCreated { run_id: number; task_id: string; status: ResearchStatus }
