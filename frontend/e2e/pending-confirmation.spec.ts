import { expect, test } from '@playwright/test'

test('pending product deactivation cannot appear cancelled', async ({ page }) => {
  const product = {
    id: 1, sku: 'FIXTURE-1', title: '合成商品', description: '', bullet_points: [],
    brand: '测试品牌', category: '测试品类', price: '19.90', currency: 'CNY', is_active: true,
    created_by_id: 1, created_at: '2026-10-26T00:00:00Z', updated_at: '2026-10-26T00:00:00Z',
  }
  let releaseDelete: (() => void) | undefined
  await page.addInitScript(() => sessionStorage.setItem('marketmind_access_token', 'dialog-test-token'))
  await page.route('**/api/v1/**', (route) => route.fulfill({ json: { items: [], total: 0 } }))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: {
    id: 1, email: 'admin@fixture.example.com', full_name: 'Fixture Admin', role: 'admin',
    is_active: true, created_at: '2026-10-26T00:00:00Z', updated_at: '2026-10-26T00:00:00Z',
  } }))
  await page.route('**/api/v1/products/1', async (route) => {
    if (route.request().method() === 'DELETE') {
      await new Promise<void>((resolve) => { releaseDelete = resolve })
      await route.fulfill({ json: { ...product, is_active: false } })
    } else await route.fulfill({ json: product })
  })

  await page.goto('/products/1')
  await page.getByRole('button', { name: '停用商品' }).click()
  const dialog = page.getByRole('alertdialog', { name: '停用商品' })
  await dialog.getByRole('button', { name: '确认' }).click()
  await expect.poll(() => releaseDelete !== undefined).toBe(true)
  const cancel = dialog.getByRole('button', { name: '取消' })
  await expect(cancel).toHaveAttribute('aria-disabled', 'true')
  await expect(cancel).toBeFocused()
  await page.keyboard.press('Escape')
  await cancel.click({ force: true })
  await page.locator('.dialog-backdrop').click({ position: { x: 5, y: 5 } })
  await page.keyboard.press('Tab')
  await expect(cancel).toBeFocused()
  await expect(dialog).toBeVisible()
  releaseDelete?.()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('status')).toContainText('商品已停用')
})
