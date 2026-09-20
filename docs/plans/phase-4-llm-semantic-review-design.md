# 阶段 4：LLM Listing 语义审核设计

## 1. 阶段目标

阶段 4 在阶段 3 的商品库和确定性 Listing 检查之上，增加可追溯的 LLM 语义审核。Admin、Operator 可以为商品发起异步审核，三种角色都可以查看审核历史和结果。审核记录保存到 MySQL，包含请求时商品快照、模型身份、提示词版本、评分、问题、改写建议、Token 用量和安全错误摘要。

本阶段固定拆分为 4 个 Task，每个 Task 5 个学习单元。实现继续复用现有 FastAPI、Pydantic、SQLAlchemy、Alembic、MySQL、Redis、Celery、JWT、RBAC、统一异常和测试基础设施。

学习优先级是先理解一条完整的真实调用链，再增加必要的生产边界。代码只实现一个 OpenAI-compatible 调用路径，不为尚未出现的协议差异创建 Provider 接口、工厂或策略体系。

## 2. 范围边界

### 2.1 本阶段实现

- LLM 审核 ORM Model、Alembic 迁移和 MySQL 历史记录；
- 请求时商品快照，保证历史结果可追溯；
- OpenAI-compatible 配置和 Python SDK 调用；
- 固定版本 Prompt、提示词注入边界和 JSON 输出；
- Pydantic 对外部模型输出的二次校验；
- Celery 异步执行、Redis 单任务锁、有限重试和状态迁移；
- Admin、Operator 发起审核，三种角色查看历史和结果；
- 同一商品只允许一个活动审核；
- OpenAI、Qwen、DeepSeek 等兼容服务的配置切换说明；
- 单元测试、数据库集成测试、API 测试和一次人工真实调用验收。

### 2.2 本阶段不实现

- RAG、向量数据库、Embedding 或知识库；
- Agent、工具调用、MCP 或联网搜索；
- SSE、WebSocket、流式 Token 输出或前端；
- 图片、多模态或商品图片审核；
- 自动修改正式商品数据；
- 平台专属政策库或 Amazon、淘宝等平台规则爬取；
- Prompt 在线管理后台、A/B 实验或自动评测平台；
- 批量审核全部商品；
- 对所有供应商协议提前开发独立适配器；
- 保存 API Key、模型思维链、未经验证的原始响应或内部异常堆栈。

## 3. 方案选择

### 3.1 采用的方案

采用 `OpenAI-compatible SDK + Celery + MySQL + Pydantic`：

```text
HTTP 创建审核记录
  → Celery 投递 review_id
  → Worker 读取 MySQL 快照
  → OpenAI-compatible Chat Completions
  → JSON 解析和 Pydantic 校验
  → MySQL 保存最终结果
```

选择原因：

- HTTP 不等待模型响应，避免超时和长连接占用；
- 复用阶段 2 已有 Celery 与 Redis，不新增消息系统；
- MySQL 记录不会随 Celery Result Backend 过期；
- Chat Completions 是 OpenAI-compatible 服务共同支持度较高的接口；
- JSON Mode 保证响应是 JSON，Pydantic 再保证业务结构；
- 供应商、Base URL、模型和密钥全部来自配置，切换模型不修改业务代码。

OpenAI 官方优先推荐 Responses API，但 Chat Completions 仍受支持；本项目为兼容 Qwen、DeepSeek 等第三方服务，选择兼容面更广的 Chat Completions。OpenAI 与 SiliconFlow 都提供 JSON 输出能力，但外部服务仍可能返回截断或业务结构不合法的 JSON，因此必须保留本地校验。

### 3.2 不采用的方案

不采用同步 HTTP 审核。它更少代码，但模型延迟、限流和重试会长期占用 Web 请求，不适合真实业务。

不采用每个供应商一个 Provider 类。当前供应商都通过相同的 OpenAI-compatible 参数工作，只有一个实现的抽象层不能降低复杂度。当真实服务出现不兼容请求或响应时，再以测试证明需要适配器。

不使用 Celery Result Backend 作为业务结果存储。它具有过期时间，只适合任务基础设施状态，不适合审核历史。

## 4. 配置与依赖

新增直接依赖：

- `openai>=2.0,<3.0`：提供类型化 OpenAI-compatible Chat Completions 客户端和异常类型。

阶段 0 的 `SILICONFLOW_*` 占位配置改成通用配置：

```text
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=60
LLM_MAX_OUTPUT_TOKENS=2000
```

配置规则：

- `llm_provider` 只用于审计显示，不控制代码分支；
- `llm_base_url` 默认为 OpenAI 官方兼容地址；
- `llm_model` 不提供时间敏感的代码默认值，运行真实审核时必须配置；
- `llm_api_key` 使用 `SecretStr | None`，不得出现在 `repr`、日志、响应或数据库；
- `llm_timeout_seconds` 必须大于 0；
- `llm_max_output_tokens` 必须大于 0；
- 自动化测试不读取真实 `.env`，也不请求真实模型。

切换供应商只修改环境变量。例如 SiliconFlow 使用它的兼容 Base URL 和模型 ID；其他 Qwen、DeepSeek 服务使用对应服务商公开的兼容地址与模型 ID。模型必须支持 Chat Completions 和 JSON Mode。

## 5. 审核数据模型

正式表名为 `listing_semantic_reviews`。

| 字段 | 数据库类型 | 规则 |
|---|---|---|
| `id` | 整数 | 自增主键 |
| `product_id` | 整数外键 | 指向 `products.id`，索引 |
| `requested_by_id` | 整数外键 | 指向 `users.id`，索引 |
| `celery_task_id` | `VARCHAR(255)` | 可空、唯一，投递成功后写入 |
| `status` | `VARCHAR(20)` Enum | `pending/running/success/failure`，索引 |
| `product_snapshot` | `JSON` | 请求时的固定商品输入 |
| `provider` | `VARCHAR(50)` | 发起时的配置值 |
| `model` | `VARCHAR(255)` | 发起时的模型 ID |
| `prompt_version` | `VARCHAR(50)` | 固定 Prompt 版本 |
| `score` | 整数 | 成功时 0～100，否则为空 |
| `dimension_scores` | `JSON` | 五项固定维度分数 |
| `summary` | `TEXT` | 成功时的中文摘要 |
| `issues` | `JSON` | 结构化问题列表 |
| `rewrite` | `JSON` | 标题、描述和卖点改写 |
| `prompt_tokens` | 整数 | 供应商返回时保存，否则为空 |
| `completion_tokens` | 整数 | 供应商返回时保存，否则为空 |
| `total_tokens` | 整数 | 供应商返回时保存，否则为空 |
| `attempt_count` | 整数 | 实际开始模型调用的次数，默认 0 |
| `error_code` | `VARCHAR(50)` | 失败时的稳定安全错误码 |
| `error_message` | `VARCHAR(255)` | 失败时的安全中文摘要 |
| `started_at` | 时间 | 首次进入 running 时写入 |
| `completed_at` | 时间 | 进入终态时写入 |
| `created_at` | 时间 | 数据库生成 |
| `updated_at` | 时间 | 数据库生成并在状态更新时刷新 |

不配置 ORM Relationship。当前调用只需要明确的外键 ID，关系属性不会减少查询或代码数量。

`product_snapshot` 保存：

```text
sku, title, description, bullet_points,
brand, category, price, currency, is_active
```

`Decimal` 在 JSON 快照中保存为十进制字符串，避免二进制浮点误差。

快照序列化后最多 20000 个字符。阶段 3 允许保存较长描述，而 LLM 调用会产生真实 Token 成本，因此超过上限的商品不能发起审核，返回 422 `SEMANTIC_REVIEW_INPUT_TOO_LARGE`。数据不做静默截断，避免审核结论与数据库原文不一致。

## 6. 状态机与并发

允许的状态迁移：

```text
PENDING → RUNNING → SUCCESS
                  → FAILURE
PENDING → FAILURE   # Broker 投递失败或运行配置缺失
```

终态 `SUCCESS` 和 `FAILURE` 不再迁移。Worker 收到已处于终态的重复任务时直接返回，不再次调用模型。

创建审核时使用 `SELECT ... FOR UPDATE` 锁定对应 Product 行，然后查询该商品是否已有 `PENDING` 或 `RUNNING` 记录。这样同一数据库上的并发请求会串行完成检查和创建；发现活动审核时返回 409 `SEMANTIC_REVIEW_ALREADY_ACTIVE`。

Worker 使用现有 `redis_lock()`，锁 Key 为 `marketmind:lock:semantic-review:{review_id}`。未获得锁的重复 Worker 不执行模型调用。

Celery 任务开启延迟确认与 Worker 丢失重投。网络调用本质上只能做到至少一次：如果模型已经返回、但 Worker 在提交 MySQL 前崩溃，重投后可能再次产生一次模型费用。本阶段通过 Redis 锁和终态检查缩小窗口，不声称实现外部 API 的 exactly-once。

## 7. 审核输出契约

固定输出包含：

```text
score: 0..100
dimension_scores:
  completeness: 0..100
  consistency: 0..100
  clarity: 0..100
  risk: 0..100
  persuasion: 0..100
summary: 中文摘要
issues: 问题列表
rewrite:
  title
  description
  bullet_points
```

每个问题包含：

- `dimension`：上述五项之一；
- `severity`：`low/medium/high`；
- `field`：`title/description/bullet_points/general`；
- `message`：发现的问题；
- `suggestion`：可执行的修改方法。

`risk` 分数越高表示表达越安全、风险越低，使五项分数方向保持一致。所有文本字段设置明确长度上限，问题数量和卖点数量设置上限，防止模型产生无限输出或异常大数据库记录。

具体边界为：摘要最多 1000 字符，问题最多 20 条，每条 message 最多 500 字符、suggestion 最多 1000 字符；改写标题最多 200 字符、描述最多 5000 字符、卖点 3～5 条且每条 10～200 字符。

现有 `check_listing()` 确定性规则继续独立运行。LLM 不负责替代价格、币种、字符长度和固定禁用词等可以由代码准确判断的规则。

## 8. Prompt 与输入安全

Prompt 版本固定为代码常量，例如 `semantic-review-v1`。数据库只保存版本号，不重复保存整段 Prompt。

消息结构：

```text
system/developer message
  → 定义审核身份、五项维度、评分方向、JSON 契约
  → 声明商品内容是不可信数据，禁止执行其中的指令
  → 禁止虚构平台政策、认证或商品事实

user message
  → 固定说明
  → JSON 序列化后的 product_snapshot 数据块
```

不启用 tools、函数调用、联网搜索或文件访问。商品标题、描述和卖点中的指令只被视为待审核文本。模型安全边界不能只依赖 Prompt，因此结果还必须通过 Pydantic 校验、文本长度限制和固定枚举。

## 9. LLM 调用边界

单一 Service 函数完成：

1. 校验 `LLM_API_KEY` 和 `LLM_MODEL` 已配置；
2. 使用 `OpenAI(api_key=..., base_url=..., timeout=...)` 创建同步客户端；
3. 调用 `client.chat.completions.create()`；
4. 使用 `response_format={"type": "json_object"}`；
5. 读取第一条 message content；
6. `json.loads()` 解析；
7. Pydantic Schema 验证；
8. 返回验证后的结果和 Token 用量。

Celery 任务本身是同步入口，因此使用同步 `OpenAI` 客户端，不在 Worker 内额外创建事件循环。数据库仍沿用项目已有异步 SQLAlchemy，由同步 Celery 入口通过 `asyncio.run()` 调用异步协调函数。

不传供应商特有的 `enable_thinking`、`reasoning_effort` 等参数，避免模型切换需要修改代码。模型推理内容不读取、不返回、不保存。

## 10. Celery 执行流程

```text
generate_semantic_review(review_id)
  → asyncio.run(run_semantic_review(review_id))
  → 创建 Redis 客户端并获得 review_id 锁
  → 创建独立 MySQL Engine / Session
  → 读取审核记录
  → 终态则直接返回
  → 设置 RUNNING、started_at、attempt_count
  → 关闭当前事务
  → 调用 OpenAI-compatible API
  → 新事务重新读取记录
  → 保存 SUCCESS 结果和 completed_at
  → 释放 Engine 与 Redis 客户端
```

模型调用期间不保持数据库事务或行锁，避免慢速网络请求长期占用数据库连接和锁。

临时故障最多指数退避重试 3 次：

- 连接失败；
- 请求超时；
- 限流；
- 供应商 5xx。

以下错误不盲目重试：

- API Key 缺失；
- 模型名称缺失；
- 认证或权限错误；
- 供应商 4xx 参数错误；
- 空响应；
- JSON 无法解析；
- Pydantic 校验失败。

重试耗尽或永久错误进入 `FAILURE`。日志只记录 `review_id`、安全错误分类和重试次数，不记录密钥、完整请求、商品全文或供应商原始响应。

## 11. API 与权限

新增接口：

```text
POST /api/v1/products/{product_id}/semantic-reviews
GET  /api/v1/products/{product_id}/semantic-reviews
GET  /api/v1/products/{product_id}/semantic-reviews/{review_id}
```

权限：

| 操作 | Admin | Operator | Analyst |
|---|---:|---:|---:|
| 发起审核 | 允许 | 允许 | 禁止 |
| 查看历史 | 允许 | 允许 | 允许 |
| 查看结果 | 允许 | 允许 | 允许 |

POST 返回 202，包含 `review_id`、`task_id` 和 `status`。创建记录成功但 Broker 投递失败时，记录改为 FAILURE，接口返回 503 `SEMANTIC_REVIEW_DISPATCH_FAILED`。

列表接口使用 `page`、`page_size`，按 `id` 降序返回该商品审核历史。详情接口同时校验 `product_id` 与 `review_id`，避免通过错误商品路径读取其他商品审核。

读取接口只查询 MySQL，不调用 Celery Result Backend，也不触发模型调用。

## 12. 错误契约

新增 HTTP 业务错误码：

- `SEMANTIC_REVIEW_NOT_FOUND`：审核不存在，404；
- `SEMANTIC_REVIEW_ALREADY_ACTIVE`：商品已有活动审核，409；
- `SEMANTIC_REVIEW_INPUT_TOO_LARGE`：商品快照超过 20000 字符，422；
- `SEMANTIC_REVIEW_CONFIG_MISSING`：真实运行配置缺失，503；
- `SEMANTIC_REVIEW_DISPATCH_FAILED`：Broker 投递失败，503。

持久化任务错误码：

- `REVIEW_CONFIG_ERROR`；
- `REVIEW_PROVIDER_AUTH_ERROR`；
- `REVIEW_PROVIDER_REQUEST_ERROR`；
- `REVIEW_PROVIDER_UNAVAILABLE`；
- `REVIEW_INVALID_RESPONSE`；
- `REVIEW_INTERNAL_ERROR`。

持久化 `error_message` 只包含预定义中文摘要，不保存 `str(exc)`。API 继续复用统一 `AppError` 和 request_id 响应。

## 13. 文件职责

计划使用以下最小文件边界：

```text
backend/app/models/semantic_review.py
  审核状态 Enum 与 ORM Model

backend/app/schemas/semantic_review.py
  快照、模型输出、创建响应、详情和分页 Schema

backend/app/services/semantic_reviews.py
  快照、Prompt、LLM 调用、创建与查询数据库操作

backend/app/tasks/semantic_review.py
  Worker 生命周期、锁、重试和状态持久化

backend/app/api/v1/semantic_reviews.py
  HTTP、RBAC、任务投递和安全错误

alembic/versions/0003_create_listing_semantic_reviews.py
  数据库迁移
```

同时最小修改：

```text
pyproject.toml
.env.example
README.md
backend/app/core/config.py
backend/app/models/__init__.py
backend/app/celery_app.py
backend/app/main.py
tests/conftest.py
```

不创建 Repository、Provider 接口、Provider 工厂、Prompt 管理器或通用工作流引擎。

## 14. 测试策略

### 14.1 单元测试

- 通用 LLM 配置、安全默认值和 SecretStr；
- 商品快照的 Decimal 字符串；
- 输出分数、枚举、数量和长度边界；
- Prompt 包含版本、数据分隔和注入防护说明；
- OpenAI-compatible 请求参数；
- 正常 JSON、空内容、损坏 JSON和 Schema 错误；
- Token 用量存在和缺失；
- SDK 异常到内部错误分类。

所有 SDK 测试使用 Mock，不调用真实网络，不消耗 Token。

### 14.2 数据库集成测试

- 审核表字段、外键和 Enum；
- 创建记录时保存商品快照、请求人、供应商和模型；
- 商品更新后旧快照不变化；
- 同一商品已有活动审核时返回冲突；
- 成功或失败后允许再次创建；
- 历史分页按 ID 降序；
- review_id 必须属于路径中的 product_id；
- 测试清理顺序为审核记录、商品、用户。

数据库测试继续只允许连接 `marketmind_test`。

### 14.3 Celery 测试

- 未获得 Redis 锁时不调用模型；
- 已完成任务重复投递时不调用模型；
- 正常状态从 pending 到 running 到 success；
- 成功保存结构化结果和 Token 用量；
- 临时错误触发有限重试；
- 永久错误直接失败；
- 失败结果不泄露 API Key、连接串或原始响应；
- Engine、Session 和 Redis 客户端始终释放。

### 14.4 API 测试

- Admin、Operator 可以发起，Analyst 返回 403；
- 三种角色都可以查看历史和详情；
- 未登录返回 401；
- 商品或审核不存在返回 404；
- 活动审核冲突返回 409；
- Broker 故障返回 503 并保存失败记录；
- POST 返回 202 和稳定响应结构；
- 查询只读 MySQL，不请求 LLM。

### 14.5 人工验收

- 在 `.env` 配置一个真实 OpenAI-compatible 服务；
- 只选一个测试商品发起一次审核，控制实际费用；
- Worker 成功处理任务；
- MySQL 保存快照、模型、结果和 Token 用量；
- 修改商品后重新审核，形成第二条历史；
- 切换另一个兼容模型，只改配置并重启 Worker；
- 验证历史记录保留各自的 provider 和 model；
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过。

## 15. Task 与学习单元

### Task 1：审核领域模型与 MySQL 持久化（5 个单元）

1. 审核状态 Enum、身份字段和外键；
2. 快照、结果、Token、错误和时间字段；
3. Alembic 审核表迁移；
4. 创建、读取、分页 Service；
5. 活动审核并发约束和数据库集成验收。

### Task 2：Prompt 与 OpenAI-compatible 调用（5 个单元）

1. 通用 LLM 配置、依赖和密钥保护；
2. 商品快照、模型输出、详情和分页 Pydantic Schema；
3. 商品快照、Prompt 版本和注入防护；
4. Chat Completions、JSON 解析和 Pydantic 校验；
5. 异常分类、Token 用量和 Mock 验收。

### Task 3：Celery 语义审核任务（5 个单元）

1. Celery 任务注册与同步入口；
2. Worker 独立 MySQL Session 和审核状态迁移；
3. Redis 单审核锁和终态幂等；
4. 临时错误重试与永久错误持久化；
5. Worker 资源释放和故障验收。

### Task 4：审核 API 与阶段验收（5 个单元）

1. 发起审核 API 与 202 响应；
2. 历史分页和详情 API；
3. RBAC、404、409 和 503；
4. OpenAI、Qwen、DeepSeek 配置切换和人工调用；
5. 全量回归、README、学习问答和阶段 4 总流程图。

## 16. 学习文档规则

每个 Task 开始时生成一份本地中文教程，完成后在同一文件追加实际参考实现和排错记录：

```text
docs/learning/phase-4-task-1-semantic-review-model.md
docs/learning/phase-4-task-2-llm-client-prompt.md
docs/learning/phase-4-task-3-celery-review-task.md
docs/learning/phase-4-task-4-review-api-acceptance.md
```

教程保持未跟踪，不进入 Git。每份教程必须包含：

- 本 Task 的业务目标和学习目标；
- 新建、修改和复用文件的完整职责；
- RED、GREEN、重构和验收的真实顺序；
- 每个代码块的依赖来源：标准库、第三方包、已有项目代码或本阶段代码；
- 所有影响执行的代码行为什么存在；
- 函数输入、返回值、调用者和被调用者；
- 数据、事务、任务状态和异常的流动；
- 方法与框架功能的实现原理；
- 为什么按当前依赖顺序编写；
- 实际测试失败、根因和修复；
- 可迁移场景、常见错误和面试口述。

重复 import、括号和纯格式行集中解释，不机械复制相同文字；所有业务分支、数据转换、调用、事务和错误处理逐行解释。

## 17. Git 与安全边界

- 阶段分支为 `phase/4-llm-semantic-review`；
- 每个 Task 独立通过测试后提交；
- 使用精确 `git add` 文件列表，禁止 `git add .` 和 `git add -A`；
- 不修改、删除、还原、暂存或提交已有本地学习文件与 `tests/unit/models/test_product_practice.py`；
- 不读取、输出或提交 `.env`；
- 测试和文档不包含真实 API Key；
- 自动化测试不调用收费模型；
- 未经阶段验收不合并 main，不删除阶段分支。

## 18. 阶段完成条件

- 4 个 Task、每个 Task 5 个单元全部完成；
- 异步审核、历史持久化、快照和状态迁移与本文一致；
- 活动审核并发保护与 Worker 重投边界经过测试；
- 外部模型输出经过 JSON 和 Pydantic 双重校验；
- OpenAI-compatible 配置可以在不修改业务代码的情况下切换；
- Admin、Operator、Analyst 权限与本文一致；
- 自动化测试不产生模型费用；
- 至少完成一次受控的真实模型人工验收；
- 不泄露密钥、思维链、原始异常或敏感连接信息；
- 教学教程完整记录代码组成、编写思路、执行原理和真实排错；
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过；
- 用户验收后才允许合并和推送 main。

## 19. 设计依据

- OpenAI Chat Completions 与 Python SDK：<https://pypi.org/project/openai/>；
- OpenAI 结构化输出与 JSON Mode：<https://developers.openai.com/zh-Hans/api/docs/guides/structured-outputs?api-mode=responses>；
- SiliconFlow OpenAI-compatible Chat Completions：<https://docs.siliconflow.cn/docs/api/chat-completions-post>；
- SiliconFlow JSON Mode：<https://docs.siliconflow.cn/docs/userguide/guides/json-mode>。

外部服务的可用模型、价格和参数支持会变化，真实部署前以所选服务商当时的官方文档为准。业务代码只依赖本文明确的兼容契约，不依赖某个时间点的模型名称或价格。
