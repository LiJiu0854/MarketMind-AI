import { apiJson } from '../../lib/api'
import type { Page } from '../../lib/types'
import type { KnowledgeBase, KnowledgeBaseCreate, KnowledgeDocument, KnowledgeDocumentCreated, KnowledgeQuery } from './types'

export const listKnowledgeBases = (page: number) => apiJson<Page<KnowledgeBase>>(`/knowledge-bases?page=${page}`)
export const getKnowledgeBase = (id: number) => apiJson<KnowledgeBase>(`/knowledge-bases/${id}`)
export const createKnowledgeBase = (input: KnowledgeBaseCreate) => apiJson<KnowledgeBase>('/knowledge-bases', { method: 'POST', body: JSON.stringify(input) })
export const listDocuments = (baseId: number, page: number) => apiJson<Page<KnowledgeDocument>>(`/knowledge-bases/${baseId}/documents?page=${page}`)
export const getDocument = (baseId: number, documentId: number) => apiJson<KnowledgeDocument>(`/knowledge-bases/${baseId}/documents/${documentId}`)
export function uploadDocument(baseId: number, file: File): Promise<KnowledgeDocumentCreated> {
  const body = new FormData(); body.set('file', file)
  return apiJson(`/knowledge-bases/${baseId}/documents`, { method: 'POST', body })
}
export const askKnowledge = (baseId: number, question: string) => apiJson<KnowledgeQuery>(`/knowledge-bases/${baseId}/questions`, { method: 'POST', body: JSON.stringify({ question: question.trim() }) })
export const listQuestions = (baseId: number, page: number) => apiJson<Page<KnowledgeQuery>>(`/knowledge-bases/${baseId}/questions?page=${page}`)
