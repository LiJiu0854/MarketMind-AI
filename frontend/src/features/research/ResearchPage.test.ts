import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../../lib/session'
import ResearchPage from './ResearchPage.vue'

afterEach(() => { currentUser.value = null; vi.unstubAllGlobals() })

const base = { id: 4, product_id: 1, goal: '机会分析', knowledge_base_ids: [3], product_snapshot: {}, status: 'success', steps: [], evidence: [], report: { outcome: 'insufficient_evidence', summary: '资料不足', findings: [], recommendations: [], evidence_gaps: ['证据不足'] }, total_tokens: 120, review_status: 'not_reviewable', review: null }

it('rejects unreviewable and unapproved actions', async () => {
  currentUser.value = { id: 1, email: 'a@example.com', full_name: '管理员', role: 'admin', is_active: true, created_at: '', updated_at: '' }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(base)))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ResearchPage, { props: { productId: '1', runId: '4' }, global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('证据不足'))
  expect(wrapper.text()).not.toContain('批准报告')
  expect(wrapper.text()).not.toContain('下载 Excel')
  expect(fetchMock.mock.calls.every(([, init]) => !init || init.method !== 'POST')).toBe(true)
})

it('shows a conflict from direct approval without initiating download', async () => {
  currentUser.value = { id: 1, email: 'a@example.com', full_name: '管理员', role: 'admin', is_active: true, created_at: '', updated_at: '' }
  const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => init?.method === 'POST'
    ? new Response(JSON.stringify({ code: 'RESEARCH_REVIEW_CONFLICT', message: '审核状态已变化', request_id: 'r1' }), { status: 409 })
    : new Response(JSON.stringify({ ...base, review_status: 'pending_review', report: { outcome: 'supported', summary: '有证据结论', findings: [{ claim: '发现', source_ids: ['product:1:snapshot'] }], recommendations: [], evidence_gaps: [] }, evidence: [{ source_id: 'product:1:snapshot', source_type: 'product', text: '商品快照' }] })))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ResearchPage, { props: { productId: '1', runId: '4' }, global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('有证据结论'))
  await wrapper.get('button[data-test="approve"]').trigger('click')
  await wrapper.get('[role="alertdialog"] .button.danger').trigger('click')
  await vi.waitFor(() => expect(wrapper.text()).toContain('审核状态已变化'))
  expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/export'))).toBe(false)
})

it('shows persisted action steps and separate token usage', async () => {
  currentUser.value = { id: 2, email: 'a@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...base,
    steps: [{ number: 1, action: { action: 'search_knowledge', knowledge_base_id: 3, query: '价格策略' }, source_ids: ['kb:3:document:4:chunk:0'], prompt_tokens: 40, completion_tokens: 12, embedding_tokens: 8, at: '2026-10-07T00:00:00Z' }],
    prompt_tokens: 40, completion_tokens: 12, embedding_tokens: 8,
  }))))
  const wrapper = mount(ResearchPage, { props: { productId: '1', runId: '4' }, global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('价格策略'))
  expect(wrapper.text()).toContain('kb:3:document:4:chunk:0')
  expect(wrapper.text()).toContain('40')
  expect(wrapper.text()).toContain('12')
  expect(wrapper.text()).toContain('8')
})

it('allows analyst to download only an approved report without rendering report HTML', async () => {
  currentUser.value = { id: 2, email: 'a@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  sessionStorage.setItem('marketmind_access_token', 'download-token')
  const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(url.endsWith('/export')
    ? 'xlsx'
    : JSON.stringify({ ...base, review_status: 'approved', report: { ...base.report, summary: '<img src=x onerror=alert(1)>' } })))
  vi.stubGlobal('fetch', fetchMock)
  const NativeURL = URL
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', class extends NativeURL { static createObjectURL = vi.fn().mockReturnValue('blob:approved'); static revokeObjectURL = revokeObjectURL })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const wrapper = mount(ResearchPage, { props: { productId: '1', runId: '4' }, global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('下载 Excel'))
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('<img src=x')
  await wrapper.get('button').trigger('click')
  await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/export'))).toBe(true))
  const request = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/export'))
  expect(new Headers(request?.[1]?.headers).get('Authorization')).toBe('Bearer download-token')
  await vi.waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:approved'))
  sessionStorage.clear()
  vi.restoreAllMocks()
})
