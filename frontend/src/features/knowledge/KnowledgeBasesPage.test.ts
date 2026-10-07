import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../../lib/session'
import KnowledgeBasesPage from './KnowledgeBasesPage.vue'

afterEach(() => { currentUser.value = null; vi.unstubAllGlobals() })

it('allows analyst to read bases but not create one', async () => {
  currentUser.value = { id: 2, email: 'a@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }))))
  const wrapper = mount(KnowledgeBasesPage, { global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('暂无知识库'))
  expect(wrapper.find('form').exists()).toBe(false)
})
