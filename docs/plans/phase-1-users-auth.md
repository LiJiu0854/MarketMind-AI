# 阶段 1 用户、数据库与权限实施计划

> **给 Agent 执行者：** 必须使用 `superpowers:executing-plans` 在当前会话逐 Task 执行。每一步使用复选框跟踪；每个功能严格遵循 RED → GREEN → REFACTOR。

**目标：** 使用真实 MySQL 构建可迁移、可测试的内部用户管理、JWT 认证和固定角色 RBAC。

**架构：** FastAPI Router 只处理 HTTP；依赖提供异步数据库会话、当前用户和角色判断；Service 持有可被 API 与 CLI 复用的业务规则；SQLAlchemy Model 与 Pydantic Schema 分离；Alembic 是唯一建表方式。

**技术栈：** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、MySQL 8、asyncmy、Pydantic、pwdlib/Argon2、PyJWT、pytest、HTTPX、Ruff、mypy

**设计：** `docs/plans/phase-1-users-auth-design.md`

## 全局约束

- 仓库根目录固定为 `C:\Users\17905\Desktop\MarketMind-AI`。
- 只在 `phase/1-users-auth` 开发；本人验收前不得合并 `main` 或创建标签。
- 阶段 1 固定为 4 个 Task，不增加第五个 Task。
- 开发库 `marketmind` 与测试库 `marketmind_test` 必须物理隔离。
- 不使用 SQLite 替代 MySQL 集成测试。
- 数据库密码、`DATABASE_URL`、`TEST_DATABASE_URL`、`JWT_SECRET` 不得进入代码、测试、日志或 Git。
- 不提供公开注册；第一个 Admin 由交互式 CLI 创建。
- 删除用户表示停用，不执行物理删除。
- JWT 只实现 30 分钟 Access Token；不实现 Refresh Token。
- 每个 Task 按“问题与数据流 → 必要语法 → RED 测试 → 学习者编写关键代码 → 逐段讲解 → GREEN → 迁移练习”推进；首次出现的核心代码必须从零解释，重复代码说明复用方法。
- 每个 Task 必须同时通过“能看懂、会使用、能编写、会迁移”四层学习验收，不能只用口述概念题代替代码练习。
- 每个 Task 结束前运行聚焦测试、完整 pytest、Ruff 和 mypy，并创建独立提交。

## 文件结构

```text
backend/app/
├── api/
│   ├── dependencies.py
│   └── v1/
│       ├── auth.py
│       └── users.py
├── cli/create_admin.py
├── core/
│   ├── errors.py
│   └── security.py
├── db/
│   ├── base.py
│   └── session.py
├── models/user.py
├── schemas/
│   ├── auth.py
│   └── user.py
└── services/users.py
alembic/
├── env.py
└── versions/0001_create_users_table.py
tests/
├── api/
│   ├── test_auth.py
│   └── test_users.py
├── integration/db/
│   ├── conftest.py
│   ├── test_migrations.py
│   └── test_users.py
└── unit/
    ├── core/test_security.py
    └── services/test_users.py
```

---

### Task 1：从 Python 对象到 MySQL 表

#### 学习目标

- **掌握什么：** Model、Engine、Connection、AsyncSession、Transaction、Alembic Revision。
- **真实用途：** 让数据库结构可审查、可升级、可回滚，而不是应用启动时偷偷建表。
- **数据流：** `Settings → create_async_engine → async_sessionmaker → User ORM → Alembic → MySQL users 表`。
- **迁移场景：** 后续商品表、任务表、报告表都复用同一模式。
- **完成标准：** 能独立创建一个 ORM Model、生成迁移、升级测试库并用事务写入/回滚数据。

**文件：**

- 修改：`pyproject.toml`
- 修改：`.env.example`
- 修改：`backend/app/core/config.py`
- 创建：`backend/app/db/__init__.py`
- 创建：`backend/app/db/base.py`
- 创建：`backend/app/db/session.py`
- 创建：`backend/app/models/__init__.py`
- 创建：`backend/app/models/user.py`
- 创建：`alembic.ini`
- 创建：`alembic/env.py`
- 创建：`alembic/script.py.mako`
- 创建：`alembic/versions/0001_create_users_table.py`
- 修改：`tests/unit/core/test_config.py`
- 创建：`tests/unit/db/test_session.py`
- 创建：`tests/unit/models/test_user.py`
- 创建：`tests/integration/db/conftest.py`
- 创建：`tests/integration/db/test_users.py`
- 创建：`docs/learning/phase-1-users-auth.md`

**接口：**

- `class Base(DeclarativeBase)`：所有 ORM Model 的共同元数据入口。
- `class Role(StrEnum)`：值为 `admin`、`operator`、`analyst`。
- `class User(Base)`：映射 `users` 表。
- `create_engine(database_url: SecretStr) -> AsyncEngine`。
- `create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]`。
- `database_url: SecretStr | None` 与 `test_database_url: SecretStr | None`。

- [x] **步骤 1：声明并安装 Task 1 数据库依赖**

在运行依赖中加入：

```toml
"alembic>=1.16,<2.0",
"asyncmy>=0.2,<1.0",
"cryptography>=42,<47",
"sqlalchemy[asyncio]>=2.0,<3.0",
```

运行：

```powershell
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
```

- [x] **步骤 2：为数据库配置编写 RED 测试**

在配置隔离变量中加入 `DATABASE_URL` 和 `TEST_DATABASE_URL`，并新增：

```python
def test_database_urls_are_secret_and_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql+asyncmy://user:secret@localhost/marketmind")
    settings = Settings()

    assert isinstance(settings.database_url, SecretStr)
    assert "secret" not in repr(settings)
    assert settings.test_database_url is None
```

运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\core\test_config.py -v
```

预期：因 `Settings` 没有 `database_url` 字段而失败。

- [x] **步骤 3：实现最小数据库配置并进入 GREEN**

在 `Settings` 中加入：

```python
database_url: SecretStr | None = None
test_database_url: SecretStr | None = None
```

`.env.example` 只加入空占位符：

```dotenv
DATABASE_URL=
TEST_DATABASE_URL=
```

重新运行步骤 2 的测试，预期通过。

- [x] **步骤 4：为 Engine 和 Session 工厂编写 RED 测试**

创建 `tests/unit/db/test_session.py`：

```python
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.session import create_engine, create_session_factory


@pytest.mark.asyncio
async def test_create_database_resources() -> None:
    engine = create_engine(SecretStr("mysql+asyncmy://user:password@localhost/database"))
    session_factory = create_session_factory(engine)

    assert isinstance(engine, AsyncEngine)
    assert session_factory.class_ is AsyncSession
    await engine.dispose()
```

运行并确认因 `app.db.session` 不存在而失败。

- [x] **步骤 5：实现 Base、Engine 和 Session 工厂**

`base.py`：

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM Model 的声明基类。"""
```

`session.py` 的公开函数：

```python
def create_engine(database_url: SecretStr) -> AsyncEngine:
    return create_async_engine(database_url.get_secret_value(), pool_pre_ping=True)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

重新运行 `tests/unit/db/test_session.py`，预期通过；测试结束显式 `await engine.dispose()`，避免连接资源警告。

- [x] **步骤 6：为 User Model 编写 RED 测试**

创建 `tests/unit/models/test_user.py`，断言：

```python
def test_user_model_exposes_expected_table_contract() -> None:
    assert User.__tablename__ == "users"
    assert set(User.__table__.columns.keys()) == {
        "id",
        "email",
        "full_name",
        "password_hash",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert {role.value for role in Role} == {"admin", "operator", "analyst"}
```

运行并确认因 `app.models.user` 不存在而失败。

- [x] **步骤 7：实现最小 User ORM Model**

使用 SQLAlchemy 2 `Mapped`/`mapped_column`，满足以下约束：

```python
class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"


class User(Base):
    __tablename__ = "users"
```

字段类型：自增整数主键、`VARCHAR(320)` 唯一邮箱、`VARCHAR(100)` 姓名、`VARCHAR(255)` 密码哈希、长度 20 的角色字符串约束、布尔启用状态、创建和更新时间。重新运行 Model 测试，预期通过。

- [x] **步骤 8：配置 Alembic 并创建初始迁移**

执行：

```powershell
.venv\Scripts\alembic.exe init -t async alembic
```

修改 `alembic/env.py`，从 `Settings().database_url` 读取连接串，并设置：

```python
target_metadata = Base.metadata
```

显式导入 `app.models.user`，确保 `users` 表进入 metadata。连接串缺失时抛出清晰配置错误，不写死密码。

生成迁移：

```powershell
.venv\Scripts\alembic.exe revision --autogenerate --rev-id 0001 -m "create users table"
```

人工检查 `upgrade()` 创建字段、唯一索引和角色约束，`downgrade()` 只删除 `users` 表。

- [x] **步骤 9：在真实测试库验证迁移与事务**

使用 Alembic 的显式测试库目标，运行：

```powershell
.venv\Scripts\alembic.exe -x database=test upgrade head
.venv\Scripts\alembic.exe -x database=test current
```

创建数据库集成测试：打开连接和外层事务，创建绑定连接的 `AsyncSession`，插入一个测试用户后 `flush()`，查询确认存在，最后回滚外层事务并再次查询确认数据不存在。

运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\integration\db -v
```

- [x] **步骤 10：本人练习与学习门禁**

学习者亲手完成：在测试库上依次运行 `alembic current`、`alembic history`，并阅读初始迁移的 `upgrade()`/`downgrade()`，用自己的话解释：

1. Model 改了为什么数据库不会自动改变；
2. Session 与 Connection 有什么区别；
3. 为什么测试必须使用 `marketmind_test`；
4. 外层事务回滚如何防止测试数据污染。

- [x] **步骤 11：Task 1 完整验证并提交**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
git diff --check
```

提交信息：

```text
feat: add MySQL persistence foundation
```

---

### Task 2：从业务输入到数据库事务

#### 学习目标

- **掌握什么：** Schema/Model 分离、Service 规则、事务提交与回滚、分页、业务异常、CLI 复用。
- **真实用途：** 让 API、脚本和以后 Celery 任务执行同一套用户规则。
- **数据流：** `UserCreate → normalize_email → hash_password → AsyncSession → UserRead`。
- **迁移场景：** 商品、报告、Agent Task 的 CRUD Service。
- **完成标准：** 能独立写一个带唯一约束、分页和软删除语义的 Service。

**文件：**

- 修改：`pyproject.toml`
- 创建：`backend/app/core/errors.py`
- 创建：`backend/app/core/security.py`
- 创建：`backend/app/schemas/user.py`
- 创建：`backend/app/services/__init__.py`
- 创建：`backend/app/services/users.py`
- 创建：`backend/app/cli/__init__.py`
- 创建：`backend/app/cli/create_admin.py`
- 创建：`tests/unit/core/test_security.py`
- 创建：`tests/unit/services/test_users.py`
- 创建：`tests/integration/db/test_user_service.py`
- 创建：`docs/learning/phase-1-task-2-user-service.md`

**接口：**

- `hash_password(password: str) -> str`
- `verify_password(password: str, password_hash: str) -> bool`
- `create_user(session: AsyncSession, data: UserCreate) -> User`
- `get_user(session: AsyncSession, user_id: int) -> User`
- `list_users(session: AsyncSession, page: int, page_size: int) -> UserPage`
- `update_user(session: AsyncSession, user: User, data: UserUpdate) -> User`
- `deactivate_user(session: AsyncSession, user: User, actor: User) -> User`

- [ ] 添加 `email-validator` 与 `pwdlib[argon2]` 依赖并安装。
- [ ] 先写 Argon2 测试：哈希不等于明文、相同密码生成不同哈希、正确密码通过、错误密码失败；观察缺少模块的 RED。
- [ ] 实现 `hash_password()` 和 `verify_password()`，进入 GREEN。
- [ ] 定义 `UserCreate`、`UserUpdate`、`UserRead`、`UserPage`；输入邮箱使用 `EmailStr`，密码最少 12 字符，响应不含 `password_hash`。
- [ ] 先写 Service RED：邮箱转小写、重复邮箱返回 `USER_EMAIL_CONFLICT`、分页 total/items 正确、停用不删除、自停用被拒绝。
- [ ] 实现 `AppError(code, message, status_code)` 和最小用户 Service；每个写操作成功时提交，异常时回滚。
- [ ] 编写真实 MySQL Service 集成测试，验证唯一约束和测试事务隔离。
- [ ] 实现 `python -m app.cli.create_admin`：使用 `input()` 读取邮箱/姓名，`getpass()` 读取密码并调用 `create_user()`；不得接受命令行密码参数。
- [ ] 本人练习：亲手增加 `page_size=0` 的失败测试并通过 Schema 约束修复；解释 422 与业务 409 的区别。
- [ ] 运行完整质量门禁并提交：`feat: add user service and admin bootstrap`。

---

### Task 3：从密码凭证到当前用户

#### 学习目标

- **掌握什么：** JWT 签名、`sub`、`exp`、OAuth2 Bearer、当前用户依赖、401。
- **真实用途：** 把无状态 Token 还原成数据库中的当前有效用户。
- **数据流：** `邮箱/密码 → authenticate_user → JWT → Bearer Header → get_current_user → UserRead`。
- **迁移场景：** 所有需要登录身份的商品、RAG、Agent 和报告接口。
- **完成标准：** 能独立实现登录、Token 校验和 `/auth/me`。

**文件：**

- 修改：`pyproject.toml`
- 修改：`.env.example`
- 修改：`backend/app/core/config.py`
- 修改：`backend/app/core/security.py`
- 创建：`backend/app/schemas/auth.py`
- 创建：`backend/app/api/dependencies.py`
- 创建：`backend/app/api/v1/auth.py`
- 修改：`backend/app/main.py`
- 创建：`tests/api/test_auth.py`
- 扩展：`tests/unit/core/test_security.py`

**接口：**

- `create_access_token(user_id: int, secret: SecretStr, expires_minutes: int) -> str`
- `decode_access_token(token: str, secret: SecretStr) -> int`
- `authenticate_user(session: AsyncSession, email: str, password: str) -> User`
- `get_current_user(token: str, session: AsyncSession) -> User`

- [ ] 添加 `PyJWT` 与 `python-multipart`；配置 `jwt_secret: SecretStr | None` 和 `access_token_expire_minutes: int = 30`。
- [ ] 先写 JWT RED：Token 包含字符串 `sub`、过期 Token 被拒绝、篡改签名被拒绝、密钥不出现在 repr。
- [ ] 使用固定算法白名单实现 JWT 创建和解析，不从 Token Header 动态选择算法。
- [ ] 先写登录 API RED：正确凭证返回 Bearer Token，错误邮箱和错误密码返回相同 401，响应带 `WWW-Authenticate: Bearer`。
- [ ] 实现 `authenticate_user()`；用户不存在时执行虚拟密码校验，停用用户不签发 Token。
- [ ] 实现 `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")`、`get_current_user()` 和 `/auth/me`，并在应用工厂注册 auth router。
- [ ] API 测试使用真实 MySQL 会话依赖覆盖；验证无 Token、过期 Token、停用用户和有效用户。
- [ ] 本人练习：亲手添加“Token 的用户 ID 不存在”测试，并让依赖返回 401；解释为何 Token 签名正确仍可能无效。
- [ ] 运行完整质量门禁并提交：`feat: add JWT authentication`。

---

### Task 4：从当前用户到受保护接口

#### 学习目标

- **掌握什么：** 认证与授权、依赖工厂、Admin CRUD、统一异常处理、故障边界。
- **真实用途：** 确保用户只能调用角色允许的业务接口，并返回可追踪的稳定错误。
- **数据流：** `Bearer Token → current_user → require_roles → users router → Service → MySQL`。
- **迁移场景：** 商品管理、知识库管理、Agent 执行和报告访问控制。
- **完成标准：** 能独立保护新接口、解释 401/403，并测试越权和数据库故障。

**文件：**

- 修改：`backend/app/api/dependencies.py`
- 创建：`backend/app/api/v1/users.py`
- 修改：`backend/app/main.py`
- 修改：`backend/app/core/errors.py`
- 创建：`backend/app/core/exception_handlers.py`
- 创建：`tests/api/test_users.py`
- 创建：`tests/api/test_errors.py`
- 修改：`docs/learning/phase-1-users-auth.md`
- 修改：`docs/plans/phase-1-users-auth.md`

**接口：** `require_roles(*allowed_roles: Role)` 返回一个异步 FastAPI 依赖；该依赖接收 `get_current_user()` 的 `User`，允许角色时返回该用户，否则抛出 `PERMISSION_DENIED`。

路由契约：

```text
POST   /api/v1/users
GET    /api/v1/users?page=1&page_size=20
GET    /api/v1/users/{user_id}
PATCH  /api/v1/users/{user_id}
DELETE /api/v1/users/{user_id}
```

- [ ] 先写 RBAC RED：Admin 成功，Operator/Analyst 返回 403，无 Token 返回 401。
- [ ] 实现 `require_roles(Role.ADMIN)` 依赖并一次性保护整个 users router。
- [ ] 注册用户管理路由，连接 Task 2 的 Service；`DELETE` 只设置 `is_active=False`。
- [ ] 先写统一错误 RED，精确断言 `code`、`message`、`request_id` 和 HTTP 状态。
- [ ] 注册 `AppError`、请求校验异常和数据库不可用异常处理器；不得返回 SQL 或连接串。
- [ ] API 测试覆盖创建、重复邮箱、列表分页、读取、更新、停用、重新启用、自停用拒绝和密码哈希不泄露。
- [ ] 在数据库调用边界模拟连接异常，验证 503；正常路径仍使用真实 MySQL。
- [ ] 本人练习：亲手编写 Analyst 访问用户列表返回 403 的测试，再亲手把一个练习接口从 Admin-only 改为 `Admin | Analyst` 并解释适用场景。
- [ ] 手工验收：Alembic 升级、CLI 创建 Admin、登录、Swagger 授权、创建 Operator、验证越权与停用。
- [ ] 口述验收：Model/Schema、Session/Transaction、迁移、哈希/JWT、401/403、RBAC、测试回滚和数据库故障。
- [ ] 运行完整质量门禁并提交：`docs: complete phase 1 learning gate`。
- [ ] 推送 `phase/1-users-auth`，等待本人明确验收；不得自动合并 `main` 或创建标签。

## 阶段 1 完成门禁

只有四个 Task 全部通过聚焦测试、真实 MySQL 集成测试、完整 pytest、Ruff、mypy、手工运行和本人学习验收，阶段分支已推送，并得到本人明确确认后，阶段 1 才算完成。
