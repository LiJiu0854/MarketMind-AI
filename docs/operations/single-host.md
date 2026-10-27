# MarketMind AI 单机运行与恢复手册

本手册面向一台受控主机上的 Docker Compose。它不是公网部署方案：默认仅监听 `127.0.0.1:8080`，没有 TLS、外部负载均衡或多机高可用。所有示例中的项目名都应由操作者先确认归自己所有；不要在既有生产项目上演练恢复或执行 `down --volumes`。

## Docker 部署入门：从本项目学会部署新项目

如果以前没有用过 Docker，先记住一条主线：**Dockerfile 规定怎样把代码做成镜像；Compose 规定用哪些镜像创建容器、容器之间怎样连接；数据卷和密钥文件放在镜像外。** Docker Desktop 提供本机 Docker 引擎，不需要在界面里手工“导入项目”。在项目根目录运行 `docker compose`，它会读取这里的 `compose.yaml`。

| 名词 | 本项目中的实例 | 解决的问题 |
| --- | --- | --- |
| 镜像（image） | Python 后端镜像、Nginx 前端镜像、MySQL 官方镜像 | 可重复使用的运行模板；构建时把代码和依赖装进去 |
| 容器（container） | `api`、`web`、`mysql` 等服务的运行实例 | 各自执行一个命令，拥有隔离的进程和文件系统 |
| Compose 项目 | 命令中的 `-p marketmind` | 把同一应用的容器、默认网络和命名卷归为一组；项目名不同，资源也不同 |
| 网络（network） | Compose 自动创建的内部网络 | 容器用服务名 `mysql`、`redis`、`api` 通信，不必查容器 IP |
| 命名卷（volume） | `mysql_data`、`redis_data`、`chroma_data`、`knowledge_data` | 容器重建后保留业务数据；卷不等于备份 |
| Secret | `deploy/secrets/` 中的本地文件，挂载到容器的 `/run/secrets/` | 将密码与镜像、普通环境变量分开；仍需保护宿主机上的源文件 |

### 1. 代码怎样进入镜像

本项目有三个构建入口，均由 [`compose.yaml`](../../compose.yaml) 的 `build` 指定。`context: .` 表示以仓库根目录为构建上下文；[`.dockerignore`](../../.dockerignore) 排除 `.env`、真实密钥、虚拟环境和测试输出等，不让它们随上下文进入构建过程。

| 构建文件 | 构建时做什么 | 运行时做什么 |
| --- | --- | --- |
| [`Dockerfile`](../../Dockerfile) | 从 Python 镜像开始，复制 `pyproject.toml`、后端和 Alembic 文件，`pip install .` 安装依赖，并切换到非 root 用户 | 同一个镜像分别用于 `migration`、`api`、`celery-worker`；各自的 `command` 由 Compose 覆盖 |
| [`frontend/Dockerfile`](../../frontend/Dockerfile) | 第一阶段用 Node 执行 `npm ci` 和 `npm run build`，第二阶段只把编译后的 `dist` 复制进 Nginx 镜像 | Nginx 提供静态页面；[`deploy/nginx.conf`](../../deploy/nginx.conf) 把 `/api/` 转给 `api:8010`，其余前端路由回退到 `index.html` |
| [`deploy/Dockerfile.chroma`](../../deploy/Dockerfile.chroma) | 在固定版本的 Chroma 镜像中加入 `curl` | `curl` 用于 Compose 的 Chroma 健康检查 |

这里没有把本机源代码目录挂载给 API/Web 容器，所以**修改后端或前端代码不会自动进入正在运行的容器**。本地开发可按 README 的开发模式热更新；用 Compose 部署时则重新运行下文带 `--build` 的命令，让镜像和容器更新。MySQL、Redis 的官方镜像由 Compose 拉取，不需要自己写 Dockerfile。

### 2. `compose.yaml` 怎样把应用接起来

读 Compose 文件时按下面的顺序看，比从第一行逐字背更容易理解：

| 配置项 | 本项目中的作用 |
| --- | --- |
| `services` 与 `image`/`build` | 定义七个服务：MySQL、Redis、Chroma、一次性迁移、API、Celery Worker、Web；MySQL/Redis 使用固定版本的官方镜像，Chroma 在固定版本的基础镜像上补装 `curl`，其余服务构建项目代码 |
| `command` | 后端同一镜像可以分别执行 `alembic upgrade head`、Uvicorn API、Celery Worker；镜像不必为每个命令重新写一份 |
| `depends_on` 与 `healthcheck` | MySQL/Redis 健康后才运行迁移；迁移成功后才运行 API/Worker；API 就绪后才启动 Web。Chroma 有自己的健康检查，但目前不是 API 的启动门禁 |
| `environment` 与 `secrets` | 非敏感的运行参数（如 `CHROMA_HOST=chroma`、模型名）用环境变量；数据库 URL、JWT、Redis URL、模型密钥通过 Secret 文件提供 |
| `volumes` | MySQL 数据库、Redis AOF、Chroma 索引、知识原件分别写入命名卷，不随着容器替换而消失 |
| `ports` | 仅 Web 映射 `127.0.0.1:${MARKETMIND_WEB_PORT:-8080}:80`：左边是你电脑的地址和端口，右边是容器内 Nginx 的 80 端口 |

例如，Compose 文件末尾的 `secrets.database_url.file` 使用 `${DATABASE_URL_FILE:-./deploy/secrets/database_url}` 指定宿主机密钥文件的位置；服务中的 `secrets: [database_url]` 才会把它挂到该容器的 `/run/secrets/database_url`。[后端配置类](../../backend/app/core/config.py) 用 Pydantic Settings 的 `secrets_dir` 从那里读取 `database_url`；MySQL 官方镜像则使用自己的 `MYSQL_PASSWORD_FILE` 变量读取密钥。`${变量:-默认值}` 是 Compose 在启动前做的替换，例如不设置 `MARKETMIND_WEB_PORT` 就用 8080；它不是 Python 代码，也不是 Dockerfile 指令。换项目时先弄清**谁消费这个配置**，再选环境变量、Secret 或卷。

浏览器访问 `http://127.0.0.1:8080` 时，实际路径是“浏览器 → Web 容器的 Nginx → `/api/` 请求转给 API 容器 → MySQL/Redis/Chroma”。`localhost` 在**每个容器内部**都只代表它自己；因此 API 连数据库使用 `mysql:3306`，连 Redis 使用 `redis:6379`，不能填写宿主机开发时常用的 `localhost`。Worker 通过 Redis 取得异步任务，API 与 Worker 共享知识文件卷。外部只开放 Web 的回环端口，并不等于公网部署：要给外部用户访问，还需另行设计域名、TLS、网络访问控制和备份。

### 3. 跟着配置完成第一次启动

以下是学习顺序；具体可复制的启动、排障和备份命令分别在本手册第 2～5 节。所有命令都在**仓库根目录的 PowerShell** 执行，不是在容器里执行：

1. 启动 Docker Desktop，运行 `docker version` 和 `docker compose version`，确认客户端能够连接 Docker 引擎。若本机 `docker` 命令不在 `PATH`，按第 2 节使用 Docker 可执行文件的绝对路径。
2. 按第 1 节准备未被 Git 跟踪的 `deploy/secrets/`。十个文件名及连接串格式见 [`deploy/secrets.example/README.md`](../../deploy/secrets.example/README.md)。文件名必须与 Compose `secrets` 一致；数据库和 Redis URL 中的主机名必须是容器服务名。测试夹具中的公开密码不能用于真实项目。
3. 检查 `8080` 是否空闲；若被已有测试栈占用，在当前 PowerShell 会话先设置 `$env:MARKETMIND_WEB_PORT='8081'`。运行 `docker compose -p marketmind config --quiet` 检查配置，再运行第 2 节的 `up -d --build --wait --wait-timeout 300`。首次运行会拉取基础镜像、构建项目镜像并创建网络、卷、容器，可能比以后启动慢。
4. 用 `docker compose -p marketmind ps -a` 看服务状态，用 `docker compose -p marketmind logs --tail 100 migration api celery-worker web` 查启动错误。`migration` 是一次性任务，成功退出是预期行为，不要求它一直显示为 `running`；API/Web 的健康状态比“容器进程已启动”更有意义。
5. 按第 2 节执行 `docker compose -p marketmind exec api python -m app.cli.create_admin`，交互创建第一个管理员，再访问本机 Web `/login` 登录。模型名或 Key 未配置时，普通商品管理等功能仍可用，但 AI 功能不会自动接入供应商。
6. 修改代码或审核升级版本后，先备份，再在**同一个项目名**下运行带 `--build` 的 `up`；这样 Compose 更新需要替换的容器，同时保留命名卷。`docker compose -p marketmind down` 会移除容器和网络，默认保留卷；`down --volumes` 会删卷，**不要把它当作普通停止命令**。

`docker compose` 是声明式的：它读取文件后把当前状态调整到所写配置，不要求你逐个在 Docker Desktop 点“创建容器”。Docker Desktop 可以用来观察容器、日志和卷；真正可复现的部署步骤仍是版本化的 Dockerfile、Compose 文件、密钥准备和上述命令。

### 4. 以后部署自己的新项目，照什么思路配置

1. 先列出运行单元：例如 Web、API、数据库、后台任务。每个长期运行的进程通常对应一个 Compose 服务；数据库迁移这类只需执行一次的操作可用一次性服务。并非每个项目都需要本项目的 Redis、Chroma 或 Worker。
2. 为**自己的代码**写 Dockerfile：选择适合语言的基础镜像，复制依赖声明并安装依赖，再复制代码，写清运行命令；前端若是静态构建，可沿用“Node 构建 → Nginx 提供文件”的多阶段思路。用 `.dockerignore` 排除本地缓存和真实密钥。
3. 用 `compose.yaml` 把服务连接起来：自写代码用 `build`，数据库等成熟组件用固定版本 `image`；服务之间用 Compose 服务名作为主机名，只将确实需要的入口映射到宿主机。准备健康检查与迁移顺序，不能只靠“容器已启动”判断应用可用。
4. 决定什么必须持久化、什么必须保密：数据库和上传文件接命名卷，并制定**独立备份与恢复**方案；密码/API Key 放 Secret 或部署平台的密钥管理，不写进 Dockerfile、公开仓库或镜像。普通配置可放环境变量；不要把测试凭据沿用到正式环境。
5. 在隔离环境验证 `docker compose config`、`up --build --wait`、登录/核心业务、日志、重建后的数据和恢复演练。再决定是否需要公网发布；本手册的回环地址方案只适合受控单机，不自动具备公网安全性或高可用。

迁移到新项目时要**替换服务名、端口、构建路径、数据库连接串、迁移命令、健康检查、卷和密钥清单**，而不是直接复制本项目的七个服务。把这套“构建代码 → 编排服务 → 注入配置 → 持久化数据 → 验证与恢复”的顺序掌握后，技术栈换成别的语言或数据库，部署方法仍相通。

## 1. 准备与安全边界

安装 Docker Desktop/Compose、检查 Docker 引擎可用，并在仓库根目录运行命令。正式环境使用单独的、未被 Git 跟踪的 `deploy/secrets/`，照 [文件说明](../../deploy/secrets.example/README.md) 创建十个文件：MySQL root/应用密码、数据库 URL、JWT 密钥、Redis 密码/URL、Celery broker/result URL、LLM 和 Embedding Key。不要复制 `tests/fixtures/deploy-secrets/`：那里只有公开的合成测试凭据。URL 中的密码需要 URL 编码；文件内容不要出现在命令行参数、日志、仓库或镜像里。

不配置付费模型时，让 `llm_api_key`、`embedding_api_key` 文件为空，不设置 `LLM_MODEL`、`EMBEDDING_MODEL`。此时登录、用户/商品管理、Excel、确定性 Listing 检查可用；语义审核、文档向量索引、RAG、受控研究会明确失败，不会假装生成结果。以后切换 OpenAI-compatible 的 Qwen、DeepSeek 或其他供应商，只在宿主机设置 `LLM_MODEL`/`LLM_BASE_URL`、`EMBEDDING_MODEL`/`EMBEDDING_BASE_URL` 并替换对应 Key 文件；模型输出仍受现有 Pydantic Schema 和证据校验约束。

## 2. 首次启动、升级与检查

在 PowerShell 中先运行 `docker compose config --quiet`；它会校验变量、文件路径和 YAML。本机若 `docker` 不在 `PATH`，可先设 `$mmDocker = 'C:\Users\17905\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'`，把下文每条命令开头的 `docker` 写成 `& $mmDocker`。确认 `127.0.0.1:8080` 未被别的 Compose 项目占用；若需要保留隔离测试栈，可在同一 PowerShell 会话先设 `$env:MARKETMIND_WEB_PORT='8081'`，然后用 `http://127.0.0.1:8081/login`，不要与测试数据复用项目名或密钥。然后运行：

```powershell
docker compose -p marketmind up -d --build --wait --wait-timeout 300
docker compose -p marketmind ps
docker compose -p marketmind logs --tail 100 migration api celery-worker web
```

`migration` 等 MySQL/Redis 健康后执行项目已有的 `alembic upgrade head`；只有迁移退出码为 0，API/Worker 才能启动；Web 再等 API 的 `/api/v1/health/ready` 成功。浏览器打开 `http://127.0.0.1:8080/login`，直接刷新 `/products` 等深层路由仍应由 Nginx 返回 Vue 页面。宿主机只应看到回环 Web 端口；内部 MySQL、Redis、Chroma、API 与 Worker 仅在 Compose 网络内通信。

第一次创建 Admin，交互式执行以下命令；CLI 使用 `getpass` 隐藏密码，调用现有 `create_user` 服务。不要把密码写在命令参数中：

```powershell
docker compose -p marketmind exec api python -m app.cli.create_admin
```

自动化只允许合成、隔离测试项目使用 `--email ... --full-name ... --password-stdin` 成套参数，并从标准输入输送密码；CI 中使用的公开 fixture 密码绝不能用于真实账号。升级时先备份（见下文），再拉取本项目已经审核的代码，在同一个项目名下运行 `docker compose -p marketmind up -d --build --wait --wait-timeout 300`；不要绕过迁移容器直接更新 API 镜像。

## 3. 排障

`docker compose -p marketmind ps -a` 先找失败服务；`docker compose -p marketmind logs --tail 200 <service>` 查看对应容器。迁移失败先检查 MySQL 健康状态、密钥文件和 Alembic 版本，不能强行启动 API。`curl.exe -i http://127.0.0.1:8080/api/v1/health/live` 只测进程；`/health/ready` 同时检查 MySQL/Redis，不证明 Chroma、Worker、真实模型已可用。文档长时间未 `ready` 时分别看 `celery-worker`、`chroma` 日志。业务错误响应中的 `request_id` 与 API 日志中的 `X-Request-ID` 用于关联请求；不要把凭证、上传原文或模型密钥粘贴到公开工单。

迁移容器若以非零码退出，依赖 `service_completed_successfully` 的 API/Worker 即使已被 Compose 创建，也应保持 `Created` 而不启动。修正 Secret **来源文件路径**后，只重跑迁移可能不够：已创建的 API/Worker 容器仍可能挂载旧路径。先用 `docker inspect <容器名>` 的 `Mounts` 核对 `/run/secrets/database_url` 来源，再在确认属于自己的隔离项目中以正确配置执行 `docker compose -p <项目名> up -d --force-recreate --wait api celery-worker`，复查迁移退出码和两项健康状态。正式环境的容器重建应安排维护窗口，不能照搬合成演练命令。

停止 Web/API/Worker 但保留卷：`docker compose -p marketmind stop web api celery-worker`。`docker compose -p marketmind down` 删除容器和网络，但默认保留命名卷；确认停机窗口后再使用。不要在保留业务数据的项目上使用 `down --volumes`。Redis 是缓存、限流与任务队列，不是业务真相；重新启动后以 MySQL 的任务业务状态、知识原件与 Chroma 索引为准排查未完成任务。

## 4. 一致性备份

需要同时保存 MySQL 业务关系、`knowledge_data` 原件卷和 `chroma_data` 向量索引；三者必须来自同一停写窗口。先确认项目名、卷名、备份目录以及可用空间，设置只用于本次操作的变量，例如 `$mmProject = 'marketmind'`、`$mmBackup = 'C:\\MarketMindBackups\\2026-10-08'`。目录应位于受控加密存储且只允许管理员访问；先用 `docker pull registry-1.docker.io/library/alpine:3.22` 备好归档镜像，避免停写后才等待下载。以下命令的目标只限该明确目录。先停入口和所有可能写入的进程：

```powershell
docker compose -p marketmind stop web api celery-worker chroma
docker compose -p marketmind exec -T mysql sh -c 'MYSQL_PWD="$(cat /run/secrets/mysql_root_password)" mysqldump -u root --single-transaction --routines --triggers --default-character-set=utf8mb4 marketmind' > C:\MarketMindBackups\2026-10-08\marketmind.sql
docker run --rm --mount type=volume,source=marketmind_knowledge_data,target=/source,readonly --mount type=bind,source=C:\MarketMindBackups\2026-10-08,target=/backup registry-1.docker.io/library/alpine:3.22 tar -C /source -czf /backup/knowledge.tgz .
docker run --rm --mount type=volume,source=marketmind_chroma_data,target=/source,readonly --mount type=bind,source=C:\MarketMindBackups\2026-10-08,target=/backup registry-1.docker.io/library/alpine:3.22 tar -C /source -czf /backup/chroma.tgz .
```

PowerShell 重定向写 SQL 时须确认运行的是支持 UTF-8 原样处理的 PowerShell 7；随后核对 SQL、两个 tar 都非空，记录 SHA-256（`Get-FileHash`），并用独立恢复演练验证，而不是仅相信文件存在。MySQL dump 期间数据库仍运行，但 API/Worker 已停写。密钥文件须由安全密钥管理单独备份，不能塞进业务 tar。备份完成后 `docker compose -p marketmind up -d --wait --wait-timeout 300` 恢复服务。

## 5. 只向全新隔离项目恢复

恢复演练选择全新的项目名，例如 `marketmind-restore-20261008`。先使用 `docker compose ls` 与 `docker volume ls` 证明该项目和其四个卷不存在；存在就停止，绝不覆盖。用与备份相同的应用代码版本，在仓库外的 `C:\MarketMindRecovery\restore.env` 写入与 `tests/fixtures/deploy.env` 相同的十个 `*_FILE` 变量名，但值全部指向恢复专用密钥文件的绝对路径（不要复用 `deploy/secrets` 或测试密钥）；每条恢复 Compose 命令都显式传 `--env-file`。在该 PowerShell 会话设 `$env:MARKETMIND_WEB_PORT='8081'`，使恢复 Web 只监听独立的 `127.0.0.1:8081`；恢复结束后移除此会话变量。先启动 MySQL/Redis；知识卷可先用 `docker volume create marketmind-restore-20261008_knowledge_data` 建立，不启动 API/Worker 以免空卷被写入。将 SQL 导入新的 MySQL，分别把 tar 解到新的同名业务卷，然后再启动 Chroma、migration、API、Worker、Web。下面展示核心恢复动作；执行前再次核对每个 `source`、备份文件、目标卷的完整名称：

```powershell
docker compose --env-file C:\MarketMindRecovery\restore.env -p marketmind-restore-20261008 up -d mysql redis
Get-Content -Raw -Encoding utf8 C:\MarketMindBackups\2026-10-08\marketmind.sql | docker compose --env-file C:\MarketMindRecovery\restore.env -p marketmind-restore-20261008 exec -T mysql sh -c 'MYSQL_PWD="$(cat /run/secrets/mysql_root_password)" mysql -u root --default-character-set=utf8mb4 marketmind'
docker volume create marketmind-restore-20261008_knowledge_data
docker volume create marketmind-restore-20261008_chroma_data
docker run --rm --mount type=volume,source=marketmind-restore-20261008_knowledge_data,target=/target --mount type=bind,source=C:\MarketMindBackups\2026-10-08,target=/backup,readonly registry-1.docker.io/library/alpine:3.22 tar -C /target -xzf /backup/knowledge.tgz
docker run --rm --mount type=volume,source=marketmind-restore-20261008_chroma_data,target=/target --mount type=bind,source=C:\MarketMindBackups\2026-10-08,target=/backup,readonly registry-1.docker.io/library/alpine:3.22 tar -C /target -xzf /backup/chroma.tgz
docker compose --env-file C:\MarketMindRecovery\restore.env -p marketmind-restore-20261008 up -d --build --wait --wait-timeout 300
```

恢复后在隔离入口检查：原商品/用户 ID、知识库文档元数据与原件、Chroma 检索返回的引用坐标一致，已批准研究报告仍能读取和导出。具体做法是在源项目和恢复项目运行相同的只读查询：用 MySQL `SELECT` 比对商品 ID、SKU、文档状态及路径、研究报告和证据哈希、审核决定；用 `sha256sum` 比对知识原件；用 Chroma `get(include=['documents','metadatas'])` 比对向量 ID、文本与来源元数据。三组结果都一致后，再检查恢复入口 `/api/v1/health/ready`。若检查失败，保留隔离项目和日志排查；不要在生产项目中“重试导入”。只有本次演练的项目确认为全新且不再需要时，才可经人工复核执行 `docker compose --env-file C:\MarketMindRecovery\restore.env -p marketmind-restore-20261008 down --volumes`。真实生产备份恢复应在授权维护窗口单独演练，合成数据演练不代表生产恢复已通过。

## 6. 当前验收边界

2026-10-08 的本机合成栈验收：`mm_phase9_local` 完成镜像构建，迁移退出码 0，MySQL/Redis/Chroma/API/Worker/Web 与模型桩健康；仅 Web 发布 `127.0.0.1:8080`，`/`、深层 `/products` 和同源 `/api/v1/health/ready` 均返回 200。Chromium 三条真实页面旅程全部通过：Admin 商品与 Excel 往返、Analyst 权限限制，以及知识上传/索引/问答、语义审核、证据研究、一次性批准与导出。全部容器强制重建后再次达到健康状态。2026-10-12 重启 Docker 引擎后只读核对：MySQL 有 9 个商品、2 份 `ready` 文档、2 个成功研究；知识卷有 3 个文件；Chroma 有 2 个集合且各含 1 条向量，数量与重建前记录一致。同日重跑浏览器验收时，模型桩因旧配置无重启策略而保持退出，知识索引失败；给 `compose.e2e.yaml` 的模型桩添加 `restart: unless-stopped`、只重建该测试服务后，三条 Chromium 旅程重新通过。2026-10-13 对同一合成项目停写备份 SQL、知识原件卷和 Chroma 卷，在新建的 `mm_restore_20261013` 项目恢复：源与目标的 22 行关键业务记录、5 个原件 SHA-256、Chroma 集合的向量 ID/文本/元数据逐项一致；双方均有 7 个用户、14 个商品、5 份文档、3 个成功研究及 3 条批准记录，恢复入口返回 200。演练项目及其四个卷已清理，源合成项目仍可用；备份留在本地忽略目录 `deploy/backups/2026-10-13-restore-drill/`，未提交。远端 GitHub Actions 状态未核实；公网 TLS、真实付费模型调用和生产数据恢复不属于本次合成验收。

2026-10-14 在此前不存在的 `mm_migration_fail_20261014` 合成项目注入不可解析的数据库主机：MySQL/Redis 健康，迁移因连接失败退出码为 1，API/Worker 容器保持 `Created`，未接受请求。改回正确测试 Secret 后迁移退出码为 0；检查发现 API/Worker 仍挂载创建时的错误 Secret 路径，导致 API 一度返回 503。只在该隔离项目强制重建两项服务后，它们均健康且挂载来源正确。Compose 契约检查及相关 23 个单元测试通过；演练项目、三个卷、镜像标签和错误夹具均已清理。此结论验证了合成环境的迁移启动门禁与修复流程，不等于生产故障恢复演练。

2026-10-15 的响应式与键盘验收：在运行中的 `mm_phase9_local` 合成栈，用 Chromium 对登录、工作台、商品、知识库、用户五个主页面按 375/768/1440px 截图，并补查 320px 边界；这些页面的文档宽度均未超过视口。发现原横向导航在 320/375px 裁掉后面的入口文本，先用浏览器测试复现失败，再把小屏导航改为两列；复测四个入口均完整可见。键盘依次可进入导航、商品筛选和表格操作，确认弹窗可聚焦、Shift+Tab 循环、Esc 关闭并还原原按钮焦点。前端 44 个单元测试、生产构建及四条 Chromium 端到端旅程通过；只重建合成项目的 Web 容器，未清理数据卷。窄屏表格保留局部横向滚动；本次并非完整无障碍标准审计，远端 GitHub Actions 状态仍未核实。

2026-10-16 继续检查窄屏表格：商品、用户、知识文档、语义审核、研究历史及导入错误共六处滚动区添加可聚焦的命名区域，并在窄屏显示横向滚动与方向键提示。Chromium 合成数据测试先因缺少区域名称失败；修复后验证 320/375px 商品表格不撑宽页面、键盘 Tab 可进入滚动区并用右方向键滚动，768px 成员表格也可用方向键滚动，1440px 不显示窄屏提示。前端 44 个单元测试、生产构建、六条 Chromium 端到端旅程均通过，同源 `/api/v1/health/ready` 返回 200。Docker Desktop 重启后只在 `mm_phase9_local` 合成项目重建 Web 及 Compose 所需依赖，保留数据卷；未做完整无障碍标准审计，远端 GitHub Actions 状态仍未核实。

2026-10-26 对商品停用等共用确认弹窗完成异步忙碌状态验收：先以单元测试复现请求未结束时按 Esc、点取消或遮罩仍会关闭弹窗的问题，再统一阻止这些取消入口；确认按钮禁用时将焦点移到仍可聚焦但带 `aria-disabled` 的取消按钮，并保持 Tab 焦点在弹窗内。新增长时间挂起 DELETE 请求的浏览器测试，验证上述操作不会造成“界面已取消、请求仍执行”的误导，放行请求后弹窗关闭并显示商品已停用。前端 45 个单元测试、生产构建、后端 406 个正式单元测试、Ruff、Mypy 和七条 Chromium 端到端旅程通过；合成项目 `mm_phase9_local` 迁移退出码 0，七项服务健康，同源 `/api/v1/health/ready` 返回 200。仅重建并启动合成项目所需服务，保留数据卷。个人练习测试未纳入正式单测结果；本次不是完整无障碍审计，远端 GitHub Actions 状态仍未核实。

2026-10-27 对前端登录态的异步竞态进行验收：先用两条定向测试复现旧请求在新登录后返回 401 时清除新凭证，以及旧 `/auth/me` 成功响应覆盖新用户的问题；两条测试在修复前均按预期失败。API 现在只在响应对应的凭证仍是当前凭证时清理会话，恢复用户信息前也再次核对凭证。修复后前端 47 个单元测试、生产构建、后端 406 个正式单元测试、Ruff 与 Mypy、七条 Chromium 端到端旅程通过。Docker Desktop 重启后只重建合成项目 Web 镜像并启动原有 `mm_phase9_local`，迁移退出码 0，七项服务健康，同源 `/api/v1/health/ready` 返回 200，数据卷保留。竞态由定向单元测试验证；本次未新增直接模拟重新登录竞态的浏览器测试，远端 GitHub Actions 状态仍未核实。
