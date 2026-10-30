import { expect, test } from '@playwright/test'

test('a broken XLSX package gives a useful error and resets the upload input', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(process.env.E2E_ADMIN_EMAIL || 'admin@fixture.example.com')
  await page.getByLabel('密码').fill(process.env.E2E_ADMIN_PASSWORD || 'fixture-only-admin-password')
  await page.getByRole('button', { name: '进入工作台' }).click()
  await page.getByRole('link', { name: '商品运营', exact: true }).click()
  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/products/import') && response.request().method() === 'POST')
  await page.getByLabel('选择文件').setInputFiles({
    name: 'damaged.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    // A valid empty ZIP container without the required XLSX package parts.
    buffer: Buffer.from([0x50, 0x4b, 0x05, 0x06, ...Array(18).fill(0)]),
  })
  const response = await responsePromise
  expect(response.status()).toBe(422)
  expect((await response.json()).code).toBe('EXCEL_INVALID_WORKBOOK')
  await expect(page.getByRole('alert')).toContainText('无法解析 Excel 文件，请确认格式正确且未损坏')
  await expect(page.getByLabel('选择文件')).toBeEnabled()
  await expect(page.getByLabel('选择文件')).toHaveValue('')
  await expect(page.getByText('导入校验完成')).toHaveCount(0)
})
