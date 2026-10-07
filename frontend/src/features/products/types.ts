export interface Product {
  id: number; sku: string; title: string; description: string; bullet_points: string[]
  brand: string; category: string; price: string; currency: string; is_active: boolean
  created_by_id: number; created_at: string; updated_at: string
}
export type ProductInput = Pick<Product, 'sku' | 'title' | 'description' | 'bullet_points' | 'brand' | 'category' | 'price' | 'currency' | 'is_active'>
export interface ProductFilters { sku?: string; brand?: string; category?: string; is_active?: boolean }
export interface ProductImportResult { total_rows: number; imported_rows: number; failed_rows: number; errors: { row: number; field: string; code: string; message: string }[] }
export interface ListingCheckResult { product_id: number; passed: boolean; issues: { code: string; field: string; message: string; suggestion: string }[] }
