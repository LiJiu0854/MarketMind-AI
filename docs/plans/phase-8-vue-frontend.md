# 单元 8：Vue 企业运营工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for the user's previously selected native execution method. Steps use checkbox (`- [ ]`) syntax for tracking. Do not implement before the user reviews and approves this plan.

**Goal:** 在现有 FastAPI 后端之上交付真实可用、视觉整洁大方的中文企业运营工作台，覆盖三角色的商品、知识库、语义审核、研究审核与 Excel 交付。

**Architecture:** 独立 `frontend/` Vue SPA，通过相对 `/api/v1` 和 Vite 本地代理使用现有 API；一个请求层处理 Bearer、错误和文件下载，页面按业务域组织，后端 MySQL 状态始终为真相。认证仅共享 Token 与当前用户，业务数据留在页面，不新建全局业务 Store。

**Tech Stack:** Vue 3、Vite、TypeScript、Vue Router、原生 CSS/fetch/FormData/Blob、Vitest、Vue Test Utils、jsdom；保留现有 Python 3.12/FastAPI/MySQL/Redis/Celery/Chroma 后端。

**Spec:** `docs/plans/phase-8-vue-frontend-design.md`。实施前阅读设计与现有 `backend/app/api/v1/`、`backend/app/schemas/`；路径和字段以已提交后端为准。

## Global Constraints

- 固定四个 Task，每个 Task 一份仅保留本地的中文教程；按真实编写顺序解释新增代码的行/段职责、调用来源、原理、RED/GREEN、故障和迁移练习。教程不加入 Git。
- 所有界面数据必须来自现有 `/api/v1`；不新增后端业务接口、表、租户、外部集成、虚构指标或付费模型自动化调用。
- `POST /auth/token` 用表单，Token 仅存当前标签页 `sessionStorage`，刷新后 `/auth/me` 复核；现有 Access Token 默认 30 分钟；`401` 清理并返回登录，`403` 不清理。
- Admin/Operator/Analyst 的写权限严格遵从设计文档；按钮隐藏不是授权。Admin 用户创建必须带 `Idempotency-Key`，同一输入的超时重试复用该键。
- 商品与研究 Excel 经认证请求下载并撤销 Blob URL；不把 Token 放在 URL；模型、商品和文档文本不用 `v-html`。
- 异步文档/语义审核/研究只读 MySQL 业务状态；只在相关页面可见且未终结时轮询，终态/离开/卸载停止；知识库问答保持同步。
- 页面使用浅暖色、深色正文、青绿色强调色的统一设计变量；约 1440/1024/390 像素人工检查；可见标签、键盘焦点、文字状态和减少动态效果不可省。
- Vite 只在本地代理 `/api/v1` 至 FastAPI `8010`；正式同源代理、CI、部署和系统级 E2E 属单元 9。模型供应商切换仍在后端 `LLM_*`、`EMBEDDING_*`，前端不得持有密钥。
- 只精确暂存本 Task 工程文件；不要 `git add .` 或 `git add -A`，不碰用户已有 `docs/learning/` 与 `tests/unit/models/test_product_practice.py`，不读 `.env`，不推送或合并。

## Review Focus

1. 刷新后残留的过期 Token：Task 1 的 `restores_only_valid_session` 测试必须断言 `/auth/me` 返回 `401` 时清空存储并到登录页；`403` 不被误当过期。
2. 用户创建网络超时后重复点击：Task 1 的 `reuses_key_for_same_create_attempt` 必须断言同一输入仍用相同 `Idempotency-Key`，输入改变才换键。
3. 快速修改商品筛选条件：Task 2 的 `ignores_stale_product_response` 必须断言旧请求后返回也不覆盖新列表，导出仍使用当前筛选。
4. 页面隐藏或离开时后台任务仍在运行：Task 3 的 `stops_polling_when_hidden_or_unmounted` 必须用假时钟断言不继续请求，恢复可见后只在非终态续查。
5. 不可审核/未批准研究的操作入口：Task 4 的 `rejects_unreviewable_and_unapproved_actions` 必须断言按钮不可用，直接 API `409` 也显示冲突而不触发文件下载。

---

## 文件职责与接口地图

| Task | 文件（均为仓库相对路径） | 单一职责 |
|---|---|---|
| 1 | `.gitignore`、`frontend/package.json`、`frontend/package-lock.json`、`frontend/index.html`、`frontend/tsconfig.json`、`frontend/vite.config.ts`、`frontend/src/main.ts`、`frontend/src/App.vue` | 可重复安装、启动、测试、类型检查、构建的最小 SPA；忽略安装/构建产物 |
| 1 | `frontend/src/router.ts`、`frontend/src/lib/api.ts`、`frontend/src/lib/session.ts`、`frontend/src/lib/types.ts` | 路由保护、统一请求/错误/下载、当前标签页凭证与用户、分页/错误公共类型 |
| 1 | `frontend/src/styles.css`、`frontend/src/components/AppShell.vue`、`frontend/src/components/StatusBadge.vue`、`frontend/src/components/ConfirmDialog.vue`、`frontend/src/pages/LoginPage.vue`、`frontend/src/pages/HomePage.vue` | 视觉变量、布局、状态、原生对话框、登录与真实入口 |
| 1 | `frontend/src/features/users/api.ts`、`frontend/src/features/users/types.ts`、`frontend/src/features/users/UsersPage.vue` | Admin 用户分页、创建、修改、停用及幂等提交 |
| 2 | `frontend/src/features/products/api.ts`、`frontend/src/features/products/types.ts`、`frontend/src/features/products/ProductsPage.vue`、`frontend/src/features/products/ProductPage.vue`、`frontend/src/features/products/ProductForm.vue`；修改 `frontend/src/router.ts`、`frontend/src/components/AppShell.vue` | 商品 API/类型、列表筛选、详情与编辑、确定性检查、导航接线 |
| 3 | `frontend/src/lib/useTaskPolling.ts`、`frontend/src/features/knowledge/api.ts`、`frontend/src/features/knowledge/types.ts`、`frontend/src/features/knowledge/KnowledgeBasesPage.vue`、`frontend/src/features/knowledge/KnowledgeBasePage.vue`、`frontend/src/features/semantic/api.ts`、`frontend/src/features/semantic/types.ts`、`frontend/src/features/semantic/SemanticReviewPanel.vue`；修改 `frontend/src/router.ts`、`frontend/src/components/AppShell.vue`、`frontend/src/features/products/ProductPage.vue` | 有界轮询、知识库/文档/问答、商品语义审核及导航接线 |
| 4 | `frontend/src/features/research/api.ts`、`frontend/src/features/research/types.ts`、`frontend/src/features/research/ResearchPanel.vue`、`frontend/src/features/research/ResearchPage.vue`；修改 `frontend/src/router.ts`、`frontend/src/features/products/ProductPage.vue`、`README.md` | 研究发起/历史、证据/报告、审核/下载、运行与局限说明 |

测试与所测代码同目录，例如 `frontend/src/lib/api.test.ts`、`frontend/src/features/products/ProductsPage.test.ts`。每个 Task 的具体测试路径见下文。避免通用 CRUD 生成器、全局业务 Store、UI 组件库和与当前功能无关的抽象。`frontend/src/lib/types.ts` 只放 `Page<T>`、`ApiErrorShape` 等真正跨域的类型，业务字段以相应 `backend/app/schemas/*.py` 为准并放入所属功能目录。

## Task 1：前端基础、身份与用户管理

**交付：** 可本地启动的工作台；三角色登录/刷新/退出与路由保护；Admin 完成用户管理，其他角色无该入口。

**接口：** `apiJson<T>(path: string, init?: RequestInit, authRequired?: boolean): Promise<T>`、`apiFile(path: string, filename: string): Promise<void>`、`new ApiError(status: number, code: string, message: string, requestId: string | null)`；`readToken(): string | null`、`saveToken(token: string): void`、`setCurrentUser(user: User | null): void`、`clearSession(): void`；`currentUser: Ref<User | null>`。用户域产出 `listUsers(page: number): Promise<Page<User>>`、`createUser(input: UserCreate, idempotencyKey: string): Promise<User>`、`updateUser(id: number, input: UserUpdate): Promise<User>`、`deactivateUser(id: number): Promise<User>`。存储键固定为 `marketmind_access_token`。`User` 的角色值是 `admin/operator/analyst`。Task 2–4 只通过这些接口访问认证与后端。

关键测试断言（请求由 `vi.fn()` 模拟）：

```ts
expect(sessionStorage.getItem('marketmind_access_token')).toBeNull() // 已认证请求返回 401
expect(wrapper.text()).not.toContain('用户管理') // Analyst 导航
expect(createHeaders.get('Idempotency-Key')).toBe(retryHeaders.get('Idempotency-Key'))
```

- [ ] **步骤 1：建立最小测试运行骨架。** 创建本 Task 的配置/入口和 `.gitignore` 规则，安装 Vue、Router、Vite、TypeScript、vue-tsc、Vitest、Vue Test Utils、jsdom，提交 `package-lock.json`；脚本固定为 `dev: vite`、`test: vitest run`、`typecheck: vue-tsc --noEmit`、`build: vue-tsc --noEmit && vite build`。在 `frontend/` 目录运行后续 npm 命令；不要运行交互式脚手架生成大量无关样例。
- [ ] **步骤 2：写请求层测试。** 在 `frontend/src/lib/api.test.ts` 写 `adds_bearer_and_decodes_safe_error`（Bearer 和 `status/code/message/requestId`）、`clears_only_on_authenticated_401`（`401` 清、`403` 留、匿名登录失败不跳转）、`maps_conflict_validation_rate_limit_and_outage`（`409/422/429/503` 与非 JSON 安全提示）、`handles_formdata_without_json_content_type`。
- [ ] **步骤 3：确认请求层 RED。** 运行 `npm run test -- src/lib/api.test.ts`；预期因目标接口不存在或断言不符而失败，安装/配置错误不算 RED。
- [ ] **步骤 4：实现请求层。** 在 `lib/api.ts` 实现相对 URL、Bearer、错误解析、FormData、Blob 下载和 `revokeObjectURL`；认证请求 `401` 调用 `clearSession()`，匿名登录失败只抛 `ApiError`。
- [ ] **步骤 5：确认请求层 GREEN。** 重跑 `npm run test -- src/lib/api.test.ts`；上述四项全部通过。
- [ ] **步骤 6：写登录与路由测试。** `frontend/src/router.test.ts::restores_only_valid_session` 断言刷新请求 `/auth/me`、过期进入登录、`403` 不作登出；`frontend/src/pages/LoginPage.test.ts` 断言用 `URLSearchParams` 发 `username/password` 且提交中禁用重复提交。
- [ ] **步骤 7：确认登录与路由 RED。** 运行 `npm run test -- src/router.test.ts src/pages/LoginPage.test.ts`；预期目标行为失败。
- [ ] **步骤 8：实现登录与路由。** 在 `session.ts`、`router.ts`、`LoginPage.vue`、`App.vue` 中实现恢复、登录、退出与路由保护；`App.vue` 观察用户变空后返回登录。
- [ ] **步骤 9：确认登录与路由 GREEN。** 重跑 `npm run test -- src/router.test.ts src/pages/LoginPage.test.ts`；全部通过。
- [ ] **步骤 10：写外壳与用户测试。** `AppShell.test.ts` 断言 Analyst/Operator 无用户管理导航；`UsersPage.test.ts::reuses_key_for_same_create_attempt` 断言同输入重试复用 `Idempotency-Key`、输入变化换键、非 Admin 无写请求；加自改角色时 `409` 的提示断言。
- [ ] **步骤 11：确认外壳与用户 RED。** 运行 `npm run test -- src/components/AppShell.test.ts src/features/users/UsersPage.test.ts`；预期目标行为失败。
- [ ] **步骤 12：实现外壳与用户页。** 建立 CSS 设计变量、布局、真实工作台入口、用户列表/创建/编辑/停用与确认；保留空、加载、失败、成功态，初始 Admin 仍由 CLI 创建。
- [ ] **步骤 13：确认外壳与用户 GREEN。** 重跑 `npm run test -- src/components/AppShell.test.ts src/features/users/UsersPage.test.ts`；全部通过。
- [ ] **步骤 14：运行 Task 1 质量检查。** 在 `frontend/` 执行 `npm run test`、`npm run typecheck`、`npm run build`；均须通过。
- [ ] **步骤 15：人工核对 Task 1。** 浏览器检查登录、刷新、退出、三角色导航与约 1440/1024/390 像素外壳；记录不能验证的服务依赖。
- [ ] **步骤 16：写本地教程。** 保存 `docs/learning/phase-8-task-1-foundation-auth.md`，解释真实新增代码、调用关系与 RED/GREEN，不暂存。
- [ ] **步骤 17：精确提交。** 仅暂存本 Task 工程文件，`git diff --cached --name-only` 不得出现 `docs/learning/` 或练习测试；提交 `feat: add Vue workspace authentication and users`。

## Task 2：商品运营闭环

**交付：** 三角色可按授权查看商品；Admin/Operator 可编辑、停用、导入；所有角色可检查 Listing 和按当前筛选导出。

**接口：** `listProducts(filters: ProductFilters, page: number): Promise<Page<Product>>`、`getProduct(id: number): Promise<Product>`、`saveProduct(input: ProductInput, id?: number): Promise<Product>`、`deactivateProduct(id: number): Promise<Product>`、`checkListing(id: number): Promise<ListingCheckResult>`、`importProducts(file: File): Promise<ProductImportResult>`、`exportProducts(filters: ProductFilters): Promise<void>`。`ProductInput.price` 为十进制字符串，不做 `Number` 金额运算。

关键测试断言（捕获 `fetch` 请求的 URL/请求体）：

```ts
expect(listUrl.searchParams.get('sku')).toBe(exportUrl.searchParams.get('sku'))
expect(exportUrl.searchParams.has('page')).toBe(false)
expect(JSON.parse(String(createInit.body)).price).toBe('19.90')
```

- [ ] **步骤 1：写商品 API 测试。** `api.test.ts` 的 `uses_identical_filters_for_list_and_export` 断言 `sku/brand/category/is_active` 一致且导出无分页；`preserves_decimal_price_text` 断言 `"19.90"` 原样提交；`downloads_only_with_bearer` 断言认证头和 Blob URL 回收。
- [ ] **步骤 2：确认 API RED。** 运行 `npm run test -- src/features/products/api.test.ts`；预期目标行为失败。
- [ ] **步骤 3：实现商品 API 与类型。** `products/api.ts` 用现有路由，`types.ts` 对齐 `backend/app/schemas/product.py`；筛选查询使用 `URLSearchParams`，金额不做浮点运算。
- [ ] **步骤 4：确认 API GREEN。** 重跑 `npm run test -- src/features/products/api.test.ts`；全部通过。
- [ ] **步骤 5：写列表竞态测试。** `ProductsPage.test.ts::ignores_stale_product_response` 让旧筛选响应晚于新响应，断言最终只显示新数据且导出使用新筛选；另断言空列表、分页、Analyst 无写按钮。
- [ ] **步骤 6：确认列表 RED。** 运行 `npm run test -- src/features/products/ProductsPage.test.ts`；预期目标行为失败。
- [ ] **步骤 7：实现商品列表。** 增加分页、后端筛选、加载/错误/空态和旧请求取消或结果序号；不要在浏览器重新实现后端分页。
- [ ] **步骤 8：确认列表 GREEN。** 重跑 `npm run test -- src/features/products/ProductsPage.test.ts`；全部通过。
- [ ] **步骤 9：写详情、表单和 Listing 测试。** `ProductPage.test.ts` 断言角色权限、停用确认、Listing 问题列表；`ProductForm.test.ts` 断言必填、逐条卖点、金额文本与重复提交禁用。
- [ ] **步骤 10：确认详情 RED。** 运行 `npm run test -- src/features/products/ProductPage.test.ts src/features/products/ProductForm.test.ts`；预期目标行为失败。
- [ ] **步骤 11：实现详情和表单。** 接现有商品与 Listing 接口，字段/长度依 `product.py`；危险操作使用确认对话框。
- [ ] **步骤 12：确认详情 GREEN。** 重跑 `npm run test -- src/features/products/ProductPage.test.ts src/features/products/ProductForm.test.ts`；全部通过。
- [ ] **步骤 13：写导入/导出测试。** 在 `ProductsPage.test.ts` 断言 `.xlsx` 与逐行 `errors[row,field,code,message]`、总/成功/失败数、非 XLSX 提示、下载 `401/409` 不生成文件。
- [ ] **步骤 14：确认导入 RED。** 运行 `npm run test -- src/features/products/ProductsPage.test.ts`；新增用例因目标行为缺失而失败。
- [ ] **步骤 15：实现导入/导出 UI。** FormData 发上传，展示逐行错误；导出复用当前筛选，后端限制和校验始终权威。
- [ ] **步骤 16：确认导入 GREEN。** 重跑 `npm run test -- src/features/products/ProductsPage.test.ts`；全部通过。
- [ ] **步骤 17：运行 Task 2 质量检查。** `npm run test`、`npm run typecheck`、`npm run build` 均通过。
- [ ] **步骤 18：人工核对 Task 2。** 三角色商品权限、导入结果、Excel 下载及约 1440/1024/390 像素的表格/表单可用。
- [ ] **步骤 19：写本地教程。** 保存 `docs/learning/phase-8-task-2-products.md`，解释真实新增代码和 RED/GREEN，不暂存。
- [ ] **步骤 20：精确提交。** 核对暂存清单只含本 Task 工程文件，提交 `feat: add product operations workspace`。

## Task 3：知识库、问答与语义审核

**交付：** Admin 创建知识库并上传资料；团队查看文档索引状态、同步问答与引用；商品详情可发起/查看异步语义审核。

**接口：** `useTaskPolling(load: () => Promise<boolean>, intervalMs = 3000): { start(): void; stop(): void }`，`load` 返回是否仍需轮询，内部处理可见性、销毁与终态；`listKnowledgeBases(page: number): Promise<Page<KnowledgeBase>>`、`createKnowledgeBase(input: KnowledgeBaseCreate): Promise<KnowledgeBase>`、`listDocuments(baseId: number, page: number): Promise<Page<KnowledgeDocument>>`、`uploadDocument(baseId: number, file: File): Promise<KnowledgeDocumentCreated>`、`askKnowledge(baseId: number, question: string): Promise<KnowledgeQuery>`、`listQuestions(baseId: number, page: number): Promise<Page<KnowledgeQuery>>`、`listSemanticReviews(productId: number): Promise<Page<SemanticReview>>`、`startSemanticReview(productId: number): Promise<SemanticReviewCreated>`、`getSemanticReview(productId: number, reviewId: number): Promise<SemanticReview>`。类型依照 `knowledge.py`、`semantic_review.py`。

关键测试断言（`vi.useFakeTimers()`，挂载后改变可见性）：

```ts
expect(uploadInit.body).toBeInstanceOf(FormData)
expect(uploadHeaders.has('Content-Type')).toBe(false)
expect(load).toHaveBeenCalledTimes(callsBeforeUnmount) // 卸载后推进时钟
```

- [ ] **步骤 1：写知识库 API 测试。** `knowledge/api.test.ts` 断言创建只发 `name/description`、上传为 FormData 且无手设 multipart `Content-Type`、同步问答保留 `citations` 和 `refused` 状态。
- [ ] **步骤 2：确认 API RED。** 运行 `npm run test -- src/features/knowledge/api.test.ts`；预期目标行为失败。
- [ ] **步骤 3：实现知识库 API 与类型。** 对齐 `knowledge.py` 的创建、分页、文档和问答契约，直接使用现有路由。
- [ ] **步骤 4：确认 API GREEN。** 重跑 `npm run test -- src/features/knowledge/api.test.ts`；全部通过。
- [ ] **步骤 5：写轮询测试。** `useTaskPolling.test.ts::stops_polling_when_hidden_or_unmounted` 用假时钟覆盖运行态、终态、隐藏、恢复、卸载及加载失败后人工重启。
- [ ] **步骤 6：确认轮询 RED。** 运行 `npm run test -- src/lib/useTaskPolling.test.ts`；预期目标行为失败。
- [ ] **步骤 7：实现最小轮询 composable。** 仅在本页面活跃且任务未终结时定时读业务详情，异常停止并给页面重试入口；不读取 Celery Result Backend。
- [ ] **步骤 8：确认轮询 GREEN。** 重跑 `npm run test -- src/lib/useTaskPolling.test.ts`；全部通过。
- [ ] **步骤 9：写知识库页面测试。** `KnowledgeBasesPage.test.ts`、`KnowledgeBasePage.test.ts` 断言 Admin-only 创建/上传、文档状态/错误、分页/空态、问答拒答与来源文件名/页码/摘录，其他角色可问不可上传。
- [ ] **步骤 10：确认知识库页面 RED。** 运行 `npm run test -- src/features/knowledge/KnowledgeBasesPage.test.ts src/features/knowledge/KnowledgeBasePage.test.ts`；预期目标行为失败。
- [ ] **步骤 11：实现知识库页面。** 接入已有 API 和轮询；上传仅提前提示默认格式/大小，服务器校验为准。
- [ ] **步骤 12：确认知识库页面 GREEN。** 重跑 `npm run test -- src/features/knowledge/KnowledgeBasesPage.test.ts src/features/knowledge/KnowledgeBasePage.test.ts`；全部通过。
- [ ] **步骤 13：写语义审核测试。** `SemanticReviewPanel.test.ts` 断言 Analyst 只读、Admin/Operator 发起后仅轮询 MySQL、成功展示分数/问题/改写及快照、`503` 诚实提示模型配置/服务不可用。
- [ ] **步骤 14：确认语义审核 RED。** 运行 `npm run test -- src/features/semantic/SemanticReviewPanel.test.ts`；预期目标行为失败。
- [ ] **步骤 15：实现语义审核面板。** 添加语义审核 API/类型、面板，并接到商品详情；不在浏览器调用模型。
- [ ] **步骤 16：确认语义审核 GREEN。** 重跑 `npm run test -- src/features/semantic/SemanticReviewPanel.test.ts`；全部通过。
- [ ] **步骤 17：运行 Task 3 质量检查。** `npm run test`、`npm run typecheck`、`npm run build` 均通过。
- [ ] **步骤 18：人工核对 Task 3。** 检查上传、问答、审核的加载、失败、拒答、空态和终态页面。
- [ ] **步骤 19：写本地教程。** 保存 `docs/learning/phase-8-task-3-knowledge-semantic.md`，解释真实新增代码和 RED/GREEN，不暂存。
- [ ] **步骤 20：精确提交。** 核对暂存清单只含本 Task 工程文件，提交 `feat: add knowledge and semantic review workspace`。

## Task 4：研究、人工审批与整体验收

**交付：** 商品到研究再到一次性审核和已批准 Excel 下载的可追溯闭环；三个角色、错误与视觉均通过验收。

**接口：** `createResearch(productId: number, goal: string, knowledgeBaseIds: number[]): Promise<ResearchCreated>`、`listResearchRuns(productId: number, page: number): Promise<Page<ResearchRun>>`、`getResearchRun(productId: number, runId: number): Promise<ResearchRun>`、`reviewResearchRun(productId: number, runId: number, decision: 'approved' | 'rejected', comment?: string): Promise<ResearchReview>`、`downloadResearchRun(productId: number, runId: number): Promise<void>`；类型依照 `research.py` 和 `research_review.py`，`review_status` 五态原样呈现。

关键测试断言（模拟真实状态而非伪造成功）：

```ts
expect(wrapper.text()).toContain('证据不足')
expect(reviewRequest).not.toHaveBeenCalled() // not_reviewable
expect(downloadRequest).not.toHaveBeenCalled() // 未批准
```

- [ ] **步骤 1：写研究 API 测试。** `research/api.test.ts` 断言目标去空白、知识库 ID 1–3 个且不重复（后端最终校验）、`202` 后按研究 ID 读取、认证 Blob 下载、外来报告文本不被当作 HTML。
- [ ] **步骤 2：确认 API RED。** 运行 `npm run test -- src/features/research/api.test.ts`；预期目标行为失败。
- [ ] **步骤 3：实现研究 API 与类型。** 对齐 `research.py`、`research_review.py`，只访问现有 `/products/{id}/research-runs` 系列路由。
- [ ] **步骤 4：确认 API GREEN。** 重跑 `npm run test -- src/features/research/api.test.ts`；全部通过。
- [ ] **步骤 5：写发起、历史和证据测试。** `ResearchPanel.test.ts`、`ResearchPage.test.ts` 断言 Analyst 无发起按钮、运行态使用 Task 3 轮询、证据不足为 `not_reviewable`、发现/建议指向真实 `source_id` 及文件名/页码/摘录、Token 用量只显示后端值。
- [ ] **步骤 6：确认研究页面 RED。** 运行 `npm run test -- src/features/research/ResearchPanel.test.ts src/features/research/ResearchPage.test.ts`；预期目标行为失败。
- [ ] **步骤 7：实现研究表单、历史和详情。** 严格渲染后端证据与报告字段；不用 `v-html`，无证据报告不装饰成已证实结论。
- [ ] **步骤 8：确认研究页面 GREEN。** 重跑 `npm run test -- src/features/research/ResearchPanel.test.ts src/features/research/ResearchPage.test.ts`；全部通过。
- [ ] **步骤 9：写审核与交付测试。** `ResearchPage.test.ts::rejects_unreviewable_and_unapproved_actions` 断言未就绪/证据不足不可审核、未批准不可下载；另断言 Admin 一次性批准/驳回、驳回意见必填，Operator/Analyst 只能下载已批准报告，API `409` 显示冲突并提供重新读取。
- [ ] **步骤 10：确认审核 RED。** 运行 `npm run test -- src/features/research/ResearchPage.test.ts`；新增用例因目标行为缺失而失败。
- [ ] **步骤 11：实现审核与交付。** 复用确认对话框；提交后重新取详情，成功只显示服务端审核记录；下载复用 Task 1 `apiFile`。
- [ ] **步骤 12：确认审核 GREEN。** 重跑 `npm run test -- src/features/research/ResearchPage.test.ts`；全部通过。
- [ ] **步骤 13：执行三角色业务走查。** 检查登录→商品→知识库→研究→Admin 审批→团队下载的真实 API 路径；外部服务未配置时记录限制，不伪造结果。
- [ ] **步骤 14：执行视觉/可访问性走查。** 约 1440/1024/390 像素截图核对间距、层级、表格溢出和操作可见性；键盘走通主要路径，焦点可见、状态非仅颜色表达，减少动态效果偏好下无必要动画。
- [ ] **步骤 15：修复走查缺陷。** 对每个真实缺陷先补失败测试，再改代码并运行聚焦 GREEN；没有缺陷则记录“无修复”，不制造改动。
- [ ] **步骤 16：更新 README。** 写前端启动、测试、模型配置归属、三角色权限和单元 9 才会提供的正式部署说明；不将真实模型调用纳入自动化。
- [ ] **步骤 17：运行前端全量检查。** `frontend/` 下 `npm run test`、`npm run typecheck`、`npm run build`；逐项记录原始结果。
- [ ] **步骤 18：运行后端回归。** 仓库根目录下 `.venv\Scripts\python.exe -m pytest -q --ignore=tests/unit/models/test_product_practice.py`、`.venv\Scripts\ruff.exe check .`、`.venv\Scripts\mypy.exe backend tests scripts`；单独报告用户练习测试的既有状态。
- [ ] **步骤 19：写本地教程。** 保存 `docs/learning/phase-8-task-4-research-delivery.md`，汇总四 Task 的调用链、逐行/逐段讲解、失败修复与面试口述，不暂存。
- [ ] **步骤 20：精确提交。** 核对暂存清单只含 Task 4 工程文件与 README，提交 `feat: complete research delivery workspace`；不推送、不合并。

## 执行后的报告格式

每 Task 报告本阶段交付、实际 RED/GREEN 命令与结果、质量检查、提交 ID、教程路径和未解决风险。单元 8 结束时说明三角色人工验收是否真的完成、哪些外部服务因未配置而无法人工验证、前端视觉检查证据，以及单元 9 尚需的 CI/正式部署工作。所有结论必须以当次命令/页面结果为依据，不能因为计划写了测试就声称已通过。
