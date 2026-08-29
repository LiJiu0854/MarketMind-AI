# 阶段 2：Redis 与任务基础设施设计

## 1. 阶段目标

阶段 2 为 MarketMind AI 增加 Redis 与 Celery 基础设施，使系统具备缓存、接口保护、跨进程协调和后台任务能力。

本阶段结束后，系统应具备以下业务效果：

- 使用 Docker Compose 启动 Redis 和 Celery Worker；
- 使用 Cache Aside 加速单个用户查询；
- 在用户数据变化后删除旧缓存；
- 使用幂等键防止重复创建用户；
- 使用 Redis 限制登录请求频率；
- 使用分布式锁避免同一后台任务并发执行；
- 通过 Celery 投递用户统计任务并查询任务状态；
- 对 Redis、MySQL 和 Celery 故障返回明确、可测试的结果。

阶段 2 不实现商品数据、Excel 导入、LLM、RAG、Agent、SSE、MCP、Playwright 或前端功能。

## 2. 学习与开发方式

阶段 2 固定划分为 4 个 Task，共 18 个学习单元。

每个 Task 开始时，一次性给出该 Task 的全部学习单元。每个单元的教程必须包含：

1. 本单元业务目标；
2. 按“必须手写、理解原理、了解用途”分层的知识点；
3. 项目文件树和只保留核心逻辑空位的骨架代码；
4. 按真实开发顺序编排的逐步实现说明；
5. RED、GREEN 和静态检查验收标准。

学习者逐单元填写核心逻辑；检查通过后，再在教程中补充参考实现、代码解释和可迁移用法。重复性基础代码由助手直接完成并解释。

## 3. 部署方案

本地开发使用一个 Redis 容器，通过逻辑库隔离用途：

| Redis 逻辑库 | 用途 |
|---|---|
| DB 0 | 应用缓存、幂等键、限流、分布式锁 |
| DB 1 | Celery Broker |
| DB 2 | Celery Result Backend |

应用分别配置三个连接 URL。虽然本地共用一个 Redis 容器，生产部署仍可把三个 URL 指向不同 Redis 实例，无需修改业务代码。

Docker Compose 最终包含 Redis 和 Celery Worker。Redis 的宿主机端口只绑定 `127.0.0.1`，并使用环境变量提供的密码；数据通过命名卷保存。FastAPI 在本机虚拟环境中运行；Worker 容器使用 `host.docker.internal` 访问 Windows 主机上的 MySQL。真实密码只保存在 `.env`，`.env.example` 只提交配置模板。

## 4. Task 与学习单元

### Task 1：Redis 基础设施（4 个单元）

目标：掌握应用连接、使用和检查 Redis 的完整基础链路。

1. Docker Compose 启动 Redis 并划分三个逻辑库；
2. Redis 配置、异步客户端与连接生命周期；
3. Key、字符串、JSON、TTL 和原子命令；
4. Redis 健康检查、连接失败处理和真实集成测试。

### Task 2：Cache Aside（4 个单元）

目标：掌握“先查缓存，未命中再查数据库”的真实代码链路。

1. 缓存 Key、序列化结构和 TTL；
2. 为 `GET /api/v1/users/{user_id}` 实现缓存读取；
3. 用户更新或停用成功后删除旧缓存；
4. 验证缓存命中、未命中、失效和 Redis 故障降级。

阶段 2 不缓存用户分页列表。分页缓存需要处理页码、筛选条件和批量失效，不会增加当前 Cache Aside 学习目标的核心价值。

### Task 3：并发与接口保护（5 个单元）

目标：理解 Redis 如何协调多个 API 进程并保护接口。

1. Redis 原子性、`SET NX`、计数器和过期时间；
2. 为创建用户接口实现 `Idempotency-Key`；
3. 为登录接口实现固定窗口限流；
4. 实现带唯一所有者标识的分布式锁；
5. 验证重复请求、并发请求和锁释放行为。

### Task 4：Celery 后台任务（5 个单元）

目标：掌握“API 投递任务，Worker 独立执行”的完整链路。

1. 配置 Celery、Broker 和 Result Backend；
2. Docker Compose 增加 Celery Worker；
3. 实现最小且真实的用户统计后台任务；
4. 实现任务投递、状态查询 API，并应用分布式锁；
5. 验证失败处理、状态流转，完成阶段总验收和类关系流程图。

## 5. 代码边界

阶段 2 预计新增或修改以下核心文件：

```text
compose.yaml
Dockerfile

backend/app/
├── core/config.py              # Redis、Celery 配置
├── db/redis.py                 # Redis 连接池和 FastAPI 依赖
├── services/user_cache.py      # 用户 Cache Aside
├── services/redis_guards.py    # 幂等、限流、分布式锁
├── celery_app.py               # Celery 实例
├── tasks/user_stats.py         # 用户统计后台任务
├── api/v1/tasks.py             # 任务投递与状态查询
└── main.py                     # 注册生命周期和任务路由
```

具体文件只有在对应 Task 确实需要时才创建。本阶段不增加只有单个实现的接口、仓储抽象或通用缓存框架。

## 6. Redis 连接生命周期

FastAPI 应用启动时创建一个异步 Redis 连接池，并将客户端保存在当前应用实例中。请求通过依赖注入取得该客户端；应用关闭时统一释放连接池。

测试可以创建全新的 FastAPI 应用实例，并覆盖 Redis 依赖，避免测试之间共享不可控的连接状态。

## 7. Cache Aside 数据流

单个用户读取流程：

```text
GET /api/v1/users/{user_id}
  -> 根据 user_id 生成缓存 Key
  -> 查询 Redis
  -> 命中：反序列化 UserRead 并返回
  -> 未命中：查询 MySQL
       -> 序列化 UserRead
       -> 写入 Redis 并设置 TTL
       -> 返回结果
```

用户更新或停用流程：

```text
修改 MySQL
  -> 数据库提交成功
  -> 删除该用户的 Redis 缓存
  -> 后续读取从 MySQL 重建缓存
```

必须先提交 MySQL，再删除缓存。若数据库提交失败，不应删除仍然有效的缓存。

缓存只保存 `UserRead` 可公开字段，不保存密码哈希或 ORM 对象。

## 8. 幂等、限流与分布式锁

### 8.1 幂等键

创建用户请求读取 `Idempotency-Key` 请求头。服务端把当前操作者、请求路径和请求内容摘要共同纳入幂等记录，防止同一个 Key 被用于不同请求。

- 第一次请求取得执行权并处理业务；
- 相同 Key 和相同请求返回第一次成功结果；
- 相同 Key 但请求内容不同返回冲突；
- Redis 不可用时拒绝创建请求，避免绕过重复提交保护。

### 8.2 登录限流

登录接口使用固定窗口计数。限流维度同时考虑客户端地址和标准化邮箱，避免只更换邮箱或只更换地址即可完全绕过限制。

达到上限时返回 `429 Too Many Requests`，并附带可重试时间。Redis 不可用时拒绝登录请求，避免安全保护失效。

### 8.3 分布式锁

加锁使用 Redis 原子 `SET key value NX PX`。锁值是每次获取时生成的唯一所有者标识。

释放锁时必须同时比较所有者标识并删除 Key，不能直接执行普通 `DEL`，否则旧任务可能误删新任务已经取得的锁。比较和删除必须在 Redis 端原子完成。

## 9. Celery 数据流

任务状态采用 Celery 自身的 Result Backend，不重复开发任务状态表。

```text
POST 任务接口
  -> FastAPI 向 Redis DB 1 投递消息
  -> 立即返回 task_id
  -> Celery Worker 获取任务
  -> 取得分布式锁
  -> 查询 MySQL 并生成用户统计
  -> 把状态和结果写入 Redis DB 2

GET 状态接口
  -> 根据 task_id 查询 Celery Result Backend
  -> 返回 PENDING、STARTED、SUCCESS 或 FAILURE
```

API 不等待后台任务执行。Celery Worker 使用独立进程运行；任务内部需要自行建立和关闭数据库会话。

## 10. 故障处理策略

| 场景 | 系统行为 |
|---|---|
| 缓存读取失败 | 记录日志并查询 MySQL |
| 缓存写入失败 | 记录日志并正常返回 MySQL 数据 |
| 缓存删除失败 | 数据库结果仍然成功返回，记录高优先级错误；旧缓存最多保留到短 TTL 到期 |
| 限流 Redis 不可用 | 拒绝登录请求 |
| 幂等 Redis 不可用 | 拒绝创建请求 |
| 无法取得分布式锁 | 不执行受保护任务 |
| Celery 投递失败 | 返回 `503 Service Unavailable`，不伪造任务 ID |
| MySQL 或 Redis 健康检查失败 | `/health/ready` 返回未就绪 |

缓存属于性能优化，可以降级到 MySQL；限流、幂等和锁属于安全或一致性保护，不能静默绕过。

数据库提交和 Redis 删除无法组成同一个事务。本阶段使用短 TTL 限制缓存删除失败造成的不一致时间，不提前引入事务消息或 Outbox。若未来业务要求缓存必须立即一致，再通过可靠事件重试缓存失效。

## 11. 测试策略

- 单元测试使用现有 `unittest.mock` 隔离 Redis，不新增 fakeredis；
- Redis 集成测试连接独立测试逻辑库，不能使用开发缓存库；
- 每个 Redis 集成测试清理自己创建的 Key，不执行无边界的全库删除；
- Celery API 测试使用 eager 模式，不要求测试时启动真实 Worker；
- 阶段最终人工验收启动真实 Redis 和 Celery Worker；
- 每个单元遵循 RED、GREEN、Ruff、mypy 的验证顺序；
- 完整阶段验收运行全量 pytest、Ruff 和 mypy。

## 12. 依赖范围

阶段 2 运行依赖只新增：

- `redis`：FastAPI 异步 Redis 客户端；
- `celery`：后台任务队列、Worker 和任务状态。

容器只新增 Redis 和 Celery Worker 所需配置。其他依赖仅在出现当前阶段无法替代的真实需求时增加。

## 13. 阶段验收标准

阶段 2 完成必须同时满足：

1. Docker Compose 能启动 Redis 和 Celery Worker；
2. FastAPI 能建立并关闭 Redis 连接；
3. 单个用户读取能演示缓存未命中与命中；
4. Redis 可用时，用户更新和停用后立即失效旧缓存；删除失败时，不一致时间不超过配置的短 TTL；
5. Redis 缓存故障时用户查询可回退到 MySQL；
6. 重复创建请求受到幂等保护；
7. 高频登录请求受到限流；
8. 分布式锁不会释放其他所有者的锁；
9. API 能投递用户统计任务并查询最终状态；
10. Redis、MySQL 或 Worker 故障具有明确结果；
11. 全量 pytest、Ruff 和 mypy 通过；
12. 中文学习文档补充完整参考实现和阶段总流程图。
