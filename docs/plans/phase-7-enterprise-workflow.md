# 单元 7：研究报告审核与交付实施计划

> **执行者须知：** 按 Task 顺序执行；原生执行使用 `superpowers:executing-plans`，若明确选择子代理执行则使用 `superpowers:subagent-driven-development`。每个步骤用 `- [ ]` 跟踪，先看到与目标行为相符的 RED，再写最小实现、看到 GREEN、检查并提交。

**目标：** 让有证据的研究报告经 Admin 一次性审核后，由团队安全下载带来源的 Excel 交付件。

**架构：** 新建一对一的不可变审核表，数据库行锁与唯一约束保证并发下只有一个最终决定。现有研究 API 增加审核及导出路由；导出仅在服务端重新确认批准后，从已持久化报告和证据生成内存工作簿。

**技术栈：** Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、MySQL 8、openpyxl、pytest、Ruff、mypy；不新增运行依赖。

**设计依据：** `docs/plans/phase-7-enterprise-workflow-design.md`。

## 全局约束

- 四个 Task，各有一份本地中文学习文档；文档说明编写顺序、每段/关键行代码、调用来源、作用、原理、真实故障与测试，不加入 Git。
- 只有 `ResearchStatus.SUCCESS` 且 `ResearchReport.outcome == "supported"` 可审核；报告、步骤和证据在审核时不可改。
- 决定只能是 `approved/rejected`；驳回意见去空格后必填，通过意见可空；意见最长 500 字符。
- 同一研究仅一个终局审核；同一 Admin 同决定和规范化意见重试返回原记录，其他再次提交均 `409`。
- Admin 审核；Admin、Operator、Analyst 读取与下载；仅已批准的报告可导出。
- 审核 POST 首次成功和完全相同的幂等重试均返回 `200` 与同一审核记录；相冲突的再次提交返回 `409`。
- `.xlsx` 仅在内存生成；固定三张工作表；不信任报告/证据文本为公式、文件路径或超链接。
- 不调用付费模型、不接外部系统、不做前端/MCP/RPA/通用工作流引擎；不合并或推送。
- 保留所有既有本地学习文件与 `tests/unit/models/test_product_practice.py`；Git 只暂存精确文件列表；`.env` 不读取或输出。
- Windows PowerShell 命令使用项目 `.venv`。DB 集成测试只连接 `marketmind_test`；先迁移测试库到 `0006`，不默认迁移开发库。

## 复核重点

1. 来源摘录以空白加 `=` 开头：`test_export_never_writes_untrusted_formula` 重新打开 Excel，断言单元格不是公式（Task 3）。
2. 同一管理员重试时意见首尾空格不同：`test_same_review_retry_is_idempotent` 断言仍只有一条、同一 ID（Task 2）。
3. 其他商品的真实研究 ID：`test_review_requires_product_scope` 与 `test_export_requires_product_scope` 均返回 `404`（Task 2/3）。
4. `insufficient_evidence` 或损坏的报告 JSON：`test_only_supported_report_is_reviewable` 返回安全 `409`，不写审核行（Task 2）。
5. 两名管理员在独立数据库连接中同时决定：`test_competing_admin_reviews_have_one_winner` 断言仅一条审核和一方 `409`（Task 2）。

---

## 文件职责与接口地图

| 文件 | 本单元职责 |
|---|---|
| `backend/app/models/research_review.py` | `ResearchReportReview`、`ResearchReviewDecision`；一对一审计记录 |
| `alembic/versions/0006_create_research_report_reviews.py` | 唯一键、外键、决定约束和审核时间 |
| `backend/app/models/__init__.py`、`alembic/env.py` | 注册新 ORM 模型，供元数据/迁移识别 |
| `backend/app/schemas/research_review.py` | 审核输入、审核输出、派生审核状态类型 |
| `backend/app/schemas/research.py` | 给现有研究响应增加审核状态与记录 |
| `backend/app/services/research_review.py` | 资格判断、事务、幂等、批量查询、交付许可 |
| `backend/app/services/research_export.py` | 已批准研究的纯内存 Excel 排版及文本安全化 |
| `backend/app/api/v1/research.py` | 审核、详情/列表展示、导出路由与 RBAC |
| `tests/conftest.py` | 测试清理时先删审核行，再删研究行 |
| `tests/unit/models/test_research_review.py`、`tests/unit/schemas/test_research_review.py` | 模型与输入契约 |
| `tests/integration/db/test_research_review.py`、`tests/api/test_research_review.py` | 真 MySQL 事务、并发、权限、归属 |
| `tests/unit/services/test_research_export.py` | 工作簿结构、来源与公式边界 |
| `README.md` | 操作步骤、权限与剩余限制 |

复用 `app.services.research.get_research_run(session, product_id, run_id)`、`app.api.dependencies.get_db_session/require_roles`、`ResearchReport`、`ResearchRun`、`app.core.errors.AppError`、现有 `StreamingResponse(BytesIO(...))` 模式；不引入 Repository/Provider 工厂。

## Task 1：审核记录、迁移和输入契约

**交付：** 独立的审核表与严格 Schema，可在测试库迁移后查询；还不提供审核 API。

**文件：** 新建模型、Schema、`0006` 迁移、两份单元测试及本地 `docs/learning/phase-7-task-1-review-persistence.md`；修改 `backend/app/models/__init__.py`、`alembic/env.py`、`tests/conftest.py`。

**接口：** 产出 `ResearchReviewDecision`（`APPROVED/REJECTED`）、`ResearchReportReview`（ORM）、`ResearchReviewCreate(decision, comment)`、`ResearchReviewRead`、`ResearchReviewStatus`（`not_ready/not_reviewable/pending_review/approved/rejected`）。后续 Task 均使用这些名字。

- [ ] **步骤 1：写 RED 测试。** `tests/unit/models/test_research_review.py::test_review_is_unique_per_run` 检查表名 `research_report_reviews`、`run_id` 唯一；`tests/unit/schemas/test_research_review.py::test_rejection_requires_comment` 检查空白意见失败、`" 需补证 "` 规范化为 `"需补证"`、非法决定和超过 500 字符失败。先用导入目标类的测试，让缺类型成为明确 RED。

  核心断言：

  ```python
  assert ResearchReviewCreate(decision="rejected", comment=" 需补证 ").comment == "需补证"
  with pytest.raises(ValidationError):
      ResearchReviewCreate(decision="rejected", comment="   ")
  ```
- [ ] **步骤 2：运行 RED。** `.venv\Scripts\python.exe -m pytest -q tests/unit/models/test_research_review.py tests/unit/schemas/test_research_review.py`；预期因目标类不存在而失败，不接受环境连接错误冒充 RED。
- [ ] **步骤 3：实现 ORM 与 Schema。** `ResearchReportReview` 用 `run_id: Mapped[int]` 唯一 FK、`reviewed_by_id: Mapped[int]` FK、`decision: Mapped[ResearchReviewDecision]`、`comment: Mapped[str | None]`、`reviewed_at: Mapped[datetime]`；Pydantic `ResearchReviewCreate` 用 `extra="forbid"` 和跨字段校验。
- [ ] **步骤 4：建立迁移及注册。** 迁移 `revision="0006"`、`down_revision="0005"`，与 ORM 相同的列/约束；在 `models/__init__.py` 与 `alembic/env.py` 注册新模型，`tests/conftest.py` 先删除审核行再删除研究行。
- [ ] **步骤 5：迁移测试库。** `.venv\Scripts\alembic.exe -x database=test upgrade head`；`.venv\Scripts\alembic.exe -x database=test current` 应为 `0006 (head)`。
- [ ] **步骤 6：验证 GREEN 与旧夹具。** `.venv\Scripts\python.exe -m pytest -q tests/unit/models/test_research_review.py tests/unit/schemas/test_research_review.py tests/integration/db/test_research.py`；预期全部通过。
- [ ] **步骤 7：静态检查。** `.venv\Scripts\ruff.exe check backend tests alembic` 与 `.venv\Scripts\mypy.exe backend tests scripts` 均通过。
- [ ] **步骤 8：写 Task 1 中文学习文档。** 保存 `docs/learning/phase-7-task-1-review-persistence.md`，记录真实 RED/GREEN、字段和迁移的编写理由；保持未跟踪。
- [ ] **步骤 9：精确暂存并提交。** 仅暂存本 Task 的模型、Schema、迁移、注册、测试与夹具文件，提交 `feat: add research report review persistence`。

## Task 2：审核事务、权限与历史展示

**交付：** Admin 可作一次审核；相同请求重试幂等，冲突与并发安全；详情和分页列表能看到审核状态。

**文件：** 新建 `backend/app/services/research_review.py`、`tests/integration/db/test_research_review.py`、`tests/api/test_research_review.py` 和本地 `docs/learning/phase-7-task-2-review-workflow.md`；修改研究 Schema/API。

**接口：**

- `review_research_report(session: AsyncSession, product_id: int, run_id: int, reviewer_id: int, payload: ResearchReviewCreate) -> ResearchReportReview`：短事务、行锁、资格、幂等；抛稳定 `AppError`。
- `get_research_review(session: AsyncSession, run_id: int) -> ResearchReportReview | None`；`list_research_reviews(session: AsyncSession, run_ids: list[int]) -> dict[int, ResearchReportReview]`：详情单查、分页批量查。
- `research_review_status(run: ResearchRun, review: ResearchReportReview | None) -> ResearchReviewStatus`：纯函数，按设计中的五种状态派生；`ResearchRead` 增 `review_status` 与 `review`。

- [ ] **步骤 1：写数据库 RED。** `test_only_supported_report_is_reviewable` 断言 pending/failure/insufficient/损坏 JSON 均 `409` 且审核行数为 0；`test_same_review_retry_is_idempotent` 断言同 Admin 的同决定与去空格意见返回同一 ID；不同意见或不同 Admin `409`；`test_competing_admin_reviews_have_one_winner` 用已提交准备数据和两条独立 MySQL 连接，`asyncio.gather` 后只存一个决定，另一方 `409`，并按精确 ID 清理测试数据。

  核心断言：

  ```python
  assert retry.id == first.id
  assert await session.scalar(
      select(func.count()).select_from(ResearchReportReview).where(
          ResearchReportReview.run_id == run_id
      )
  ) == 1
  assert sorted(concurrent_statuses) == [200, 409]
  ```
- [ ] **步骤 2：运行数据库 RED。** `.venv\Scripts\python.exe -m pytest -q tests/integration/db/test_research_review.py`；预期缺服务函数或断言失败。
- [ ] **步骤 3：实现审核事务。** 按接口在一笔事务中锁 `ResearchRun`，核对商品范围、`SUCCESS/supported`（用现有 `ResearchReport.model_validate`，校验失败映射安全 `409`），读或写审核行；遇唯一冲突时回滚、重读并应用同一幂等判断，不让原始异常进入响应。
- [ ] **步骤 4：实现状态与批量查询。** `research_review_status` 按五种状态派生；`get_research_review` 单查，`list_research_reviews` 用一次 `IN` 查询返回字典，不增加通用状态机。
- [ ] **步骤 5：运行数据库 GREEN。** `.venv\Scripts\python.exe -m pytest -q tests/integration/db/test_research_review.py tests/integration/db/test_research.py`；预期通过。并发测试只使用已提交准备数据与独立连接，失败时修正测试隔离而不弱化断言。
- [ ] **步骤 6：写 API RED。** `test_admin_reviews_operator_and_analyst_cannot` 断言 Admin 成功、其他角色 `403`、匿名 `401`；`test_review_requires_product_scope` 审核错误商品 `404`；`test_history_reports_review_state` 断言详情/列表状态及分页查询不发生逐行 N+1。使用 `tests/api/test_research.py` 的 app/认证夹具模式，运行 `.venv\Scripts\python.exe -m pytest -q tests/api/test_research_review.py` 观察缺路由/字段 RED。
- [ ] **步骤 7：实现路由。** `POST /{product_id}/research-runs/{run_id}/review` 使用 `require_roles(Role.ADMIN)`，请求体 `ResearchReviewCreate`，返回 `ResearchReviewRead`。
- [ ] **步骤 8：实现详情与列表展示。** GET 详情单查审核，GET 列表用 `list_research_reviews` 批量映射，不依赖懒加载；在 `schemas/research.py` 提供 `build_research_read(run: ResearchRun, review: ResearchReportReview | None) -> ResearchRead` 统一组装。
- [ ] **步骤 9：API GREEN。** `.venv\Scripts\python.exe -m pytest -q tests/api/test_research_review.py tests/api/test_research.py tests/integration/db/test_research_review.py`；预期通过。
- [ ] **步骤 10：静态检查。** `.venv\Scripts\ruff.exe check backend tests alembic`、`.venv\Scripts\mypy.exe backend tests scripts` 通过。
- [ ] **步骤 11：写 Task 2 中文学习文档。** 保存 `docs/learning/phase-7-task-2-review-workflow.md`，解释行锁、唯一约束、幂等与 RBAC 的实际调用链；保持未跟踪。
- [ ] **步骤 12：精确暂存并提交。** 只暂存本 Task 工程/测试文件，提交 `feat: add audited research report review`。

## Task 3：安全的 Excel 交付件

**交付：** 仅已批准报告可下载；三张固定工作表含已登记来源，危险文本不被 Excel 当公式执行。

**文件：** 新建 `backend/app/services/research_export.py`、`tests/unit/services/test_research_export.py`、本地 `docs/learning/phase-7-task-3-report-export.md`；修改 `backend/app/services/research_review.py`、`backend/app/api/v1/research.py`、`tests/api/test_research_review.py`。

**接口：** `get_approved_research_report(session: AsyncSession, product_id: int, run_id: int) -> tuple[ResearchRun, ResearchReportReview]`；`export_research_report(run: ResearchRun, review: ResearchReportReview) -> bytes`。内部纯函数 `_safe_excel_text(value: str) -> str` 对 `value.lstrip()` 以 `=+-@` 开头的内容加单引号，使其留在字符串单元格。

- [ ] **步骤 1：写导出 RED。** `test_export_contains_report_and_registered_sources` 用模拟 `ResearchRun/ResearchReportReview` 生成字节，`openpyxl.load_workbook(BytesIO(...))` 断言表名严格为“概览/发现与建议/证据”、商品快照、摘要、引用 ID、已登记文件名和免责声明；`test_export_never_writes_untrusted_formula` 对标题、发现、文件名、摘录分别注入 `=1+1`、` +cmd`、`-2`、`@SUM(1)`，重新打开后断言危险单元格 `data_type != "f"` 且文本可辨认。此时因导出函数不存在而 RED。

  核心断言：

  ```python
  assert workbook.sheetnames == ["概览", "发现与建议", "证据"]
  assert all(cell.data_type != "f" for cell in untrusted_cells)
  ```
- [ ] **步骤 2：运行 RED。** `.venv\Scripts\python.exe -m pytest -q tests/unit/services/test_research_export.py`；预期目标函数缺失/断言失败。
- [ ] **步骤 3：最小导出实现。** 用已安装的 openpyxl 和标准库 `BytesIO` 填充固定三张表；从 `run.product_snapshot`、经 `ResearchReport.model_validate` 的报告、`ResearchEvidence` 注册表和审核记录取值。保留数值/时间类型，不让字符串决定工作表名、公式、超链接、下载路径；无需 pandas/DataFrame，也不新增文件缓存。
- [ ] **步骤 4：单元 GREEN。** `.venv\Scripts\python.exe -m pytest -q tests/unit/services/test_research_export.py`；预期通过。
- [ ] **步骤 5：写 API RED。** `tests/api/test_research_review.py::test_only_approved_report_is_downloadable` 断言未审核/驳回/证据不足 `409`、批准后三种角色均可得 `200` 且 Content-Type 为 `.xlsx`、文件名仅含研究 ID；`test_export_requires_product_scope` 断言错误商品 `404`，匿名请求 `401`。运行 `.venv\Scripts\python.exe -m pytest -q tests/api/test_research_review.py -k export` 观察缺路由 RED。
- [ ] **步骤 6：实现许可查询。** `get_approved_research_report` 调原有 `get_research_run` 核对商品，读取审核记录并要求 `approved`，不接受客户端声明的状态。
- [ ] **步骤 7：实现 GET 路由。** `GET /{product_id}/research-runs/{run_id}/export` 复用 `StreamingResponse(BytesIO(content))`，固定 `research-{run_id}.xlsx`，三种已认证角色可用。
- [ ] **步骤 8：API GREEN。** `.venv\Scripts\python.exe -m pytest -q tests/unit/services/test_research_export.py tests/api/test_research_review.py tests/api/test_research.py`；预期通过。
- [ ] **步骤 9：静态检查。** `.venv\Scripts\ruff.exe check backend tests alembic`、`.venv\Scripts\mypy.exe backend tests scripts` 通过。
- [ ] **步骤 10：写 Task 3 中文学习文档。** 保存 `docs/learning/phase-7-task-3-report-export.md`，解释证据映射、工作簿安全和流式下载；保持未跟踪。
- [ ] **步骤 11：精确暂存并提交。** 只暂存相关工程/测试文件，提交 `feat: export approved research reports`。

## Task 4：跨层验收与教学收尾

**交付：** 文档、端到端证据与阶段质量门禁；不扩大业务范围。

**文件：** 修改 `README.md`、必要的 API/数据库回归测试；新建仅本地 `docs/learning/phase-7-task-4-acceptance.md`，并核对 Task 1～3 文档的真实 RED/GREEN 记录。

- [ ] **步骤 1：核对跨层覆盖。** 检查已有 API 测试是否从真实 MySQL 报告经审核、列表/详情走到 Excel，并复查原 `report/steps/evidence` 未变。缺覆盖时先写 `test_approved_report_survives_research_history_reads`，运行它观察真实缺口的 RED，再修最小代码到 GREEN；若已覆盖，记录测试名称，不制造假 RED。
- [ ] **步骤 2：更新 README。** 写明 `0006` 迁移、审核/导出调用顺序、权限、`409`、不接外部系统和不产生模型费用。
- [ ] **步骤 3：写 Task 4 中文学习文档。** `docs/learning/phase-7-task-4-acceptance.md` 给出完整请求→审核→下载链路；核对 Task 1～3 教程逐 Task 说明关键行“为什么这样写、调用了谁、输入输出、原理和真实错误”；四份教程保持本地。
- [ ] **步骤 4：验证测试库迁移。** `.venv\Scripts\alembic.exe -x database=test current` 应为 `0006 (head)`。
- [ ] **步骤 5：运行工程全量测试。** 仅在测试确需时启动持久化关闭的临时 Redis；`.venv\Scripts\python.exe -m pytest -q --ignore=tests/unit/models/test_product_practice.py` 应通过。
- [ ] **步骤 6：运行原样全量测试。** `.venv\Scripts\python.exe -m pytest -q`，分开记录用户未跟踪练习文件的已知失败；不改该文件。
- [ ] **步骤 7：静态与差异检查。** `.venv\Scripts\ruff.exe check .`、`.venv\Scripts\mypy.exe backend tests scripts`、`git diff --check` 均通过；两轮测试结束后仅停止本任务创建且核实 PID 的 Redis 进程。
- [ ] **步骤 8：精确暂存并提交。** 只暂存 README 和 Task 4 工程/测试改动，提交 `docs: complete phase 7 workflow acceptance`；不暂存教程、用户练习文件或 `.env`。
- [ ] **步骤 9：独立审查及复验。** 核对模型/迁移一致性、单次决定与并发、Excel 注入、错误安全；修复成立的问题后重新跑受影响测试与静态门禁，不合并/推送。

## 执行交接

设计已批准；本计划需用户单独审阅。用户此前要求由当前对话原生实现，故计划批准后沿用原生执行，不创建新对话、沙箱或工作树。执行时按 Task 1→4 顺序完成各自 RED→GREEN、中文学习文档、验证与精确提交；不把本计划批准解释为外部系统接入或付费模型调用许可。
