import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../../lib/session'
import ResearchPanel from './ResearchPanel.vue'

afterEach(() => { currentUser.value = null; vi.unstubAllGlobals() })

it('does not offer research creation to an analyst', async () => {
  currentUser.value = { id: 2, email: 'a@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify(url.includes('knowledge-bases') ? { items: [], total: 0, page: 1, page_size: 20 } : { items: [], total: 0, page: 1, page_size: 20 }))))
  const wrapper = mount(ResearchPanel, { props: { productId: 1 }, global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('暂无研究记录'))
  expect(wrapper.text()).not.toContain('发起研究')
})

it('can select a knowledge base beyond the first page', async () => {
  currentUser.value = { id: 2, email: 'o@example.com', full_name: '运营', role: 'operator', is_active: true, created_at: '', updated_at: '' }
  const fetchMock = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify(
    url.includes('knowledge-bases?page=2')
      ? { items: [{ id: 21, name: '第二页资料' }], total: 21, page: 2, page_size: 20 }
      : url.includes('knowledge-bases?page=1')
        ? { items: Array.from({ length: 20 }, (_, index) => ({ id: index + 1, name: `资料${index + 1}` })), total: 21, page: 1, page_size: 20 }
        : { items: [], total: 0, page: 1, page_size: 20 },
  )))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ResearchPanel, { props: { productId: 1 }, global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('资料20'))
  await wrapper.get('button[data-test="more-bases"]').trigger('click')
  await vi.waitFor(() => expect(wrapper.text()).toContain('第二页资料'))
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes('knowledge-bases?page=2'))).toBe(true)
})
