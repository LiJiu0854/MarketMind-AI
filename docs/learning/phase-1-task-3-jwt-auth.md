# Phase 1 · Task 3：JWT 登录与当前用户

## Task 业务目标

本 Task 完成从账号密码到当前登录用户的完整链路：

```text
邮箱 + 密码
    ↓ authenticate_user
有效 User
    ↓ create_access_token
JWT Bearer Token
    ↓ get_current_user
数据库中的当前有效 User
    ↓ /auth/me
安全 UserRead
```

完成后，你应能解释 Token 为什么可以无状态传递身份，以及为什么“签名正确”仍不代表当前用户一定有效。

## 四个实现单元

1. JWT 配置、签名和解析；
2. 登录数据结构与凭证认证；
3. 数据库 Session 和当前用户依赖；
4. `/auth/token`、`/auth/me` 路由与 API 测试。

四个单元按顺序验收，不提前实现 Task 4 的 RBAC 和用户管理 API。

---

# 实现单元 1：JWT 配置、签名与解析

## 【1】本单元业务目标

把整数用户 ID 放入一个有签名、有过期时间的 Token，并安全还原：

```text
user_id=42 + JWT_SECRET + 30分钟
        ↓ create_access_token
header.payload.signature
        ↓ decode_access_token（只允许 HS256）
user_id=42
```

必须拒绝两种 Token：已过期、签名被篡改。

## 【2】知识点分层

### 🔴 必须手写掌握

- 在 Settings 中声明可选 `SecretStr` 密钥和默认有效期；
- JWT 的 `sub` 写成字符串；
- 使用 UTC 当前时间计算 `exp`；
- 使用固定 `HS256` 创建 Token；
- 解码时传入固定 `algorithms=["HS256"]`；
- 把字符串 `sub` 转回整数用户 ID；
- 让过期与签名错误继续以 PyJWT 标准异常抛出。

### 🟡 理解原理即可

- JWT 只是签名，不是加密，载荷可以被读取；
- `sub` 表示主体身份，JWT 标准要求它是字符串；
- `exp` 由解码器自动验证；
- 算法白名单防止攻击者从 Token Header 指定不安全算法。

### 🔵 了解用途

- 单元 3 会把 PyJWT 异常统一转换为 HTTP 401；
- Task 4 才会使用角色做 403 授权判断；
- 当前不实现刷新 Token 和 Token 黑名单。

### 开始前只需自行查询的基础知识名称

- Python：`datetime`、`timedelta`、UTC；
- Python：字典、异常；
- Pydantic：`SecretStr`；
- JWT：Header、Payload、Signature、`sub`、`exp`；
- PyJWT：`encode()`、`decode()`、`ExpiredSignatureError`。

## 【3】文件树 + 骨架代码

```text
MarketMind-AI/
├─ .env.example
├─ pyproject.toml
├─ backend/app/core/
│  ├─ config.py
│  └─ security.py
└─ tests/unit/core/
   ├─ test_config.py
   └─ test_security.py
```

`backend/app/core/config.py` 当前骨架：

```python
class Settings(BaseSettings):
    # 已有配置省略

    # TODO: 学习者声明 jwt_secret 和 access_token_expire_minutes
```

字段合同：

| 字段 | 类型 | 默认值 |
|---|---|---|
| `jwt_secret` | `SecretStr | None` | `None`，禁止内置生产密钥 |
| `access_token_expire_minutes` | `int` | `30` |

`backend/app/core/security.py` 当前骨架：

```python
def create_access_token(
    user_id: int, secret: SecretStr, expires_minutes: int
) -> str:
    """创建包含用户 ID 和过期时间的 JWT。"""
    # TODO: 学习者实现固定 HS256 算法的 Token 创建
    raise NotImplementedError


def decode_access_token(token: str, secret: SecretStr) -> int:
    """验证 JWT 并返回整数用户 ID。"""
    # TODO: 学习者使用固定算法白名单解码并验证字符串 sub
    raise NotImplementedError
```

测试已经完整提供，不要修改测试去迁就实现。它们验证：

```text
JWT_SECRET 没有默认值且不会出现在 repr
默认有效期为 30 分钟
Token 的 sub 是字符串 "42"
正常 Token 可以还原整数 42
过期 Token 抛出 ExpiredSignatureError
篡改签名抛出 InvalidSignatureError
```

## 【4】编写顺序 + 当前依赖

新增依赖：

```toml
"PyJWT>=2.10,<3.0"
"python-multipart>=0.0.20,<1.0"
```

`python-multipart` 在单元 4 接收 OAuth2 表单时使用；Task 3 不再增加其他第三方依赖。

编写顺序：

1. 完成 Settings 的两个字段；
2. 只运行配置测试；
3. 在 `security.py` 导入 UTC 时间工具和 PyJWT；
4. 定义一个固定算法常量；
5. 实现 Token 创建；
6. 实现 Token 解码和 `sub` 类型转换；
7. 删除 TODO 与 `NotImplementedError`；
8. 运行全部聚焦检查。

## 【5】RED/GREEN 验证 + 完成标准

当前第一层 RED：

```text
ModuleNotFoundError: No module named 'jwt'
```

依赖安装并保留骨架后，RED 应转为缺少 Settings 字段和 `NotImplementedError`。

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\core\test_config.py tests\unit\core\test_security.py -v
.venv\Scripts\ruff.exe check backend\app\core tests\unit\core
.venv\Scripts\mypy.exe backend\app\core tests\unit\core
```

完成标准：15 个相关测试通过；Ruff、mypy 通过；你能解释为什么不能从 Token Header 动态选择算法。

完成后回复：

```text
【Task 3 单元 1 编码完成】
```

## 单元 1 验收与参考实现

验收结果：15 个测试通过，Ruff 与 mypy 通过，无安全警告。

你本单元实际掌握的调用关系：

```text
Settings.jwt_secret
        ↓ SecretStr.get_secret_value()
create_access_token(user_id, secret, minutes)
        ↓ 写入字符串 sub 和 UTC exp
jwt.encode(..., algorithm="HS256")
        ↓
decode_access_token(token, secret)
        ↓ 固定 algorithms=["HS256"] 并验证 exp
int(payload["sub"])
```

参考实现位于 `backend/app/core/security.py`。重点不是背整段代码，而是能独立复现以下四步：计算 UTC 过期时间、构造 Payload、固定算法签名、验证后把 `sub` 转回整数。

---

# 实现单元 2：登录响应与凭证认证

## 【1】本单元业务目标

本单元暂时不创建 HTTP 路由，只完成登录链路中可复用的业务核心：

```text
邮箱 + 明文密码
      ↓ authenticate_user
规范化邮箱并查询 users 表
      ↓
Argon2 验证密码
      ↓
检查 is_active
      ↓
返回 User 或抛出稳定 AppError
```

同时定义登录成功后 HTTP 层将使用的 Token 响应合同：

```json
{"access_token": "签名后的JWT", "token_type": "bearer"}
```

## 【2】知识点分层

### 🔴 必须手写掌握

- 使用与创建用户相同的 `_normalize_email()` 规则查询账号；
- 使用 `select(User).where(...)` 和 `session.scalar()` 查询单个用户；
- 使用 `verify_password()` 验证明文和哈希；
- 邮箱不存在与密码错误返回完全相同的 401 错误；
- 用户不存在时仍执行一次虚拟哈希验证；
- 密码正确后再检查 `is_active`，停用账号返回 403；
- 声明 `TokenResponse` 的两个字段。

### 🟡 理解原理即可

- 统一错误信息用于降低账号枚举风险；
- 虚拟密码验证用于缩小“账号存在/不存在”两条路径的耗时差异；
- Service 返回 ORM `User`，Token 的创建留给后续 HTTP 路由；
- 认证失败是读操作，不需要调用 `commit()` 或 `rollback()`。

### 🔵 了解用途

- 单元 3 会从 Bearer Token 恢复当前用户；
- 单元 4 的 `/auth/token` 会调用本单元函数并签发 JWT；
- Refresh Token、验证码和登录限流不在当前阶段。

### 开始前只需自行查询的基础知识名称

- Python：异步函数、条件判断、常量；
- SQLAlchemy：`select()`、`where()`、`AsyncSession.scalar()`；
- Pydantic：字段默认值、`ConfigDict(extra="forbid")`；
- 安全：账号枚举、时序差异、虚拟密码校验。

## 【3】项目文件树 + 骨架代码

```text
MarketMind-AI/
├─ backend/app/
│  ├─ schemas/auth.py          # 新增 TokenResponse 骨架
│  └─ services/users.py        # 新增 authenticate_user 骨架
├─ tests/
│  ├─ unit/schemas/test_auth.py
│  └─ integration/db/test_user_service.py
└─ docs/learning/phase-1-task-3-jwt-auth.md
```

`backend/app/schemas/auth.py`：

```python
class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # TODO: 学习者声明 access_token 和 token_type
    pass
```

字段合同：

| 字段 | 类型 | 默认值 |
|---|---|---|
| `access_token` | `str` | 无，调用者必须传入 |
| `token_type` | `str` | `"bearer"` |

`backend/app/services/users.py`：

```python
async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> User:
    # TODO: 学习者实现
    raise NotImplementedError
```

实现中还需要一个模块级虚拟密码哈希。它只用于“不存在的账号”路径，绝不能对应真实用户。

## 【4】编写顺序 + 类和函数如何配合

严格按下面顺序写，每一步只解决一个问题：

1. 在 `TokenResponse` 声明必填 `access_token`；
2. 声明默认值为 `"bearer"` 的 `token_type`，删除 `pass`；
3. 在 `users.py` 模块加载时用现有 `hash_password()` 生成一次虚拟哈希；
4. 在 `authenticate_user()` 第一行调用 `_normalize_email(email)`；
5. 使用 `select(User).where(User.email == normalized_email)` 查询；
6. 用户不存在时，用传入密码对虚拟哈希调用一次 `verify_password()`；
7. 用户不存在或密码错误时，抛出相同的 `AppError`：

```text
code="AUTH_INVALID_CREDENTIALS"
message="邮箱或密码错误"
status_code=401
```

8. 密码正确但 `user.is_active` 为假时，抛出：

```text
code="ACCOUNT_INACTIVE"
message="账号已停用"
status_code=403
```

9. 所有检查通过后返回 `user`；
10. 删除 TODO、`pass` 和 `NotImplementedError`。

注意判断顺序：必须先处理 `user is None`，否则访问 `user.password_hash` 会触发 `AttributeError`。

## 【5】RED/GREEN 验证 + 完成标准

当前测试应处于预期 RED：Schema 缺少字段，认证函数抛出 `NotImplementedError`。

先运行快速测试：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\schemas\test_auth.py -v
```

再运行真实 MySQL 认证测试：

```powershell
.venv\Scripts\python.exe -m pytest tests\integration\db\test_user_service.py -v
```

最后检查本单元涉及文件：

```powershell
.venv\Scripts\ruff.exe check backend\app\schemas\auth.py backend\app\services\users.py tests\unit\schemas\test_auth.py tests\integration\db\test_user_service.py
.venv\Scripts\mypy.exe backend\app\schemas\auth.py backend\app\services\users.py tests\unit\schemas\test_auth.py tests\integration\db\test_user_service.py
```

完成标准：Token Schema 的 2 个测试通过；认证成功、统一 401 和停用 403 测试通过；Ruff、mypy 通过。

完成后回复：

```text
【Task 3 单元 2 编码完成】
```

## 单元 2 验收与参考实现

验收结果：14 个相关测试通过，Ruff 与 mypy 通过。

你写出的核心调用链是：

```text
authenticate_user(email, password)
        ↓ _normalize_email
session.scalar(select(User))
        ├─ None：对 DUMMY_PASSWORD_HASH 做虚拟验证 → 统一 401
        ├─ 密码错误：统一 401
        ├─ is_active=False：403
        └─ 全部通过：返回 User
```

`DUMMY_PASSWORD_HASH` 必须在模块加载时只生成一次。如果每次不存在用户都重新执行 Argon2 哈希，不但浪费 CPU，也会让耗时变得更不稳定。

---

# 实现单元 3：数据库 Session 与当前用户依赖

## 【1】本单元业务目标

把客户端携带的 Bearer Token 转换成数据库中仍然存在、仍然启用的用户：

```text
Authorization: Bearer <token>
        ↓ OAuth2PasswordBearer
token 字符串
        ↓ decode_access_token
user_id
        ↓ AsyncSession.get(User, user_id)
User
        ↓ is_active 检查
当前有效用户
```

这一步解释了为什么“Token 签名正确”仍然不等于“允许访问”：用户可能已被删除或停用。

## 【2】知识点分层

### 🔴 必须手写掌握

- 从 `Settings` 读取 `jwt_secret`，不能在代码中写死密钥；
- 调用 `decode_access_token()` 获取整数用户 ID；
- 捕获 PyJWT 的 `InvalidTokenError`；
- 使用 `session.get(User, user_id)` 查询当前用户；
- 无效 Token 和不存在用户统一转换为 401；
- 停用用户转换为 403；
- 成功时返回 ORM `User`，供后续路由继续使用。

### 🟡 理解原理即可

- `OAuth2PasswordBearer` 只负责从请求头提取 Token，不验证签名；
- `Depends` 会自动按依赖关系准备参数；
- `yield` 依赖在响应结束后继续执行，从而关闭 Session；
- `@cache` 让整个进程复用 Engine/连接池，而不是每个请求重新创建；
- 测试可以直接调用 `get_current_user(token, session)`，也可以在 API 测试中覆盖依赖。

### 🔵 了解用途

- 单元 4 会把该依赖接入 `/auth/me`；
- Task 4 会在它后面增加角色授权依赖；
- 多进程部署时，每个 Worker 拥有自己的连接池，这是正常行为。

### 开始前只需自行查询的基础知识名称

- Python：生成器、异步生成器、`try/except`；
- FastAPI：`Depends`、`Annotated`、`OAuth2PasswordBearer`；
- SQLAlchemy：`AsyncSession.get()`；
- PyJWT：`InvalidTokenError`；
- HTTP：401 与 403。

## 【3】项目文件树 + 骨架代码

```text
MarketMind-AI/
├─ backend/app/api/dependencies.py
├─ tests/
│  ├─ unit/api/test_dependencies.py
│  └─ integration/db/test_auth_dependencies.py
└─ docs/learning/phase-1-task-3-jwt-auth.md
```

基础 Session 依赖已经实现：

```python
@cache
def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    database_url = Settings().database_url
    if database_url is None:
        raise RuntimeError("DATABASE_URL 未配置")
    return create_session_factory(create_engine(database_url))


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with _get_session_factory()() as session:
        yield session
```

你只需完成下面的核心依赖：

```python
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    # TODO: 学习者实现 Token 解析、用户查询和停用检查
    raise NotImplementedError
```

## 【4】编写顺序 + 函数如何配合

1. 在函数中创建 `settings = Settings()`；
2. 读取 `secret = settings.jwt_secret`；
3. 若密钥是 `None`，抛出 `RuntimeError("JWT_SECRET 未配置")`，这是服务器配置错误，不是客户端 401；
4. 使用 `try/except InvalidTokenError` 包住 `decode_access_token(token, secret)`；
5. Token 解码失败时抛出：

```text
code="AUTH_INVALID_TOKEN"
message="登录凭证无效"
status_code=401
```

6. 使用 `await session.get(User, user_id)` 查询用户；
7. 如果用户为 `None`，抛出与无效 Token 完全相同的 401；
8. 如果 `user.is_active` 为假，抛出：

```text
code="ACCOUNT_INACTIVE"
message="账号已停用"
status_code=403
```

9. 返回 `user`；
10. 删除 TODO 和 `NotImplementedError`。

建议先写一个内部小函数创建重复的无效 Token 异常吗？当前只有两个调用点，直接写两次更容易看懂；Task 4 统一异常处理时再判断是否值得提取。

## 【5】RED/GREEN 验证 + 完成标准

Session 基础设施已经通过：

```text
tests/unit/api/test_dependencies.py：1 passed
```

当前核心认证测试处于预期 RED：5 个测试均因 `get_current_user()` 的 `NotImplementedError` 失败。

实现后运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\api\test_dependencies.py tests\integration\db\test_auth_dependencies.py -v
.venv\Scripts\ruff.exe check backend\app\api\dependencies.py tests\unit\api\test_dependencies.py tests\integration\db\test_auth_dependencies.py
.venv\Scripts\mypy.exe backend\app\api\dependencies.py tests\unit\api\test_dependencies.py tests\integration\db\test_auth_dependencies.py
```

完成标准：6 个相关测试通过；Ruff、mypy 通过；你能解释 Token 已验证后为什么仍要查询数据库。

完成后回复：

```text
【Task 3 单元 3 编码完成】
```

## 单元 3 验收与参考实现

验收结果：6 个相关测试通过，Ruff 与 mypy 通过。

你实现的依赖链可以复用在此后所有受保护路由：

```text
OAuth2PasswordBearer 提取 token
        ↓
get_current_user
        ├─ Settings 读取密钥
        ├─ decode_access_token 验证签名和 exp
        ├─ session.get 查询数据库当前状态
        ├─ 用户不存在 → 401
        ├─ 用户停用 → 403
        └─ 返回 User
```

以后新增商品、知识库或 Agent 接口时，不需要复制 JWT 解析代码，只需在参数中声明 `Depends(get_current_user)`。

---

# 实现单元 4：登录与当前用户 HTTP 路由

## 【1】本单元业务目标

把前三个单元的独立函数串成客户端可以真正调用的 HTTP 接口：

```text
POST /api/v1/auth/token
OAuth2 表单 username(email) + password
        ↓ login 路由
authenticate_user
        ↓ create_access_token
TokenResponse

GET /api/v1/auth/me
Authorization: Bearer <token>
        ↓ get_current_user
UserRead（不含 password_hash）
```

## 【2】知识点分层

### 🔴 必须手写掌握

- 从 `OAuth2PasswordRequestForm` 读取 `username` 和 `password`；
- 把 OAuth2 的 `username` 当作本项目登录邮箱传给 `authenticate_user()`；
- 从 `Settings` 读取 JWT 密钥和有效期；
- 调用 `create_access_token()`；
- 返回 `TokenResponse`；
- 理解 Service 抛出的 `AppError` 会由全局处理器转换，不在路由重复捕获。

### 🟡 理解原理即可

- `APIRouter` 只组织 HTTP，不重新实现密码验证；
- `response_model=UserRead` 会过滤 ORM User 中的 `password_hash`；
- `app.include_router()` 才会让路由真正出现在应用中；
- `app.dependency_overrides` 让 API 测试强制使用 `marketmind_test`；
- 401 响应必须携带 `WWW-Authenticate: Bearer`；
- Request ID 中间件先写入 `request.state`，异常处理器再把它放进错误响应。

### 🔵 了解用途

- OAuth2 表单字段规范固定叫 `username`，即使业务上使用邮箱；
- Swagger 的 Authorize 按钮会使用 `tokenUrl` 获取 Token；
- Task 4 会继续复用全局异常处理器并增加 RBAC。

### 开始前只需自行查询的基础知识名称

- FastAPI：`APIRouter`、`Depends`、`response_model`；
- FastAPI Security：`OAuth2PasswordRequestForm`、`OAuth2PasswordBearer`；
- HTTP：表单编码、Authorization Header；
- Pydantic：响应模型过滤。

## 【3】项目文件树 + 骨架代码

```text
MarketMind-AI/
├─ backend/app/
│  ├─ api/v1/auth.py                 # 只填写 login TODO
│  ├─ core/exception_handlers.py     # 基础代码已完成
│  └─ main.py                        # 路由与处理器已注册
├─ tests/
│  ├─ conftest.py                    # API/集成测试共享安全数据库夹具
│  └─ api/test_auth.py
└─ docs/learning/phase-1-task-3-jwt-auth.md
```

`backend/app/api/v1/auth.py` 当前骨架：

```python
@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    # TODO: 学习者实现
    raise HTTPException(status_code=501, detail="TODO")
```

`/me` 已经是完整实现，因为它只负责返回验证后的用户：

```python
@router.get("/me", response_model=UserRead)
async def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
```

## 【4】编写顺序 + 完整调用关系

只修改 `login()`，严格按顺序：

1. 创建 `settings = Settings()`；
2. 读取 `secret = settings.jwt_secret`；
3. 若密钥为 `None`，抛出 `RuntimeError("JWT_SECRET 未配置")`；
4. 调用认证 Service：

```text
await authenticate_user(
    session,
    email=form_data.username,
    password=form_data.password,
)
```

5. 从返回的 `user.id` 创建 Token，传入 `secret` 和 `settings.access_token_expire_minutes`；
6. 返回 `TokenResponse(access_token=token)`，`token_type` 会自动使用 `bearer`；
7. 删除 TODO 和临时 501；
8. `HTTPException` 不再使用，删除该导入。

不要在路由中再次查询用户、验证密码或捕获 `AppError`。这些职责已经分别属于 Service 和全局异常处理器。

## 【5】RED/GREEN 验证 + 完成标准

当前 RED 已确认：

```text
登录相关：4 failed（临时 501）
/me 相关：3 passed
```

实现后运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\api\test_auth.py -v
.venv\Scripts\ruff.exe check backend\app\api\v1\auth.py backend\app\core\exception_handlers.py backend\app\main.py tests\api\test_auth.py tests\conftest.py
.venv\Scripts\mypy.exe backend\app\api\v1\auth.py backend\app\core\exception_handlers.py backend\app\main.py tests\api\test_auth.py tests\conftest.py
```

完成标准：7 个 API 测试通过；Ruff、mypy 通过；你能从客户端表单开始，完整说出 Token 到 `/me` 的调用链。

完成后回复：

```text
【Task 3 单元 4 编码完成】
```

## 单元 4 验收与参考实现

验收结果：7 个 API 测试通过。正确登录、两种错误凭证、停用账号、当前用户、缺少 Token 和过期 Token 均已覆盖。

`login()` 的完整参考实现：

```python
@router.post("/token", response_model=TokenResponse, summary="账号登录")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    settings = Settings()
    secret = settings.jwt_secret
    if secret is None:
        raise RuntimeError("JWT_SECRET 未配置")

    user = await authenticate_user(
        session,
        email=form_data.username,
        password=form_data.password,
    )
    token = create_access_token(
        user_id=user.id,
        secret=secret,
        expires_minutes=settings.access_token_expire_minutes,
    )
    return TokenResponse(access_token=token, token_type="bearer")
```

这段路由没有 `try/except AppError`，因为全局 `app_error_handler()` 已负责把业务失败转换成带错误码、Request ID 和正确状态码的 JSON 响应。

## Task 3 技术完成记录

本 Task 最终形成四层可复用能力：

1. `core/security.py`：密码哈希和 JWT 原语；
2. `services/users.py`：与 HTTP 无关的凭证认证规则；
3. `api/dependencies.py`：把 Bearer Token 还原为当前用户；
4. `api/v1/auth.py`：登录和当前用户 HTTP 接口。

当你在其他 FastAPI 项目迁移这套能力时，也应按这四层拆分。不要把查询数据库、验证密码、创建 Token 和处理 HTTP 全塞进一个路由函数。
