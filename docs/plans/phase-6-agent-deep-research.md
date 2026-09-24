# 单元 6：受控 Agent 与可追溯竞品研究实施计划

> **执行说明：** 审阅通过后，使用 `superpowers:executing-plans` 在当前对话逐任务实施；以 `- [ ]` 跟踪步骤。每个任务先见到测试失败，再实现、复测、记录中文教程并精确提交。

**目标：** 基于一个商品和 1～3 个管理员上传的知识库，以最多四次受控动作生成有程序核验来源的竞品研究报告，并在 MySQL 保存可恢复的任务历史。

**架构：** FastAPI 在短事务中创建固定商品快照和待处理研究，Celery Worker 借助 Redis 锁执行有限的模型动作循环；商品工具读取快照，知识库工具复用现有 Embedding、Chroma 与 MySQL 就绪文档过滤。每次动作提交检查点；结构化报告只引用本次程序登记的证据。

**技术栈：** Python 3.12、FastAPI、Pydantic 2、SQLAlchemy asyncio、Alembic、MySQL 8、Redis、Celery、OpenAI Python SDK、Chroma、pytest、Ruff、mypy；不新增产品依赖。

**设计文档：** `docs/plans/phase-6-agent-deep-research-design.md`

## 全局约束

- 在现有 `codex/phase-6-agent-research` 分支工作，不另建独立沙箱；单元 5 尚未合并 `main`，不得把单元 6 作为独立于单元 5 的提交合并。
- 不联网采集竞品，不读取任意文件、URL 或 SQL，不增加 LangChain、LangGraph、MCP、通用 Tool 接口、Provider 工厂或前端。
- 输入限一个商品、1～3 个不同知识库和 1～500 字符目标；知识库至少有一份 `ready` 文档，Embedding 配置与当前配置完全一致。
- 模型仅能选择 `read_product`、`search_knowledge`、`finish`；动作决定最多默认 4 次，配置范围 2～8；证据最多默认 12 条，配置范围 2～30；单条证据文本最多 1000 字符。
- MySQL 保存商品快照、步骤、证据、报告、状态和 Token 用量；绝不保存密钥、思维链、原始响应或原始异常。
- Admin、Operator 发起；Admin、Operator、Analyst 查看团队历史。同商品最多一个 `pending/running` 研究。
- 模型和 Chroma 在自动化测试中全部模拟；不运行付费真实调用。真实验收、推送、合并和分支清理需要单独批准。
- 保护现有 `docs/learning/` 文件和 `tests/unit/models/test_product_practice.py`；四份新增中文教程只保存在本地，不暂存。不得读取或输出 `.env`。
- 每任务遵循 RED → GREEN → Ruff/mypy → 相关回归 → `git diff --check` → 精确暂存与提交。用户未跟踪练习测试的既有失败须单独报告，不能把排除它的测试称为“原样全绿”。

## 重点复核

1. 两个并发 POST 指向同一商品时，只能生成一个活动研究；任务 1 的两个独立 Session 测试验证商品行锁与 409。
2. 不在请求选定范围内的知识库 ID、无效动作或多余字段，绝不能变成工具调用；任务 2/3 的模拟模型测试验证零调用。
3. Chroma 返回伪造文件名、跨知识库或非 `ready` 文档时，不得进入证据；任务 2 从 MySQL 文档记录取得真实文件名并测试过滤。
4. Worker 在工具执行后重投时不得再次执行已提交的步骤；任务 3 的检查点/终态重投测试验证调用次数。
5. 模型引用未登记或重复的来源 ID 时不得生成成功报告；任务 4 的报告测试验证安全失败与历史状态。

## 文件边界

| 文件 | 单一职责 |
|---|---|
| `backend/app/models/research.py`、`alembic/versions/0005_create_research_runs.py` | 研究记录、状态和数据库约束 |
| `backend/app/schemas/research.py` | 请求、动作、证据、报告、分页和详情契约 |
| `backend/app/services/research.py` | 创建/读取、商品快照、检查点、状态和用量持久化 |
| `backend/app/services/research_tools.py` | 两个只读工具、来源登记与检索数据核验 |
| `backend/app/services/research_agent.py` | 严格 JSON 动作、有限循环、报告与引用验证 |
| `backend/app/tasks/research.py` | Celery 入口、锁、重试和资源生命周期 |
| `backend/app/api/v1/research.py` | 发起/列表/详情接口与权限 |
| 现有 `config.py`、`celery_app.py`、`main.py`、`tests/conftest.py` | 配置、注册与测试清理 |

---

### 任务 1：研究记录、并发边界和 API 基础

**交付内容：** 固定商品快照，建立 `research_runs` 表；创建、列表和详情接口具有正确权限、状态和 202/409/404 行为。此阶段 Celery 投递通过测试模拟，实际执行器在任务 3 注册。

**涉及文件：**
- 新建：`backend/app/models/research.py`、`backend/app/schemas/research.py`、`backend/app/services/research.py`、`backend/app/api/v1/research.py`、`alembic/versions/0005_create_research_runs.py`
- 新建：`tests/unit/models/test_research.py`、`tests/unit/schemas/test_research.py`、`tests/integration/db/test_research.py`、`tests/api/test_research.py`
- 修改：`backend/app/models/__init__.py`、`alembic/env.py`、`backend/app/main.py`、`tests/conftest.py`
- 仅本地：`docs/learning/phase-6-task-1-research-persistence.md`

**接口契约：**
- 依赖：`Product`、`KnowledgeBase`、`KnowledgeDocument`、`KnowledgeDocumentStatus`、`build_product_snapshot()`、`AsyncSession`、`AppError`、`get_db_session()` 和现有 RBAC。
- 提供：`ResearchStatus`、`ResearchRun`、`ResearchCreate`、`ResearchCreated`、`ResearchRead`、`ResearchPage`；`create_research_run(session, product_id, actor_id, payload, settings)`、`get_research_run(session, product_id, run_id)`、`list_research_runs(session, product_id, page, page_size)`、`mark_research_failure(session, run_id, code, message)`、`set_research_task_id(session, run_id, task_id)`。任务 2～4 复用同一行与 Schema。

- [ ] **步骤 1：写模型和输入 Schema 的失败测试。**

  在 `tests/unit/models/test_research.py` 固定表名 `research_runs`、商品/用户外键、状态枚举、按商品/状态索引、非负 Token 和尝试次数检查约束；在 `tests/unit/schemas/test_research.py` 固定空白目标、501 字符、零/重复/超过三个知识库 ID 返回校验错误：

  ```python
  def test_research_create_rejects_duplicate_bases() -> None:
      with pytest.raises(ValidationError):
          ResearchCreate(goal="比较定位", knowledge_base_ids=[2, 2])
  ```

- [ ] **步骤 2：运行 RED。** `.venv\Scripts\python.exe -m pytest tests/unit/models/test_research.py tests/unit/schemas/test_research.py -q`；预期因新模块不存在而导入失败。
- [ ] **步骤 3：实现 ORM 与 Schema。** 状态枚举仅有 `PENDING/RUNNING/SUCCESS/FAILURE`。ORM 字段逐项对应设计第 4 节，JSON 字段 `knowledge_base_ids/product_snapshot/steps/evidence/report` 使用独立默认值；`prompt_tokens/completion_tokens/embedding_tokens/total_tokens` 均允许 `NULL`。`ResearchCreate` 设置 `extra="forbid"` 并去除目标首尾空格；响应 Schema 使用 `from_attributes=True`。

  创建时四个用量字段均从 0 开始；真正发生调用而缺失 usage 时，把相应分项和总量设为 `NULL`，之后保持未知。状态、字段长度、索引与数据库检查约束以设计第 4 节的表为准。

  ```python
  class ResearchStatus(StrEnum):
      PENDING = "pending"
      RUNNING = "running"
      SUCCESS = "success"
      FAILURE = "failure"

  class ResearchCreate(BaseModel):
      model_config = ConfigDict(extra="forbid")
      goal: str = Field(min_length=1, max_length=500)
      knowledge_base_ids: list[int] = Field(min_length=1, max_length=3)
  ```

  在 `model_validator` 中拒绝非正数和重复 ID；不要增加 ORM relationship。

- [ ] **步骤 4：写迁移 `0005` 并运行模型 GREEN。** `down_revision="0004"`；建立表、状态约束、外键、检查约束及 `(product_id,status)` 索引；降级只删除此表。把模型导入 `models/__init__.py`、`alembic/env.py`。运行 `.venv\Scripts\python.exe -m pytest tests/unit/models/test_research.py tests/unit/schemas/test_research.py -q`、定向 Ruff 与 mypy。
- [ ] **步骤 5：写服务的失败集成测试。** 在真实 `marketmind_test` 中验证固定快照不随商品修改、1～3 个选定知识库均有 `ready` 文档、跨库 Embedding 配置不一致被拒绝、同商品活动研究返回 409、不同商品可并行、两个独立 Session 同时创建仅一条活动记录、列表按 ID 倒序、跨商品详情 404。设置 `tests/conftest.py` 清理顺序为 `ResearchRun → KnowledgeQuery → KnowledgeDocument → KnowledgeBase → SemanticReview → Product → User`。
- [ ] **步骤 6：运行服务 RED。** `.venv\Scripts\python.exe -m pytest tests/integration/db/test_research.py -q`；预期缺少创建/查询服务函数。
- [ ] **步骤 7：实现创建与读取服务。** `create_research_run()` 用 `select(Product).with_for_update()` 锁定商品，检查选定知识库及 `ready` 文档和 Embedding 配置；通过现有 `build_product_snapshot()` 获取 JSON 快照，检查同商品 `pending/running`，保存新行并提交。捕获业务错误时回滚；并发测试只使用独立 Session，不以进程内锁冒充数据库串行化。列表/详情的 `product_id` 必须匹配路径；`set_research_task_id()` 与 `mark_research_failure()` 各用短事务。
- [ ] **步骤 8：运行服务 GREEN 和迁移检查。** `.venv\Scripts\python.exe -m pytest tests/integration/db/test_research.py -q`；`.venv\Scripts\alembic.exe -x database=test upgrade head`；`.venv\Scripts\alembic.exe -x database=test current`，预期版本为 `0005`。不得降级开发库。
- [ ] **步骤 9：写 API 的失败测试。** 模拟 `celery_app.send_task()` 返回固定任务 ID；覆盖 Admin/Operator 202、Analyst 403、未登录 401、无商品/知识库 404、无 `ready` 文档或并发研究 409、缺失配置或 Broker 故障 503、三角色列表/详情、跨商品详情 404；断言 Broker 故障后的 MySQL 状态为 `failure`。
- [ ] **步骤 10：运行 API RED。** `.venv\Scripts\python.exe -m pytest tests/api/test_research.py -q`；预期路由尚未注册。
- [ ] **步骤 11：实现并注册 API。** `router` 前缀为 `/products`，创建路径为 `/{product_id}/research-runs`；POST 依赖 `require_roles(Role.ADMIN, Role.OPERATOR)`，只从 `request.app.state.settings` 获取配置，创建行后通过现有 Celery app 的 `send_task("app.tasks.research.run_research", args=[run.id])` 投递；捕获 Broker/Celery 错误，安全标记失败并返回 503。GET 均要求 `get_current_user`。在 `main.py` 挂载路由。
- [ ] **步骤 12：任务 1 验证、教程与提交。** 运行上述单元/集成/API 测试、定向 Ruff/mypy、`git diff --check`。本地中文教程记录每个文件及所引入的标准库/第三方/项目代码、从模型到迁移到事务再到 API 的编写顺序、关键行解释、真实 RED/GREEN 和并发排错。仅精确暂存任务 1 工程文件，先核对 `git diff --cached --name-only` 不含学习文档，再提交 `feat: add research run persistence and API`。

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/models/test_research.py tests/unit/schemas/test_research.py tests/integration/db/test_research.py tests/api/test_research.py -q
  .venv\Scripts\ruff.exe check backend/app/models/research.py backend/app/schemas/research.py backend/app/services/research.py backend/app/api/v1/research.py alembic/versions/0005_create_research_runs.py tests/unit/models/test_research.py tests/unit/schemas/test_research.py tests/integration/db/test_research.py tests/api/test_research.py
  .venv\Scripts\mypy.exe backend/app/models/research.py backend/app/schemas/research.py backend/app/services/research.py backend/app/api/v1/research.py tests/unit/models/test_research.py tests/unit/schemas/test_research.py tests/integration/db/test_research.py tests/api/test_research.py
  git diff --check
  git add -- backend/app/models/research.py backend/app/schemas/research.py backend/app/services/research.py backend/app/api/v1/research.py alembic/versions/0005_create_research_runs.py backend/app/models/__init__.py alembic/env.py backend/app/main.py tests/conftest.py tests/unit/models/test_research.py tests/unit/schemas/test_research.py tests/integration/db/test_research.py tests/api/test_research.py
  git diff --cached --name-only
  git diff --cached --check
  git commit -m "feat: add research run persistence and API"
  ```

---

### 任务 2：受控工具、知识库过滤与证据登记

**交付内容：** 只读商品快照和选定知识库检索可以作为受控工具调用；跨库、非就绪、配置漂移、维度不一致及伪造来源不能进入持久化证据。

**涉及文件：**
- 新建：`backend/app/services/research_tools.py`、`tests/unit/services/test_research_tools.py`
- 修改：`backend/app/schemas/research.py`、`tests/integration/db/test_research.py`
- 仅本地：`docs/learning/phase-6-task-2-research-tools.md`

**接口契约：**
- 依赖：任务 1 的 `ResearchRun`/快照、`KnowledgeBase`/`KnowledgeDocument`、`request_embeddings()`、`create_chroma_client()`、`close_chroma_client()`、`retrieve_chunks()` 和 `Settings`。
- 提供：`ResearchEvidence`、`ToolResult`、`read_product_snapshot(run)`、`search_knowledge(session, run, base_id, query, settings)`、`register_evidence(existing, incoming, limit)`；任务 3 只根据这些返回值推进循环。
- `ResearchEvidence` 至少包含 `source_id: str`、`source_type: Literal["product", "knowledge"]`、`text: str`，以及按类型可选的商品/知识库/文档/块坐标、原始文件名、页码、距离；`ToolResult` 包含 `evidence: list[ResearchEvidence]` 与 `embedding_tokens: int | None`。

- [ ] **步骤 1：写商品工具和登记规则的失败测试。** 验证工具只返回创建时白名单快照；来源 ID 固定为 `product:{product_id}:snapshot`；同来源只登记一次；文本截为最多 1000 字符；达到 `research_max_evidence` 时不再追加；输入列表不被原位修改。

  ```python
  def test_register_evidence_deduplicates_and_caps_count() -> None:
      product_evidence = ResearchEvidence(
          source_id="product:7:snapshot",
          source_type="product",
          product_id=7,
          text="商品快照",
      )
      result = register_evidence([], [product_evidence, product_evidence], limit=2)
      assert [item.source_id for item in result] == ["product:7:snapshot"]
  ```

- [ ] **步骤 2：运行 RED。** `.venv\Scripts\python.exe -m pytest tests/unit/services/test_research_tools.py -q`；预期工具模块不存在。
- [ ] **步骤 3：实现 `ResearchEvidence` 与纯登记函数。** Schema 严格限定 `source_id/source_type/product_id/knowledge_base_id/document_id/chunk_id/chunk_index/page_number/original_name/text/distance`；商品和知识库来源使用互斥必需字段校验。`register_evidence()` 返回新列表，不原位改 JSON。`read_product_snapshot()` 不访问数据库或网络。
- [ ] **步骤 4：运行纯函数 GREEN。** 重跑对应单元测试与定向 Ruff/mypy。
- [ ] **步骤 5：写知识库检索的失败测试。** 模拟 Embedding 与 Chroma：未选定库 ID、空/301 字符查询、模型配置漂移、向量维度不符必须在 Chroma 查询前失败；跨库命中、已删除/非 `ready` 文档、无效距离和伪造文件名必须丢弃或以 MySQL 真实名称覆盖；最多返回距离合格的前三块；客户端在成功和异常时均关闭。用一项 MySQL 集成测试固定文档归属与 `ready` 过滤。
- [ ] **步骤 6：运行检索 RED。** `.venv\Scripts\python.exe -m pytest tests/unit/services/test_research_tools.py tests/integration/db/test_research.py -q`。
- [ ] **步骤 7：实现知识库工具。** 先在短事务读取所选 `KnowledgeBase`、当前文档状态和 Embedding 契约，再结束读取事务；调用 `request_embeddings([query], settings)` 并校验 `embedding_dimensions`；创建 Chroma 客户端，复用 `retrieve_chunks(session, chroma, base, embedding.vectors[0], 3, settings.rag_max_distance)`，最后关闭客户端、回滚读取事务。对命中文档重新查询 MySQL `KnowledgeDocument` 的 `knowledge_base_id/status/original_name`，来源 ID 只按程序规则生成 `kb:{base_id}:document:{document_id}:chunk:{chunk_index}`；原文件名来自 MySQL，页码来自已通过 `RetrievedChunk` 类型/范围校验的向量元数据。只把可用来源返回给 Agent。
- [ ] **步骤 8：运行任务 2 验证、教程与提交。** 重跑工具单元与 MySQL 集成测试、定向 Ruff/mypy、`git diff --check`。中文教程逐段说明已有检索函数和新工具的调用链、事务边界、来源 ID、元数据校验、为什么先校验配置再调用付费模型，并记真实 RED/GREEN。精确提交任务 2 文件，提交信息 `feat: add controlled research tools`。

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/services/test_research_tools.py tests/integration/db/test_research.py -q
  .venv\Scripts\ruff.exe check backend/app/services/research_tools.py backend/app/schemas/research.py tests/unit/services/test_research_tools.py tests/integration/db/test_research.py
  .venv\Scripts\mypy.exe backend/app/services/research_tools.py backend/app/schemas/research.py tests/unit/services/test_research_tools.py tests/integration/db/test_research.py
  git diff --check
  git add -- backend/app/services/research_tools.py backend/app/schemas/research.py tests/unit/services/test_research_tools.py tests/integration/db/test_research.py
  git diff --cached --name-only
  git diff --cached --check
  git commit -m "feat: add controlled research tools"
  ```

---

### 任务 3：有限动作循环、检查点与 Worker

**交付内容：** 模型只可提出三个严格动作；每步独立持久化并可恢复；Worker 使用 Redis 锁、有限重试和安全错误映射，记录已知/未知 Token 用量。

**涉及文件：**
- 新建：`backend/app/services/research_agent.py`、`backend/app/tasks/research.py`、`tests/unit/services/test_research_agent.py`、`tests/unit/tasks/test_research_task.py`
- 修改：`backend/app/core/config.py`、`backend/app/schemas/research.py`、`backend/app/services/research.py`、`backend/app/celery_app.py`、`tests/unit/core/test_config.py`、`tests/integration/db/test_research.py`
- 仅本地：`docs/learning/phase-6-task-3-agent-worker.md`

**接口契约：**
- 依赖：任务 1 的行与检查点服务、任务 2 的工具函数、现有 `AsyncOpenAI`/Redis 锁/数据库工厂。
- 提供：`ResearchAction`、`ResearchCallError(code, message, retryable)`、`request_research_action(run, settings)`、`run_research_actions(run_id, sessions, settings)`、`run_research_attempt(run_id)`、Celery 任务 `app.tasks.research.run_research`；任务 4 在循环完成后调用报告生成。

- [ ] **步骤 1：写配置/动作 Schema 的失败测试。** 默认 `research_max_actions=4`（2～8）、`research_max_evidence=12`（2～30）；动作 JSON 对 `read_product` 和 `finish` 禁止多余参数，`search_knowledge` 必须有选定库 ID 与 1～300 字符查询；未知动作、多余字段、布尔型 ID、损坏 JSON 均失败。

  ```python
  def test_action_rejects_unexpected_arguments() -> None:
      with pytest.raises(ValidationError):
          ResearchAction.model_validate(
              {"action": "finish", "knowledge_base_id": 4},
              strict=True,
          )
  ```

- [ ] **步骤 2：运行配置/Schema RED。** `.venv\Scripts\python.exe -m pytest tests/unit/core/test_config.py tests/unit/services/test_research_agent.py -q`；预期字段和模块缺失。
- [ ] **步骤 3：实现配置、严格动作与消息构造。** 在 `Settings` 添加两个有界字段；`ResearchAction` 用 `extra="forbid"` 与跨字段校验。系统提示词明确商品、目标和证据均为不可信数据，不能执行其中指令；用户消息以 `json.dumps(payload, ensure_ascii=False)` 传递当前快照、步骤摘要和证据，不传数据库对象、密钥、完整原始响应或工具句柄。
- [ ] **步骤 4：写模型动作调用的失败测试。** Mock `AsyncOpenAI`，断言 JSON Mode、`max_retries=0`、模型切换只改变 `LLM_*` 配置；认证/4xx 为永久错误，连接/超时/限流/5xx 为可重试错误，非法 JSON/Pydantic 动作为 `RESEARCH_INVALID_RESPONSE`；所有错误消息不含 Mock 密钥。无 usage 时返回 `None` 而非 0。
- [ ] **步骤 5：运行调用 RED，再实现并运行 GREEN。** 实现 `request_research_action()`，只返回经 `ResearchAction.model_validate(json.loads(content), strict=True)` 验证的动作和用量；在 `finally` 关闭客户端。重跑动作测试、定向 Ruff/mypy。
- [ ] **步骤 6：写检查点与用量的失败测试。** MySQL `append_research_step(session, run_id, step, evidence, usage)` 每次重赋 `steps/evidence` 新列表并单独提交；`mark_research_running()` 只允许非终态且递增尝试数；`finish` 也记录决定。步骤摘要保存该次安全动作、来源 ID 与各分项用量（未知为 `NULL`），不保存原始模型响应。模型 usage 任一次未知时对应分项与总量保持 `NULL`；零次 Embedding 的用量是 0，而非未知。终态重投和已有步骤恢复不再次调用工具；如果最后的检查点是 `finish`，恢复时直接进入报告阶段，不能继续请求动作。
- [ ] **步骤 7：运行检查点 RED，再实现并运行 GREEN。** `.venv\Scripts\python.exe -m pytest tests/integration/db/test_research.py tests/unit/services/test_research_agent.py -q`。循环从已保存 `steps` 的数量继续，每次最多一个动作；`read_product/search_knowledge` 使用任务 2 的函数；完成结果在短事务持久化后才进入下一轮；达到动作或证据上限即返回“待生成报告”，由任务 4 完成终态。用量累加从创建时的 0 开始，任一未知值将该分项置为 `NULL`，`total_tokens` 只在所有分项已知时计算。
- [ ] **步骤 8：写 Worker 的失败测试。** 模拟 Redis/Engine/Session/模型/Chroma，验证 `acks_late`、同 `run_id` 锁、锁未取得不运行、锁 TTL 至少覆盖 `max_actions × (LLM 超时 + Embedding 超时 + 检索余量) + 报告超时 + 安全余量`、资源在 `finally` 关闭、可重试错误最多额外两次、永久错误立即标记失败、数据库持续不可用时不伪造已保存状态。
- [ ] **步骤 9：运行 Worker RED，再实现并运行 GREEN。** `run_research_attempt()` 创建并负责关闭 Redis 和 Engine；锁内调用动作循环；`run_research_task()` 用 `asyncio.run` 桥接 Celery，`task.retry(exc=安全错误, countdown=2**retries, throw=False)`；任务名固定为 `app.tasks.research.run_research`，`max_retries=2`、`acks_late=True`。在 `celery_app.py` 的 `include` 注册模块。
- [ ] **步骤 10：任务 3 验证、教程与提交。** 运行配置、Agent、Worker 与 MySQL 测试、定向 Ruff/mypy、`git diff --check`。中文教程解释每次模型调用和工具调用的顺序、JSON Mode 与本地校验的差别、检查点恢复、短事务、锁 TTL、资源所有权、至少一次投递可能重复计费的窗口及真实排错。精确提交任务 3 文件，提交信息 `feat: add bounded research agent worker`。

  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/core/test_config.py tests/unit/services/test_research_agent.py tests/unit/tasks/test_research_task.py tests/integration/db/test_research.py -q
  .venv\Scripts\ruff.exe check backend/app/core/config.py backend/app/schemas/research.py backend/app/services/research.py backend/app/services/research_agent.py backend/app/tasks/research.py backend/app/celery_app.py tests/unit/core/test_config.py tests/unit/services/test_research_agent.py tests/unit/tasks/test_research_task.py tests/integration/db/test_research.py
  .venv\Scripts\mypy.exe backend/app/core/config.py backend/app/schemas/research.py backend/app/services/research.py backend/app/services/research_agent.py backend/app/tasks/research.py tests/unit/core/test_config.py tests/unit/services/test_research_agent.py tests/unit/tasks/test_research_task.py tests/integration/db/test_research.py
  git diff --check
  git add -- backend/app/core/config.py backend/app/schemas/research.py backend/app/services/research.py backend/app/services/research_agent.py backend/app/tasks/research.py backend/app/celery_app.py tests/unit/core/test_config.py tests/unit/services/test_research_agent.py tests/unit/tasks/test_research_task.py tests/integration/db/test_research.py
  git diff --cached --name-only
  git diff --cached --check
  git commit -m "feat: add bounded research agent worker"
  ```

---

### 任务 4：结构化报告、引用校验和阶段验收

**交付内容：** 证据充分时形成经校验的结构化报告；证据不足时生成确定性缺口结果；无效来源安全失败。接口、迁移、完整回归和中文学习文档均有实际验收记录。

**涉及文件：**
- 修改：`backend/app/schemas/research.py`、`backend/app/services/research_agent.py`、`backend/app/services/research.py`、`backend/app/tasks/research.py`、`backend/app/api/v1/research.py`、`README.md`、`.env.example`
- 新建：`tests/unit/services/test_research_report.py`
- 修改：`tests/unit/services/test_research_agent.py`、`tests/unit/tasks/test_research_task.py`、`tests/api/test_research.py`、`tests/integration/db/test_research.py`
- 仅本地：`docs/learning/phase-6-task-4-report-acceptance.md`

**接口契约：**
- 依赖：任务 1～3 的持久化行、证据注册表和动作循环。
- 提供：`ResearchReport`、`ResearchFinding`、`ResearchRecommendation`、`build_insufficient_report()`、`validate_report_sources()`、`request_research_report()`、`mark_research_success()`；GET 详情返回程序填充的完整引用。
- `ResearchReport` 包含 `outcome: Literal["supported", "insufficient_evidence"]`、`summary: str`、`findings: list[ResearchFinding]`、`recommendations: list[ResearchRecommendation]`、`evidence_gaps: list[str]`；`ResearchFinding` 是 `claim/source_ids`，`ResearchRecommendation` 是 `action/reason/source_ids`。模型输出只允许 `supported`。

- [ ] **步骤 1：写报告 Schema 与引用失败测试。** `supported` 的发现最多 10、建议最多 5、缺口最多 5；摘要/文本均设置有限长度。每条发现和建议至少引用一条本次知识库证据，可额外引用商品；来源 ID 不在注册表、重复 ID、仅引用商品、不可信模型坐标，均不能生成成功报告。

  ```python
  def test_report_rejects_unregistered_source() -> None:
      report = ResearchReport(
          outcome="supported",
          summary="有来源的摘要",
          findings=[
              ResearchFinding(
                  claim="竞品价格更低",
                  source_ids=["kb:99:document:1:chunk:0"],
              )
          ],
          recommendations=[],
          evidence_gaps=[],
      )
      registered = [
          ResearchEvidence(
              source_id="product:7:snapshot",
              source_type="product",
              product_id=7,
              text="商品快照",
          ),
          ResearchEvidence(
              source_id="kb:12:document:1:chunk:0",
              source_type="knowledge",
              knowledge_base_id=12,
              document_id=1,
              chunk_id="document:1:chunk:0",
              chunk_index=0,
              original_name="竞品.pdf",
              page_number=1,
              text="已核对的资料",
              distance=0.12,
          ),
      ]
      with pytest.raises(ResearchCallError):
          validate_report_sources(report, registered)
  ```

- [ ] **步骤 2：运行报告 RED。** `.venv\Scripts\python.exe -m pytest tests/unit/services/test_research_report.py -q`；预期报告函数尚不存在。
- [ ] **步骤 3：实现报告 Schema、来源校验和确定性缺口结果。** `ResearchReport` 仅接受 `outcome="supported"` 的模型结果；`build_insufficient_report()` 返回 `outcome="insufficient_evidence"`、空发现/建议和明确证据缺口。`validate_report_sources()` 只接受本次 `run.evidence` 中的唯一 ID，引用详情由程序用登记的 `original_name/page_number/chunk_id/excerpt/distance` 填充，忽略模型提供的来源描述。无商品快照工具结果或无可信知识库证据时，不调用报告模型。
- [ ] **步骤 4：写模型报告调用的失败测试。** Mock `AsyncOpenAI`，验证系统规则与不可信数据分离、JSON Mode、无效格式/伪造引用归类 `RESEARCH_INVALID_RESPONSE`、连接/超时/限流/5xx 可重试、密钥和原始响应不进入数据库/日志；缺失 usage 保持未知。
- [ ] **步骤 5：运行调用 RED，再实现报告调用与终态。** `request_research_report()` 使用现有 `LLM_*`，在 `finally` 关闭客户端；在动作循环结束后调用。`mark_research_success()` 仅从 `running` 转 `success` 并保存经校验 JSON；`mark_research_failure()` 只保存稳定码/消息且保留已提交检查点。终态不再调用模型。运行 `tests/unit/services/test_research_report.py` 和相关 Worker/MySQL 测试至 GREEN。
- [ ] **步骤 6：补齐端到端故障矩阵。** API 测试覆盖三角色权限、配置缺失、Broker 故障及跨商品 ID；MySQL/Worker 测试覆盖成功、证据不足成功、无效引用失败、可重试耗尽、终态重投、用量已知/未知、商品后来修改仍显示历史快照。对 `research_runs` 返回内容断言不含原始异常和密钥。
- [ ] **步骤 7：更新配置示例和 README。** `.env.example` 只增加 `RESEARCH_MAX_ACTIONS=4` 与 `RESEARCH_MAX_EVIDENCE=12`，密钥示例保持空。README 说明三个接口、管理员预先上传资料的前置条件、MySQL/Redis/Celery/Chroma 启动与 `0005` 迁移、模型切换位置、最大调用次数/费用风险、证据局限、状态查询及不提供实时互联网研究；不得读取 `.env`。
- [ ] **步骤 8：运行迁移和全量质量门禁。** 以下迁移 `current` 应到 `0005`。用户未跟踪练习测试如果继续失败，报告原样全量结果并另跑不包含该文件的工程测试，准确区分两者；不得修改该练习文件以制造“全绿”。

  ```powershell
  .venv\Scripts\alembic.exe -x database=test upgrade head
  .venv\Scripts\alembic.exe -x database=test current
  .venv\Scripts\python.exe -m pytest -q
  .venv\Scripts\python.exe -m pytest -q --ignore=tests/unit/models/test_product_practice.py
  .venv\Scripts\ruff.exe check .
  .venv\Scripts\mypy.exe backend tests scripts
  git diff --check
  ```
- [ ] **步骤 9：完成四份本地中文教程并核对安全边界。** 任务 4 教程包含运行流程图、每个文件/类/函数职责、为何按此顺序编写、关键代码逐行解释、标准库/第三方/已有项目代码的来源、真实 RED/GREEN、迁移和质量门禁输出、错误与修复、面试口述及未执行的付费人工验收清单。回看前三份教程是否覆盖最终代码与真实排错。检查无密钥、原始响应、未授权外部调用，也不暂存教程。
- [ ] **步骤 10：精确提交并准备独立复核。** 仅暂存本任务工程文件，运行 `git diff --cached --name-only`、`git diff --cached --check`，提交 `feat: complete controlled research reports`。请求一次整分支独立代码复核，重点检查上述五类输入、事务/锁/重试/引用/费用边界；重要问题用新的失败测试修复。无用户单独批准，不进行付费真实调用、推送或合并。

  ```powershell
  git add -- backend/app/schemas/research.py backend/app/services/research_agent.py backend/app/services/research.py backend/app/tasks/research.py backend/app/api/v1/research.py README.md .env.example tests/unit/services/test_research_report.py tests/unit/services/test_research_agent.py tests/unit/tasks/test_research_task.py tests/api/test_research.py tests/integration/db/test_research.py
  git diff --cached --name-only
  git diff --cached --check
  git commit -m "feat: complete controlled research reports"
  ```

## 计划自检

- 设计第 1～10 节分别由任务 1 的持久化/API、任务 2 的工具、任务 3 的循环/Worker、任务 4 的报告/验收覆盖。
- 四个任务均有独立 RED/GREEN、接口产出、中文教程和精确提交；外部模型与 Chroma 的自动化测试均使用模拟对象。
- 五项重点复核各有对应任务测试；报告来源必须由程序填充；真实付费验收与合并仍是单独授权事项。
