import { apiFile, apiJson } from '../../lib/api'
import type { Page } from '../../lib/types'
import type { ListingCheckResult, Product, ProductFilters, ProductImportResult, ProductInput } from './types'

function filterQuery(filters: ProductFilters): URLSearchParams {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  return query
}
export function listProducts(filters: ProductFilters, page: number): Promise<Page<Product>> {
  const query = filterQuery(filters)
  query.set('page', String(page))
  return apiJson(`/products?${query}`)
}
export const getProduct = (id: number) => apiJson<Product>(`/products/${id}`)
export const saveProduct = (input: ProductInput, id?: number) => apiJson<Product>(id ? `/products/${id}` : '/products', {
  method: id ? 'PATCH' : 'POST', body: JSON.stringify(input),
})
export const deactivateProduct = (id: number) => apiJson<Product>(`/products/${id}`, { method: 'DELETE' })
export const checkListing = (id: number) => apiJson<ListingCheckResult>(`/products/${id}/listing-check`)
export function importProducts(file: File): Promise<ProductImportResult> {
  const body = new FormData()
  body.set('file', file)
  return apiJson('/products/import', { method: 'POST', body })
}
export const exportProducts = (filters: ProductFilters) => apiFile(`/products/export?${filterQuery(filters)}`, 'products.xlsx')
