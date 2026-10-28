import { expect, test } from '@playwright/test'

test('a delayed request from the old login cannot sign out the new user', async ({ page }) => {
  const user = (name: string, role: 'admin' | 'operator') => ({
    id: role === 'admin' ? 1 : 2, email: `${name}@fixture.example.com`, full_name: name,
    role, is_active: true, created_at: '', updated_at: '',
  })
  let releaseOld!: () => void
  await page.addInitScript(() => sessionStorage.setItem('marketmind_access_token', 'old-token'))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json:
    route.request().headers().authorization === 'Bearer old-token'
      ? user('旧管理员', 'admin') : user('新运营', 'operator'),
  }))
  await page.route('**/api/v1/auth/token', (route) => route.fulfill({ json: { access_token: 'new-token' } }))
  await page.route('**/api/v1/users?page=1', async (route) => {
    await new Promise<void>((resolve) => { releaseOld = resolve })
    await route.fulfill({ status: 401, json: { code: 'AUTH_INVALID_TOKEN', message: '旧凭证无效' } })
  })

  await page.goto('/users')
  await expect.poll(() => releaseOld !== undefined).toBe(true)
  await page.getByRole('button', { name: '退出' }).click()
  await page.getByLabel('邮箱').fill('new@fixture.example.com')
  await page.getByLabel('密码').fill('fixture-only-password')
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page.locator('.account-name')).toContainText('新运营')
  const staleResponse = page.waitForResponse((response) =>
    response.url().includes('/api/v1/users?page=1') && response.status() === 401)
  releaseOld()
  await staleResponse
  await page.waitForTimeout(100)
  await expect(page.locator('.account-name')).toContainText('新运营')
  expect(await page.evaluate(() => sessionStorage.getItem('marketmind_access_token'))).toBe('new-token')
})
