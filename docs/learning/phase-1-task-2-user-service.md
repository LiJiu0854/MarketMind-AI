# 阶段 1 · Task 2：用户业务与 Admin 初始化

> 本文档按实现单元逐步追加。当前只解锁“实现单元 1：密码哈希”。完成并验收当前单元后，才追加下一个单元。

Task 2 的实现单元顺序：

```text
1. 密码哈希（已完成）
2. User Schema（2A 输入 Schema 已完成；2B 输出与分页下一单元）
3. 业务异常（未解锁）
4. 创建用户 Service（未解锁）
5. 查询、分页、更新与停用（未解锁）
6. Admin 初始化 CLI（未解锁）
```

---

## 实现单元 1：密码哈希

## 【1】本单元业务目标

系统接收用户密码时，不能把明文直接保存到数据库。当前单元要提供两个稳定入口：

- `hash_password()`：创建用户时，把明文密码转换为不可逆哈希；
- `verify_password()`：登录时，判断明文密码是否匹配数据库中的哈希。

局部流程：

```text
创建用户：明文密码 → hash_password() → pwdlib/Argon2 → password_hash → users 表

验证登录：明文密码 + password_hash → verify_password() → True / False
```

当前不实现：User Schema、数据库写入、登录接口、JWT、Router、Admin CLI。

## 【2】知识点分层

### 建议提前自行了解的知识点名称

只需自行查询这些名称，不要求现在深入算法细节：

```text
Python：函数参数、返回值、模块级变量、异常
密码安全：哈希、随机盐、明文密码、密码验证
pwdlib：PasswordHash、recommended、hash、verify
测试：assert、RED、GREEN
```

### 🔴 必须手写掌握

- 根据函数的输入和返回类型完成 `hash_password()`；
- 根据明文密码与已有哈希完成 `verify_password()`；
- 理解为什么验证密码不能“重新哈希后比较两个字符串”。

### 🟡 理解原理即可

- `PasswordHash.recommended()` 为项目选择推荐的密码哈希配置；
- Argon2 每次生成随机盐，因此相同密码的哈希通常不同；
- 测试为什么同时验证正确密码和错误密码。

### 🔵 了解用途

- Argon2 的内存成本、时间成本和并行度参数；
- 将来调整哈希参数和旧哈希升级；
- 更底层的密码学实现。

## 【3】项目文件树 + 骨架代码

当前单元只涉及：

```text
MarketMind-AI/
├── backend/app/core/
│   └── security.py                 # 需要填写两个 TODO
├── tests/unit/core/
│   └── test_security.py            # 已提供完整行为测试
├── docs/learning/
│   └── phase-1-task-2-user-service.md
└── pyproject.toml                  # 已加入 pwdlib[argon2]
```

### `backend/app/core/security.py`

仓库中的骨架：

```python
"""密码哈希与验证入口。"""

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """把明文密码转换为带随机盐的安全哈希。"""
    # TODO: 学习者调用 password_hasher 完成密码哈希
    raise NotImplementedError("TODO: 学习者实现 hash_password")


def verify_password(password: str, password_hash: str) -> bool:
    """验证明文密码是否匹配已有哈希。"""
    # TODO: 学习者调用 password_hasher 完成密码验证
    raise NotImplementedError("TODO: 学习者实现 verify_password")
```

已经替你完成的重复性代码：

- import `PasswordHash`；
- 创建全局复用的 `password_hasher`；
- 确定函数名称、参数和返回类型；
- 创建测试文件及三个行为测试；
- 安装当前单元需要的依赖。

你需要完成的只有两个 TODO，不要修改测试。

### 两个函数怎样使用

以后创建用户的 Service 会这样调用：

```python
password_hash = hash_password(data.password)
```

以后验证登录凭证会这样调用：

```python
password_is_valid = verify_password(input_password, user.password_hash)
```

当前不需要编写这些调用者，它们只是说明两个函数的输入来自哪里、结果去哪里。

### 实现提示

`password_hasher` 已经提供生成哈希和验证哈希的方法。你需要：

1. 在 `hash_password()` 中，把 `password` 交给生成哈希的方法，并返回结果；
2. 在 `verify_password()` 中，把明文密码和 `password_hash` 交给验证方法，并返回布尔结果；
3. 查阅 `pwdlib.PasswordHash.hash` 与 `pwdlib.PasswordHash.verify` 的参数顺序；
4. 删除两个 `raise NotImplementedError`，但保留函数签名和中文文档字符串。

不要自己生成随机盐，不要手写 Argon2，不要捕获并吞掉所有异常；这些职责已经由 pwdlib 完成。

## 【4】编写顺序 + 依赖清单

### 当前单元唯一新增依赖

```toml
"pwdlib[argon2]>=0.2,<1.0"
```

已执行安装：

```powershell
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
```

安装结果包含：

```text
pwdlib
argon2-cffi
argon2-cffi-bindings
```

### 你的编写顺序

1. 打开 `backend/app/core/security.py`；
2. 查看两个函数的参数和返回类型；
3. 查询 pwdlib 的 `hash` 与 `verify` 方法签名；
4. 只填写 `hash_password()`；
5. 运行第一个测试，确认哈希测试通过；
6. 再填写 `verify_password()`；
7. 运行整个测试文件；
8. 运行 Ruff 和 mypy。

第一个聚焦测试：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\core\test_security.py::test_hash_password_returns_salted_hash -v
```

全部密码测试：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\core\test_security.py -v
```

## 【5】运行验证 + 完成标准

当前 RED 已由 Agent 验证：

```text
3 failed
NotImplementedError: TODO: 学习者实现 hash_password
```

你完成后运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\core\test_security.py -v
.venv\Scripts\ruff.exe check backend\app\core\security.py tests\unit\core\test_security.py
.venv\Scripts\mypy.exe backend\app\core\security.py tests\unit\core\test_security.py
```

完成标准：

- 三个测试全部通过；
- 哈希不等于明文；
- 相同密码的两次哈希不同；
- 正确密码返回 `True`；
- 错误密码返回 `False`；
- Ruff 和 mypy 通过；
- 你能说明两个函数各自在创建用户和验证登录流程中的位置。

完成两个 TODO 后回复：

```text
【本阶段编码完成】
```

收到后，Agent 才会检查你的代码，并在本文档追加完整参考实现、对比说明和本单元学习记录。

---

## 实现单元 1：完整参考实现与纠错记录

### 完整参考代码

```python
"""密码哈希与验证入口。"""

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """把明文密码转换为带随机盐的安全哈希。"""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """验证明文密码是否匹配已有哈希。"""
    return password_hasher.verify(password, password_hash)
```

### 本次实现对比

第一次实现已经找对 `password_hasher.hash()` 和 `password_hasher.verify()`，但只调用了方法，没有把结果返回给调用者：

```python
password_hasher.hash(password)
```

函数调用产生的哈希会被直接丢弃。正确实现使用 `return`，把结果交给创建用户或登录验证的调用者：

```python
return password_hasher.hash(password)
```

第一次实现还把验证结果赋给了与函数同名的局部变量。该变量没有被使用，Ruff 因此报告 `F841`。直接返回验证结果更短，也准确表达函数职责。

### 为什么不能重新哈希后比较字符串

Argon2 每次哈希都会生成随机盐。同一个密码连续哈希两次，结果通常不同：

```text
hash_password("same-password") != hash_password("same-password")
```

因此验证密码不能重新生成哈希后使用 `==`。`verify()` 会读取已有哈希中保存的算法参数和盐，再验证明文密码。

### 本单元验证结果

```text
pytest：3 passed
Ruff：通过
mypy：通过
```

### 已掌握的可复用模式

```text
创建凭证：原始秘密 → 专用 hash 方法 → 保存哈希
验证凭证：原始秘密 + 已存哈希 → 专用 verify 方法 → bool
```

密码哈希属于安全边界。业务层以后只调用 `hash_password()` 和 `verify_password()`，不直接依赖 pwdlib，从而把密码算法使用方式集中在一个文件中。

实现单元 1 状态：**已完成并验证。**

---

## 实现单元 2A：UserCreate 与 UserUpdate

## 【1】本单元业务目标

外部调用者提交的是普通字典，字段可能缺失、类型错误或包含危险的额外数据。Pydantic Schema 位于输入边界，负责在数据进入 Service 前完成结构校验。

局部流程：

```text
外部字典
  → UserCreate / UserUpdate
  → Pydantic 校验字段、类型和长度
  → 可信输入对象
  → 后续 User Service（尚未实现）
```

两个输入类职责不同：

- `UserCreate`：创建用户需要完整数据，所以所有业务字段必填；
- `UserUpdate`：只修改调用者提供的字段，所以所有业务字段可选。

当前不实现：邮箱转小写、重复邮箱检查、密码哈希调用、数据库事务、UserRead、UserPage、Router。

## 【2】知识点分层

### 建议提前自行了解的知识点名称

```text
Python：类属性、联合类型、None、默认值
Pydantic：BaseModel、EmailStr、Field、ValidationError
Pydantic：model_dump、exclude_unset、ConfigDict
API：输入 Schema、部分更新、额外字段
```

### 🔴 必须手写掌握

- 独立声明 `UserCreate` 的四个必填字段；
- 独立声明 `UserUpdate` 的五个可选字段；
- 使用 `Field` 表达字符串长度和密码隐藏规则；
- 理解“类型允许 None”和“字段可以不提供”为什么都要表达。

### 🟡 理解原理即可

- `EmailStr` 依赖 email-validator 检查邮箱基本格式；
- `ConfigDict(extra="forbid")` 拒绝未声明字段；
- `model_dump(exclude_unset=True)` 只导出调用者实际提供的更新字段。

### 🔵 了解用途

- Pydantic 内部如何生成校验器；
- 邮箱 RFC 的全部边界情况；
- FastAPI 将 ValidationError 转换为 HTTP 422 的过程，Task 4 再深入。

## 【3】项目文件树 + 骨架代码

当前单元新增或修改：

```text
MarketMind-AI/
├── backend/app/
│   ├── models/user.py              # 复用 Role，不修改
│   └── schemas/user.py             # 需要填写字段 TODO
├── tests/unit/schemas/
│   └── test_user.py                # 已提供四个行为测试
├── docs/learning/
│   └── phase-1-task-2-user-service.md
└── pyproject.toml                  # 已加入 email-validator
```

### Schema 与 Model 的区别

```text
User Model：描述 MySQL users 表，包含 password_hash
UserCreate：描述创建接口允许输入什么，包含 password 明文
UserUpdate：描述更新接口允许修改什么
```

不能直接把 User Model 当成 API 输入：数据库字段和外部输入职责不同，混用可能让客户端提交 `id`、`password_hash`、`created_at` 等本应由系统控制的字段。

### `backend/app/schemas/user.py` 骨架

```python
"""用户输入与输出数据结构。"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field  # noqa: F401

from app.models.user import Role  # noqa: F401


class UserCreate(BaseModel):
    """创建用户时允许接收的字段。"""

    model_config = ConfigDict(extra="forbid")

    # TODO: 学习者声明 email、full_name、password、role 字段及约束
    pass


class UserUpdate(BaseModel):
    """更新用户时允许接收的可选字段。"""

    model_config = ConfigDict(extra="forbid")

    # TODO: 学习者声明 email、full_name、password、role、is_active 可选字段
    pass
```

`# noqa: F401` 只是让尚未使用的骨架 import 暂时通过 Ruff。字段完成后这些类型都会被使用，可以删除注释；如果忘记删除，我会在验收时直接处理。

### UserCreate 字段契约

| 字段 | Python/Pydantic 类型 | 约束 |
| --- | --- | --- |
| `email` | `EmailStr` | 必填，必须是合法邮箱 |
| `full_name` | `str` | 必填，长度 1～100 |
| `password` | `str` | 必填，长度 12～128，`repr` 不显示 |
| `role` | `Role` | 必填，只能是固定角色 |

### UserUpdate 字段契约

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `email` | `EmailStr \| None` | 可不提供 |
| `full_name` | `str \| None` | 可不提供；提供时长度 1～100 |
| `password` | `str \| None` | 可不提供；提供时长度 12～128，`repr` 不显示 |
| `role` | `Role \| None` | 可不提供 |
| `is_active` | `bool \| None` | 可不提供 |

注意：Markdown 表格中的 `|` 是分隔符，真正 Python 类型写法仍是 `EmailStr | None`。

### 必要语法示例

下面只演示写法，不是本项目字段答案：

```python
# 必填且有长度约束
title: str = Field(min_length=1, max_length=50)

# 可以不提供；提供后仍有长度约束
description: str | None = Field(default=None, max_length=200)

# 必填但不出现在 repr 中
secret: str = Field(min_length=8, repr=False)
```

“可选字段”的两个部分缺一不可：

```text
str | None   → 值允许是 None
= None       → 创建对象时允许不提供该字段
```

### 测试正在约束什么

`tests/unit/schemas/test_user.py` 已验证：

1. 合法 UserCreate 可以创建，明文密码不出现在 `repr()`；
2. 非法邮箱产生 `email` 字段的格式错误；
3. 少于 12 字符的密码产生长度错误；
4. `UserUpdate()` 可以为空，提供 role 时只导出 role。

不要修改测试去迁就实现。如果测试失败，应根据错误定位缺少的字段或约束。

## 【4】编写顺序 + 依赖清单

### 当前单元唯一新增依赖

```toml
"email-validator>=2.2,<3.0"
```

Pydantic 的 `EmailStr` 使用它完成邮箱格式检查。已执行：

```powershell
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
```

### 你的编写顺序

1. 打开 `backend/app/schemas/user.py`；
2. 先完成 `UserCreate` 四个字段；
3. 删除 `UserCreate` 中的 `pass`；
4. 运行前三个 UserCreate 测试；
5. 再完成 `UserUpdate` 五个可选字段；
6. 删除 `UserUpdate` 中的 `pass`；
7. 运行整个 Schema 测试文件；
8. 删除已经不需要的 `# noqa: F401`；
9. 运行 Ruff 和 mypy。

只运行 UserCreate 测试：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\schemas\test_user.py -k user_create -v
```

全部输入 Schema 测试：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\schemas\test_user.py -v
```

## 【5】运行验证 + 完成标准

当前 RED 已由 Agent 验证：

```text
4 failed
合法字段被 extra_forbidden 拒绝
邮箱没有产生 value_error
短密码没有产生 string_too_short
UserUpdate 不认识 role
```

字段尚未声明时，mypy 也会报告 `Unexpected keyword argument` 和属性不存在。这同样是当前骨架的预期 RED；完成字段后再要求 mypy 通过。

完成字段后运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\schemas\test_user.py -v
.venv\Scripts\ruff.exe check backend\app\schemas\user.py tests\unit\schemas\test_user.py
.venv\Scripts\mypy.exe backend\app\schemas\user.py tests\unit\schemas\test_user.py
```

完成标准：

- 四个测试全部通过；
- UserCreate 所有字段必填；
- UserUpdate 所有字段可以不提供；
- 邮箱和密码边界正确；
- 明文密码不出现在 `repr()`；
- Ruff 和 mypy 通过；
- 你能解释为什么输入 Schema 不能直接复用数据库 User Model。

完成 TODO 后回复：

```text
【本阶段编码完成】
```

收到后，Agent 将检查你的实现，并在本文档追加完整参考代码、差异说明和本单元学习记录。

---

## 实现单元 2A：完整参考实现与纠错记录

### 完整参考代码

```python
"""用户输入与输出数据结构。"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class UserCreate(BaseModel):
    """创建用户时允许接收的字段。"""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="用户邮箱")
    full_name: str = Field(min_length=1, max_length=100, description="用户全名")
    password: str = Field(min_length=12, max_length=128, repr=False)
    role: Role = Field(..., description="用户角色")


class UserUpdate(BaseModel):
    """更新用户时允许接收的可选字段。"""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = Field(default=None, description="用户邮箱")
    full_name: str | None = Field(
        default=None, min_length=1, max_length=100, description="用户全名"
    )
    password: str | None = Field(
        default=None, min_length=12, max_length=128, repr=False
    )
    role: Role | None = Field(default=None, description="用户角色")
    is_active: bool | None = Field(default=None, description="用户是否激活")
```

### 本次实现对比

第一次 `UserUpdate` 使用了非空类型配合 `None` 默认值：

```python
email: EmailStr = Field(None)
```

Pydantic 运行时可以读取默认值，但 mypy 看到的是“EmailStr 变量被赋值为 None”，因此报告类型不兼容。

第二次改成了联合类型，但 `email` 仍使用 `Field(...)`：

```python
email: EmailStr | None = Field(...)
```

这表示字段的值可以是 `None`，但调用者仍必须提供该字段。`UserUpdate()` 因此失败。

最终写法同时表达两个条件：

```python
email: EmailStr | None = Field(default=None)
```

```text
EmailStr | None   → 值允许为空
default=None      → 调用时允许省略
```

这是部分更新 Schema 的核心模式。商品更新、报告更新和任务配置更新都会复用它。

### 为什么使用 exclude_unset

调用：

```python
UserUpdate(role=Role.OPERATOR).model_dump(exclude_unset=True)
```

只得到：

```python
{"role": Role.OPERATOR}
```

如果不使用 `exclude_unset=True`，未提供字段也会以 `None` 出现在字典中。Service 可能误把原有邮箱、姓名或密码覆盖为空值。

### Schema 与 Model 的责任边界

```text
UserCreate/UserUpdate：决定外部调用者允许提交什么
User Model：决定数据库实际保存什么
User Service：决定业务上是否允许这次操作
```

例如：

- Schema 判断字符串是不是邮箱；
- Service 判断邮箱是否已被其他用户使用；
- Model 和数据库唯一索引负责最终阻止重复数据。

三层解决的是不同问题，不能互相代替。

### 本单元验证结果

```text
pytest：4 passed
mypy：通过
Ruff：格式化后通过
```

实现单元 2A 状态：**已完成并验证。**

---

# 实现单元 2B：用户安全输出与分页输出 Schema

## 【1】本单元业务目标

本单元只完成两个“响应数据盒子”：

```text
数据库 User 对象
    ↓ UserRead.model_validate(user)
UserRead 安全输出
    ↓ 只保留允许公开的字段
客户端（看不到 password_hash）
```

```text
多个 UserRead + 分页数字
    ↓ UserPage
用户列表接口的统一响应
```

你要掌握的不是“再写两个类”，而是两条可迁移规则：

1. 数据库对象不能直接返回给客户端，必须经过输出 Schema 过滤；
2. 列表接口不能只返回列表，还要携带总数、页码和每页数量。

以后商品、报告、任务等模块都可以复用这两个模式：

```text
数据库 Model → Read Schema
list[Read Schema] + 分页元数据 → Page Schema
```

## 【2】知识点分层

### 🔴 必须手写掌握

- 为 `UserRead` 声明允许对外返回的字段；
- 明确不声明 `password_hash`；
- 为 `UserPage` 声明列表字段和四项分页结构；
- 理解字段是否存在由 Schema 的字段声明决定，而不是由原始 ORM 对象决定。

### 🟡 理解原理即可

- `ConfigDict(from_attributes=True)`：允许 Pydantic 从普通对象或 ORM 对象的属性读取值；
- `list[UserRead]`：列表中的每一项都必须符合 `UserRead`；
- `datetime`：响应中的创建时间和更新时间类型；
- 输出过滤：ORM 对象即使有 `password_hash`，只要输出 Schema 没有声明，输出结果就不会包含它；
- 嵌套校验：创建 `UserPage` 时，Pydantic 会继续检查 `items` 中的每个用户。

### 🔵 了解用途

- FastAPI 后续可以通过 `response_model` 使用输出 Schema；
- JSON 响应时，Pydantic 会把 `datetime` 转换为标准时间字符串；
- 分页数值的边界限制将在本单元基础结构通过后单独练习，现在不提前实现。

### 开始前只需自行查询的基础知识名称

- Python：类属性、类型注解、泛型容器 `list[T]`；
- Python：`datetime`；
- Pydantic：`BaseModel`、`model_validate()`、`model_dump()`；
- Pydantic：`ConfigDict(from_attributes=True)`；
- ORM：模型实例与对象属性。

## 【3】项目文件树 + 骨架代码

本单元只涉及两个现有文件，不新增依赖：

```text
MarketMind-AI/
├─ backend/
│  └─ app/
│     └─ schemas/
│        └─ user.py
└─ tests/
   └─ unit/
      └─ schemas/
         └─ test_user.py
```

`backend/app/schemas/user.py` 当前新增骨架：

```python
from datetime import datetime  # noqa: F401


class UserRead(BaseModel):
    """返回给客户端的安全用户数据。"""

    model_config = ConfigDict(from_attributes=True)

    # TODO: 学习者实现公开字段，禁止声明 password_hash
    pass


class UserPage(BaseModel):
    """用户分页查询结果。"""

    model_config = ConfigDict(extra="forbid")

    # TODO: 学习者实现用户列表与分页元数据字段
    pass
```

`# noqa: F401` 只是骨架阶段临时告诉 Ruff：“`datetime` 很快会被使用”。当你真正使用 `datetime` 后，把这段临时注释删除。

### 你需要实现的字段合同

`UserRead` 必须包含：

| 字段 | 类型 | 用途 |
|---|---|---|
| `id` | `int` | 用户主键 |
| `email` | `EmailStr` | 用户邮箱 |
| `full_name` | `str` | 用户全名 |
| `role` | `Role` | 用户角色 |
| `is_active` | `bool` | 是否可用 |
| `created_at` | `datetime` | 创建时间 |
| `updated_at` | `datetime` | 更新时间 |

`UserPage` 必须包含：

| 字段 | 类型 | 用途 |
|---|---|---|
| `items` | `list[UserRead]` | 当前页用户列表 |
| `total` | `int` | 符合条件的用户总数 |
| `page` | `int` | 当前页码 |
| `page_size` | `int` | 每页数量 |

本轮不要写 `password_hash`，也不要给分页字段添加 `Field(ge=...)`。后者会作为下一次迁移练习，由你自己先写失败测试再实现。

## 【4】编写顺序 + 当前依赖

严格按下面顺序编写：

1. 在 `UserRead` 中按“身份 → 公开资料 → 状态 → 时间”声明字段；
2. 检查 `UserRead` 中没有 `password_hash`；
3. 删除 `UserRead` 类中的 `pass` 和 TODO；
4. 在 `UserPage` 中先声明 `items`，再声明 `total`、`page`、`page_size`；
5. 删除 `UserPage` 类中的 `pass` 和 TODO；
6. `datetime` 已被使用后，删除导入行末尾的 `# noqa: F401`；
7. 依次运行 pytest、Ruff、mypy。

为什么按这个顺序：

- 先写 `UserRead`，因为 `UserPage.items` 的类型依赖它；
- 先确认单个用户的安全边界，再把它放进列表；
- 测试先验证单个 ORM 对象转换，再验证分页容器，失败范围更小、更容易定位。

当前依赖：**无新增依赖**。继续使用已有的 Pydantic、SQLAlchemy、pytest。

## 【5】RED/GREEN 验证 + 完成标准

Agent 已验证当前 RED：

```text
6 个测试中：4 passed，2 failed

UserRead 失败原因：model_dump() 得到空字典，缺少 7 个公开字段
UserPage 失败原因：items、total、page、page_size 都被判定为 extra_forbidden
```

这次失败是正确的，因为它准确证明了两个类已经存在，但字段合同尚未实现。

完成字段后运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\schemas\test_user.py -v
.venv\Scripts\ruff.exe check backend\app\schemas\user.py tests\unit\schemas\test_user.py
.venv\Scripts\mypy.exe backend\app\schemas\user.py tests\unit\schemas\test_user.py
```

完成标准：

- 6 个测试全部通过；
- `UserRead.model_validate(user)` 能读取 ORM User 的属性；
- `UserRead.model_dump()` 只含 7 个公开字段；
- 输出中不存在 `password_hash`；
- `UserPage` 能保存 `items` 和四项分页信息；
- Ruff 与 mypy 全部通过；
- 你能解释为什么必须先定义 `UserRead`，再在 `UserPage` 中使用它。

完成 TODO 后回复：

```text
【本阶段编码完成】
```

收到后，Agent 会检查代码并追加完整参考实现。随后进入分页边界迁移练习。

---

## 实现单元 2B：完整参考实现与纠错记录

### 完整参考代码

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class UserRead(BaseModel):
    """返回给客户端的安全用户数据。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="用户 ID")
    email: EmailStr = Field(description="用户邮箱")
    full_name: str = Field(description="用户全名")
    role: Role = Field(description="用户角色")
    is_active: bool = Field(description="用户是否激活")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class UserPage(BaseModel):
    """用户分页查询结果。"""

    model_config = ConfigDict(extra="forbid")

    items: list[UserRead] = Field(description="用户列表")
    total: int = Field(description="总用户数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页用户数")
```

### 你的实现为什么正确

`UserRead` 只声明了七个公开字段，因此：

```text
User.password_hash 存在于 ORM 对象
        ↓
UserRead 没有声明 password_hash
        ↓
model_dump() 不会输出 password_hash
```

这不是删除了数据库密码哈希，而是建立了“数据库字段”和“API 公开字段”之间的边界。

`UserPage.items` 使用 `list[UserRead]`，表示列表里不能随意放其他结构。Pydantic 会继续按照 `UserRead` 检查每一项。

### 本次纠错

你的业务字段和类型全部正确，只存在空格格式问题：

```python
id : int
```

Python 类型注解的标准格式是：

```python
id: int
```

这不会改变运行结果，属于非核心格式问题，已由 Agent 直接统一修复。

### 基础结构验证结果

```text
pytest：6 passed
mypy：通过
Ruff：修复前仅有 1 个可自动修复的空格问题
```

基础结构状态：**已完成。**

---

# 实现单元 2B 迁移练习：分页边界

## 【1】练习目标

当前 `UserPage` 接受下面这种无效数据：

```python
UserPage(items=[], total=0, page=1, page_size=0)
```

`page_size=0` 表示“一页显示零条”，业务上没有意义。你的目标是使用刚学过的 Pydantic 字段约束阻止它。

本练习训练举一反三：你已经在 `UserCreate.password` 使用过 `Field(min_length=...)`，现在把同一种“在输入边界声明规则”的思想迁移到整数范围。

## 【2】知识点分层

### 🔴 必须手写掌握

- 先写一个会失败的边界测试；
- 使用 `pytest.raises(ValidationError)` 捕获预期异常；
- 使用 `Field` 给整数添加边界，而不是在测试中手动判断；
- 观察 RED，再修改业务代码得到 GREEN。

### 🟡 理解原理即可

- `ge` 表示 greater than or equal，大于或等于；
- `le` 表示 less than or equal，小于或等于；
- Schema 是信任边界：无效分页参数应尽早失败。

### 🔵 了解用途

- 后续 API 查询参数还会在路由层限制页码；
- 数据库查询会根据 `page` 和 `page_size` 计算偏移量，本练习暂不实现查询。

### 开始前只需自行查询的基础知识名称

- pytest：`pytest.raises`；
- Pydantic：整数约束 `Field(ge=..., le=...)`；
- Pydantic：`ValidationError`。

## 【3】文件树 + 测试骨架

```text
MarketMind-AI/
├─ backend/app/schemas/user.py
└─ tests/unit/schemas/test_user.py
```

在 `tests/unit/schemas/test_user.py` 最后新增测试，核心内容由你填写：

```python
def test_user_page_rejects_zero_page_size() -> None:
    """每页数量为零时应拒绝创建分页结果。"""
    # TODO: 使用 pytest.raises(ValidationError)
    # TODO: 在上下文中创建 items=[]、total=0、page=1、page_size=0 的 UserPage
    raise NotImplementedError
```

注意：完成 TODO 后必须删除 `raise NotImplementedError`。

## 【4】编写顺序 + 当前依赖

1. 只新增测试，不修改 `UserPage`；
2. 运行测试，确认新测试失败，原因是没有抛出 `ValidationError`；
3. 再修改 `UserPage.page_size`，要求它最小为 `1`、最大为 `100`；
4. 同样限制 `page` 最小为 `1`；
5. 限制 `total` 最小为 `0`；
6. 重新运行测试，观察 GREEN；
7. 运行 Ruff 和 mypy。

无新增依赖。

## 【5】验证与完成标准

RED 阶段只运行新测试：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\schemas\test_user.py::test_user_page_rejects_zero_page_size -v
```

正确 RED 应显示：没有抛出预期的 `ValidationError`。如果看到 `NotImplementedError`，说明测试骨架还未填写完成。

GREEN 阶段运行全部 Schema 测试：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\schemas\test_user.py -v
.venv\Scripts\ruff.exe check backend\app\schemas\user.py tests\unit\schemas\test_user.py
.venv\Scripts\mypy.exe backend\app\schemas\user.py tests\unit\schemas\test_user.py
```

完成标准：

- 你亲眼观察过新增测试先失败；
- `page_size=0` 会产生 `ValidationError`；
- `page_size` 只允许 `1` 到 `100`；
- `page` 最小为 `1`；
- `total` 最小为 `0`；
- 所有检查通过。

完成后回复：

```text
【分页边界练习完成】
```

---

## 分页边界练习：验收记录

最终约束：

```python
total: int = Field(ge=0, description="总用户数")
page: int = Field(ge=1, description="当前页码")
page_size: int = Field(ge=1, le=100, description="每页用户数")
```

最终测试使用了 `pytest.raises` 的函数调用形式：

```python
pytest.raises(
    ValidationError,
    UserPage,
    items=[],
    total=0,
    page=1,
    page_size=0,
)
```

它与 `with pytest.raises(...)` 都能验证异常。上下文管理器形式更适合包含多行准备代码；函数形式适合“调用一次并期待异常”的短测试。

验收结果：

```text
pytest：7 passed
Ruff：通过
mypy：通过
```

实现单元 2B 状态：**已完成并验证。**

---

# 实现单元 3：业务异常 AppError

## 【1】本单元业务目标

Service 遇到“邮箱重复”“用户不存在”“不能停用自己”等业务失败时，不返回 `None`，也不抛出含 SQL 细节的底层异常，而是抛出统一的 `AppError`：

```text
Service 发现业务规则不满足
        ↓
AppError(code, message, status_code)
        ↓
后续 API 异常处理器转换为安全 JSON
```

本单元只建立异常对象，不实现 API 异常处理器。

## 【2】知识点分层

### 🔴 必须手写掌握

- 继承 Python 内置 `Exception`；
- 在 `__init__` 中保存 `code`、`message`、`status_code`；
- 调用父类构造函数，让 `str(error)` 返回安全消息。

### 🟡 理解原理即可

- 错误码供程序判断，错误消息供人阅读；
- HTTP 状态码描述请求结果类型；
- `AppError` 不应携带 SQL、密码、连接串等敏感信息。

### 🔵 了解用途

- Task 4 会注册 FastAPI 全局异常处理器；
- 数据库异常与业务异常的处理方式不同。

### 开始前只需自行查询的基础知识名称

- Python：异常、继承、`super()`、`__init__`；
- HTTP：400、404、409 状态码；
- FastAPI：异常处理器。

## 【3】项目文件树 + 骨架代码

```text
MarketMind-AI/
├─ backend/app/core/errors.py
└─ tests/unit/core/test_errors.py
```

`backend/app/core/errors.py`：

```python
"""应用业务异常。"""


class AppError(Exception):
    """可以安全转换为 API 响应的业务异常。"""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        # TODO: 学习者保存三个公开属性
        # TODO: 学习者调用父类构造函数
        raise NotImplementedError
```

`tests/unit/core/test_errors.py` 将验证：

```python
def test_app_error_keeps_safe_public_data() -> None:
    """业务异常应保留错误码、消息和状态码。"""
    error = AppError(
        code="USER_EMAIL_CONFLICT",
        message="用户邮箱已存在",
        status_code=409,
    )

    assert error.code == "USER_EMAIL_CONFLICT"
    assert error.message == "用户邮箱已存在"
    assert error.status_code == 409
    assert str(error) == "用户邮箱已存在"
```

## 【4】编写顺序 + 当前依赖

1. Agent 激活测试并运行 RED；
2. 你保存 `code`；
3. 保存 `message`；
4. 保存 `status_code`；
5. 调用父类构造函数；
6. 删除 `raise NotImplementedError`；
7. 运行测试和静态检查。

无新增依赖。

## 【5】验证与完成标准

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\core\test_errors.py -v
.venv\Scripts\ruff.exe check backend\app\core\errors.py tests\unit\core\test_errors.py
.venv\Scripts\mypy.exe backend\app\core\errors.py tests\unit\core\test_errors.py
```

完成标准：三个属性正确，`str(error)` 是安全消息，所有检查通过，并能解释为什么业务错误不直接使用 `ValueError`。

当前 RED 已验证：测试可以导入 `AppError`，但构造对象时准确停在 `raise NotImplementedError`；Ruff 已通过。

### 单元 3 完整参考实现与验收

```python
class AppError(Exception):
    """可以安全转换为 API 响应的业务异常。"""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)
```

`super().__init__(message)` 把安全消息交给 `Exception` 保存，所以日志或 `str(error)` 能得到消息；三个属性则供后续 API 异常处理器构造结构化响应。

```text
pytest：1 passed
Ruff：通过
mypy：通过
```

实现单元 3 状态：**已完成并验证。**

---

# 实现单元 4：创建用户 Service

## 【1】本单元业务目标

把已经完成的 Schema、密码哈希和数据库 Session 串成第一条完整业务链：

```text
UserCreate
   ↓ 邮箱转为小写
查询邮箱是否存在
   ├─ 已存在 → AppError(USER_EMAIL_CONFLICT, 409)
   └─ 不存在
         ↓ hash_password
       创建 User
         ↓ session.add
         ↓ session.commit
         ↓ session.refresh
       返回 User
```

任何写入失败都必须回滚，不能让 Session 停留在失败事务状态。

## 【2】知识点分层

### 🔴 必须手写掌握

- 使用 `select(User).where(...)` 查询重复邮箱；
- 使用 `await session.scalar(...)` 取得一个结果；
- 把邮箱标准化为小写；
- 只存储 `hash_password(data.password)`，绝不存明文；
- 正确使用 `add → commit → refresh`；
- 异常路径调用 `rollback()`；
- 把重复邮箱转换为统一 `AppError`。

### 🟡 理解原理即可

- `add()` 是同步方法，只把对象加入 Session；
- `commit()` 和 `refresh()` 需要 `await`；
- 应用层预检查改善错误信息，数据库唯一索引负责最终并发安全；
- `IntegrityError` 可能来自并发插入，不能只依赖预检查。

### 🔵 了解用途

- 后续 API 和 CLI 都调用同一个 `create_user()`；
- 以后创建商品、报告时会复用同样事务结构。

### 开始前只需自行查询的基础知识名称

- Python：`async`、`await`、`try/except`、`raise`；
- SQLAlchemy：`select`、`AsyncSession.scalar`、`add`、`commit`、`refresh`、`rollback`；
- 数据库：唯一索引、事务；
- Python：字符串 `strip()`、`lower()`。

## 【3】项目文件树 + 骨架代码

```text
MarketMind-AI/
├─ backend/app/services/
│  ├─ __init__.py
│  └─ users.py
└─ tests/integration/db/test_user_service.py
```

以下路径不是仓库原有文件，而是本单元需要**新建**的路径。Agent 已创建目录、空包标记和 `users.py` 骨架：

- `backend/app/services/`：新建目录；
- `backend/app/services/__init__.py`：新建空包标记；
- `backend/app/services/users.py`：单元 4 创建，单元 5 继续在同一文件追加函数。

`backend/app/services/users.py`：

```python
"""用户业务服务。"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """创建用户；邮箱冲突时抛出统一业务异常。"""
    # TODO: 学习者标准化邮箱
    # TODO: 学习者查询是否已经存在
    # TODO: 学习者构造 User，密码只保存哈希
    # TODO: 学习者提交、刷新并返回
    # TODO: 学习者在异常路径回滚
    raise NotImplementedError
```

集成测试将依次验证：

```text
创建成功
邮箱自动转小写
密码列不是明文且可以验证
重复邮箱产生 USER_EMAIL_CONFLICT / 409
失败事务已回滚，Session 仍可继续使用
```

当前已激活第一个真实 MySQL RED：`create_user()` 被调用后准确停在 `raise NotImplementedError`；Ruff 已通过。

## 【4】编写顺序 + 当前依赖

1. Agent 创建真实 MySQL RED 测试；
2. 先完成邮箱标准化和重复查询；
3. 运行测试，确认仍因未创建用户而失败；
4. 构造 User 并哈希密码；
5. 完成正常事务提交；
6. 最后补充业务异常与 `IntegrityError` 回滚；
7. 运行完整集成测试。

无新增依赖，复用现有 SQLAlchemy、asyncmy、pwdlib 和测试数据库。

## 【5】验证与完成标准

```powershell
.venv\Scripts\python.exe -m pytest tests\integration\db\test_user_service.py -v
.venv\Scripts\ruff.exe check backend\app\services tests\integration\db\test_user_service.py
.venv\Scripts\mypy.exe backend\app\services tests\integration\db\test_user_service.py
```

完成标准：真实 MySQL 创建成功；数据库没有明文密码；重复邮箱是 409 业务异常；所有失败路径回滚；能解释为什么“先查询”仍不能替代唯一索引。

---

# 实现单元 5：查询、分页、更新与停用用户

## 【1】本单元业务目标

在同一个 Service 文件补齐用户管理操作：

```text
get_user(id)       → 找到 User / USER_NOT_FOUND
list_users(page)   → count + offset/limit → UserPage
update_user(data)  → 只更新调用者提供的字段
deactivate_user()  → is_active=False，不删除数据库记录
```

停用流程还必须阻止管理员停用自己：

```text
actor.id == user.id
        ↓
USER_SELF_DEACTIVATE_FORBIDDEN
```

## 【2】知识点分层

### 🔴 必须手写掌握

- 按主键查询并处理“未找到”；
- 使用 `func.count()` 获得总数；
- 使用 `(page - 1) * page_size` 计算 offset；
- 使用 `offset()`、`limit()` 和稳定排序分页；
- 使用 `model_dump(exclude_unset=True)` 实现部分更新；
- 更新密码时重新哈希；
- 更新邮箱时重新标准化并检查冲突；
- 使用 `is_active=False` 实现软删除；
- 阻止用户停用自己。

### 🟡 理解原理即可

- 分页必须稳定排序，否则翻页时顺序可能漂移；
- 软删除保留审计和关联数据；
- `setattr()` 可以根据字段名应用部分更新，但敏感字段需要单独处理；
- 每个写操作单独提交和回滚。

### 🔵 了解用途

- Task 4 的 Admin API 会直接复用这些函数；
- 更复杂的数据量出现前不需要通用 Repository 或分页框架。

### 开始前只需自行查询的基础知识名称

- SQLAlchemy：`scalar_one_or_none`、`scalars`、`func.count`；
- SQLAlchemy：`order_by`、`offset`、`limit`；
- Python：字典遍历、`setattr()`；
- 数据库：软删除、稳定排序；
- Pydantic：`exclude_unset=True`。

## 【3】项目文件树 + 骨架代码

```text
MarketMind-AI/
├─ backend/app/services/users.py
└─ tests/integration/db/test_user_service.py
```

追加到 `backend/app/services/users.py`：

```python
async def get_user(session: AsyncSession, user_id: int) -> User:
    """按 ID 查询用户，不存在时抛出业务异常。"""
    # TODO: 学习者实现查询与 USER_NOT_FOUND
    raise NotImplementedError


async def list_users(
    session: AsyncSession, page: int, page_size: int
) -> UserPage:
    """按 ID 稳定排序并分页返回用户。"""
    # TODO: 学习者查询 total
    # TODO: 学习者计算 offset 并查询当前页
    # TODO: 学习者组装 UserPage
    raise NotImplementedError


async def update_user(
    session: AsyncSession, user: User, data: UserUpdate
) -> User:
    """只更新调用者实际提供的字段。"""
    # TODO: 学习者导出 exclude_unset 数据
    # TODO: 学习者单独处理 email 和 password
    # TODO: 学习者更新普通字段并提交
    # TODO: 学习者处理回滚
    raise NotImplementedError


async def deactivate_user(
    session: AsyncSession, user: User, actor: User
) -> User:
    """软停用目标用户，但不允许操作者停用自己。"""
    # TODO: 学习者检查 actor.id 与 user.id
    # TODO: 学习者设置 is_active=False 并提交
    # TODO: 学习者处理回滚
    raise NotImplementedError
```

集成测试将验证：

```text
不存在的 ID → USER_NOT_FOUND / 404
分页 total 与 items 正确
page=2 时 offset 正确
只更新提供的字段
新密码被重新哈希
停用后记录仍存在且 is_active=False
操作者不能停用自己
```

## 【4】编写顺序 + 当前依赖

1. `get_user()`：单条查询和 404；
2. `list_users()`：先 total，再 items，最后 UserPage；
3. `update_user()`：先普通字段，再邮箱，最后密码和事务；
4. `deactivate_user()`：先自停用规则，再软删除事务；
5. 每完成一个函数就只运行对应测试；
6. 最后运行整个 Service 测试文件。

无新增依赖。

## 【5】验证与完成标准

```powershell
.venv\Scripts\python.exe -m pytest tests\integration\db\test_user_service.py -v
.venv\Scripts\ruff.exe check backend\app\services tests\integration\db\test_user_service.py
.venv\Scripts\mypy.exe backend\app\services tests\integration\db\test_user_service.py
```

完成标准：四个函数的成功和失败路径通过；分页稳定；部分更新不覆盖未提交字段；密码不以明文保存；停用不删除记录；所有写失败都回滚。

---

# 实现单元 6：管理员创建 CLI

## 【1】本单元业务目标

系统第一次部署时还没有可登录的管理员，需要一个只在服务器终端运行的安全入口：

```text
python -m app.cli.create_admin
        ↓
input() 读取邮箱和姓名
getpass() 隐藏读取密码
        ↓
UserCreate(role=ADMIN)
        ↓
create_user()
        ↓
MySQL 中生成首个管理员
```

CLI 不重新实现用户规则，也不接受命令行密码参数。

## 【2】知识点分层

### 🔴 必须手写掌握

- 使用 `input()` 读取非敏感信息；
- 使用 `getpass()` 隐藏密码输入；
- 构造 `UserCreate(role=Role.ADMIN)`；
- 创建 Engine 和 Session，并调用现有 `create_user()`；
- 使用 `asyncio.run(main())` 启动异步入口；
- 正确关闭 Engine；
- 捕获 `AppError` 并输出安全信息。

### 🟡 理解原理即可

- CLI、API 和未来后台任务应复用同一 Service；
- 密码若作为命令行参数，会出现在 shell 历史和进程列表；
- `try/finally` 用于确保数据库 Engine 被释放。

### 🔵 了解用途

- 生产部署初始化管理员；
- 后续可以由运维系统调用，但当前不实现自动化部署脚本。

### 开始前只需自行查询的基础知识名称

- Python：模块入口 `if __name__ == "__main__"`；
- Python：`asyncio.run()`；
- Python 标准库：`getpass.getpass()`；
- SQLAlchemy：异步 Engine、Session 工厂和上下文管理器；
- 命令行安全：shell history、process arguments。

## 【3】项目文件树 + 骨架代码

```text
MarketMind-AI/
├─ backend/app/cli/
│  ├─ __init__.py
│  └─ create_admin.py
└─ tests/unit/cli/test_create_admin.py
```

`backend/app/cli/` 当前还不存在，它是单元 6 开始时需要**新建**的目录，不是需要提前找到的旧目录。届时 Agent 会创建 `__init__.py`、真实 RED 测试和 `create_admin.py` 骨架。

`backend/app/cli/create_admin.py`：

```python
"""交互式创建首个管理员。"""

import asyncio
from getpass import getpass

from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import create_engine, create_session_factory
from app.models.user import Role
from app.schemas.user import UserCreate
from app.services.users import create_user


async def main() -> None:
    """读取终端输入并通过统一 Service 创建管理员。"""
    # TODO: 学习者读取并清理邮箱、姓名和隐藏密码
    # TODO: 学习者检查 DATABASE_URL 是否配置
    # TODO: 学习者创建 Engine 与 Session 工厂
    # TODO: 学习者构造 UserCreate 并调用 create_user
    # TODO: 学习者处理 AppError
    # TODO: 学习者确保 Engine 最终关闭
    raise NotImplementedError


if __name__ == "__main__":
    asyncio.run(main())
```

测试不会连接真实数据库，而是只验证 CLI 边界：

```text
邮箱和姓名来自 input()
密码来自 getpass()，不是命令行参数
角色固定为 ADMIN
传给 create_user() 的 Schema 正确
业务错误只打印安全消息
```

## 【4】编写顺序 + 当前依赖

1. Agent 创建 CLI RED 测试并完成重复性 mock 配置；
2. 你实现输入读取和 UserCreate；
3. 你接入 Engine、Session 和 create_user；
4. 你用 `try/finally` 关闭 Engine；
5. 你处理 AppError；
6. 运行单元测试；
7. 在本地手动运行一次 CLI，密码继续使用本地 `.env`，不得提交 Git。

无新增依赖，`asyncio` 与 `getpass` 都来自 Python 标准库。

## 【5】验证与完成标准

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\cli\test_create_admin.py -v
.venv\Scripts\ruff.exe check backend\app\cli tests\unit\cli
.venv\Scripts\mypy.exe backend\app\cli tests\unit\cli
```

手工运行：

```powershell
.venv\Scripts\python.exe -m app.cli.create_admin
```

完成标准：终端密码不回显；CLI 复用 `create_user()`；角色固定为 Admin；错误输出不泄露数据库信息；Engine 总能关闭；所有自动检查通过。

---

## 后续四个单元的执行规则

四个教程已经一次性给出，但编码仍遵守：

```text
单元 3 验收通过
    ↓
单元 4 解锁并验收
    ↓
单元 5 解锁并验收
    ↓
单元 6 解锁并验收
    ↓
Task 2 总验收与提交
```

当前单元 3～6 均已完成自动化验收，完整参考实现与纠错记录如下。

---

# 实现单元 4～5：完整参考实现与纠错记录

## 完整参考代码

`backend/app/services/users.py`：

```python
"""用户业务服务。"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserPage, UserRead, UserUpdate


def _normalize_email(email: str) -> str:
    """把邮箱转换为数据库中的统一形式。"""
    return email.strip().lower()


def _email_conflict() -> AppError:
    """创建统一的邮箱冲突业务异常。"""
    return AppError(
        code="USER_EMAIL_CONFLICT",
        message="用户邮箱已存在",
        status_code=409,
    )


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """创建用户；邮箱冲突时抛出统一业务异常。"""
    email = _normalize_email(str(data.email))

    try:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise _email_conflict()

        user = User(
            email=email,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=data.role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    except AppError:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise _email_conflict() from exc
    except Exception:
        await session.rollback()
        raise


async def get_user(session: AsyncSession, user_id: int) -> User:
    """按 ID 查询用户，不存在时抛出业务异常。"""
    user = await session.get(User, user_id)
    if user is None:
        raise AppError(
            code="USER_NOT_FOUND",
            message="用户不存在",
            status_code=404,
        )
    return user


async def list_users(
    session: AsyncSession, page: int, page_size: int
) -> UserPage:
    """按 ID 稳定排序并分页返回用户。"""
    total = await session.scalar(select(func.count()).select_from(User)) or 0
    users = (
        await session.scalars(
            select(User)
            .order_by(User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return UserPage(
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_user(
    session: AsyncSession, user: User, data: UserUpdate
) -> User:
    """只更新调用者实际提供的字段。"""
    updates = data.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return user

    try:
        email = updates.pop("email", None)
        if email is not None:
            normalized_email = _normalize_email(str(email))
            existing = await session.scalar(
                select(User).where(
                    User.email == normalized_email,
                    User.id != user.id,
                )
            )
            if existing is not None:
                raise _email_conflict()
            user.email = normalized_email

        password = updates.pop("password", None)
        if password is not None:
            user.password_hash = hash_password(str(password))

        for field, value in updates.items():
            setattr(user, field, value)

        await session.commit()
        await session.refresh(user)
        return user
    except AppError:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise _email_conflict() from exc
    except Exception:
        await session.rollback()
        raise


async def deactivate_user(
    session: AsyncSession, user: User, actor: User
) -> User:
    """软停用目标用户，但不允许操作者停用自己。"""
    if actor.id == user.id:
        await session.rollback()
        raise AppError(
            code="USER_SELF_DEACTIVATE_FORBIDDEN",
            message="不能停用当前登录用户",
            status_code=409,
        )

    try:
        user.is_active = False
        await session.commit()
        await session.refresh(user)
        return user
    except Exception:
        await session.rollback()
        raise
```

## 关键纠错对照

| 错误写法 | 问题 | 正确写法 |
|---|---|---|
| `session.excute()` | 方法名拼写错误 | `session.execute()` 或更短的 `session.scalar()` |
| `await hash_password(...)` | 密码哈希函数是同步函数 | `hash_password(...)` |
| `hash_password = hash_password(...)` | 局部变量遮蔽函数 | 使用 `password_hash` 等不同名称 |
| `User(password=...)` | ORM Model 没有该字段 | `User(password_hash=...)` |
| `AppError(detail=...)` | 构造函数接口不一致 | `AppError(message=...)` |
| 找到用户后 `raise NotImplementedError` | 成功路径没有返回 | `return user` |
| `setattr(user, field, update=value)` | `setattr` 参数错误 | `setattr(user, field, value)` |
| `user.update_at` | ORM 字段名错误 | 使用 `updated_at`；当前由 `onupdate` 自动处理 |

## 为什么保留两个邮箱冲突检查

```text
先查询邮箱
    ↓ 改善常规重复请求的错误信息
数据库 UNIQUE 索引
    ↓ 防止两个并发请求同时通过预检查
捕获 IntegrityError
    ↓ 转换成相同 USER_EMAIL_CONFLICT
```

应用预检查不能代替数据库唯一索引；数据库唯一索引也不能代替安全、稳定的业务错误。

## 为什么密码和邮箱要单独更新

普通字段可以使用：

```python
setattr(user, field, value)
```

但密码必须哈希，邮箱必须标准化并检查冲突，所以先从 `updates` 字典中 `pop()` 出来单独处理。剩余字段才进入通用循环。

实现单元 4、5 状态：**已完成并通过真实 MySQL 集成测试。**

---

# 实现单元 6：完整参考实现与纠错记录

`backend/app/cli/create_admin.py`：

```python
"""交互式创建首个管理员。"""

import asyncio
from getpass import getpass

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import create_engine, create_session_factory
from app.models.user import Role
from app.schemas.user import UserCreate
from app.services.users import create_user


def read_admin_data() -> UserCreate:
    """从终端读取管理员资料，密码不会回显。"""
    return UserCreate(
        email=input("请输入管理员邮箱: ").strip().lower(),
        full_name=input("请输入管理员姓名: ").strip(),
        password=getpass("请输入管理员密码: "),
        role=Role.ADMIN,
    )


async def main() -> int:
    """读取配置并通过统一 Service 创建管理员。"""
    try:
        data = read_admin_data()
    except ValidationError:
        print("创建失败: 输入数据不符合要求")
        return 1

    database_url = Settings().database_url
    if database_url is None:
        print("创建失败: DATABASE_URL 未配置")
        return 1

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            user = await create_user(session, data)
    except AppError as exc:
        print(f"创建失败: {exc}")
        return 1
    except Exception:
        print("创建失败: 发生内部错误")
        return 1
    finally:
        await engine.dispose()

    print(f"管理员 {user.email} 创建成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

CLI 将同步终端输入放在 `read_admin_data()`，异步 `main()` 只负责数据库操作。这样既避免在异步函数中直接调用阻塞 `input()`，也让输入规则和数据库流程可以分别测试。

关键纠错：

```text
role=[Role.ADMIN]  → 错误：列表不是 Role
role=Role.ADMIN    → 正确：固定创建单个 Admin 角色

e.detail           → 错误：AppError 没有 detail
str(e)             → 正确：输出父类保存的安全 message
```

实现单元 6 状态：**已完成自动化验收。** 为避免写入真实生产数据，本轮没有交互运行创建管理员命令。

---

# Task 2 自动化总验收

```text
pytest：42 passed
Ruff：All checks passed
mypy：Success，40 个源文件无类型错误
```

Task 2 已覆盖：

- Argon2 密码哈希与验证；
- 输入、输出和分页 Schema；
- 统一业务异常；
- 创建、查询、分页、部分更新与软停用；
- 邮箱冲突和自停用保护；
- CLI 隐藏密码、固定 Admin 角色并复用 Service；
- 真实 MySQL 事务隔离测试。
