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

it('reports row-level xlsx import errors and rejects other extensions', async () => {
  currentUser.value = { id: 2, email: 'o@example.com', full_name: '运营', role: 'operator', is_active: true, created_at: '', updated_at: '' }
  const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => new Response(JSON.stringify(
    init?.method === 'POST'
      ? { total_rows: 2, imported_rows: 1, failed_rows: 1, errors: [{ row: 3, field: 'price', code: 'INVALID_PRICE', message: '价格无效' }] }
      : { items: [], total: 0, page: 1, page_size: 20 },
  )))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ProductsPage, { global: { stubs: ['RouterLink'] } })
  await vi.waitFor(() => expect(wrapper.text()).toContain('暂无商品'))
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['bad'], 'data.csv')] })
  await input.trigger('change')
  expect(wrapper.text()).toContain('请上传 .xlsx')
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['file'], 'data.xlsx')] })
  await input.trigger('change')
  await vi.waitFor(() => expect(wrapper.text()).toContain('价格无效'))
  expect(wrapper.text()).toContain('成功 1 行')
  const upload = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(upload?.[1].body).toBeInstanceOf(FormData)
})
