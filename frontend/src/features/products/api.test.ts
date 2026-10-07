import { afterEach, expect, it, vi } from 'vitest'
import { exportProducts, listProducts, saveProduct } from './api'

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear() })

it('uses identical filters for list and export, excluding pagination from export', async () => {
  const fetchMock = vi.fn().mockImplementation(async () => new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  const NativeURL = URL
  vi.stubGlobal('URL', class extends NativeURL {
    static createObjectURL = vi.fn().mockReturnValue('blob:x')
    static revokeObjectURL = vi.fn()
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const filters = { sku: 'A-1', brand: 'Acme', category: 'Tools', is_active: true }
  await listProducts(filters, 3)
  await exportProducts(filters)
  const listUrl = new URL(fetchMock.mock.calls[0][0], 'http://localhost')
  const exportUrl = new URL(fetchMock.mock.calls[1][0], 'http://localhost')
  for (const key of ['sku', 'brand', 'category', 'is_active']) {
    expect(listUrl.searchParams.get(key)).toBe(exportUrl.searchParams.get(key))
  }
  expect(listUrl.searchParams.get('page')).toBe('3')
  expect(exportUrl.searchParams.has('page')).toBe(false)
  vi.restoreAllMocks()
})

it('preserves decimal price as text when saving', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  await saveProduct({ sku: 'A-1', title: '商品', description: '', bullet_points: [], brand: '', category: '', price: '19.90', currency: 'CNY', is_active: true })
  expect(JSON.parse(String(fetchMock.mock.calls[0][1].body)).price).toBe('19.90')
})
