import { afterEach, expect, it, vi } from 'vitest'
import { askKnowledge, createKnowledgeBase, uploadDocument } from './api'

afterEach(() => vi.unstubAllGlobals())

it('creates a base with only name and description', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  await createKnowledgeBase({ name: '说明书', description: '官方资料' })
  expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ name: '说明书', description: '官方资料' })
})

it('uploads a document with FormData and no manually set content type', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  await uploadDocument(1, new File(['hello'], 'manual.txt', { type: 'text/plain' }))
  const init = fetchMock.mock.calls[0][1] as RequestInit
  expect(init.body).toBeInstanceOf(FormData)
  expect(new Headers(init.headers).has('Content-Type')).toBe(false)
})

it('keeps synchronous answer refusal and citations', async () => {
  const answer = { id: 1, status: 'refused', answer: '资料不足', citations: [] }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(answer))))
  await expect(askKnowledge(1, '这个商品适合谁？')).resolves.toMatchObject(answer)
})
