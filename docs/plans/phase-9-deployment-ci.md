# 单元 9：单机部署、CI 与系统级验收实施计划

> **执行者须知：** 实施时须使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按 Task 逐项执行与核对。本计划待用户审阅；未获批准前不得执行。

**目标：** 交付本机可复现的同源单机部署、自动化 CI、无付费模型调用的真实浏览器 E2E，以及可演练的数据恢复说明。

**架构：** 扩展现有 Compose 为 MySQL/Redis/Chroma/migration/API/Worker/Web 完整栈；同一 Python 镜像运行迁移、API 和 Worker，Vue 经构建后由 Web 服务器提供，只有回环 Web 端口发布。GitHub Actions 跑现有质量门禁和隔离的系统 E2E；E2E 通过单独覆盖配置接入确定性兼容模型服务。

**技术栈：** Python 3.12、FastAPI、Pydantic Settings、Alembic、MySQL 8、Redis、Celery、Chroma、Docker Compose、Vue 3、Node 22、Web 反向代理、GitHub Actions、Playwright Chromium。

**设计依据：** `docs/plans/phase-9-deployment-ci-design.md`。执行每个 Task 前阅读本计划和设计；接口以现有 `backend/app/`、`frontend/src/` 为准。

## 全局约束

- 固定四个 Task，每个 Task 独立检查、复查和提交，并生成一份只保留本地的中文教程；教程解释真实代码的行/组职责、调用来源、原理、编写顺序与 RED/GREEN。
- 无服务器、域名和公网 TLS；唯一宿主机发布端口为 `web` 的 `127.0.0.1:8080`，不得把本地部署写成公网生产上线。
- 默认 `compose.yaml` 不发布数据库、Redis、Chroma、API、Worker 宿主机端口；旧的宿主机直连 Redis 开发方式放在显式开发覆盖文件。CI 的一次性服务容器仅对隔离 runner 开放测试连接，不改变部署拓扑。
- MySQL、Redis 健康后运行一次 Alembic `upgrade head`；迁移成功才启动 API/Worker；Web 等待 API ready。知识能力另验 Chroma，不修改现有 ready 的 MySQL/Redis 语义。
- MySQL、Chroma、知识文件使用持久卷；Redis 队列不是永久业务真相。不得对用户已有 Compose 项目或卷执行 `down --volumes`、覆盖恢复或 Chroma reset。
- 真正的密钥文件位于 Git 忽略目录并按服务挂载为 Compose secrets；CI 只用合成测试凭据，不读取 `.env`，不触发真实模型请求。
- E2E 仅 Chromium，验证真实页面→同源代理→API→MySQL/Redis/Chroma/Worker；模拟模型只在 E2E 覆盖配置中出现，未知请求必须失败。
- 仅精确暂存本 Task 工程文件；不暂存既有 `docs/learning/`、`tests/unit/models/test_product_practice.py`，不推送、不合并。
- 本机 Docker CLI 不在当前终端 PATH，但已核实安装于 `C:\Users\17905\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`；以下 `docker compose` 为可移植写法，当前 Windows 执行时使用该程序的绝对路径。所有本地试运行使用先确认不存在的独立 Compose 项目名。

## 审查重点

1. **误把数据库或向量服务发布到宿主机：** Task 1 的 `test_rejects_exposed_internal_port` 及 `docker compose config` 必须只允许 Web 的 `127.0.0.1:8080`。
2. **迁移失败却启动 API 接受写入：** Task 1 的 `test_requires_successful_migration` 和容器失败注入检查必须确认 API/Worker 未就绪。
3. **CI 指向开发库或读真实模型密钥：** Task 2 检查 `TEST_DATABASE_URL` 的库名严格是 `marketmind_test`，且工作流仅使用合成测试凭据和 fixture 密钥路径。
4. **测试模型对未知请求也返回成功：** Task 3 的 `test_rejects_unknown_model_and_prompt` 保证桩只响应约定的 Embedding/Chat 请求。
5. **E2E 成功但研究报告无证据或未批准仍可下载：** Task 3 的 `research_requires_evidence_review_and_approval` 断言来源、一次性审批、未批准 `409` 与批准后 Excel 下载。

---

## 文件职责与接口地图

| Task | 文件 | 职责 |
| --- | --- | --- |
| 1 | `compose.yaml`、`compose.dev.yaml`、`Dockerfile`、`frontend/Dockerfile`、`deploy/nginx.conf` | 完整单机栈、旧开发覆盖、共用 Python 镜像、静态 Web 镜像和同源代理 |
| 1 | `backend/app/core/config.py`、`tests/unit/core/test_config.py`、`.gitignore`、`deploy/secrets.example/README.md`、`tests/fixtures/deploy.env`、`tests/fixtures/deploy-secrets/*` | Settings 读取容器 secrets；保护真实密钥；提供明确标识的合成测试凭据 |
| 1 | `scripts/check_compose.py`、`tests/unit/scripts/test_check_compose.py` | 用标准库校验解析后的 Compose 服务、端口、迁移门禁和持久卷契约 |
| 2 | `.github/workflows/ci.yml` | Python/Node 质量检查、镜像构建、Compose 契约；为 Task 3 留 E2E 作业位置 |
| 3 | `tests/e2e/__init__.py`、`tests/e2e/model_stub.py`、`tests/e2e/Dockerfile.model-stub`、`tests/unit/test_model_stub.py`、`compose.e2e.yaml` | 仅测试用 OpenAI-compatible 响应与 E2E 服务覆盖 |
| 3 | `backend/app/cli/create_admin.py`、`tests/unit/cli/test_create_admin.py` | 保留交互式 CLI，增加从标准输入读取密码的非交互式测试初始化模式 |
| 3 | `frontend/package.json`、`frontend/package-lock.json`、`frontend/playwright.config.ts`、`frontend/e2e/auth-products.spec.ts`、`frontend/e2e/knowledge-research.spec.ts`、`.github/workflows/ci.yml`、`.gitignore` | 锁定 Playwright；浏览器旅程；在 CI 启动隔离栈并短期保存失败轨迹 |
| 4 | `README.md`、`docs/operations/single-host.md` | 本机启动、升级、健康/日志、备份、隔离恢复、已验证与未验证边界 |

接口约定：`scripts/check_compose.py::validate_compose(config: dict[str, object]) -> None` 对违反部署契约的配置抛 `ValueError`，CLI 从标准输入读取 `docker compose config --format json`。测试桩 `tests/e2e/model_stub.py::embedding_for(text: str) -> list[float]` 对合成输入返回固定 `[1.0, 0.0, 0.0]`，只验证索引/检索接线，不冒充真实语义相似度；`completion_for(model: str, messages: list[dict[str, object]]) -> dict[str, object]` 仅返回现有 Pydantic Schema 可接受的 JSON 内容，未知模型/提示抛 `ValueError`。Playwright 只通过 Web 的同源 `http://127.0.0.1:8080`，不直接访问 API/数据库/模型服务。

## Task 1：完整单机栈与同源入口

**交付：** 独立项目名下可构建、可启动、可刷新路由、可读健康接口的真实容器栈；默认只发布 Web；重建容器不删除业务卷。

**接口：** 产出 `Settings()` 对 `/run/secrets` 的读取、`validate_compose(config: dict[str, object]) -> None`、默认 `compose.yaml` 与测试 fixture；后续 Task 直接消费，不再复制部署配置。

- [ ] **步骤 1：写 Settings 和 Compose 契约测试。** 在 `test_config.py::test_reads_docker_secret_files` 用临时目录写 `database_url`、`jwt_secret`，断言 `Settings(_env_file=None, _secrets_dir=tmp_path)` 读取 `SecretStr` 且无配置时保持安全默认；在 `test_check_compose.py` 写 `test_rejects_exposed_internal_port`、`test_requires_successful_migration`、`test_requires_persistent_business_volumes`，使用最小解析后字典断言错误和合法配置。

  核心断言：`settings.database_url.get_secret_value() == fixture_url`；解析后的 `web.ports` 仅有一项且 `host_ip="127.0.0.1"`、`published="8080"`、`target=80`，任意 `mysql/redis/chroma/api/celery-worker.ports` 非空必须抛 `ValueError`；缺 `api/worker → migration: service_completed_successfully` 或业务卷也必须抛 `ValueError`。
- [ ] **步骤 2：确认 RED。** 运行 `.venv\Scripts\python.exe -m pytest tests/unit/core/test_config.py::test_reads_docker_secret_files tests/unit/scripts/test_check_compose.py -q`；预期因新函数/契约缺失失败，而不是缺包或连接外部服务。
- [ ] **步骤 3：实现配置和契约校验。** `SettingsConfigDict` 在容器 `/run/secrets` 存在时加载该目录，不影响 Windows 本地 `.env`；`validate_compose` 检查固定七项服务、仅 Web `127.0.0.1:8080` 发布、API/Worker 依赖 migration 的 `service_completed_successfully`、业务卷存在、禁止 `container_name`；CLI 只输出不含密钥的错误摘要。
- [ ] **步骤 4：确认 GREEN。** 重跑步骤 2 的命令；预期全部通过。运行 Ruff 和 mypy 检查新增 Python 文件。
- [ ] **步骤 5：建立合成部署夹具与忽略规则。** `tests/fixtures/deploy.env` 指向仓库内仅测试用的 `tests/fixtures/deploy-secrets/`；其中 `mysql_root_password`、`mysql_app_password`、`database_url`、`jwt_secret`、`redis_password`、`redis_url`、`celery_broker_url`、`celery_result_backend`、`llm_api_key`、`embedding_api_key` 均为显著标注的无效测试值。真实同名文件只允许建在被 `.gitignore` 忽略的 `deploy/secrets/`；`deploy/secrets.example/README.md` 说明文件名、URL 内部主机名和创建方式，不含真实值。
- [ ] **步骤 6：扩展 Python 镜像。** `Dockerfile` 复制 `alembic.ini`、`alembic/` 与 `backend/`；验证同一镜像可分别执行 Alembic、Uvicorn 工厂和 Celery 命令，不内置密钥。
- [ ] **步骤 7：建立静态 Web 镜像和代理。** `frontend/Dockerfile` 以 Node 22 执行 `npm ci && npm run build`，再交给 Web 服务器；`deploy/nginx.conf` 保留 `/api/*` 原路径代理及 SPA 回退。运行 Web 服务器配置检查，预期成功。
- [ ] **步骤 8：扩展 Compose。** `compose.yaml` 配置七服务、服务级 secrets、内部连接 URL、必要的共享卷、健康检查和迁移门禁；MySQL 用官方 `_FILE` 变量读密钥，Redis 从密钥文件生成容器内临时配置再以配置文件启动，不能把密码展开到 `redis-server` 参数。`compose.dev.yaml` 只供显式启用的宿主机 Redis 开发端口；镜像版本固定为已本机验证的版本/摘要，不使用 `latest`。
- [ ] **步骤 9：运行部署静态检查。** 以测试用 env 文件执行 `docker compose --env-file tests/fixtures/deploy.env config --format json | python scripts/check_compose.py`，预期退出码 0；删除迁移依赖或加入 MySQL `ports` 的临时输入必须使校验失败。运行 `docker compose ... build`，预期成功。
- [ ] **步骤 10：在隔离项目做实际烟雾。** 先确认 `mm_phase9_local` 不存在、回环端口 8080 未被占用，再以 `-p mm_phase9_local` 启动；确认 migration 为 0、API/Worker/Web healthy、浏览器入口 `/` 与刷新路由可读、`/api/v1/health/ready` 为 200、内部服务无宿主机端口；故意提供错误数据库 URL 的另一独立项目时 API/Worker 不得 healthy。只清理本 Task 创建的测试项目，不清除用户既有卷。
- [ ] **步骤 11：运行 Task 1 回归。** 跑后端项目测试（排除用户本地练习测试）、Ruff、mypy、前端 test/typecheck/build；所有检查须通过或逐项报告真实环境限制。
- [ ] **步骤 12：写本地教程。** 保存 `docs/learning/phase-9-task-1-deployment.md`，逐行/重复段解释镜像、Compose、代理、secrets、测试和实际故障，不暂存。
- [ ] **步骤 13：精确提交。** 只暂存 Task 1 工程文件，核对 `git diff --cached --name-only` 后提交 `feat: add single-host Compose deployment`。

## Task 2：GitHub Actions 基础质量门禁

**交付：** 可在干净仓库运行 Python/Node 检查、镜像构建与 Compose 契约的工作流；远端是否通过必须以实际运行记录为准。

**接口：** 消费 Task 1 的 `tests/fixtures/deploy.env`、`scripts/check_compose.py`、完整 `compose.yaml`；向 Task 3 留出可追加 E2E 作业的同一工作流。

- [ ] **步骤 1：记录工作流缺口和本地基线。** 检查 `.github/workflows/ci.yml` 尚不存在；在本机执行现有后端项目测试、Ruff、mypy 和前端 test/typecheck/build，记录基线。Redis/MySQL 不可用时先报告环境状态，不把环境失败当成代码 RED。
- [ ] **步骤 2：新增 `.github/workflows/ci.yml`。** 对 `main`、`phase/**`、`codex/**` 的 push 与 Pull Request 运行；Python 作业使用 3.12、一次性 MySQL 8/Redis 服务和严格指向 `marketmind_test` 的 `TEST_DATABASE_URL`，先运行 `alembic -x database=test upgrade head`，再执行 `pytest`、Ruff、mypy；Node 作业使用 Node 22、`npm ci`、Vitest、typecheck、build；部署作业构建镜像并用测试 fixture 运行 `config --format json | python scripts/check_compose.py`。不配置生产密钥、真实模型 URL 或 `continue-on-error`。
- [ ] **步骤 3：本地复跑等价命令。** 用测试库和本地 Redis 运行 Python 门禁、Node 门禁及镜像/Compose 检查；预期全绿。审核工作流在缺少 `TEST_DATABASE_URL`、迁移失败、pytest 非零、npm 构建失败时不能继续标为成功；不伪称尚未推送的远端 Actions 已通过。
- [ ] **步骤 4：写本地教程。** 保存 `docs/learning/phase-9-task-2-ci.md`，解释 jobs、服务容器、测试库隔离和失败传播，不暂存。
- [ ] **步骤 5：精确提交。** 只暂存 `.github/workflows/ci.yml` 及本 Task 必需文件，提交 `ci: add backend frontend and container checks`。

## Task 3：无付费模型调用的系统 E2E

**交付：** 合成测试栈中完成关键真实用户旅程；CI 不连接任何真实模型，失败可定位到浏览器、API、Worker 或存储边界。

**接口：** 消费 Task 1 的部署栈和 Task 2 的工作流；测试桩仅接受 `fixture-chat`、`fixture-embedding`，E2E 覆盖配置将 `LLM_BASE_URL`、`EMBEDDING_BASE_URL` 指向 `model-stub` 容器。现有 `ResearchAction`、`ResearchReport`、`LLMReviewResult`、`RAGModelResult` 是输出契约。

- [ ] **步骤 1：先写测试桩契约测试并确认 RED。** `tests/unit/test_model_stub.py::test_known_requests_match_existing_schemas` 断言固定三维向量及四种 Schema 有效；`test_rejects_unknown_model_and_prompt` 断言未知模型/提示与缺少知识来源时报错；运行 `.venv\Scripts\python.exe -m pytest tests/unit/test_model_stub.py -q`，预期缺实现失败。

  核心断言：`embedding_for("fixture") == [1.0, 0.0, 0.0]`；`LLMReviewResult`、`RAGModelResult`、`ResearchAction`、`ResearchReport` 分别能验证已知提示结果；`completion_for("unknown", messages)` 必须抛 `ValueError`，不能返回默认成功内容。
- [ ] **步骤 2：实现最小测试桩并确认 GREEN。** 用标准库 `ThreadingHTTPServer` 实现 `/health`、`/v1/embeddings`、`/v1/chat/completions`；`completion_for` 只产生业务 JSON，HTTP handler 再封装 OpenAI SDK 需要的 `id/object/created/model/choices/message/content` 与稳定 usage。研究动作依已有步骤按 read_product→search_knowledge→finish 给出，报告从请求中选本次登记的 knowledge `source_id`，不虚构坐标；未知路由/模型/提示返回非 2xx。重跑测试与 Ruff/mypy。
- [ ] **步骤 3：写非交互式管理员初始化测试并确认 RED。** 在现有 `test_create_admin.py` 测试 `--email`、`--full-name`、`--password-stdin` 成套使用时只从 stdin 读密码，缺任一参数拒绝，原有交互模式保持；运行聚焦 pytest，预期新 CLI 行为失败。
- [ ] **步骤 4：实现 CLI 并确认 GREEN。** 只扩展 `backend/app/cli/create_admin.py` 的参数解析与安全输入，仍调用现有 `create_user` 服务；不把密码放入命令行参数或日志，重跑聚焦和原有 CLI 测试。
- [ ] **步骤 5：接入测试栈与浏览器。** 新增只在 `-f compose.yaml -f compose.e2e.yaml` 使用的 `model-stub`；用 fixture 假密钥和模型名配置 API/Worker；将 `@playwright/test` 锁入前端开发依赖，`frontend/playwright.config.ts` 只启用 Chromium、`baseURL=http://127.0.0.1:8080`、CI 单 worker、失败重试 trace，禁止 `test.only`。安装浏览器只选 Chromium。
- [ ] **步骤 6：写浏览器测试并确认 RED。** `auth-products.spec.ts` 测登录/退出、Analyst 无用户管理、Admin 商品创建/筛选/Listing 检查及 `.xlsx` 导入导出；`knowledge-research.spec.ts::research_requires_evidence_review_and_approval` 测上传到 ready、带来源问答、语义审核终态、研究证据和报告、未批准下载被拒、Admin 一次性批准后 Excel 下载。测试只用有界 `expect`/轮询和可访问标签，不用固定睡眠。先在未配置模型桩的栈上运行，预期 AI 旅程不能通过，并记录具体边界。
- [ ] **步骤 7：确认 E2E GREEN。** 在先确认不存在的独立项目名下启动 E2E 栈，以标准输入创建合成 Admin，运行 `npm run test:e2e`；预期关键旅程通过且模型桩无外网调用。执行失败场景：去掉文档证据时不可审核/不可下载；第二次审批应得到冲突。仅处理本次创建的测试项目，记录每项实际结果。
- [ ] **步骤 8：接入 CI。** 在同一工作流增加隔离的 E2E 作业：构建/启动、等待健康、创建合成 Admin、运行 Chromium、失败时短期保留受限 trace、在 `always()` 清理只属于本作业的项目。
- [ ] **步骤 9：运行 Task 3 回归。** 重跑模型桩/CLI 单元测试、浏览器 E2E、前后端质量门禁，分别记录实际结果。
- [ ] **步骤 10：写本地教程。** 保存 `docs/learning/phase-9-task-3-e2e.md`，解释兼容协议、测试隔离、浏览器定位、异步等待与无付费边界，不暂存。
- [ ] **步骤 11：精确提交。** 只暂存 Task 3 工程文件，检查暂存清单后提交 `test: add cost-free full-stack browser acceptance`。

## Task 4：运行手册、恢复演练与单元验收

**交付：** 他人可按文档从零运行和排障；隔离恢复有实际证据；所有未验证项被明确列出。

**接口：** 消费前三个 Task 的镜像、Compose、CI、E2E 和已有健康端点；不新建业务层或外部监控平台。

- [ ] **步骤 1：写运行/恢复验收清单并观察缺口。** 清单至少要求：迁移门禁、唯一回环 Web 端口、刷新路由、`/health/ready`、角色/业务 E2E、容器重建后 MySQL/文件/Chroma 保留、备份后独立项目恢复与引用一致性；先核对现有 README 不足与未演练项。
- [ ] **步骤 2：完成 `docs/operations/single-host.md` 与 README 入口。** 文档按 Windows PowerShell 和通用 Compose 说明：准备忽略的密钥文件、构建/启动/升级、交互式 Admin 创建、状态/日志/请求 ID、无模型配置时功能边界、受控停止、备份 MySQL/知识文件/Chroma、在隔离项目恢复并检查、数据卷和 Redis 队列差异。所有破坏性命令明确项目名、目标卷和前置核对，不提供对默认项目一键清库命令。
- [ ] **步骤 3：实际执行并记录验证。** 在已确认归本 Task 所有的独立项目中运行完整启动、浏览器 E2E、容器重建后读取原记录/文件/引用；停止写入，备份合成数据，在另一个先确认不存在的项目中恢复并核对关联数据。失败时按根因修正文档或前三 Task 代码，再重跑相关检查；不碰用户既有数据卷。
- [ ] **步骤 4：最终质量与视觉检查。** 运行后端项目 pytest、Ruff、mypy，前端 test/typecheck/build、Compose 契约、镜像构建与 E2E；浏览器人工检查约 1440/1024/390 像素宽度和键盘主路径。若尚未授权推送，远端 Actions 状态记为未验证；真实付费模型、公网 TLS、真实生产备份仍记为未验证。
- [ ] **步骤 5：完成中文教程。** 保存本地 `docs/learning/phase-9-task-4-operations-acceptance.md`，与前三篇一起检查代码来源、逐行/重复段解释和真实命令结果，不暂存。
- [ ] **步骤 6：精确提交并报告。** 只暂存 README/正式操作文档和必要修正，`git diff --cached --name-only` 不得有学习文档或用户练习文件，提交 `docs: complete phase 9 operations and acceptance`。最终报告包含四次提交、测试证据、不可验证项和未推送状态。

## 执行方式与停止点

本计划优先推荐**当前对话原生执行**：四个 Task 有明确顺序，Compose 是 CI/E2E 的前提，而用户一直要求同一对话与本地教程。计划经用户审阅批准后才调用 `superpowers:executing-plans`；每个 Task 分别复查，不因计划列出命令就声称命令已运行。单元 9 不自动推送、合并或发布公网。
