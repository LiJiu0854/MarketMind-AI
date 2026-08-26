# 阶段 0 学习基线

## 项目目标

MarketMind AI 是面向电商运营团队的内部 AI 平台。完整产品将支持商品数据导入与清洗、Listing 检查、大模型辅助分析、竞品研究、内部知识检索、长时间 Agent 任务、实时进度、报告导出、企业系统集成、MCP 工具、RPA、权限、可观测性、测试和部署。

阶段 0 不实现上述业务功能。它只建立一套最小但可信的工程基础，使后续阶段能够安全地继续开发。

## 已核实的环境

创建项目文件前，已在 2026-08-26 核实以下状态：

| 检查项 | 已核实的值 |
| --- | --- |
| 仓库根目录 | `C:/Users/17905/Desktop/MarketMind-AI` |
| 当前分支 | `phase/0-foundation` |
| 当前提交 | `375516c chore: initialize MarketMind AI` |
| 任务 1 开始前的工作区 | 干净 |
| origin 拉取地址 | `https://github.com/LiJiu0854/MarketMind-AI.git` |
| origin 推送地址 | `https://github.com/LiJiu0854/MarketMind-AI.git` |
| 任务 1 开始前的跟踪文件 | 无 |

用于核实基线的命令：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short
git log --oneline --decorate -3
git remote -v
```

`git status --short` 没有输出，表示检查时不存在已暂存、已修改、已删除或未跟踪的文件。

## 目录隔离

当前打开的 `MarketMind-AI` 文件夹已经是仓库根目录。所有新项目路径都必须直接创建在它下面；如果再创建一层 `MarketMind-AI/` 或 `marketmind-ai/`，就会形成错误的嵌套项目。

旧项目 `C:\Users\17905\Desktop\helloagents-deepresearch` 位于新仓库之外，也不属于本项目的操作范围。不得把它的文件作为实现来源读取或复制，也不得修改或删除。MarketMind AI 必须从零实现。

## 为什么要先建立基线

修改文件前，必须先明确回答三个问题：

1. **我正在什么位置编辑？** 检查仓库根目录可以防止文件被创建到父目录、重复嵌套目录或无关项目中。
2. **我正在修改哪条开发线？** 检查分支可以防止未完成的阶段代码被直接写入 `main`。
3. **工作区中已经存在哪些改动？** 检查状态可以防止误覆盖已有工作，也能区分原有改动和本次任务产生的改动。

检查远程地址还可以避免以后把代码推送到错误的 GitHub 仓库。

## 阶段 0 范围

阶段 0 将建立：

- Python 3.12 项目独立虚拟环境；
- `pyproject.toml` 项目元数据与依赖配置；
- 安全的环境变量示例和忽略规则；
- 类型化配置模型；
- FastAPI 应用工厂；
- 请求 ID 中间件；
- 存活检查端点和 OpenAPI 文档；
- pytest、Ruff 和 mypy 检查；
- 学习记录、手工验证、故障排查和 Git 证据。

阶段 0 明确不实现 MySQL、Redis、Celery、LLM 调用、Vue、Docker、Nginx、RAG、MCP、RPA 和 Kubernetes。

## 学习验收位置

执行清单和技术门禁记录在 `docs/plans/phase-0-foundation.md`。学习证据和面试回答记录在本文件中，使仓库不仅能说明“实现了什么”，还能说明学习者是否能够解释并复现这些内容。

每个任务都遵循以下循环：

```text
解释问题和文件边界
→ 涉及功能行为时先编写聚焦的失败测试
→ 观察符合预期的失败
→ 添加最小实现
→ 观察聚焦测试通过
→ 运行 Ruff、mypy 和完整测试
→ 完成一个由学习者亲手编写的小练习
→ 复查并提交
→ 得到确认后再进入下一任务
```

## 任务 1 学习检查

开始任务 2 前，学习者应在项目根目录亲手运行：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short --untracked-files=all
```

然后用自己的话回答：

1. `git rev-parse --show-toplevel` 在本项目中防止什么风险？
2. 为什么阶段开发要在 `phase/0-foundation` 上进行，而不是直接修改 `main`？
3. 完成任务 1 后，为什么 `git status --short --untracked-files=all` 应该只显示两份文档？

当回答能够体现对仓库位置、分支隔离和工作区状态的理解时，任务 1 的本人学习检查才算通过。用户确认前不得开始任务 2。

### 任务 1 验收记录

验收日期：2026-08-26

本人学习检查已通过。学习者已经能够说明：

- 检查仓库根目录可以避免路径误判，以及在错误项目或嵌套目录中修改文件；
- 阶段分支用于隔离未完成改动，使 `main` 保持当前已验收基线，并方便独立测试、审查、合并或放弃阶段内容；
- 初始工作区是干净的，而且本轮严格只执行任务 1，因此 Git 状态只能出现本任务要求创建的两份文档。

补充纠正：`git branch -D` 删除的是本地分支引用，不是完整的工作区或阶段回退操作。已合并分支通常优先使用更安全的 `git branch -d`；只有明确决定放弃未合并分支且确认没有需要保留的提交时，才考虑使用 `-D`。

## 任务 2 学习验收记录

验收日期：2026-08-26

本人练习与口述检查已通过。学习者亲手添加了 `*.log` 忽略规则，并使用 `git check-ignore -v marketmind.log` 验证规则生效。学习者已经能够说明：

- 独立 `.venv` 可以隔离依赖版本和安装范围，减少系统环境污染，并提高环境复现能力；
- `.env` 是不提交的本机运行时配置文件，可能包含密钥；`.env.example` 是可提交的安全配置模板，不包含真实密钥；
- `pyproject.toml` 集中管理项目元数据、Python 版本范围、核心依赖、可选开发依赖，以及 pytest、Ruff 和 mypy 的工具配置。

术语纠正：`.env` 不是“仓库密钥”，`pyproject.toml` 中的 `[tool.*]` 也不是私有配置表。

## 任务 3 学习验收记录

验收日期：2026-08-26

Settings 的 TDD 与本人练习已通过：

- 首次 RED 因 `app.core.config` 不存在而失败，证明测试依赖真实配置模块；
- 最小实现加入类型化默认值、环境变量读取、整数转换和 `SecretStr` 密钥保护后，原有 3 个测试进入 GREEN；
- 学习者先编写 `app_version` 默认值和环境变量覆盖测试，观察到 2 个 `AttributeError`，再亲手添加字段使 5 个测试全部通过；
- 学习者能够区分语法错误、fixture 准备错误和功能缺失导致的有效 RED，并完成 Ruff 与 mypy 清理。

## 任务 4 学习验收记录

验收日期：2026-08-26

请求 ID 中间件的 TDD 与本人练习已通过：

- RED 因 `app.middleware.request_id` 不存在而失败，最小实现加入 UUID4 生成、客户端 ID 透传、`request.state` 写入和响应头回写后进入 GREEN；
- 测试通过真实 FastAPI 应用与 HTTPX 请求验证中间件，不使用 Mock；
- 学习者亲手补充连续请求 ID 唯一性断言；测试环境统一使用 `ASGITransport + AsyncClient`；
- mutation check 将生成逻辑临时替换为固定 ID 后，唯一性测试准确失败；恢复 UUID4 后测试重新通过。

## 任务 5 学习验收记录

验收日期：2026-08-26

FastAPI 健康检查纵向切片已完成：

- RED 因 `app.main` 不存在而失败；实现 Schema、Router、应用工厂及中间件组装后进入 GREEN；
- 真实 API 测试验证 `GET /api/v1/health/live` 返回 200、精确 JSON 和相同的 `X-Request-ID`，并验证 `/docs` 可访问；
- Uvicorn 使用 `app.main:create_app --factory` 在 `127.0.0.1:8010` 成功启动；健康检查、接口文档和 OpenAPI 均返回 200；
- OpenAPI 元数据为 `MarketMind AI`、版本 `0.1.0`，并包含 `/api/v1/health/live` 路径。

任务 5 不新增重复的本人小练习；任务 6 将集中完成 `ready` 端点、`APP_DEBUG`、故意制造测试失败、手工运行和口述验收。

## 任务 6 学习验收记录

验收日期：2026-08-26

阶段综合本人练习与技术门禁已完成：

- 学习者先为 `GET /api/v1/health/ready` 编写真实 API 测试，观察到接口缺失导致的 404，再亲手添加最小路由实现使测试进入 GREEN；
- 学习者为 `APP_DEBUG` 的安全默认值和环境变量覆盖编写测试，观察到缺少字段导致的 `AttributeError`，再添加 `bool = False` 字段，使 Pydantic 能将环境变量转换为布尔值；
- 学习者故意将就绪响应中的 `service` 改为错误值，测试准确报告响应契约差异；恢复正确实现后聚焦测试重新通过；
- 完整检查结果为 pytest 12 项通过、Ruff 通过、mypy 对 15 个源文件检查通过；
- Uvicorn 在 `127.0.0.1:8010` 启动后，存活检查、就绪检查和接口文档均返回 200；两个健康接口均返回预期 JSON 和独立的 `X-Request-ID`；
- 首次手工启动命令因工作目录与 `.venv` 相对路径组合错误而未能找到解释器；确认错误发生在应用导入前，改用已核实的解释器绝对路径成功启动，证明排障应先区分命令、环境与应用故障。

口述验收确认学习者能够解释虚拟环境的依赖隔离、路由与中间件职责、依赖注入、请求 ID 透传与生成、应用工厂的测试隔离价值、测试层级，以及通过仓库根目录、分支、解释器路径和端口进程确认当前运行对象。

两点术语校准：

- `.env` 是可能包含密钥的本机运行时配置，不得提交；`.env.example` 只提供安全占位模板，可以提交；
- `tests/unit/middleware/test_request_id.py` 聚焦单个中间件，但通过 ASGI 请求链验证行为，因此从测试边界看更接近组件测试；`tests/unit/core/test_config.py` 是更典型的单元测试，`tests/api/test_health.py` 是 API 集成测试。

## 阶段 0 面试口述题

以下问题已在最终学习门禁中完成回答：

- 为什么要使用独立虚拟环境？
- `.env.example` 和 `.env` 有什么区别？
- Router、Middleware 和 Depends 分别负责什么？
- 请求 ID 有什么价值？
- 为什么应用工厂更容易测试？
- 单元测试和 API 测试有什么区别？
- 如何确认当前启动的是这个新项目？

## Git 门禁

任务 1 的计划提交信息是 `docs: record phase 0 baseline`，但只能在任务 1 文档复查和用户确认后创建。后续每个任务都有自己独立、聚焦的提交。阶段检查通过后才能推送阶段分支；在用户明确验收前，不得合并到 `main`，也不得创建 `v0.1.0` 标签。
