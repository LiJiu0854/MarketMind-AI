# 阶段 1：用户、数据库与认证学习手册

## 这份文档为谁编写

本文假设学习者第一次系统学习 Python 后端工程。首次出现的语法、对象和调用关系必须解释；已经完整讲过的重复代码，只说明在哪里复用、怎样调用。

阶段目标不是“看过代码”或“记住答案”，而是达到四层掌握：

1. **看懂：** 能说出一段代码接收什么、返回什么；
2. **会用：** 知道业务代码应该调用哪个入口；
3. **会写：** 能根据需求自己写出核心代码；
4. **会迁移：** 需求换成商品、报告或 Agent 任务时，仍能使用同一模式。

## 后续 Task 的学习驱动开发规则

从现在开始，每个 Task 不再一次性实现完再提问，而是拆成多个小节。每个小节严格按以下顺序推进：

```text
真实问题
  → 画出本节数据流
  → 解释准备使用的语法和组件
  → 先写失败测试（RED）
  → 学习者亲手写关键代码
  → 逐段讲解实现
  → 运行测试进入 GREEN
  → 改变条件，完成迁移练习
```

我负责项目架构、机械性代码、风险控制和代码审查；学习者必须亲手完成每个 Task 的核心代码练习。只有“能解释 + 能运行 + 能仿写”同时通过，Task 才能验收。

---

# Task 1：从 Python 对象到 MySQL 表

## 1. 最终要解决的真实问题

MarketMind AI 需要保存内部用户。如果只有 Python 中的 `User` 类，程序退出后数据就消失；如果只在 MySQL 中手工建表，其他开发环境又无法知道应该创建什么结构。

Task 1 同时解决两个问题：

- SQLAlchemy 负责让 Python 代码读写 MySQL；
- Alembic 负责让数据库结构能够升级、审查和回滚。

完整链路是：

```text
.env 中的连接串
  → Settings 读取并保护秘密
  → AsyncEngine 管理数据库连接池
  → Connection 承载一次真实连接
  → AsyncSession 管理 ORM 对象和 SQL
  → Transaction 决定提交或回滚
  → User Model 描述 users 表目标结构
  → Alembic 比较目标结构与真实结构
  → Migration 修改 MySQL
```

## 2. 阅读代码前必须知道的 Python 语法

### 2.1 类型标注不是赋值

```python
database_url: SecretStr | None = None
```

从左到右解释：

- `database_url`：属性名；
- `:`：后面开始写类型；
- `SecretStr | None`：值可以是 `SecretStr`，也可以没有值；
- `=`：设置默认值；
- `None`：默认没有配置。

类型标注帮助编辑器、mypy 和读代码的人理解数据形状。真正负责从环境变量读取并转换数据的是 Pydantic Settings。

### 2.2 函数参数和返回类型

```python
def create_engine(database_url: SecretStr) -> AsyncEngine:
```

- 函数名是 `create_engine`；
- 调用者必须传入一个 `SecretStr`；
- `-> AsyncEngine` 表示函数承诺返回 `AsyncEngine`；
- 函数只有在被调用时才执行。

### 2.3 class 是对象模板

```python
class User(Base):
```

`User` 是类名，`Base` 是父类。继承 `Base` 后，SQLAlchemy 才会把 `User` 当作 ORM Model，并把字段登记到共同的 `metadata` 中。

### 2.4 async 和 await

数据库访问需要等待网络和 MySQL 响应。`async def` 定义异步函数，`await` 表示当前任务暂停等待，但程序仍可处理其他异步任务。

```python
stored_user = await session.scalar(select(User))
```

这里必须 `await`，因为查询结果不是立即产生的。

## 3. 为什么按这个顺序开发

Task 1 的真实开发顺序如下：

```text
依赖
  → 配置测试与配置字段
  → Engine/Session 测试与工厂
  → User Model 测试与实现
  → Alembic 配置
  → 初始迁移
  → 测试库升级、回滚、恢复
  → 真实事务隔离测试
```

这个顺序不是唯一语法顺序，而是最短的“每一步都能验证”顺序。

### 第 1 步：先安装依赖

涉及文件：`pyproject.toml`

```toml
"alembic>=1.16,<2.0",
"asyncmy>=0.2,<1.0",
"cryptography>=42,<47",
"sqlalchemy[asyncio]>=2.0,<3.0",
```

各依赖的职责：

| 依赖 | 职责 |
| --- | --- |
| SQLAlchemy | ORM、SQL 生成、Engine、Session、Transaction |
| asyncmy | SQLAlchemy 与 MySQL 之间的异步驱动 |
| Alembic | 数据库结构版本管理 |
| cryptography | 支持 MySQL 8 默认安全认证需要的 RSA 加密 |

为什么最先做：后面的 import 和测试都依赖这些包。没有依赖时，失败只说明“模块不存在”，还不能验证业务代码。

### 第 2 步：先测试配置，再添加配置字段

涉及文件：

- `tests/unit/core/test_config.py`
- `backend/app/core/config.py`
- `.env.example`

先写测试：

```python
def test_database_urls_are_secret_and_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "mysql+asyncmy://user:not-a-real-password@localhost/marketmind"
    monkeypatch.setenv("DATABASE_URL", database_url)

    settings = Settings()

    assert isinstance(settings.database_url, SecretStr)
    assert database_url not in repr(settings)
    assert settings.test_database_url is None
```

逐段解释：

1. `monkeypatch.setenv()` 只为当前测试设置临时环境变量，不修改真实 `.env`；
2. `Settings()` 创建配置对象，此时 Pydantic 才读取环境变量；
3. 第一个断言验证普通字符串被转换成 `SecretStr`；
4. 第二个断言验证调试输出不会泄露连接串；
5. 第三个断言保证没有人为配置测试库时，不会偷偷连接某个默认数据库。

这时运行测试会失败，因为 `Settings` 还没有数据库字段。这就是 RED：失败原因正好证明待实现能力不存在。

最小实现只有两行：

```python
database_url: SecretStr | None = None
test_database_url: SecretStr | None = None
```

为什么使用 `SecretStr`：`repr(settings)`、错误日志和调试器通常会显示对象内容。秘密类型默认遮盖值，降低密码意外进入日志的风险。

为什么允许 `None`：有些命令只运行单元测试，不需要数据库。若应用一 import 就强制要求数据库连接串，这些无关测试也会失败。真正需要数据库时再检查配置是否存在。

为什么下一步才写 Engine：Engine 需要连接串；配置入口没有确定前，Engine 不知道从哪里取得参数。

### 第 3 步：先测试 Engine/Session 工厂，再实现它们

涉及文件：

- `tests/unit/db/test_session.py`
- `backend/app/db/session.py`

先写的测试只验证对象契约，不连接 MySQL：

```python
engine = create_engine(
    SecretStr("mysql+asyncmy://user:not-a-real-password@localhost/database")
)
session_factory = create_session_factory(engine)

assert isinstance(engine, AsyncEngine)
assert session_factory.class_ is AsyncSession

await engine.dispose()
```

为什么虚假连接串也能测试：`create_async_engine()` 默认只创建 Engine 和连接池配置，尚未真正借出 Connection；第一次连接或执行 SQL 时才访问 MySQL。

为什么最后 `dispose()`：Engine 可能持有连接池资源。测试主动释放资源，避免后续出现未关闭连接或事件循环警告。

实现代码：

```python
def create_engine(database_url: SecretStr) -> AsyncEngine:
    return create_async_engine(
        database_url.get_secret_value(),
        pool_pre_ping=True,
    )
```

逐行解释：

- 参数仍保持 `SecretStr`，调用者不能误把秘密当普通字符串打印；
- `get_secret_value()` 只在必须把连接串交给 SQLAlchemy 的边界解密；
- `create_async_engine()` 依据 URL 中的 `mysql+asyncmy` 选择 MySQL 方言和 asyncmy 驱动；
- `pool_pre_ping=True` 在复用连接前做存活检查，避免 MySQL 已断开但连接池仍返回旧连接。

Session 工厂：

```python
def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

逐行解释：

- 参数是已经配置好的 Engine；
- `async_sessionmaker` 是“生产 Session 的工厂”，不是 Session 本身；
- 同一个工厂可以为多个请求分别创建 Session；
- `expire_on_commit=False` 表示提交后对象字段仍可读取，API 组装响应时不会因为字段过期再次隐式查询数据库。

四个容易混淆的对象：

| 对象 | 简单理解 | 生命周期 |
| --- | --- | --- |
| `AsyncEngine` | 数据库入口和连接池管理员 | 通常跟应用一样长 |
| `Connection` | 从连接池借出的一条真实连接 | 一次操作或事务 |
| `AsyncSession` | 管理 ORM 对象并组织 SQL | 通常一个请求一个 |
| `Transaction` | 决定一组 SQL 提交还是回滚 | 一组必须保持一致的操作 |

为什么下一步才写 Model：Engine 和 Session 解决“怎样访问数据库”；Model 接下来解决“要访问什么表和字段”。

### 第 4 步：先定义共同 Base，再测试和实现 User Model

涉及文件：

- `backend/app/db/base.py`
- `tests/unit/models/test_user.py`
- `backend/app/models/user.py`

共同 Base：

```python
class Base(DeclarativeBase):
    """所有 ORM Model 共用的元数据入口。"""
```

`DeclarativeBase` 是 SQLAlchemy 提供的 ORM 声明基类。`User`、未来的 `Product` 和 `Report` 都继承同一个 `Base`，Alembic 才能从一份 metadata 中看到全部表。

先写 Model 契约测试：

```python
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

这个测试不连接 MySQL，只检查 Python Model 的结构。如果有人误删字段或改动角色值，测试立即失败。

角色定义：

```python
class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
```

`StrEnum` 同时具有枚举和字符串特性：代码中使用 `Role.ADMIN` 避免拼写错误，写入数据库时保存稳定字符串 `admin`。

```python
def _role_values(role_type: type[Role]) -> list[str]:
    return [role.value for role in role_type]
```

SQLAlchemy 默认可能使用枚举成员名 `ADMIN`。`values_callable` 调用这个函数后，数据库保存明确约定的值 `admin`、`operator`、`analyst`。函数名前的 `_` 表示它只服务于本模块，不是给业务层调用的公开接口。

User Model 的核心结构：

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
```

语法拆解：

- `Mapped[int]` 表示对象属性在 Python 中是整数，并且由 ORM 管理；
- `mapped_column()` 描述对应数据库列；
- `primary_key=True` 把 `id` 设为主键；
- `autoincrement=True` 让 MySQL 自动生成递增 ID；
- `String(320)` 对应最大长度 320 的字符串列；
- `unique=True` 要求邮箱不能重复；
- `index=True` 为邮箱创建索引，加快按邮箱登录查询；
- 数据库保存 `password_hash`，永远不保存明文密码。

角色字段：

```python
role: Mapped[Role] = mapped_column(
    Enum(
        Role,
        name="user_role",
        native_enum=False,
        length=20,
        create_constraint=True,
        values_callable=_role_values,
    )
)
```

- Python 侧类型是 `Role`；
- `native_enum=False` 使用普通字符串列，而不是依赖 MySQL 专用 ENUM；
- `create_constraint=True` 让数据库也限制合法角色；
- `length=20` 给字符串列明确长度；
- `values_callable` 决定保存小写值。

状态和时间字段：

```python
is_active: Mapped[bool] = mapped_column(
    Boolean,
    default=True,
    server_default=true(),
)
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
)
```

`default=True` 是 ORM 创建对象时的默认值；`server_default=true()` 是数据库收到没有该字段的 INSERT 时使用的默认值。两层默认值保护不同入口。

`server_default=func.now()` 让数据库创建记录时填写时间。`onupdate=func.now()` 让 SQLAlchemy 通过 ORM 更新该对象时生成更新时间表达式。

为什么 Model 后才配置 Alembic：Alembic 自动生成迁移需要读取 Model 的 metadata。没有目标结构，它不知道应该生成什么表。

### 第 5 步：配置 Alembic 读取 Model 和正确数据库

涉及文件：`alembic/env.py`

Alembic 初始化命令先生成通用异步模板：

```powershell
.venv\Scripts\alembic.exe init -t async alembic
```

模板负责建立异步连接和运行迁移。本项目真正新增的关键逻辑是数据库选择：

```python
settings = Settings()
database_target = context.get_x_argument(as_dictionary=True).get(
    "database", "development"
)
if database_target not in {"development", "test"}:
    raise RuntimeError("database 只能是 development 或 test")
```

运行普通命令时没有 `-x` 参数，因此目标默认是 `development`。运行：

```powershell
.venv\Scripts\alembic.exe -x database=test current
```

Alembic 会把 `database=test` 放入扩展参数字典。集合判断拒绝拼错或未知目标，避免静默连接错误数据库。

选择连接串：

```python
database_url = (
    settings.test_database_url
    if database_target == "test"
    else settings.database_url
)
```

这是条件表达式：目标是测试库就使用 `TEST_DATABASE_URL`，否则使用 `DATABASE_URL`。

```python
if database_url is None:
    variable_name = (
        "TEST_DATABASE_URL" if database_target == "test" else "DATABASE_URL"
    )
    raise RuntimeError(f"{variable_name} 未配置，Alembic 无法连接数据库")
```

这里在真正需要数据库的边界检查 `None`，并告诉使用者缺少哪个变量。配置类本身仍允许无数据库场景运行。

```python
config.set_main_option(
    "sqlalchemy.url",
    database_url.get_secret_value().replace("%", "%%"),
)
target_metadata = User.metadata
```

- 第一段把运行时连接串交给 Alembic，密码没有写入 `alembic.ini`；
- `%` 在配置解析中有特殊含义，替换成 `%%` 防止合法连接串被错误插值；
- `target_metadata` 告诉 Alembic 应拿哪份 Model 结构与数据库比较；
- 导入 `User` 同时保证 Python 已执行 User 类定义，`users` 表已经登记到 metadata。

模板中的 `run_async_migrations()`、`run_migrations_online()` 是 Alembic 官方异步模板代码。现阶段只需会调用和知道它们负责“建 Engine → 取 Connection → 执行迁移”，不要求背写模板。

### 第 6 步：自动生成迁移，但必须人工检查

生成命令：

```powershell
.venv\Scripts\alembic.exe revision --autogenerate --rev-id 0001 -m "create users table"
```

Alembic 比较：

```text
User.metadata 中的目标结构  ↔  MySQL 当前实际结构
```

迁移版本头：

```python
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
```

- `revision` 是本迁移 ID；
- `down_revision` 指向上一版本；
- `0001` 是第一份迁移，所以没有上一版本。

`upgrade()` 使用 `op.create_table()` 创建 `users` 表，再用 `op.create_index()` 创建唯一邮箱索引。`downgrade()` 按相反顺序删除索引和表。

为什么不能只相信自动生成：Alembic 能检测大部分结构变化，但不知道业务意图。例如“删除旧字段再新增字段”和“给字段改名”在结果上可能相似，前者可能丢失数据。每份迁移都必须人工审查。

为什么以后不能修改已经执行过的 `0001`：数据库只记录“我执行过 0001”，不会自动重新运行内容发生变化的旧文件。新变化必须创建 `0002`，让版本历史保持可追踪。

### 第 7 步：先在测试库验证升级和回滚

执行顺序：

```powershell
.venv\Scripts\alembic.exe -x database=test upgrade head
.venv\Scripts\alembic.exe -x database=test current
.venv\Scripts\alembic.exe -x database=test downgrade base
.venv\Scripts\alembic.exe -x database=test upgrade head
```

- 第一次升级证明空测试库能创建结构；
- `current` 证明数据库记录的版本是 `0001`；
- 回滚证明 `downgrade()` 可执行；
- 最后恢复到 head，供后续集成测试使用。

MySQL 输出 `Will assume non-transactional DDL`，表示建表、删表等 DDL 不应被当作普通业务事务依赖自动回滚。因此更需要先在测试库验证迁移。

### 第 8 步：真实事务集成测试

单元测试只能证明 Python 对象结构正确。最后必须连接真实 MySQL，证明驱动、SQL、表结构和事务共同工作。

测试 Engine 夹具首先建立安全边界：

```python
database_url = Settings().test_database_url
if database_url is None:
    pytest.fail("TEST_DATABASE_URL 未配置")
if make_url(database_url.get_secret_value()).database != "marketmind_test":
    pytest.fail("集成测试只能连接 marketmind_test")
```

- `pytest.fail()` 立即让测试失败，并提供清晰原因；
- `make_url()` 解析连接串，不用自己切割字符串；
- 数据库名必须精确是 `marketmind_test`，避免测试误写开发库。

```python
engine = create_engine(database_url)
yield engine
await engine.dispose()
```

异步 fixture 在 `yield` 前准备资源，把 Engine 交给测试；测试结束后从 `yield` 后继续执行，释放 Engine。

事务测试的关键代码：

```python
async with test_engine.connect() as connection:
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
```

- `async with` 保证离开代码块时归还 Connection；
- `begin()` 开启外层事务；
- `bind=connection` 强制 Session 使用这条 Connection，因此 Session 的 SQL 都属于外层事务。

```python
session.add(user)
await session.flush()
```

`add()` 只把对象放进 Session；`flush()` 才真正发送 INSERT。因为没有 commit，数据目前只存在于当前事务。

```python
stored_user = await session.scalar(
    select(User).where(User.email == email)
)
```

- `select(User)` 表示查询 User 对象；
- `.where()` 添加邮箱条件；
- `scalar()` 取查询结果中的第一个 ORM 对象。

```python
finally:
    await session.close()
    await transaction.rollback()
```

`finally` 无论断言成功还是失败都会执行。先关闭 Session，再回滚外层事务，测试插入的数据不会永久保留。

最后用新 Connection 查询数量为 0。这个检查同时证明两件事：前面的 `flush()` 确实执行了 SQL，后面的 `rollback()` 也确实清除了事务数据。

## 4. 怎样把 Task 1 迁移到其他业务

以后新增 Product、Report 或 AgentTask 时，固定复用流程是：

1. 把业务字段和数据库约束写成 Model 契约测试；
2. 运行测试看到 RED；
3. 新 Model 继承共同 `Base`；
4. 运行单元测试进入 GREEN；
5. 确保 Alembic 加载新 Model；
6. 生成新的 revision；
7. 人工检查 upgrade/downgrade；
8. 在测试库升级、回滚、恢复；
9. 写真实事务测试；
10. 运行完整质量门禁。

不会变化的代码：Base、Engine 工厂、Session 工厂和测试库安全检查。需要变化的是 Model 字段、约束、迁移内容和业务测试数据。

## 5. Task 1 动手练习

练习必须按顺序完成。不要一次做完；每完成一题，把代码和测试结果交给我检查，再进入下一题。

### 练习 1：补写现有 Model 约束测试

目标：从“知道 User 有 email 字段”进步到“能用测试确认字段约束”。

你需要亲手修改 `tests/unit/models/test_user.py`，增加一个新测试，验证：

- `email` 列具有唯一约束；
- `email` 列建立了索引；
- `id` 列是主键。

先通过下面的对象找到列：

```python
User.__table__.columns["email"]
User.__table__.columns["id"]
```

不要修改 `User` Model，因为这些约束已经存在。本练习重点是学习怎样通过测试读取 ORM metadata。

运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\models\test_user.py -v
```

验收标准：你能解释每个断言读取了哪个对象、验证了什么约束。

### 练习 2：补写 Session 工厂配置测试

目标：理解工厂返回的是“如何创建 Session 的配置”，不是已经连接数据库的 Session。

你需要亲手修改 `tests/unit/db/test_session.py`，增加断言，验证 Session 工厂的 `expire_on_commit` 配置是 `False`。

提示：工厂保存的关键字参数位于 `session_factory.kw`。先在调试时查看它包含哪些键，再写精确断言。

运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\db\test_session.py -v
```

验收标准：你能解释为什么 API 返回刚提交的用户时需要这个配置。

### 练习 3：独立仿写 Product Model

目标：把 User Model 的模式迁移到新业务，而不是复制答案。

创建临时文件 `tests/unit/models/test_product_practice.py`。这个文件只用于学习，Task 1 验收后不进入正式提交。

你需要在这个文件中独立完成：

1. 定义仅供练习使用的 `PracticeBase`；
2. 定义 `Product` Model，表名为 `product_practice`；
3. 字段包含自增整数主键 `id`、唯一且有索引的 `sku`、长度 200 的 `name`、默认启用的 `is_active`；
4. 编写测试验证表名、字段集合、主键和 SKU 约束；
5. 本练习不连接数据库、不生成真实迁移。

你可以从这些 import 开始，但 Model 主体和断言必须自己写：

```python
from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
```

运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\models\test_product_practice.py -v
```

验收标准：不看 User Model 时，也能说明 `Mapped`、`mapped_column`、主键、唯一约束和索引各自的作用。

### 练习 4：迁移阅读与运行

亲手执行：

```powershell
.venv\Scripts\alembic.exe -x database=test current
.venv\Scripts\alembic.exe -x database=test history
```

阅读 `alembic/versions/0001_create_users_table.py` 后，用自己的话回答：

1. 修改 User Model 后，为什么现有 MySQL 表不会自动改变？
2. `revision` 和 `down_revision` 怎样形成版本顺序？
3. 为什么自动生成迁移后还必须人工审查？
4. 为什么测试库可以回滚验证，而生产库不能随意尝试？

#### 练习 4 参考答案（已校正）

**1. 修改 User Model 后，为什么现有 MySQL 表不会自动改变？**

SQLAlchemy Model 是 Python 中的目标结构，MySQL 表是数据库中已经存在的物理结构。修改 Model 只会改变 `Base.metadata`，不会自动执行 `ALTER TABLE`。

这种分离是必要的：如果程序启动时自动同步表结构，一次字段误删或类型误改就可能直接破坏数据。正确流程是让 Alembic 比较 Model 与数据库的差异，生成迁移脚本，人工审查后再执行。

**2. `revision` 和 `down_revision` 怎样形成版本顺序？**

`revision` 是当前迁移的唯一字符串标识，不一定是哈希；本项目第一份迁移人为指定为 `0001`。`down_revision` 指向当前迁移所依赖的上一版本：

```text
0001：down_revision = None
0002：down_revision = "0001"
0003：down_revision = "0002"
```

当前项目因此形成线性顺序。大型项目可能同时产生两个分支，再通过合并迁移汇合，所以 Alembic 的完整历史本质上是有向无环图，不保证永远是一条单链。

**3. 为什么自动生成迁移后还必须人工审查？**

Alembic 能比较结构差异，但不知道业务意图。例如把字段改名时，它可能生成“删除旧字段 + 新增字段”，导致旧数据丢失；数据清洗、复杂默认值和数据搬迁逻辑也通常不能完整自动生成。

人工审查至少确认：

- `upgrade()` 只修改预期对象；
- `downgrade()` 与本次修改对应；
- 没有意外删表、删列或改变约束；
- 大表索引和字段变更不会造成不可接受的锁表时间；
- 需要保留的旧数据具有明确迁移方式。

**4. 为什么测试库可以回滚验证，而生产库不能随意尝试？**

测试库没有真实业务数据，失败后可以重建，因此适合验证升级和回滚脚本。生产库可以在必要时执行经过验证的回滚，但不能把生产环境当作试验场。

生产回滚可能删除新字段中的数据、锁表或中断服务；MySQL 的部分 DDL 还不能依赖普通事务自动撤销。因此生产迁移前必须完成测试库验证、备份、影响评估和恢复方案。有些已写入新格式数据的变更，使用新的前向修复迁移会比执行 `downgrade()` 更安全。

### 练习 5：完整迁移题

不用实际修改正式 User Model，先写出你的操作顺序：如果需求要求给用户增加一个可为空的 `last_login_at` 字段，你会先改哪个测试、怎样修改 Model、怎样生成 `0002`、怎样在测试库验证升级和回滚。

验收重点不是命令背诵，而是顺序中必须包含 RED、Model、迁移审查、测试库回滚和完整质量检查。

#### 练习 5 参考答案（已校正）

**第 1 步：先写 Model 契约 RED 测试**

在 `tests/unit/models/test_user.py` 新增测试，要求 `User` 包含 `last_login_at`，并且该列允许 `NULL`。此时 Model 还没有字段，测试应当失败。

这一步只验证 Python Model 的目标结构，不连接 MySQL。

**第 2 步：修改 User Model 进入 GREEN**

项目使用 Python 3.12 的联合类型写法：

```python
last_login_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True),
    nullable=True,
)
```

`datetime | None` 表示 Python 属性允许没有值，`nullable=True` 表示数据库列允许 `NULL`。重新运行 Model 单元测试，预期进入 GREEN。

**第 3 步：生成明确编号的 0002 迁移**

先确认开发数据库已经位于 `0001 (head)`，然后运行：

```powershell
.venv\Scripts\alembic.exe current
.venv\Scripts\alembic.exe revision --autogenerate --rev-id 0002 -m "add user last login time"
```

显式指定 `--rev-id 0002`，使本项目迁移编号保持清晰、连续。

**第 4 步：人工审查迁移**

确认 `upgrade()` 只为 `users` 表增加可空的 `last_login_at`，`downgrade()` 只删除该列；不能出现其他字段、索引或表的意外变化。

还要确认：已有用户没有登录时间时可以保存为 `NULL`，因此这次迁移不需要先为历史数据填充值。

**第 5 步：在测试库验证升级**

```powershell
.venv\Scripts\alembic.exe -x database=test upgrade head
.venv\Scripts\alembic.exe -x database=test current
```

此时测试库和 Model 都位于 0002，可以运行单元测试和真实数据库集成测试，验证新字段可为空且现有用户写入不受影响。

**第 6 步：验证回滚，再立即恢复**

```powershell
.venv\Scripts\alembic.exe -x database=test downgrade 0001
.venv\Scripts\alembic.exe -x database=test current
```

此时应检查测试库版本回到 0001，并确认真实表已经没有 `last_login_at`。不能期待 Model 单元测试失败，因为它只检查 Python Model，完全不读取数据库。

数据库处于 0001 而代码 Model 处于 0002 时，两者暂时不一致，不应运行依赖该字段的完整应用测试。验证回滚后立即恢复：

```powershell
.venv\Scripts\alembic.exe -x database=test upgrade head
```

**第 7 步：运行完整质量门禁**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
git diff --check
```

只有测试库恢复到 head 且全部检查通过，0002 才具备提交条件。生产执行前还需要备份、评估锁表时间、选择低峰窗口并准备经过验证的恢复方案。


## 6. Task 1 验收门禁

只有满足以下条件，Task 1 才能提交：

- 练习 1、2 的代码通过测试；
- 练习 3 能独立仿写并通过测试；
- 练习 4 能读懂迁移并回答问题；
- 练习 5 能给出完整开发顺序；
- 能画出 Settings 到 MySQL 的数据流；
- 完整 pytest、Ruff、mypy 和 `git diff --check` 全部通过。

当前状态：**Task 1 正式代码、动手练习、文字答案和质量门禁均已验证；临时 Product 练习文件保留在本地，不进入正式提交。**
