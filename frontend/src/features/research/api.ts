import { apiFile, apiJson } from '../../lib/api'
import type { Page } from '../../lib/types'
import type { ResearchCreated, ResearchReview, ResearchRun } from './types'

const base = (productId: number) => `/products/${productId}/research-runs`
export async function createResearch(productId: number, goal: string, knowledgeBaseIds: number[]): Promise<ResearchCreated> {
  const trimmed = goal.trim()
  if (!trimmed || trimmed.length > 500) throw new Error('研究目标需为 1–500 个字符')
  if (knowledgeBaseIds.length < 1 || knowledgeBaseIds.length > 3 || new Set(knowledgeBaseIds).size !== knowledgeBaseIds.length || knowledgeBaseIds.some((id) => !Number.isInteger(id) || id <= 0)) {
    throw new Error('请选择 1–3 个不同的知识库')
  }
  return apiJson(base(productId), { method: 'POST', body: JSON.stringify({ goal: trimmed, knowledge_base_ids: knowledgeBaseIds }) })
}
export const listResearchRuns = (productId: number, page: number) => apiJson<Page<ResearchRun>>(`${base(productId)}?page=${page}`)
export const getResearchRun = (productId: number, runId: number) => apiJson<ResearchRun>(`${base(productId)}/${runId}`)
export const reviewResearchRun = (productId: number, runId: number, decision: 'approved' | 'rejected', comment?: string) => apiJson<ResearchReview>(`${base(productId)}/${runId}/review`, { method: 'POST', body: JSON.stringify({ decision, comment: comment?.trim() || null }) })
export const downloadResearchRun = (productId: number, runId: number) => apiFile(`${base(productId)}/${runId}/export`, `research-${runId}.xlsx`)
