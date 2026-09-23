# 单元 6：受控 Agent 与可追溯竞品研究设计

**状态：** 待用户审阅正式文档；本文件不是实施许可。

## 1. 目标与已确认边界

MarketMind AI 的单元 6 要让运营人员基于平台商品和**管理员已经上传**的竞品资料，发起一项异步研究，获得可复查来源的对比发现与行动建议。用户希望先易于学习和解释，再达到真实项目而非演示程序的质量：代码、状态、费用、故障和证据都应能在面试中讲清楚。Agent 必须能在有限范围内决定下一步读取商品还是检索资料，而不能只是固定的单轮 RAG 总结。

已确认：

- 输入只来自现有 `products` 与单元 5 的知识库；不自动联网搜索、抓取网页或读取任意文件。
- 一个研究选定一个商品、一个研究目标和 1～3 个知识库。知识库须有 `ready` 文档；其 Embedding 配置须与当前配置一致。
- 使用现有 FastAPI、MySQL、Redis、Celery、OpenAI-compatible SDK 与 Chroma 边界；不加入 LangChain、LangGraph、MCP 或通用工作流框架。
- 采用有上限的模型动作循环。模型只能选 `read_product`、`search_knowledge`、`finish`；程序严格校验和执行，最多 4 次动作决定。
- MySQL 保存任务状态、商品快照、检查点、证据、报告与 Token 用量。报告中的事实与建议要引用本次程序核验的证据；证据不足时说明缺口，不补造竞品事实。
- Admin、Operator 可发起研究；Admin、Operator、Analyst 都能查看团队共享的研究历史。同一商品同时至多一个活动研究。
- 每阶段四个 Task，TDD；每个 Task 生成本地中文学习文档，说明代码职责、编写顺序、逐段/关键行原理、真实错误与验收。四份学习文档不加入工程提交。
- 自动化测试模拟模型与 Chroma，不产生付费调用；真实付费验收需单独批准。未经用户验收，不合并或推送。

当前 Git 基点为单元 5 提交 `8fd6ee7`。单元 5 尚未合并 `main`；单元 6 分支从该提交派生，不能将单元 6 的提交误认为可单独从 `main` 运行。用户原有的本地学习文档与 `tests/unit/models/test_product_practice.py` 必须保持原样、不得暂存。

## 2. 方案选择与排除

| 方案 | 优点 | 不足 | 结论 |
|---|---|---|---|
| 固定“检索后一次总结” | 代码少、费用低 | 模型无法基于中间证据决定继续查什么，无法体现 Agent | 不采用 |
| **受控动作循环** | 真实展示规划、工具执行、证据反馈和停止条件；仍可解释、可测试 | 需明确动作、费用和检查点边界 | **采用** |
| 通用 Agent/工作流框架 | 工具生态丰富 | 引入目前没有用途的抽象、依赖和调试面；跨供应商行为更难核对 | 不采用 |

本设计不实现网页采集、自动搜索、任意 URL 访问、任意 Python/SQL 执行、动态工具注册、前端界面、SSE、MCP、多 Agent 协作、自动改写商品或自动发送报告。后续有真实需求再单独设计。所谓“Deep Research”指在**受控已上传证据**上迭代检索并生成可追溯报告，不暗示实时互联网覆盖。

## 3. 用户可见的业务流程

1. Admin 已将竞品公开资料或内部市场资料按单元 5 的流程上传至命名知识库，并等待至少一份文档 `ready`。
2. Admin/Operator 选择一个商品、1～3 个知识库并输入研究目标，例如“比较这款商品与已上传资料中的竞品定位，找出可验证的 Listing 改进机会”。
3. HTTP 层检查权限、输入、商品、知识库、配置和同商品活动任务；在短事务中保存商品快照和 `pending` 记录，投递 Celery，返回 `202`、`run_id`、`task_id`、状态。
4. Worker 获得该运行的 Redis 锁，转为 `running`。每一步从 MySQL 检查点恢复上下文，调用配置的模型取得一个严格 JSON 动作；只有程序认识的动作才执行。商品工具返回创建时的快照；知识库工具复用单元 5 的 Embedding、Chroma 和 MySQL `ready` 二次过滤。
5. 程序为每份证据分配自己的 `source_id`，限制总量、长度并在短事务中保存动作和结果。模型看得到证据，但不能决定真实文件名、页码或来源 ID 的含义。
6. 模型选择 `finish`，或达到 4 次决定的上限后，程序根据已保存证据请求结构化报告。每项事实和建议的来源 ID 都由程序对照本次证据注册表校验，再映射成文件、页码、Chunk 或商品快照坐标。
7. 无可靠知识库证据时直接生成“证据不足”的确定性结果，不调用报告生成 Chat。成功、证据不足和失败均保留历史；客户端用详情接口查询，不依赖会过期的 Celery Result Backend。

MySQL 读取事务在模型、Embedding、Chroma 网络调用之前结束。每个动作完成后独立提交检查点；不能把一次长研究包在一个 MySQL 事务里。

## 4. 数据模型与不变量

Alembic `0005` 新增 `research_runs` 一张表，不建立抽象工作流表。主要字段：

| 字段 | 类型/含义 |
|---|---|
| `id`, `product_id`, `requested_by_id` | 主键、商品和请求人的外键；按商品和状态建索引 |
| `goal` | 去空格后的研究目标，1～500 字符 |
| `knowledge_base_ids` | JSON 整数列表，1～3 个、互不重复，创建后不改 |
| `product_snapshot` | 请求时固定的可审计商品字段 JSON，避免商品后来修改影响旧报告 |
| `status` | `pending/running/success/failure`，只允许合法状态迁移 |
| `celery_task_id` | 投递回执，仅用于排查；业务状态仍以 MySQL 为准 |
| `provider`, `model`, `prompt_version` | 本次 Chat 配置与提示词版本；不保存密钥或可能含秘密的 Base URL |
| `steps` | 有界 JSON 列表：步骤号、已校验动作、参数摘要、来源 ID、时间；不保存模型思维链或原始响应 |
| `evidence` | 有界 JSON 列表：程序生成的来源 ID、来源类型、商品/知识库/文档/Chunk 坐标、页码、最多 1000 字符的证据文本及距离 |
| `report` | 成功或证据不足时的结构化 JSON；失败时为空，不保存未经校验的模型输出 |
| `prompt_tokens`, `completion_tokens`, `embedding_tokens`, `total_tokens` | 已知用量；某次调用缺少 usage 时，相应分项及无法完整计算的总量用 `NULL` 表示未知，不能把不完整总量误记为全部费用 |
| `attempt_count`, `error_code`, `error_message` | 任务尝试次数与安全错误摘要；禁止原始网络/数据库异常 |
| `started_at`, `completed_at`, `created_at`, `updated_at` | 运行和审计时间 |

创建时锁定 Product 行，再检查是否存在同商品的 `pending/running` 记录。这个串行化边界避免两个请求都通过“无活动研究”的检查。历史记录永久新增而不覆盖。`steps`、`evidence` 每次赋新列表后提交，避免 SQLAlchemy 对 JSON 原位修改不自动追踪的问题。成功/失败/证据不足后不再发起任何模型调用。

单元 5 的知识库目前没有删除接口，仍不可假设永远不变；报告引用使用**本次持久化的证据摘录和坐标**，历史页面不依赖当前 Chroma 是否还保有相同向量。

## 5. 输入、API 与权限

基础路径：`/api/v1/products/{product_id}/research-runs`。

| 方法/路径 | 权限 | 行为 |
|---|---|---|
| `POST /api/v1/products/{product_id}/research-runs` | Admin、Operator | 请求体 `goal`、`knowledge_base_ids`；校验后返回 `202` 与 `run_id/task_id/status` |
| `GET /api/v1/products/{product_id}/research-runs` | 三种角色 | 按创建时间倒序分页读取任务摘要 |
| `GET /api/v1/products/{product_id}/research-runs/{run_id}` | 三种角色 | 读取状态、步骤摘要、已验证报告/引用、用量和安全错误 |

三种角色只能读取指定商品下的研究；其他商品的 `run_id` 返回 404。未登录 401；无发起权限 403；商品或知识库不存在 404；同商品已有活动研究、知识库没有 `ready` 文档时 409；配置缺失或 Broker 不可用时 503。请求字段不合法由 Pydantic 返回 422。知识库团队共享，不按上传人隔离；请求人只用于审计。

发起前确认选中知识库的 Embedding provider、Base URL、model 都与当前 `EMBEDDING_*` 一致。不同向量空间不能在一次研究中混用；配置不一致时返回稳定配置错误，不能冒险检索。无需为研究复制原始上传文件。

## 6. 受控动作协议和工具边界

模型每次只返回一个 JSON 对象，Pydantic `extra="forbid"` 严格校验：

```json
{"action":"read_product"}
{"action":"search_knowledge","knowledge_base_id":12,"query":"竞品价格与差异化卖点"}
{"action":"finish"}
```

- `read_product` 只返回 `product_snapshot` 的白名单字段，登记 `product:{product_id}:snapshot` 来源；可以在模型对比前读取，但程序不会访问其他商品。
- `search_knowledge` 的知识库 ID 必须属于创建请求的 1～3 个 ID；查询文本 1～300 字符。调用单元 5 已存在的 `request_embeddings()` 和 `retrieve_chunks()`，先检查当前向量维度与该库记录一致，再只取该知识库、距离在 `RAG_MAX_DISTANCE` 内且 MySQL 状态为 `ready` 的前 3 个块。
- `finish` 不执行工具，进入报告阶段。若 4 次决定用尽，程序也强制结束循环。
- 任意其他动作、额外字段、无效 JSON、越界 ID、空查询或模型企图把文档文字当新系统指令，均不能变成工具调用；无效动作作为安全失败，不会“猜测”并执行。
- 同一个来源只登记一次。证据注册表最多 12 项，单项文本最多 1000 字符；超出上限停止新增证据并进入报告/缺口结果。`source_id` 由程序按固定规则产生，模型不可创建任意来源。
- 对工具结果、问题和商品字段都采用数据区与系统规则区分隔的 Prompt；模型不获得数据库连接、文件系统、浏览器、HTTP 客户端或 Python 执行能力。

允许模型选择下一步并不等于允许模型自由执行。程序中的三分支 dispatch 是唯一执行入口；没有动态 `eval`、反射调用或任意 SQL。

## 7. 报告契约与引用验证

报告由模型输出严格 JSON 并由 Pydantic 校验：

```json
{
  "outcome": "supported",
  "summary": "有证据支持的中文摘要",
  "findings": [
    {"claim": "一条可核对的竞品或差异发现", "source_ids": ["kb:12:document:7:chunk:0"]}
  ],
  "recommendations": [
    {"action": "一个运营动作", "reason": "与证据对应的理由", "source_ids": ["kb:12:document:7:chunk:0"]}
  ],
  "evidence_gaps": ["当前资料未覆盖的关键问题"]
}
```

`supported` 报告要求本次已登记商品快照和至少一条知识库证据；每条发现、建议都至少引用一个**本次检索到的知识库证据**，可以额外引用商品快照。报告中的 `source_ids` 必须全部在持久化证据注册表中且无重复；最终 API 的文件名、页码、Chunk ID、摘录、距离和商品坐标由程序填充，绝不从模型文字直接采信。文本长度和列表数量设上限（发现最多 10、建议最多 5、缺口最多 5），防止异常大响应。来源 ID 合法不等于结论语义正确，业务人员仍应核对重要结论。

若没有商品快照工具结果或可信知识库证据，程序写入 `outcome="insufficient_evidence"`、空发现/建议和明确的证据缺口，研究任务状态为 `success`，表示受控地完成而非系统故障；不请求最终报告模型。若模型有证据却提交不存在或不合规引用，任务进入 `failure`，记录安全的 `RESEARCH_INVALID_RESPONSE`，不把不可靠报告作为成功返回。报告是基于已上传资料的分析，不宣称覆盖实时市场。

## 8. 状态、可靠性和费用

状态迁移：`pending → running → success/failure`；Broker 投递失败可由 `pending → failure`。终态重投必须立即返回而不再调用模型。Worker 使用每项研究的 Redis 锁和 Celery `acks_late`；崩溃重投时从已提交的 `steps/evidence` 检查点恢复，不重复执行已记录的工具步骤。锁 TTL 应覆盖最多 4 次动作、Embedding 与一次报告调用的配置超时及安全余量；不能用短于预期运行时间的默认锁 TTL。

短事务只负责状态检查、步骤/证据检查点和终态写入。调用 Chat、Embedding 或 Chroma 时不持有 MySQL 事务。Chroma 客户端、OpenAI 客户端、数据库 Engine 和 Redis 客户端均由创建它们的边界负责关闭。索引任务可以和研究任务并行，但研究检索只接受已 `ready` 的文档。

网络断开、限流、服务端错误最多进行 2 次额外任务重试；认证失败、请求配置错误、无效动作或伪造引用不重试。错误码和消息必须来自固定安全映射，不保存 API Key、模型思维链、原始响应、堆栈或可能含连接串的异常。重试只复用已完成的检查点；如果进程在供应商**已处理调用但检查点尚未提交**时崩溃，仍可能重复计费，不能承诺绝对一次调用。

默认最多 4 次模型动作决定和 1 次最终报告生成，每次动作至多一次知识库 Embedding。复用 `LLM_MAX_OUTPUT_TOKENS`、`LLM_TIMEOUT_SECONDS`、`EMBEDDING_TIMEOUT_SECONDS`、`RAG_MAX_DISTANCE`；新增可调且有界的 `RESEARCH_MAX_ACTIONS=4`（2～8）和 `RESEARCH_MAX_EVIDENCE=12`（2～30），两个下限保证至少容纳商品与一条知识库证据。用量单独累积并记录，缺失 usage 保留未知；不根据可能变化的供应商价格猜算费用。没有实时全局/每日额度系统，调用者须在运维文档中自行控制启动次数。

## 9. 复用、文件边界与四个 Task

新代码按现有项目层次放置，不建 Repository、Provider 工厂或通用 Tool 接口：

| 位置 | 职责 |
|---|---|
| `alembic/versions/0005_*.py`、`backend/app/models/research.py` | 表、状态和约束 |
| `backend/app/schemas/research.py` | 请求、动作、证据、报告、响应的严格契约 |
| `backend/app/services/research.py` | 创建/读取、快照、并发检查、检查点和终态持久化 |
| `backend/app/services/research_tools.py` | 只读商品工具与单元 5 的 Embedding/Chroma 检索复用、来源登记 |
| `backend/app/services/research_agent.py` | JSON 动作解析、有限循环、报告/引用校验与安全错误映射 |
| `backend/app/tasks/research.py` | Celery/Redis 锁、恢复、重试和资源生命周期 |
| `backend/app/api/v1/research.py` | `202` 创建、列表、详情与 RBAC |
| 现有 `config.py`、`celery_app.py`、`main.py` | 两个配置字段和已有应用注册点 |

四个独立可测试的 Task：

1. **领域记录与 API 基础**：ORM、迁移、Schema、固定商品快照、同商品活动任务控制、创建/列表/详情和 RBAC。此时仅模拟投递，不进行 Agent 调用。
2. **受控工具与证据**：商品快照工具、指定 KB 检索、配置/维度一致性、来源 ID 与元数据核验、总证据上限。
3. **Agent 与 Worker**：严格动作 JSON、4 步循环、检查点恢复、Celery/Redis 锁、错误分类、重投与费用记录。
4. **报告与阶段验收**：结构化分析、引用校验、证据不足结果、API 故障矩阵、完整回归、README 和四份本地中文学习文档。

每个 Task 先写可失败的测试并观察 RED，再做最小实现、GREEN、Ruff、mypy、相关回归并精确提交。测试层次涵盖纯函数/模型假响应、MySQL `marketmind_test`、API 权限、Celery 重试、提示词注入与伪造引用。全仓已有一个用户未跟踪练习测试断言练习表名错误；要单独报告，不修改或暂存它，也不能把排除后的通过说成“原样全绿”。

## 10. 完成标准与手工验收

工程完成需证明：迁移可执行；三种角色权限与并发冲突正确；模型只能触发允许动作；最多 4 次动作；只检索被授权 KB 的 ready 文档；来源和报告引用不可伪造；无证据不生成普通竞品结论；Worker 重投不重复已完成步骤；终态与 Token 用量在 MySQL 可查询；自动化测试、Ruff、mypy 和差异检查有实际结果。四份学习文档分别说明各文件调用链、每步为何按此顺序编写、所用标准库/第三方包/自写代码和真实调试记录。

需要用户另行批准的真实验收：配置有预算的兼容模型与 Chroma，上传一份小型竞品资料，运行一项研究，核对 MySQL 记录、实际引用和费用。没有该批准时只做模拟测试，不宣称已验证真实供应商行为。单元 6 的合并、推送和旧分支清理也须单独由用户决定。
