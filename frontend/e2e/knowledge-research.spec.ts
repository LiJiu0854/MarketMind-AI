import { expect, test } from '@playwright/test'

const adminEmail = process.env.E2E_ADMIN_EMAIL || 'admin@fixture.example.com'
const adminPassword = process.env.E2E_ADMIN_PASSWORD || 'fixture-only-admin-password'

test('research requires evidence, review and one-time approval', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('邮箱').fill(adminEmail)
  await page.getByLabel('密码').fill(adminPassword)
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page).toHaveURL('http://127.0.0.1:8080/')

  const baseName = `验收知识库-${Date.now()}`
  await page.getByRole('link', { name: '知识库', exact: true }).click()
  await page.getByRole('textbox', { name: '名称' }).fill(baseName)
  await page.getByRole('button', { name: '创建知识库' }).click()
  await page.getByRole('link', { name: new RegExp(baseName) }).click()
  const baseId = Number(new URL(page.url()).pathname.split('/').pop())
  const text = '测试商品使用场景：仅供内部培训和系统验收。资料标识为 FIXTURE-EVIDENCE，未声明真实功效或市场排名。'
  await page.getByLabel('上传文档').setInputFiles({ name: 'fixture-evidence.txt', mimeType: 'text/plain', buffer: Buffer.from(text) })
  await expect(page.getByRole('row').filter({ hasText: 'fixture-evidence.txt' })).toContainText('已就绪', { timeout: 90_000 })
  await page.getByRole('textbox', { name: '问题' }).fill('这份测试资料的用途是什么？')
  await page.getByRole('button', { name: '提交问题' }).click()
  await expect(page.getByRole('heading', { name: '回答' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '回答' }).locator('..')).toContainText('fixture-evidence.txt')

  await page.getByRole('link', { name: '商品运营', exact: true }).click()
  await page.getByRole('link', { name: '新建商品' }).click()
  await page.getByLabel('SKU').fill(`RESEARCH-${Date.now()}`)
  await page.getByLabel('标题').fill('研究验收测试商品')
  await page.getByLabel('价格').fill('29.90')
  await page.getByLabel('描述').fill('本商品只用于测试研究证据和人工审批流程。')
  await page.getByRole('button', { name: '保存商品' }).click()
  await expect(page.getByRole('status').filter({ hasText: '商品已保存' })).toBeVisible()
  await expect(page).toHaveURL(/\/products\/\d+$/)
  const productId = Number(new URL(page.url()).pathname.split('/').pop())
  await page.getByRole('button', { name: '发起语义审核' }).click()
  await expect(page.getByRole('heading', { name: '语义审核' }).locator('xpath=ancestor::section')).toContainText('已完成', { timeout: 90_000 })

  const token = await page.evaluate(() => sessionStorage.getItem('marketmind_access_token'))
  if (!token) throw new Error('missing test session token')
  const headers = { Authorization: `Bearer ${token}` }
  const emptyBaseName = `空知识库-${Date.now()}`
  await page.getByRole('link', { name: '知识库', exact: true }).click()
  await page.getByRole('textbox', { name: '名称' }).fill(emptyBaseName)
  await page.getByRole('button', { name: '创建知识库' }).click()
  await page.getByRole('link', { name: new RegExp(emptyBaseName) }).click()
  const emptyBaseId = Number(new URL(page.url()).pathname.split('/').pop())
  const noEvidence = await page.request.post(`/api/v1/products/${productId}/research-runs`, {
    headers, data: { goal: '无证据测试', knowledge_base_ids: [emptyBaseId] },
  })
  expect(noEvidence.status()).toBe(409)

  await page.goto(`/products/${productId}`)
  await page.getByRole('textbox', { name: '研究目标' }).fill('请根据内部测试资料分析商品使用场景。')
  await page.getByRole('checkbox', { name: baseName }).check()
  await page.getByRole('button', { name: '发起研究' }).click()
  await expect(page).toHaveURL(/\/research-runs\/\d+$/)
  const runId = Number(new URL(page.url()).pathname.split('/').pop())
  await expect(page.getByRole('heading', { name: '研究报告' })).toBeVisible({ timeout: 90_000 })
  await expect(page.getByRole('heading', { name: '已登记证据' }).locator('..')).toContainText('fixture-evidence.txt')
  const beforeApproval = await page.request.get(`/api/v1/products/${productId}/research-runs/${runId}/export`, { headers })
  expect(beforeApproval.status()).toBe(409)
  await page.getByRole('button', { name: '批准报告' }).click()
  await page.getByRole('alertdialog', { name: '批准报告' }).getByRole('button', { name: '确认' }).click()
  await expect(page.getByRole('button', { name: '下载 Excel' })).toBeVisible()
  const secondApproval = await page.request.post(`/api/v1/products/${productId}/research-runs/${runId}/review`, {
    headers, data: { decision: 'rejected', comment: '二次决定必须拒绝' },
  })
  expect(secondApproval.status()).toBe(409)
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 Excel' }).click()
  expect((await downloadPromise).suggestedFilename()).toBe(`research-${runId}.xlsx`)
  expect(baseId).toBeGreaterThan(0)
})
