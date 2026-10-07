import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../../lib/session'
import KnowledgeBasePage from './KnowledgeBasePage.vue'

afterEach(() => { currentUser.value = null; vi.unstubAllGlobals() })

it('renders a refused answer without inventing citations', async () => {
  currentUser.value = { id: 2, email: 'a@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, init?: RequestInit) => new Response(JSON.stringify(
    url.endsWith('/knowledge-bases/1') ? { id: 1, name: '产品资料', description: null, embedding_provider: 'openai', embedding_model: 'x', embedding_dimensions: null, created_at: '' }
      : url.endsWith('/questions') && init?.method === 'POST' ? { id: 3, status: 'refused', answer: '资料不足', citations: [], question: '问题', total_tokens: 10 }
        : { items: [], total: 0, page: 1, page_size: 20 },
  ))))
  const wrapper = mount(KnowledgeBasePage, { props: { id: '1' }, global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('产品资料'))
  await wrapper.get('textarea[name="question"]').setValue('问题')
  await wrapper.get('form').trigger('submit')
  await vi.waitFor(() => expect(wrapper.text()).toContain('资料不足'))
  expect(wrapper.text()).toContain('拒答')
  expect(wrapper.text()).not.toContain('上传文档')
})
