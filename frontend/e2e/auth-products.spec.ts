import { readFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'

const adminEmail = process.env.E2E_ADMIN_EMAIL || 'admin@fixture.example.com'
const adminPassword = process.env.E2E_ADMIN_PASSWORD || 'fixture-only-admin-password'

async function login(page: Page, email = adminEmail, password = adminPassword) {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(email)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page).toHaveURL('http://127.0.0.1:8080/')
}

test('admin creates, filters, checks and round-trips product workbook', async ({ page }) => {
  await login(page)
  await page.getByRole('link', { name: '商品运营', exact: true }).click()
  await page.getByRole('link', { name: '新建商品' }).click()
  const sku = `E2E-${Date.now()}`
  await page.getByLabel('SKU').fill(sku)
  await page.getByLabel('标题').fill('系统验收测试商品')
  await page.getByLabel('品牌').fill('测试品牌')
  await page.getByLabel('品类').fill('测试品类')
  await page.getByLabel('价格').fill('19.90')
  await page.getByLabel('描述').fill('仅供端到端验收的合成商品，不代表真实销售承诺。')
  await page.getByLabel('卖点 1').fill('仅供测试的商品卖点')
  await page.getByRole('button', { name: '保存商品' }).click()
  await expect(page.getByRole('status').filter({ hasText: '商品已保存' })).toBeVisible()
  await expect(page).toHaveURL(/\/products\/\d+$/)
  const productUrl = page.url()
  await page.getByRole('button', { name: '运行检查' }).click()
  await expect(page.getByRole('heading', { name: 'Listing 检查' })).toBeVisible()
  await page.getByRole('link', { name: '返回列表' }).click()
  await page.getByPlaceholder('按 SKU 搜索').fill(sku)
  await page.getByRole('button', { name: '应用筛选' }).click()
  await expect(page.getByRole('row').filter({ hasText: sku })).toBeVisible()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出 Excel' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('products.xlsx')
  const workbook = await download.path()
  if (!workbook) throw new Error('missing product workbook')
  await page.goto(productUrl)
  await page.getByRole('button', { name: '编辑商品' }).click()
  await page.getByLabel('SKU').fill(`${sku}-RENAMED`)
  await page.getByRole('button', { name: '保存商品' }).click()
  await expect(page.getByRole('status').filter({ hasText: '商品已保存' })).toBeVisible()
  await page.getByRole('link', { name: '返回列表' }).click()
  await page.getByPlaceholder('按 SKU 搜索').fill(sku)
  await page.getByRole('button', { name: '应用筛选' }).click()
  await page.getByLabel('选择文件').setInputFiles({
    name: 'products.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: await readFile(workbook),
  })
  await expect(page.getByText('导入校验完成')).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '总计' })).toContainText('成功 1 行')
  await expect(page.getByRole('row').filter({ hasText: sku })).toBeVisible()
})

test('analyst cannot reach user management', async ({ page }) => {
  await login(page)
  await page.getByRole('link', { name: '用户管理', exact: true }).click()
  const suffix = Date.now()
  const email = `analyst-${suffix}@fixture.example.com`
  const password = `fixture-only-analyst-${suffix}`
  await page.getByRole('textbox', { name: '邮箱' }).fill(email)
  await page.getByRole('textbox', { name: '姓名' }).fill('测试分析员')
  await page.getByLabel('初始密码').fill(password)
  await page.getByRole('button', { name: '创建用户' }).click()
  await expect(page.getByRole('status').filter({ hasText: '用户已创建' })).toBeVisible()
  await page.getByRole('button', { name: '退出' }).click()
  await login(page, email, password)
  await expect(page.getByRole('link', { name: '用户管理' })).toHaveCount(0)
  await page.goto('/users')
  await expect(page).toHaveURL('http://127.0.0.1:8080/')
})
