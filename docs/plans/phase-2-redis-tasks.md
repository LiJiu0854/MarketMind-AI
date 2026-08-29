# 阶段 2：Redis 与任务基础设施实施计划

> **执行要求：** 本计划按当前“学习者手写核心逻辑、助手提供骨架并逐单元验收”的模式执行。每个 Task 开始前生成完整中文教程，每个单元通过后再进入下一单元。

**目标：** 为 MarketMind AI 增加 Redis 缓存、幂等、限流、分布式锁以及 Celery 后台任务能力。

**架构：** 本地使用一个 Redis 容器，通过 DB 0、DB 1、DB 2 隔离应用数据、Celery Broker 和 Celery Result Backend。FastAPI 使用异步 redis-py 客户端；Celery Worker 作为独立容器运行，并通过 Celery 原生状态保存任务结果。

**技术栈：** Python 3.12、FastAPI、redis-py 6.4.x、Redis Server 8.x、Celery 5.6.x、Docker Compose、pytest、Ruff、mypy。

**设计文档：** `docs/plans/phase-2-redis-tasks-design.md`

## 全局约束

- 阶段固定为 4 个 Task、18 个学习单元。
- 运行依赖只新增 `redis>=6.4,<6.5` 和 `celery>=5.6,<5.7`。
- 真实密码只写入 `.env`；`.env.example` 只保存无秘密模板。
- Redis 开发端口只绑定 `127.0.0.1`，不得直接暴露到局域网。
- DB 0 用于缓存、幂等、限流和锁；DB 1 用作 Broker；DB 2 用作 Result Backend。
- Redis 集成测试必须使用独立测试逻辑库，不允许清空开发库。
- 核心逻辑由学习者手写；重复配置、导入整理和无学习价值的小修复由助手完成。
- 每个单元依次经过 RED、GREEN、Ruff、mypy；每个 Task 结束运行相关回归测试。
- 不跨阶段实现商品、Excel、LLM、RAG、Agent、SSE、MCP、Playwright 或前端。
- 不修改或提交 `docs/learning/phase-0-baseline.md` 和 `tests/unit/models/test_product_practice.py`。

依赖版本兼容性依据：Celery 5.6 使用的 Kombu 5.6 Redis 扩展要求 `redis>=4.5.2,!=4.5.5,!=5.0.2,<6.5`。本项目选择该范围内较新的 6.4 系列，同时保持对 Python 3.12 和 Redis Server 8.x 的支持。

---

## Task 1：Redis 基础设施（4 个单元）

**学习成果：** 能解释并独立写出 Redis 配置、连接生命周期、依赖注入、基础命令和健康检查。

**涉及文件：**

- 新建：`compose.yaml`
- 新建：`backend/app/db/redis.py`
- 新建：`tests/unit/db/test_redis.py`
- 新建：`tests/integration/redis/test_redis_commands.py`
- 修改：`.env.example`
- 修改：`backend/app/core/config.py`
- 修改：`backend/app/main.py`
- 修改：`backend/app/api/v1/health.py`
- 修改：`pyproject.toml`
- 修改：`tests/api/test_health.py`
- 新建：`docs/learning/phase-2-task-1-redis-foundation.md`

**对外接口：**

- `create_redis_client(url: SecretStr) -> Redis`
- `close_redis_client(client: Redis) -> None`，异步执行
- `get_redis(request: Request) -> Redis`
- `create_app(settings: Settings | None = None) -> FastAPI`

### 单元 1：Docker Redis 与配置

- [ ] 在 `tests/unit/core/test_config.py` 增加 Redis URL、测试 URL和缓存 TTL 的默认值及环境变量覆盖测试。
- [ ] 运行配置测试，确认新断言因字段不存在而失败。
- [ ] 在 `pyproject.toml` 加入 `redis>=6.4,<6.5`，更新虚拟环境依赖。
- [ ] 在 `Settings` 增加 `redis_url`、`test_redis_url`、`redis_cache_ttl_seconds`；URL 使用 `SecretStr | None`，TTL 使用正整数。
- [ ] 在 `.env.example` 增加无真实密码的 Redis 配置模板。
- [ ] 新建 `compose.yaml`：Redis 8.x、密码认证、AOF、命名卷、回环地址端口、健康检查。
- [ ] 启动 Docker Desktop 后运行 `docker compose config`，确认配置可以解析且模板中没有真实密码。
- [ ] 运行配置测试、Ruff 和 mypy，确认通过。

### 单元 2：异步客户端与生命周期

- [ ] 在 `tests/unit/db/test_redis.py` 先写客户端 URL、关闭调用和缺少客户端时返回 503 的失败测试。
- [ ] 运行该测试文件，确认因 `app.db.redis` 尚不存在而 RED。
- [ ] 新建 `backend/app/db/redis.py`，集中实现客户端创建、关闭和请求依赖，不在每次请求中创建连接池。
- [ ] 修改 `create_app`，允许传入 `Settings`，在 lifespan 启动阶段保存客户端，在关闭阶段释放客户端。
- [ ] 保持没有 `redis_url` 时应用仍可创建，但需要 Redis 的依赖必须返回明确的 `503` 业务错误。
- [ ] 运行单元测试，确认创建一次、复用多次、关闭一次。
- [ ] 运行现有 API 回归测试，确认应用工厂兼容阶段 0、阶段 1 用法。

### 单元 3：Redis 命令实验

- [ ] 启动 Redis：`docker compose up -d redis`。
- [ ] 新建 Redis 集成测试目录和测试文件，只连接 `test_redis_url`。
- [ ] 先写 `SET/GET`、JSON 字符串、TTL、`SET NX` 四组测试。
- [ ] 为每组测试使用唯一 Key，并在 `finally` 中只删除该 Key。
- [ ] 运行集成测试，观察字符串返回、TTL 递减和第二次 `SET NX` 失败。
- [ ] 记录普通 `SET` 与带 `NX` 的 `SET` 在并发语义上的区别。
- [ ] 运行 Ruff 和 mypy，确认测试代码也通过静态检查。

### 单元 4：健康检查与故障行为

- [ ] 在 `tests/api/test_health.py` 增加 Redis 正常时 `/ready` 返回 200 的测试。
- [ ] 增加 Redis `ping` 失败时 `/ready` 返回 503 且错误结构稳定的测试。
- [ ] 运行两个测试，确认健康路由尚未检查 Redis而 RED。
- [ ] 修改健康路由，使 readiness 同时检查 MySQL 与 Redis；liveness 不连接外部服务。
- [ ] 用依赖覆盖或应用状态替换隔离真实 Redis，保证 API 单元测试快速稳定。
- [ ] 关闭 Redis 容器人工请求 `/api/v1/health/ready`，确认未就绪；重新启动后确认恢复。
- [ ] 运行 Task 1 全部测试、Ruff、mypy。
- [ ] 提交 Task 1，提交信息为 `feat: add Redis infrastructure`。

**Task 1 验收命令：**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\core\test_config.py tests\unit\db\test_redis.py tests\api\test_health.py -q
.venv\Scripts\python.exe -m pytest tests\integration\redis -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
```

---

## Task 2：Cache Aside（4 个单元）

**学习成果：** 能独立写出缓存 Key、序列化、命中/未命中、回源、TTL 和写后失效链路。

**涉及文件：**

- 新建：`backend/app/services/user_cache.py`
- 新建：`tests/unit/services/test_user_cache.py`
- 修改：`backend/app/api/v1/users.py`
- 修改：`tests/api/test_users.py`
- 新建：`docs/learning/phase-2-task-2-cache-aside.md`

**对外接口：**

- `user_cache_key(user_id: int) -> str`
- `get_user_with_cache(session: AsyncSession, redis: Redis, user_id: int, ttl_seconds: int) -> UserRead`
- `invalidate_user_cache(redis: Redis, user_id: int) -> None`，异步执行

### 单元 1：Key、序列化与 TTL

- [ ] 先写缓存 Key 格式、`UserRead` JSON 往返和 TTL 参数传递测试。
- [ ] 运行测试，确认模块不存在而 RED。
- [ ] 创建 `user_cache.py`，Key 固定为带版本的 `marketmind:user:v1:{id}`。
- [ ] 只序列化 `UserRead`，验证缓存内容不包含 `password` 或 `password_hash`。
- [ ] Redis 异常只在缓存边界捕获并记录，不吞掉 Pydantic 数据错误。
- [ ] 运行测试、Ruff 和 mypy。

### 单元 2：缓存命中与未命中

- [ ] 先写缓存命中时不访问 MySQL 的测试。
- [ ] 先写缓存未命中时访问 MySQL、返回 `UserRead` 并写入 TTL 的测试。
- [ ] 运行测试，确认读取协调逻辑尚不存在而 RED。
- [ ] 实现 `get_user_with_cache`：Redis、MySQL、Redis、返回值严格按 Cache Aside 顺序执行。
- [ ] 修改单个用户读取路由，注入 Redis 和 TTL，不修改分页接口。
- [ ] 运行服务单元测试和用户 API 回归测试。

### 单元 3：更新后的缓存失效

- [ ] 先写用户更新成功后删除对应 Key 的 API 测试。
- [ ] 先写用户停用成功后删除对应 Key 的 API 测试。
- [ ] 增加数据库提交失败时不删除缓存的测试。
- [ ] 运行测试，确认当前路由未执行失效而 RED。
- [ ] 在数据库服务成功返回后调用 `invalidate_user_cache`。
- [ ] 保持数据库提交职责仍在用户 Service，不把事务移动到缓存模块。
- [ ] 运行相关用户服务和 API 回归测试。

### 单元 4：降级与一致性验收

- [ ] 先写 Redis 读取失败后仍从 MySQL 返回用户的测试。
- [ ] 先写 Redis 写入失败但接口仍返回成功的测试。
- [ ] 先写缓存删除失败时数据库结果仍成功返回并记录错误的测试。
- [ ] 运行测试，确认异常策略尚不完整而 RED。
- [ ] 实现缓存错误日志和 MySQL 回退，保持安全异常不会被误吞。
- [ ] 使用短 TTL 验证删除失败造成的旧值会自动到期。
- [ ] 运行 Task 2 全部测试、Ruff、mypy。
- [ ] 提交 Task 2，提交信息为 `feat: add user cache aside`。

**Task 2 验收命令：**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\services\test_user_cache.py tests\api\test_users.py -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
```

---

## Task 3：并发与接口保护（5 个单元）

**学习成果：** 能解释 Redis 原子命令，并实现幂等、固定窗口限流和不会误释放的分布式锁。

**涉及文件：**

- 新建：`backend/app/services/redis_guards.py`
- 新建：`tests/unit/services/test_redis_guards.py`
- 修改：`backend/app/api/v1/auth.py`
- 修改：`backend/app/api/v1/users.py`
- 修改：`backend/app/core/config.py`
- 修改：`.env.example`
- 修改：`tests/api/test_auth.py`
- 修改：`tests/api/test_users.py`
- 新建：`docs/learning/phase-2-task-3-redis-guards.md`

**对外接口：**

- `request_fingerprint(actor_id: int, path: str, payload: dict[str, object]) -> str`
- `begin_idempotent_request(redis: Redis, key: str, fingerprint: str, ttl_seconds: int) -> str | None`
- `complete_idempotent_request(redis: Redis, key: str, fingerprint: str, response_json: str, ttl_seconds: int) -> None`
- `enforce_login_rate_limit(redis: Redis, identity: str, limit: int, window_seconds: int) -> None`
- `redis_lock(redis: Redis, key: str, ttl_ms: int) -> AsyncIterator[bool]`

### 单元 1：原子操作基础

- [ ] 先写首次 `SET NX` 成功、重复设置失败、计数器递增和过期时间存在的测试。
- [ ] 先写比较所有者后删除锁的 Lua 脚本行为测试。
- [ ] 运行测试，确认生产函数不存在而 RED。
- [ ] 在 `redis_guards.py` 保存最小 Lua 脚本常量和 Key 前缀函数。
- [ ] 禁止用“先 GET 再 DEL”替代原子比较删除。
- [ ] 运行单元测试和 Redis 集成测试。

### 单元 2：创建用户幂等

- [ ] 先写稳定请求摘要测试：字典键顺序不同但摘要相同，内容不同则摘要不同。
- [ ] 先写第一次请求取得执行权、相同请求重放结果、不同请求冲突、处理中冲突测试。
- [ ] 运行测试，确认幂等函数尚不存在而 RED。
- [ ] 使用规范 JSON 和 SHA-256 生成摘要，不把密码明文写入 Redis Key 或日志。
- [ ] 使用 Redis 原子占位记录处理中状态，成功后保存响应；处理中记录使用短 TTL 防止永久卡死。
- [ ] 修改创建用户路由，要求 `Idempotency-Key`，并把操作者、路径和请求摘要纳入判断。
- [ ] 运行用户 API 测试。

### 单元 3：登录固定窗口限流

- [ ] 先写窗口内未达上限可通过、达到上限返回 429、过期后重新计数的测试。
- [ ] 先写 Redis 不可用时返回 503 的测试。
- [ ] 运行测试，确认登录路由没有限流而 RED。
- [ ] 用 Redis 端原子脚本完成计数与首次过期时间设置，避免计数 Key 永不过期。
- [ ] 限流身份由标准化邮箱和客户端地址组成；日志不得记录密码。
- [ ] 响应包含 `Retry-After`。
- [ ] 运行认证 API 回归测试。

### 单元 4：分布式锁

- [ ] 先写首次取得锁、第二个所有者失败、错误所有者不能释放、正确所有者释放成功的测试。
- [ ] 先写代码块异常时仍尝试释放锁的测试。
- [ ] 运行测试，确认上下文管理器不存在而 RED。
- [ ] 使用 UUID 作为所有者值，使用毫秒 TTL 防止 Worker 崩溃造成永久死锁。
- [ ] 使用异步上下文管理器保证退出路径统一释放。
- [ ] 运行锁单元测试和真实 Redis 集成测试。

### 单元 5：并发与故障验收

- [ ] 同时发送两个相同幂等请求，验证业务只执行一次。
- [ ] 连续发送超过上限的登录请求，验证只在窗口内阻止。
- [ ] 并发获取同一个锁，验证最多一个调用者进入临界区。
- [ ] 停止 Redis，验证缓存查询可降级，但幂等、限流和锁拒绝绕过。
- [ ] 运行 Task 3 全部测试、Ruff、mypy。
- [ ] 提交 Task 3，提交信息为 `feat: add Redis request guards`。

**Task 3 验收命令：**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\services\test_redis_guards.py tests\api\test_auth.py tests\api\test_users.py -q
.venv\Scripts\python.exe -m pytest tests\integration\redis -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
```

---

## Task 4：Celery 后台任务（5 个单元）

**学习成果：** 能独立说明任务投递、Broker、Worker、Result Backend、状态查询和失败重试之间的关系。

**涉及文件：**

- 新建：`Dockerfile`
- 新建：`backend/app/celery_app.py`
- 新建：`backend/app/tasks/__init__.py`
- 新建：`backend/app/tasks/user_stats.py`
- 新建：`backend/app/schemas/task.py`
- 新建：`backend/app/api/v1/tasks.py`
- 新建：`tests/unit/tasks/test_user_stats.py`
- 新建：`tests/api/test_tasks.py`
- 修改：`compose.yaml`
- 新建：`.dockerignore`
- 修改：`.env.example`
- 修改：`backend/app/core/config.py`
- 修改：`backend/app/main.py`
- 修改：`pyproject.toml`
- 新建：`docs/learning/phase-2-task-4-celery.md`

**对外接口：**

- `celery_app: Celery`
- `collect_user_stats() -> dict[str, int]`，异步执行
- `generate_user_stats() -> dict[str, int]`，Celery 任务
- `POST /api/v1/tasks/user-stats -> TaskCreated`
- `GET /api/v1/tasks/{task_id} -> TaskStatus`

### 单元 1：Celery 配置

- [ ] 在配置测试中增加 Broker、Result Backend、eager 模式字段。
- [ ] 运行测试，确认字段不存在而 RED。
- [ ] 在 `pyproject.toml` 加入 `celery>=5.6,<5.7`，更新虚拟环境。
- [ ] 创建 `celery_app.py`，从 `Settings` 读取 DB 1 和 DB 2 URL。
- [ ] 配置 JSON 序列化、UTC、任务开始状态和结果过期时间；不启用 pickle。
- [ ] 测试模式通过 eager 设置同步执行任务。
- [ ] 运行配置测试、Ruff、mypy。

### 单元 2：Worker 容器

- [ ] 创建最小 Python 3.12 `Dockerfile`，只安装项目运行依赖。
- [ ] 创建 `.dockerignore`，排除 `.git`、`.venv`、`.env`、缓存和测试产物。
- [ ] 在 Compose 中增加 Worker 服务，等待 Redis 健康后启动。
- [ ] Worker 容器把 `.env` 中的容器专用数据库 URL 映射为应用的 `DATABASE_URL`。
- [ ] 运行 `docker compose config` 验证秘密没有写死在 Compose 文件。
- [ ] 构建 Worker 镜像并确认 Celery 能列出已注册任务。

### 单元 3：用户统计任务

- [ ] 先写统计活跃用户、停用用户和各角色数量的 Service 测试。
- [ ] 先写 Celery 包装函数调用异步统计函数并返回 JSON 数据的测试。
- [ ] 运行测试，确认任务模块不存在而 RED。
- [ ] 使用独立数据库会话查询聚合结果，不把 ORM 对象作为 Celery 参数或结果。
- [ ] 使用分布式锁保护统计执行；未取得锁时返回明确的“已在执行”结果。
- [ ] 对可重试数据库连接错误配置有限次数和退避，不重试业务错误。
- [ ] 运行任务单元测试。

### 单元 4：投递与状态 API

- [ ] 先写管理员能投递任务并取得 `task_id` 的测试。
- [ ] 先写普通用户被 RBAC 拒绝的测试。
- [ ] 先写 PENDING、STARTED、SUCCESS、FAILURE 四种状态映射测试。
- [ ] 先写 Broker 不可用时返回 503 且不伪造 ID 的测试。
- [ ] 运行测试，确认路由不存在而 RED。
- [ ] 创建任务响应 Schema 和任务路由，复用阶段 1 的管理员角色依赖。
- [ ] 注册路由；状态接口不泄露异常堆栈，只返回安全错误摘要。
- [ ] 运行任务 API 测试和现有认证回归测试。

### 单元 5：真实链路与阶段验收

- [ ] 启动 Redis 和 Worker，确认两个容器健康或正在正常运行。
- [ ] 启动 FastAPI，以管理员身份投递用户统计任务。
- [ ] 使用返回的 `task_id` 查询，观察 PENDING、STARTED 到 SUCCESS 的状态变化。
- [ ] 停止 Worker，验证任务保持待处理而 API 不假报成功。
- [ ] 停止 Redis，验证投递返回 503、readiness 返回未就绪。
- [ ] 恢复容器后再次完成任务，确认系统可恢复。
- [ ] 运行全量 pytest、Ruff、mypy 和 `git diff --check`。
- [ ] 在 Task 4 教程末尾增加阶段 2 组件关系 Mermaid 流程图。
- [ ] 完成人工文字题和 Swagger 验收。
- [ ] 提交 Task 4，提交信息为 `feat: complete phase 2 Redis and task infrastructure`。

**Task 4 与阶段总验收命令：**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
git diff --check
docker compose ps
```

## 提交与合并边界

- 每个 Task 只提交本 Task 的代码、测试和中文学习文档。
- 阶段开发期间不直接修改 `main`。
- 阶段 2 的 4 个 Task、自动化验收、文字题和人工运行验收全部通过后，才允许推送阶段分支并请求合并。
- 不使用强制删除分支作为撤销开发手段；需要纠错时保留可审计提交并进行正常修复。
