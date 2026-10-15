import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('marketmind_access_token', 'table-test-token'))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: {
    id: 1, email: 'admin@fixture.example.com', full_name: 'Fixture Admin', role: 'admin',
    is_active: true, created_at: '2026-10-16T00:00:00Z', updated_at: '2026-10-16T00:00:00Z',
  } }))
})

test('phone product table announces scrolling and supports arrow keys', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 812 })
  await page.route('**/api/v1/products?*', (route) => route.fulfill({ json: { total: 1, items: [{
    id: 1, sku: 'SKU-001', title: '测试商品', description: '', bullet_points: [],
    brand: '测试品牌', category: '测试品类', price: '129.00', currency: 'CNY', is_active: true,
    created_by_id: 1, created_at: '2026-10-16T00:00:00Z', updated_at: '2026-10-16T00:00:00Z',
  }] } }))
  await page.goto('/products')
  const table = page.getByRole('region', { name: '商品列表表格，可按左右方向键查看隐藏列' })
  await expect(table.getByText('测试商品')).toBeVisible()
  await expect(table.getByText('如有隐藏列，向右滑动；键盘聚焦后按左右方向键。')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  await page.getByRole('button', { name: '应用筛选' }).focus()
  await page.keyboard.press('Tab')
  await expect(table).toBeFocused()
  const before = await table.evaluate((element) => element.scrollLeft)
  await page.keyboard.press('ArrowRight')
  await expect.poll(() => table.evaluate((element) => element.scrollLeft)).toBeGreaterThan(before)
  await expect(page.getByRole('link', { name: '查看详情' })).toBeAttached()
  await page.setViewportSize({ width: 375, height: 812 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375)
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(table.getByText('如有隐藏列，向右滑动；键盘聚焦后按左右方向键。')).toBeHidden()
})

test('tablet member table keeps its own keyboard scroll target', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 })
  await page.route('**/api/v1/users?*', (route) => route.fulfill({ json: { total: 1, items: [{
    id: 2, email: 'operator@fixture.example.com', full_name: '测试成员', role: 'operator', is_active: true,
    created_at: '2026-10-16T00:00:00Z', updated_at: '2026-10-16T00:00:00Z',
  }] } }))
  await page.goto('/users')
  const table = page.getByRole('region', { name: '团队成员表格，可按左右方向键查看隐藏列' })
  await expect(table.getByText('测试成员')).toBeVisible()
  await expect(table.getByText('如有隐藏列，向右滑动；键盘聚焦后按左右方向键。')).toBeVisible()
  await table.focus()
  const before = await table.evaluate((element) => element.scrollLeft)
  await page.keyboard.press('ArrowRight')
  await expect.poll(() => table.evaluate((element) => element.scrollLeft)).toBeGreaterThan(before)
})
