export interface SemanticReview {
  id: number; product_id: number; status: 'pending' | 'running' | 'success' | 'failure'
  product_snapshot: { sku: string; title: string; description: string; bullet_points: string[] }
  provider: string; model: string; score: number | null
  dimension_scores: Record<string, number> | null; summary: string | null
  issues: { dimension: string; severity: string; field: string; message: string; suggestion: string }[] | null
  rewrite: { title: string; description: string; bullet_points: string[] } | null
  total_tokens: number | null; error_code: string | null; error_message: string | null; created_at: string
}
export interface SemanticReviewCreated { review_id: number; task_id: string; status: SemanticReview['status'] }
