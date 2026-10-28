import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../lib/session'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppShell from './AppShell.vue'
import ResearchPage from '../features/research/ResearchPage.vue'
import KnowledgeBasePage from '../features/knowledge/KnowledgeBasePage.vue'

afterEach(() => { currentUser.value = null; vi.unstubAllGlobals() })

it.each(['analyst', 'operator'] as const)('hides user management from %s navigation', (role) => {
  currentUser.value = { id: 2, email: 'member@example.com', full_name: '成员', role, is_active: true, created_at: '', updated_at: '' }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
  const wrapper = mount(AppShell, { global: { plugins: [router], stubs: ['RouterView'] } })
  expect(wrapper.text()).not.toContain('用户管理')
  expect(wrapper.text()).toContain('商品运营')
})

it('shows the new report when navigating between research detail URLs', async () => {
  currentUser.value = { id: 1, email: 'admin@example.com', full_name: '管理员', role: 'admin', is_active: true, created_at: '', updated_at: '' }
  const fetchMock = vi.fn().mockImplementation(async (url: string) => {
    const id = Number(url.split('/').pop())
    return new Response(JSON.stringify({
      id, product_id: 1, goal: `报告 ${id}`, knowledge_base_ids: [], status: 'failed',
      steps: [], evidence: [], report: null, review_status: 'not_ready', review: null,
      provider: 'fixture', model: 'fixture', total_tokens: null,
    }))
  })
  vi.stubGlobal('fetch', fetchMock)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/users', component: { template: '<div />' } },
      { path: '/products/:productId/research-runs/:runId', component: ResearchPage, props: true, meta: { remountOnParamChange: true } },
    ],
  })
  await router.push('/products/1/research-runs/4')
  await router.isReady()
  const wrapper = mount(AppShell, { global: { plugins: [router], stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('报告 4'))
  await router.push('/products/1/research-runs/5')
  await vi.waitFor(() => expect(wrapper.text()).toContain('报告 5'))
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe('/api/v1/products/1/research-runs/5')
  wrapper.unmount()
})

it('shows the new knowledge base when its URL parameter changes', async () => {
  currentUser.value = { id: 2, email: 'analyst@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify(
    /\/knowledge-bases\/\d+$/.test(url)
      ? { id: Number(url.split('/').pop()), name: `资料库 ${url.split('/').pop()}`, description: null }
      : { items: [], total: 0, page: 1, page_size: 20 },
  ))))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/knowledge-bases/:id', component: KnowledgeBasePage, props: true, meta: { remountOnParamChange: true } }],
  })
  await router.push('/knowledge-bases/1')
  await router.isReady()
  const wrapper = mount(AppShell, { global: { plugins: [router], stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('资料库 1'))
  await router.push('/knowledge-bases/2')
  await vi.waitFor(() => expect(wrapper.text()).toContain('资料库 2'))
  wrapper.unmount()
})
