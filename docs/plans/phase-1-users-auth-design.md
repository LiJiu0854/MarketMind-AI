# MarketMind AI 阶段 1：用户、数据库与权限设计

## 目标

在阶段 0 的 FastAPI 基础上接入真实 MySQL，建立可迁移、可测试的用户数据模型，并实现内部用户管理、密码哈希、JWT 登录和固定角色 RBAC。

阶段 1 完成后，学习者不只应记住代码写法，还应能够解释并迁移以下四条数据流：

1. Python ORM 对象如何通过迁移成为 MySQL 表；
2. 经过校验的业务输入如何通过 Service 和事务变成数据库数据；
3. 邮箱与密码如何换取可验证、会过期的用户身份；
4. 当前用户身份如何通过依赖注入变成接口权限。

## 已确认的产品决策

- 系统是企业内部平台，不提供公开注册。
- 用户只能由 Admin 创建。
- 第一个 Admin 通过一次性交互式 CLI 创建；密码使用 `getpass` 输入，不进入命令历史。
- JWT 只实现 30 分钟 Access Token；阶段 1 不实现 Refresh Token。
- 每个用户只有一个固定角色：`Admin`、`Operator` 或 `Analyst`。
- 删除用户表示停用账号，不执行物理删除；Admin 可以重新启用账号。
- Admin 不能停用自己，也不能修改自己的角色。
- 开发和测试使用本机正在运行的 MySQL 8.0；不在本阶段引入 Docker。

## 范围外

阶段 1 不实现：

- 公开注册、邮箱验证、忘记密码；
- Refresh Token、Token 吊销列表、Redis Session；
- 动态角色表、权限表、多角色关系；
- 商品、报告、Agent 等业务表；
- Docker、CI 和生产部署。

这些能力没有当前调用方或验收需求，提前实现只会扩大安全面和测试成本。

## 技术选择

- SQLAlchemy 2 异步 ORM；
- MySQL 异步驱动；
- Alembic 管理结构迁移；
- `pwdlib[argon2]` 哈希密码；
- PyJWT 使用 `HS256` 签发和验证 Access Token；
- FastAPI `Depends` 提供数据库会话、当前用户和角色校验；
- pytest + HTTPX 对真实测试数据库执行集成测试。

参考：

- [SQLAlchemy 异步 ORM 官方文档](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic 异步迁移官方说明](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)
- [FastAPI OAuth2、JWT 与密码哈希官方教程](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)

## 配置与密钥

新增运行时配置：

- `DATABASE_URL`：开发数据库连接；
- `TEST_DATABASE_URL`：只供测试连接 `marketmind_test`；
- `JWT_SECRET`：JWT 签名密钥，没有代码默认值；
- `ACCESS_TOKEN_EXPIRE_MINUTES=30`。

包含密码或密钥的值只写入本机 `.env`，不得出现在 `.env.example`、代码、测试、日志、Git 提交或终端命令参数中。`.env.example` 只记录空占位符和安全默认值。

数据库账号使用唯一强密码和最小权限；不使用简单密码，也不把密码发送到对话中。

## 代码边界

```text
HTTP 请求
  ↓
Router：HTTP 输入、输出和状态码
  ↓
Depends：数据库会话、当前用户、角色校验
  ↓
Service：用户业务规则和事务边界
  ↓
AsyncSession：ORM 查询和提交
  ↓
MySQL
```

计划新增或修改的主要模块：

| 模块 | 单一职责 |
| --- | --- |
| `app/db/base.py` | 声明 SQLAlchemy ORM Base |
| `app/db/session.py` | 创建异步 Engine、Session 工厂和请求会话依赖 |
| `app/models/user.py` | 定义用户表和 `Role` 枚举 |
| `app/schemas/user.py` | 定义用户创建、更新、分页和响应契约 |
| `app/schemas/auth.py` | 定义 Token 响应和 Token 数据 |
| `app/core/security.py` | 密码哈希、密码验证、JWT 创建与解析 |
| `app/core/errors.py` | 稳定业务错误码和异常类型 |
| `app/services/users.py` | 用户查询、创建、更新、停用和认证规则 |
| `app/api/dependencies.py` | 当前用户与 `require_roles()` 依赖 |
| `app/api/v1/auth.py` | 登录和当前用户接口 |
| `app/api/v1/users.py` | Admin 用户管理接口 |
| `app/cli/create_admin.py` | 交互式创建首个 Admin，并复用用户 Service |
| `alembic/`、`alembic.ini` | 数据库结构版本与升级脚本 |

不创建只有一个实现的 Repository 接口或 Unit of Work 包装。Service 直接接收 `AsyncSession`，这是当前最短且可测试的复用边界。

## 用户数据模型

`users` 表至少包含：

| 字段 | 约束与用途 |
| --- | --- |
| `id` | 自增主键；JWT 的 `sub` 使用其字符串形式 |
| `email` | 规范化为小写；唯一索引；作为登录名 |
| `full_name` | 用户展示名称 |
| `password_hash` | Argon2 哈希；永不出现在 API 响应 |
| `role` | 固定值 `admin`、`operator`、`analyst` |
| `is_active` | 停用后禁止登录和访问受保护接口 |
| `created_at` | 创建时间 |
| `updated_at` | 最近更新时间 |

ORM Model 表达数据库结构；Pydantic Schema 表达 API 输入输出。二者不得混用，避免把 `password_hash` 等数据库字段意外序列化给客户端。

## 接口设计

### 认证接口

- `POST /api/v1/auth/token`：提交邮箱和密码，成功后返回 Bearer Access Token；
- `GET /api/v1/auth/me`：返回当前有效用户，不返回密码哈希。

登录失败统一返回“邮箱或密码错误”，不能暴露邮箱是否存在。用户不存在时仍执行一次虚拟密码校验，减少通过响应时间枚举账号的风险。

### Admin 用户管理接口

- `POST /api/v1/users`：创建用户；
- `GET /api/v1/users?page=1&page_size=20`：分页查询，`page_size` 最大为 100；
- `GET /api/v1/users/{user_id}`：读取单个用户；
- `PATCH /api/v1/users/{user_id}`：修改姓名、角色或启用状态；
- `DELETE /api/v1/users/{user_id}`：语义为停用，不物理删除。

上述接口只允许 Admin。Operator 和 Analyst 在阶段 1 只能登录、读取自己，不能管理用户。

## 请求与数据流

### 创建内部用户

```text
Admin 请求
→ Request ID 中间件
→ 解析 JWT
→ 查询当前有效用户
→ require_roles(Admin)
→ UserCreate 校验
→ Service 规范化邮箱、检查重复、哈希密码
→ AsyncSession 写入并提交
→ UserResponse 过滤敏感字段
```

### 登录

```text
邮箱和密码
→ 查询用户
→ Argon2 验证密码或执行虚拟校验
→ 检查 is_active
→ JWT 写入 sub 和 exp 并签名
→ 返回 access_token 与 token_type=bearer
```

### CLI 创建首个 Admin

```text
终端输入邮箱和姓名
→ getpass 安全输入密码
→ 创建 AsyncSession
→ 调用同一 User Service
→ 以 Admin 角色写入 MySQL
```

CLI 不复制用户创建逻辑，因此 API 和脚本执行相同的邮箱规范化、唯一性检查与密码哈希规则。

## JWT 与 RBAC 规则

- `JWT_SECRET` 必须由本机生成并通过环境变量提供；
- JWT 使用 `sub=str(user.id)`、UTC `exp` 和固定算法白名单；
- Token 不保存角色，每次请求重新查询数据库；
- Token 无效、过期、签名错误或用户不存在时返回 401；
- 用户已停用或角色不足时返回 403；
- 401 响应包含 `WWW-Authenticate: Bearer`；
- `require_roles(Role.ADMIN)` 作为可复用依赖保护用户管理路由。

## 统一错误响应

所有业务错误使用以下格式：

```json
{
  "code": "USER_EMAIL_CONFLICT",
  "message": "邮箱已存在",
  "request_id": "..."
}
```

核心映射：

| 错误码 | HTTP 状态 |
| --- | --- |
| `AUTH_INVALID_CREDENTIALS` | 401 |
| `ACCOUNT_INACTIVE` | 403 |
| `PERMISSION_DENIED` | 403 |
| `USER_NOT_FOUND` | 404 |
| `USER_EMAIL_CONFLICT` | 409 |
| `VALIDATION_ERROR` | 422 |
| `DATABASE_UNAVAILABLE` | 503 |

数据库异常发生时必须回滚事务。响应不得泄露 SQL、表名、连接串、密码或堆栈信息。

## 测试设计

开发数据库 `marketmind` 与测试数据库 `marketmind_test` 必须物理隔离。

测试层级：

- 单元测试：密码哈希、密码验证、JWT 创建、过期与篡改；
- 数据库集成测试：真实 MySQL 唯一约束、事务回滚、CRUD 和分页；
- API 集成测试：登录、当前用户、401、403、404、409、422 和停用账号；
- 故障测试：在数据库调用边界模拟连接异常，验证稳定的 503 响应；
- 迁移测试：对空测试库运行 `alembic upgrade head`。

每个数据库测试在外层事务中运行。测试使用绑定到该连接的 `AsyncSession`；API 内部可以提交自己的事务，测试结束仍由外层事务统一回滚，确保用例互不污染。

测试不得使用开发数据库，也不得通过 SQLite 替代 MySQL。外部数据库故障可以在边界处模拟，但正常数据库行为必须由真实 MySQL 验证。

## 固定 4 个 Task 与学习目标

### Task 1：从 Python 对象到 MySQL 表

实现数据库配置、异步 Engine/Session、用户 ORM Model、Alembic 初始迁移和真实测试库连接。

完成后应能独立解释并使用：Model、Engine、Connection、Session、Transaction、迁移版本，以及为什么生产项目不用应用启动时 `create_all()`。

### Task 2：从业务输入到数据库事务

实现用户 Schema、Service、Admin CLI、Service 层 CRUD、分页、停用语义和业务异常。此时不注册用户管理 HTTP 路由，避免在认证与授权完成前暴露管理接口。

完成后应能把同一模式迁移到商品、报告或任务 CRUD，并能判断校验、业务规则和数据库操作分别应放在哪一层。

### Task 3：从密码凭证到当前用户

实现 Argon2 密码验证、JWT Access Token、登录接口、当前用户依赖与 `/auth/me`。

完成后应能独立说明哈希、签名、`sub`、`exp`、401 和停用检查，并为其他 FastAPI 项目增加登录能力。

### Task 4：从当前用户到受保护接口

实现 `require_roles()`、Admin 用户管理 HTTP 路由、统一错误处理、越权测试、数据库故障测试、手工联调和阶段综合学习验收。

完成后应能把 RBAC 依赖迁移到后续商品、RAG、Agent 和报告接口，并独立诊断 401、403、数据库连接和迁移问题。

## 每个 Task 的学习交付格式

每个 Task 开始前必须先说明：

1. 本 Task 目的是掌握什么；
2. 代码在真实项目中的用途；
3. 请求或数据如何流动；
4. 同一模式可以迁移到哪些场景；
5. 完成后学习者必须能独立写什么、解释什么。

每个 Task 均采用 TDD，并至少包含一个由学习者亲手完成的小改动。Agent 只能提示、检查和纠错，不代写本人练习。

## 阶段验收

阶段 1 只有同时满足以下条件才算完成：

- 四个 Task 均完成独立测试、静态检查、学习检查和 Git 提交；
- Alembic 能从空测试库升级到最新版本；
- API 使用真实 MySQL 完成登录、用户管理和 RBAC 手工验证；
- pytest、Ruff 和 mypy 全部通过；
- 密钥、数据库密码和密码哈希未进入 Git 或日志；
- 常见错误排查和面试口述通过；
- 阶段分支推送到 GitHub；
- 学习者明确确认阶段验收通过后，才允许合并 `main`。
