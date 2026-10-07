import { afterEach, expect, it, vi } from 'vitest'
import { createResearch, downloadResearchRun, getResearchRun } from './api'

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); vi.restoreAllMocks() })

it('trims goal and rejects duplicate or out-of-range knowledge-base IDs', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ run_id: 7, task_id: 'job-1', status: 'pending' }), { status: 202 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(createResearch(2, '  比较市场机会  ', [1, 2])).resolves.toMatchObject({ run_id: 7 })
  expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ goal: '比较市场机会', knowledge_base_ids: [1, 2] })
  await expect(createResearch(2, '目标', [1, 1])).rejects.toThrow()
  await expect(createResearch(2, '目标', [])).rejects.toThrow()
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it('reads accepted run by returned ID and downloads with bearer', async () => {
  sessionStorage.setItem('marketmind_access_token', 'token')
  const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(url.endsWith('/export') ? 'xlsx' : '{}'))
  vi.stubGlobal('fetch', fetchMock)
  const NativeURL = URL
  const revoke = vi.fn()
  vi.stubGlobal('URL', class extends NativeURL { static createObjectURL = vi.fn().mockReturnValue('blob:report'); static revokeObjectURL = revoke })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  await getResearchRun(2, 7)
  await downloadResearchRun(2, 7)
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/products/2/research-runs/7')
  expect(new Headers(fetchMock.mock.calls[1][1].headers).get('Authorization')).toBe('Bearer token')
  expect(revoke).toHaveBeenCalledWith('blob:report')
})
