import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../../lib/session'
import ProductsPage from './ProductsPage.vue'

afterEach(() => { vi.unstubAllGlobals(); currentUser.value = null })

const product = (title: string) => ({ id: 1, sku: 'A', title, description: '', bullet_points: [], brand: '', category: '', price: '19.90', currency: 'CNY', is_active: true, created_by_id: 1, created_at: '', updated_at: '' })

it('ignores stale product response after filters change', async () => {
  currentUser.value = { id: 2, email: 'a@example.com', full_name: '分析员', role: 'analyst', is_active: true, created_at: '', updated_at: '' }
  let resolveOld!: (response: Response) => void
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (url.includes('sku=NEW')) return Promise.resolve(new Response(JSON.stringify({ items: [product('新商品')], total: 1, page: 1, page_size: 20 })))
    return new Promise<Response>((resolve) => { resolveOld = resolve })
  })
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ProductsPage, { global: { stubs: ['RouterLink'] } })
  await wrapper.get('input[name="sku"]').setValue('NEW')
  await wrapper.get('form').trigger('submit')
  await vi.waitFor(() => expect(wrapper.text()).toContain('新商品'))
  resolveOld(new Response(JSON.stringify({ items: [product('旧商品')], total: 1, page: 1, page_size: 20 })))
  await new Promise((resolve) => setTimeout(resolve, 0))
  expect(wrapper.text()).not.toContain('旧商品')
  expect(wrapper.text()).toContain('新商品')
  expect(wrapper.text()).not.toContain('新建商品')
})
