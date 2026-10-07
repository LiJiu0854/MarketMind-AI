import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../../lib/session'
import ProductPage from './ProductPage.vue'

afterEach(() => { currentUser.value = null; vi.unstubAllGlobals() })

it('shows listing issues and no write actions to analyst', async () => {
  currentUser.value = { id: 2, email: 'a@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify(
    url.includes('semantic-reviews') || url.includes('research-runs') ? { items: [], total: 0, page: 1, page_size: 20 } : url.includes('listing-check')
      ? { product_id: 1, passed: false, issues: [{ code: 'TITLE_SHORT', field: 'title', message: '标题过短', suggestion: '增加核心信息' }] }
      : { id: 1, sku: 'A', title: '商品A', description: '', bullet_points: [], brand: '', category: '', price: '19.90', currency: 'CNY', is_active: true, created_by_id: 1, created_at: '', updated_at: '' },
  ))))
  const wrapper = mount(ProductPage, { props: { id: '1' }, global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('商品A'))
  await wrapper.get('button[data-test="listing-check"]').trigger('click')
  await vi.waitFor(() => expect(wrapper.text()).toContain('标题过短'))
  expect(wrapper.text()).not.toContain('停用商品')
})
