# 单元 9：单机部署、CI 与系统级验收设计

**状态：** 对话设计已获用户确认；本文待用户审阅。本文不是开始编码的许可，实施计划和原生执行仍需分别批准。

## 1. 目标、现状与完成标准

MarketMind AI 已有 FastAPI、MySQL、Redis、Celery、Chroma、Vue 工作台及相应的自动化测试，但尚无同源正式构建入口、完整单机编排、GitHub Actions 和真实浏览器端到端验收。现有 `compose.yaml` 只编排 Redis 与 Worker；`Dockerfile` 只构建 Python Worker 镜像；前端 `/api` 代理仅供 Vite 开发使用。

用户没有服务器和域名，但本机 Docker Desktop 正在运行。因此本单元交付的是**可在本机完整复现、可迁移到单机服务器的部署工程**，不是已经上线的公网服务。成功标准是：一个入口访问静态前端与 `/api/v1`；一次性迁移成功后 API/Worker 才启动；商品、知识、审核和研究链路使用真实 MySQL/Redis/Chroma/Celery；CI 自动运行工程检查；浏览器 E2E 在不花费模型调用费用的条件下验证关键业务闭环；重启后业务数据保留，故障和恢复步骤可复现。

保留前几个单元的学习方式：四个 Task，每个 Task 一份本地中文教程，按实际代码编写顺序解释每行或重复代码组为何存在、调用的是项目代码还是已有包、请求与数据流、机制、RED/GREEN 证据及适用边界。`docs/learning/` 和现有用户练习测试只留本地，不纳入提交。

## 2. 方案选择与非目标

| 方案 | 取舍 | 结论 |
| --- | --- | --- |
| 扩展现有 Docker Compose，单机运行完整服务；GitHub Actions + Playwright | 与现有 Dockerfile/Compose 和服务拆分一致，既能本机复现又能迁移到单机服务器 | 采用 |
| Windows 本机进程组合，再单独维护 CI 部署方式 | 少构建镜像，但环境差异大，无法验证最终运行拓扑 | 不采用 |
| Kubernetes、云托管数据库和公网发布 | 没有目标服务器/域名，配置、费用和运维面显著增加 | 不采用 |

本单元不增加业务表、租户、外部企业系统、模型供应商专用分支、Prometheus 集群或自动公网发布；也不把测试桩结果解释成真实 Qwen、DeepSeek、OpenAI 等模型质量。无域名时仅绑定本机入口，不声称具备公网 TLS、跨主机高可用或真实生产环境的秘密管理。后续取得目标服务器时，再单独完成域名、TLS、主机防护和供应商实际调用验收。

## 3. 单机拓扑与请求流

在现有 `compose.yaml` 基础上编排 `mysql`、`redis`、`chroma`、一次性 `migration`、`api`、`celery-worker` 和 `web`。`api`、`migration`、`celery-worker` 复用同一个 Python 应用镜像，命令各不相同；`web` 用 Node 构建 Vue 静态文件，再由轻量 Web 服务器提供文件和反向代理，不运行 Vite 开发服务器。优先使用 Compose 默认内部网络，不额外制造网络层抽象。

浏览器只访问绑定 `127.0.0.1` 的 `web` 端口。`/api/*` 原路径反向代理到 `api:8010`，其余路径提供 SPA 文件并支持刷新后回退到 `index.html`；前端继续使用现有相对 `/api/v1`，不增加环境 URL 或把 Token 放入 URL。MySQL、Redis、Chroma、API 与 Worker 不向宿主机发布端口。需要宿主机直连 Redis 的旧开发方式可使用明确的开发覆盖配置，不改变默认部署边界。

API、Worker 共用受控知识文件卷，MySQL 和 Chroma 各有持久卷。MySQL 是业务状态真相，Chroma 保存可用于检索的向量，原始文件不能只留在 API 容器可写层。Redis 用于缓存、限流与任务队列，不被当作审核、研究或问答的永久业务历史。容器重建不能清空这些卷。

## 4. 启动顺序、配置与安全边界

MySQL、Redis 必须通过自身健康检查；Chroma 使用与锁定镜像版本匹配的健康探针。`migration` 在数据库健康后运行已有 Alembic `upgrade head`，退出码为零才允许 API 与 Worker 启动；迁移失败时服务不得以旧表结构接受写请求。API 的现有 `/health/live` 用于进程存活，`/health/ready` 用于已有 MySQL/Redis 依赖就绪；知识相关 E2E 另验证 Chroma，不把 Chroma 故障错误地解释为所有商品接口不可用。Web 在 API 就绪后才对外提供完整页面。Compose 的 `service_healthy` 和 `service_completed_successfully` 支持这两类门禁。

本地密码、JWT、数据库/Redis 连接串和可选模型密钥放在 Git 忽略的本地密钥文件；提交的示例只含字段名和无效占位值。Compose 将这些文件作为服务级 secrets 挂载，应用 Settings 从容器密钥目录读取相应值；普通非敏感参数才用环境变量。不得把真实值写入 Dockerfile、Compose 源码、CI YAML、浏览器包、命令行参数或日志。CI 只使用一次性测试凭据；真实供应商密钥不进入自动化。`APP_DEBUG=false`，初始化 Admin 仍调用现有 CLI，不能在镜像或仓库里预置管理员密码。

目前只有本机回环访问，无域名和 TLS；即使容器安全检查通过也不能公开绑定到 `0.0.0.0`。如果以后迁移到公网主机，必须先增加 TLS、主机防火墙、备份保管和合适的秘密管理，再重新进行安全验收。

## 5. CI 质量门禁

新增 GitHub Actions，在阶段分支/main 推送及 Pull Request 上运行；工作流以提交中的锁定依赖安装，不引用开发机 `.env`。快速检查分为：Python 3.12 的 pytest、Ruff、mypy（测试用 MySQL/Redis 是一次性服务）；Node 22 的 `npm ci`、Vitest、Vue 类型检查及生产构建。检查还要验证容器镜像可构建、Compose 配置可解析，失败即阻止宣称该提交可交付。

浏览器作业在隔离的 Compose 项目名下启动完整栈和仅用于测试的模型服务，等待健康探针而不是固定睡眠，完成后只清理这个一次性 CI 项目的容器和卷。失败时保存短期的 Playwright trace/截图和经过检查的服务日志；只使用合成数据和仅在该作业有效的测试凭据，因为 trace 可能包含请求头，只允许受限、短期保留，不上传真实环境轨迹、真实密码或供应商响应。GitHub Actions 真正运行且成功之前，只能说“工作流已编写/本地验证”，不能说“远端 CI 通过”。本地已有未跟踪练习测试不属于提交后的 CI 源树，也不能被悄悄加入阶段提交。

## 6. 系统级端到端测试与模型费用隔离

Playwright 仅增加 Chromium 一种浏览器的少量高价值测试，使用可访问名称/标签定位，避免依赖 CSS 类名。测试操作真实构建的页面、同源代理、FastAPI、数据库和 Worker，至少覆盖：Admin 登录/退出与角色权限；商品创建、筛选、Listing 检查、`.xlsx` 导入/导出；知识文件上传、索引到 ready、带来源问答；语义审核的异步终态；研究证据、一次性 Admin 审批与批准后报告下载。对不可审核/未批准结果验证拒绝路径，不只检查按钮隐藏。使用独立测试账号和合成文件，任务轮询有超时与终态断言。

模型请求只指向 E2E 覆盖配置中的确定性 OpenAI-compatible 测试服务。它只实现当前代码确实调用的 `/v1/embeddings`、`/v1/chat/completions` 响应，针对已知测试模型和请求产生结构合法的向量、语义审核、RAG 与研究结果；未知模型/请求明确失败，不提供通用“总是成功”的假接口。测试服务不出现在默认部署，不能误连接真实供应商。现有服务层单元/集成测试继续检查无效 JSON、无来源、供应商失败等细节；浏览器 E2E 重点证明跨进程接线和用户可见状态，不复制所有单元断言。真实模型效果、价格和 JSON Mode 兼容性属于另行显式批准的人工烟雾测试，不是自动化通过条件。

## 7. 故障恢复与操作手册

README 增加从配置示例、构建、启动、迁移、初始化 Admin、查看健康/日志、升级、停止到故障定位的命令；说明 Docker CLI 若未加入当前终端 PATH 时如何定位它。每种失败保留明确边界：数据库不可用时迁移/API 不应假启动；Redis 不可用时 ready 不应显示成功；Chroma 或模型服务故障只影响依赖它们的知识/AI 操作，并显示真实错误，不伪造完成。沿用后端 `X-Request-ID` 和安全错误码追踪请求，不新增日志平台。

持久化与恢复手册分别说明 MySQL 业务数据、知识原件、Chroma 索引卷和 Redis 队列的职责；备份前停止 API/Worker 写入，再对 MySQL 做逻辑导出并归档知识文件与 Chroma 卷，以免复制过程中数据继续变化。恢复只在**独立的测试 Compose 项目**中演练，并校验记录、文件与引用一致性；至少演练一次重启后的数据保留和一次测试数据恢复。不得对用户现有卷自动执行 `down --volumes`、覆盖恢复或重置 Chroma。备份文件包含敏感内容，必须保存在忽略目录中，不能上传 CI artifact 或提交。若恢复后有任务仍显示 pending/running，不可凭 Redis 结果强行标记成功，应按 MySQL 状态及 Worker 日志人工排查。

## 8. 四个 Task 与验收证据

1. **Task 1：容器与同源入口。** 扩展 Compose/Python 镜像、前端静态镜像和代理；实现迁移门禁、配置/卷/健康检查；验证页面刷新、API 同源、内部服务不暴露、重启数据保留。
2. **Task 2：GitHub Actions。** 后端/前端检查、镜像构建和 Compose 校验；以一次性数据库和 Redis 测试，验证失败会使流水线失败，不读取本机秘密。
3. **Task 3：系统 E2E。** 加入测试专用兼容模型服务、隔离的完整栈和 Playwright 关键旅程；验证异步终态、角色边界、证据与交付、失败轨迹，无付费请求。
4. **Task 4：可操作性与最终验收。** 完成启动/升级/备份/恢复手册和隔离恢复演练；核对测试、类型、构建、容器、浏览器及约 1440/1024/390 像素视觉证据；形成四份仅本地保存的中文教程与剩余风险清单。

每个 Task 先用最小检查证明目标行为缺失或配置无效，再完成实现、重跑聚焦检查、运行相关回归、精确暂存工程文件并提交。只提交工程代码、设计/实施计划和正式运行文档；不暂存 `docs/learning/` 或 `tests/unit/models/test_product_practice.py`，不读取本地 `.env`，不擅自推送、合并或删除分支。任何未实际运行的外部服务、远端 CI、真实模型调用、视觉或恢复验收均逐项标注“未验证”，不能以自动化替代。

## 9. 参考依据

- [Docker Compose 单机部署](https://docs.docker.com/compose/how-tos/production/)
- [Compose 启动顺序与健康门禁](https://docs.docker.com/compose/how-tos/startup-order)
- [Docker Compose 密钥](https://docs.docker.com/compose/how-tos/use-secrets/)
- [Docker 数据卷备份与恢复](https://docs.docker.com/engine/storage/volumes/)
- [Playwright CI](https://playwright.dev/docs/ci)
- [GitHub Actions 服务容器](https://docs.github.com/en/actions/tutorials/use-containerized-services)
