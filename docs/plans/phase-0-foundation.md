# MarketMind AI 阶段 0：工程基础实施计划

> **给执行者：** 必须一次只执行一个任务。修改前先解释，涉及功能行为时使用测试驱动开发，并在每个本人验收门禁处停止。

**目标：** 在不连接数据库、缓存、大模型、前端或容器基础设施的前提下，建立最小、类型安全、可测试的 FastAPI 工程基础。

**架构：** 后端采用应用工厂，并将配置、中间件、响应模型和路由拆分为独立模块。测试从最小单元开始驱动功能实现，文档负责记录各阶段的学习过程与验收证据。

**技术栈：** Python 3.12、FastAPI、Pydantic Settings、pytest、HTTPX、Ruff、mypy

**需求基线：** `docs/learning/phase-0-baseline.md`

## 全局约束

- 仓库根目录是 `C:\Users\17905\Desktop\MarketMind-AI`，不得再创建嵌套的项目目录。
- 只能在 `phase/0-foundation` 上开发；本人验收阶段通过前，不得合并到 `main`，也不得创建标签。
- 不得读取、复制、修改或删除 `C:\Users\17905\Desktop\helloagents-deepresearch` 中的代码。
- 使用 Python 3.12 和项目根目录下的独立 `.venv`。
- 开发端口使用 `8010`。
- API Key 不得写入源代码、测试、日志或 Git。
- 面向学习者的项目文档默认使用中文；命令、路径、代码标识符和约定的 Git 提交信息保持原文。
- 功能行为必须遵循红—绿—重构的 TDD 流程：先看到测试失败，再写最小实现，然后看到测试通过，最后运行质量检查。
- 每次只完成一个任务，得到用户确认后才能开始下一个任务。
- 阶段 0 不得连接 MySQL、Redis、LLM、前端或 Docker。

## 计划目录结构

```text
MarketMind-AI/
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   └── config.py
│       ├── middleware/
│       │   ├── __init__.py
│       │   └── request_id.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── health.py
│       ├── api/
│       │   ├── __init__.py
│       │   └── v1/
│       │       ├── __init__.py
│       │       └── health.py
│       └── main.py
├── docs/
│   ├── learning/
│   │   └── phase-0-baseline.md
│   └── plans/
│       └── phase-0-foundation.md
└── tests/
    ├── __init__.py
    ├── unit/
    │   ├── core/test_config.py
    │   └── middleware/test_request_id.py
    └── api/test_health.py
```

每个模块只承担一种职责：配置模块读取带类型的环境变量；中间件负责请求追踪；响应模型定义接口契约；路由定义 HTTP 端点；应用工厂组装这些组件；测试验证对外行为。

---

### 任务 1：建立项目基线

**文件：**

- 创建：`docs/plans/phase-0-foundation.md`
- 创建：`docs/learning/phase-0-baseline.md`

**产出：** 建立项目边界、当前 Git 状态、阶段范围、任务顺序和学习门禁的书面事实来源。

- [x] 核对仓库根目录、当前分支、工作区、最近提交和远程地址。
- [x] 记录阶段目标、排除项、任务顺序和验收门禁。
- [x] 记录当前环境和目录隔离规则。
- [x] 检查两个任务 1 文档的完整新增文件差异和空白错误。
- [x] 与用户完成任务 1 学习检查。
- [x] 用户确认后，使用 `docs: record phase 0 baseline` 创建提交。

**验收证据：**

- 两份文档都位于当前仓库根目录下。
- 没有创建应用、测试、环境或依赖文件。
- `git status --short --untracked-files=all` 只显示两份新增文档。
- 用户能够解释为什么编辑前必须检查仓库根目录和分支。

### 任务 2：搭建 Python 工程

**文件：**

- 创建：`.gitignore`
- 创建：`.env.example`
- 创建：`pyproject.toml`
- 创建：`README.md`
- 创建：`backend/app/__init__.py`
- 创建：`tests/__init__.py`
- 仅在本地创建且不得跟踪：`.venv/`

**产出：** 建立声明了运行依赖与质量检查依赖、可以安装使用的 Python 3.12 开发环境。

- [ ] 使用 `git check-ignore -v .env` 确认 `.env` 尚未被忽略；命令不得返回匹配规则。
- [ ] 添加 `.gitignore`，再使用 `git check-ignore -v .env` 确认 `.env` 已被忽略。
- [ ] 创建只包含安全非敏感默认值、API Key 留空的 `.env.example`。
- [ ] 在 `pyproject.toml` 中定义项目元数据、依赖、pytest 路径、Ruff 规则和严格 mypy 设置。
- [ ] 使用 Python 3.12 创建 `.venv`，并安装项目开发依赖。
- [ ] 运行已配置的 Ruff、mypy 和 pytest 命令，证明工程骨架可以使用。
- [ ] 完成任务 2 本人练习并得到用户确认。
- [ ] 使用 `build: scaffold MarketMind AI project` 创建提交。

### 任务 3：使用 TDD 添加类型化应用配置

**文件：**

- 创建：`tests/unit/core/test_config.py`
- 创建：`backend/app/core/__init__.py`
- 创建：`backend/app/core/config.py`

**产出：** 提供包含 `app_name`、`app_env`、`app_host`、`app_port`、`log_level`、`siliconflow_base_url`、`siliconflow_model` 和 `siliconflow_api_key` 的类型化配置对象。

- [ ] 为安全默认值、环境变量覆盖、端口整数解析、可选 API Key 和不会泄露密钥的 `repr` 编写测试。
- [ ] 只运行 `tests/unit/core/test_config.py`，看到测试因 `app.core.config` 不存在而失败。
- [ ] 实现让测试通过所需的最小 Pydantic Settings 模型。
- [ ] 再次运行聚焦测试并看到通过。
- [ ] 运行 Ruff、mypy 和完整测试。
- [ ] 完成任务 3 本人练习并得到用户确认。
- [ ] 使用 `feat: add typed application settings` 创建提交。

### 任务 4：使用 TDD 添加请求 ID 中间件

**文件：**

- 创建：`tests/unit/middleware/test_request_id.py`
- 创建：`backend/app/middleware/__init__.py`
- 创建：`backend/app/middleware/request_id.py`

**产出：** 实现能够接收或生成请求 ID、写入 `request.state`，并通过 `X-Request-ID` 响应头返回 ID 的中间件。

- [ ] 编写测试，证明缺少请求头时会生成有效 UUID、传入 ID 时会原样保留、请求状态包含相同值，而且响应头与其一致。
- [ ] 只运行中间件测试，看到测试因中间件模块不存在而失败。
- [ ] 实现让测试通过所需的最小中间件。
- [ ] 再次运行聚焦测试并看到通过。
- [ ] 运行 Ruff、mypy 和完整测试。
- [ ] 完成任务 4 本人练习并得到用户确认。
- [ ] 使用 `feat: add request id middleware` 创建提交。

### 任务 5：使用 TDD 添加 FastAPI 健康检查纵向切片

**文件：**

- 创建：`tests/api/test_health.py`
- 创建：`backend/app/schemas/__init__.py`
- 创建：`backend/app/schemas/health.py`
- 创建：`backend/app/api/__init__.py`
- 创建：`backend/app/api/v1/__init__.py`
- 创建：`backend/app/api/v1/health.py`
- 创建：`backend/app/main.py`

**产出：** 通过应用工厂提供 `GET /api/v1/health/live` 和 FastAPI 接口文档页面。

- [ ] 编写 API 测试，覆盖存活检查的精确响应内容、200 状态码、请求 ID 响应头和 `/docs` 的 200 状态码。
- [ ] 只运行健康检查 API 测试，看到测试因应用模块不存在而失败。
- [ ] 添加响应模型、健康检查路由和组装请求 ID 中间件的应用工厂。
- [ ] 再次运行聚焦 API 测试并看到通过。
- [ ] 在 8010 端口启动应用，手工验证存活检查和接口文档端点。
- [ ] 运行 Ruff、mypy 和完整测试。
- [ ] 完成任务 5 本人练习并得到用户确认。
- [ ] 使用 `feat: add FastAPI health vertical slice` 创建提交。

### 任务 6：完成本人学习门禁

**文件：**

- 修改：`backend/app/core/config.py`
- 修改：`backend/app/api/v1/health.py`
- 修改：任务 3 和任务 5 创建的配置与健康检查测试
- 修改：`docs/learning/phase-0-baseline.md`

**产出：** 由用户亲手实现就绪检查端点和调试配置，并记录阶段验收证据。

- [ ] 用户在指导下亲手添加 `GET /api/v1/health/ready`，Agent 不代写实现。
- [ ] 用户在指导下亲手添加 `APP_DEBUG` 及其环境变量覆盖测试，Agent 不代写实现。
- [ ] 用户故意写错一次健康检查响应字段，观察测试失败，然后修复。
- [ ] 运行 Ruff、mypy 和完整测试。
- [ ] 在 8010 端口手工启动服务，验证阶段端点。
- [ ] 复习常见故障排查方法并回答阶段面试口述题。
- [ ] 使用 `docs: complete phase 0 learning gate` 创建提交。
- [ ] 本地检查通过后，使用 `git push -u origin phase/0-foundation` 推送阶段分支。
- [ ] 停止并等待本人明确验收；不得合并或创建标签。

## 阶段 0 完成门禁

只有当六个任务全部勾选、聚焦测试和完整测试通过、Ruff 与 mypy 通过、服务能在 8010 端口手工启动、阶段分支已经推送，并且用户明确确认学习验收通过时，阶段 0 才算完成。在得到该确认前，仍然禁止合并到 `main` 或创建 `v0.1.0` 标签。
