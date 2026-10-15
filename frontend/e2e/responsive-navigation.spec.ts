import { expect, test } from '@playwright/test'

test('mobile navigation keeps every destination fully visible', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('marketmind_access_token', 'layout-test-token'))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({
    json: {
      id: 1,
      email: 'admin@fixture.example.com',
      full_name: 'Fixture Admin',
      role: 'admin',
      is_active: true,
      created_at: '2026-10-15T00:00:00Z',
      updated_at: '2026-10-15T00:00:00Z',
    },
  }))
  await page.goto('/')
  const nav = page.getByRole('navigation')
  const names = ['工作台', '商品运营', '知识库', '用户管理']
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 812 })
    const bounds = await nav.boundingBox()
    expect(bounds).not.toBeNull()
    for (const name of names) {
      const link = nav.getByRole('link', { name, exact: true })
      const linkBounds = await link.boundingBox()
      expect(linkBounds).not.toBeNull()
      expect(linkBounds!.x, `${name} left at ${width}px`).toBeGreaterThanOrEqual(bounds!.x)
      expect(linkBounds!.x + linkBounds!.width, `${name} right at ${width}px`).toBeLessThanOrEqual(bounds!.x + bounds!.width)
    }
  }
})
