import { afterEach, expect, it, vi } from 'vitest'
import { apiFile, apiJson } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

it('adds bearer token to authenticated API requests', async () => {
  sessionStorage.setItem('marketmind_access_token', 'sample-token')
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)

  await apiJson<{ items: unknown[] }>('/products')

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toBe('/api/v1/products')
  expect(new Headers(options.headers).get('Authorization')).toBe('Bearer sample-token')
})

it('decodes a safe business error and request ID', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
    new Response(JSON.stringify({
      code: 'RESEARCH_REVIEW_CONFLICT',
      message: '审核状态冲突',
      request_id: 'req-42',
    }), { status: 409 }),
  ))

  await expect(apiJson('/products/1')).rejects.toMatchObject({
    status: 409,
    code: 'RESEARCH_REVIEW_CONFLICT',
    message: '审核状态冲突',
    requestId: 'req-42',
  })
})

it('clears an expired authenticated session on 401', async () => {
  sessionStorage.setItem('marketmind_access_token', 'expired-token')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
    new Response(JSON.stringify({
      code: 'AUTH_INVALID_TOKEN', message: '登录凭证无效', request_id: 'req-401',
    }), { status: 401 }),
  ))

  await expect(apiJson('/auth/me')).rejects.toMatchObject({ status: 401 })
  expect(sessionStorage.getItem('marketmind_access_token')).toBeNull()
})

it('uses a safe error when the server returns non-JSON text', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
    new Response('<html>internal stack</html>', { status: 503 }),
  ))

  await expect(apiJson('/products')).rejects.toMatchObject({
    status: 503,
    code: 'HTTP_ERROR',
    message: '服务暂时不可用，请稍后重试',
    requestId: null,
  })
})

it('sets JSON content type only for JSON string bodies', async () => {
  const fetchMock = vi.fn().mockImplementation(async () => new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  await apiJson('/products', { method: 'POST', body: JSON.stringify({ sku: 'A' }) })
  const jsonHeaders = new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers)
  expect(jsonHeaders.get('Content-Type')).toBe('application/json')

  await apiJson('/products/import', { method: 'POST', body: new FormData() })
  const formHeaders = new Headers((fetchMock.mock.calls[1][1] as RequestInit).headers)
  expect(formHeaders.has('Content-Type')).toBe(false)
})

it('keeps the session on 403 and anonymous login 401', async () => {
  sessionStorage.setItem('marketmind_access_token', 'keep-me')
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('{}', { status: 403 }))
    .mockResolvedValueOnce(new Response('{}', { status: 401 })))
  await expect(apiJson('/users')).rejects.toMatchObject({ status: 403 })
  await expect(apiJson('/auth/token', { method: 'POST' }, false)).rejects.toMatchObject({ status: 401 })
  expect(sessionStorage.getItem('marketmind_access_token')).toBe('keep-me')
})

it.each([409, 422, 429])('keeps server error details for %i', async (status) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    JSON.stringify({ code: `ERROR_${status}`, message: '业务操作未完成', request_id: 'trace-1' }),
    { status },
  )))
  await expect(apiJson('/products')).rejects.toMatchObject({
    status, code: `ERROR_${status}`, message: '业务操作未完成', requestId: 'trace-1',
  })
})

it('downloads with bearer and revokes the blob URL', async () => {
  sessionStorage.setItem('marketmind_access_token', 'download-token')
  const fetchMock = vi.fn().mockResolvedValue(new Response('xlsx', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const createObjectURL = vi.fn().mockReturnValue('blob:download')
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  await apiFile('/products/export', 'products.xlsx')
  expect(new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers).get('Authorization'))
    .toBe('Bearer download-token')
  expect(click).toHaveBeenCalledOnce()
  expect(revokeObjectURL).toHaveBeenCalledWith('blob:download')
  click.mockRestore()
})
