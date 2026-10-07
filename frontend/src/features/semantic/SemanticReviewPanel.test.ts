import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../../lib/session'
import SemanticReviewPanel from './SemanticReviewPanel.vue'

afterEach(() => { currentUser.value = null; vi.unstubAllGlobals() })

it('allows analyst to read reviews but not start one', async () => {
  currentUser.value = { id: 2, email: 'a@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 })))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(SemanticReviewPanel, { props: { productId: 1 } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('暂无语义审核'))
  expect(wrapper.text()).not.toContain('发起语义审核')
  expect(fetchMock.mock.calls.every(([, init]) => !init || init.method !== 'POST')).toBe(true)
})
