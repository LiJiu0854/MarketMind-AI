# MarketMind AI

MarketMind AI 是面向电商运营团队的 AI 商品运营与竞品研究平台。

当前已完成阶段 6 后端主链路：用户认证与 RBAC、共享商品 CRUD、`.xlsx`
同步导入、确定性 Listing 检查和筛选导出，以及异步 LLM Listing 语义审核与
MySQL 历史持久化；另有 PDF/MD/TXT 知识库、异步向量索引、带来源引用的 RAG 问答，
以及基于已上传资料的受控竞品研究。

## 环境要求

- Python 3.12
- MySQL 8（开发库和只用于测试的 `marketmind_test`）
- Redis（健康检查、限流、缓存和 Celery 相关测试需要）
- Docker Desktop 或可访问的 Chroma HTTP 服务（知识库索引与问答需要）
- 开发端口：`8010`
- 项目根目录下的独立虚拟环境：`.venv`

## 本地开发

在 Windows PowerShell 中执行：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
```

运行完整质量检查：

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests scripts
```

功能变更遵循红—绿—重构循环：先观察聚焦测试因缺少目标行为而失败，再添加最小实现，最后运行完整质量检查。

## 商品接口

所有接口位于 `/api/v1/products` 并要求有效 JWT：

- `POST /products`：Admin、Operator 创建商品；
- `GET /products`：分页并按 SKU、品牌、分类、启用状态筛选；
- `POST /products/import`：Admin、Operator 同步导入最大 5 MiB、5000 行的 `.xlsx`；
- `GET /products/export`：三种角色按相同筛选语义下载 `.xlsx`；
- `GET /products/{product_id}/listing-check`：三种角色执行确定性 Listing 检查；
- `GET/PATCH/DELETE /products/{product_id}`：读取、部分更新和软停用。
- `POST /products/{product_id}/semantic-reviews`：Admin、Operator 发起异步语义审核；
- `GET /products/{product_id}/semantic-reviews`：三种角色分页查看 MySQL 审核历史；
- `GET /products/{product_id}/semantic-reviews/{review_id}`：三种角色查看结构化结果。
- `POST /products/{product_id}/research-runs`：Admin、Operator 发起受控研究，返回 `202` 与 `run_id/task_id/status`；
- `GET /products/{product_id}/research-runs`：三种角色分页查看 MySQL 研究历史；
- `GET /products/{product_id}/research-runs/{run_id}`：三种角色读取状态、步骤、证据、报告与 Token 用量。

导入和导出只使用请求内存，不保存工作簿文件。导入允许合法行成功、错误行返回稳定错误；并发 SKU 冲突会整体回滚。

语义审核创建接口返回 `202`、`review_id` 和 Celery `task_id`。客户端随后轮询历史或
详情接口；业务状态以 MySQL 中的 `pending/running/success/failure` 为准，不读取会过期的
Celery Result Backend。同一商品只允许一条 pending/running 审核，终态后可再次发起并保留历史。

## 数据库迁移与 Worker

API 和 Celery Worker 启动前，确保 MySQL 与 Redis 可用，并应用开发库迁移：

```powershell
.venv\Scripts\alembic.exe -x database=development upgrade head
```

Windows 本地启动 Celery Worker：

```powershell
.venv\Scripts\celery.exe -A app.celery_app.celery_app worker --loglevel=INFO --pool=solo
```

Worker 使用 Redis 锁避免同一审核、文档或研究并行执行，模型结果、错误摘要和 Token 用量最终写入
MySQL。自动化测试会 Mock 模型 SDK，不产生真实模型费用。

## 受控竞品研究（单元 6）

先由 Admin 上传竞品公开资料或内部市场资料至单元 5 知识库，并等待至少一份文档成为
`ready`。Admin/Operator 再为一个商品选择 1～3 个知识库，提交 1～500 字符研究目标；
同一商品不能同时运行两项研究。提交前必须完成 `0005` 迁移，并启动 MySQL、Redis、
Celery Worker 和 Chroma；知识库 Embedding 配置须与当前运行配置一致。

Worker 只允许模型选择 `read_product`、`search_knowledge`、`finish` 三个动作；
最多默认 4 次决定，并最多登记 12 条证据。每步写入 MySQL 检查点。检索来源会核对
知识库范围、MySQL 文档归属与 `ready` 状态；报告每项发现/建议的来源 ID 必须来自本次
登记的知识库证据，文件名、页码和摘录由程序回填。没有可靠知识库证据时直接生成
`insufficient_evidence`，不会调用报告模型。客户端轮询研究详情即可读取
`pending/running/success/failure`，不依赖 Celery 结果缓存。

`RESEARCH_MAX_ACTIONS`（2～8）和 `RESEARCH_MAX_EVIDENCE`（2～30）控制动作与证据预算；
一次动作可能调用 Chat，知识库检索还可能调用 Embedding，证据充分时报告另调用一次
Chat，因此应按模型计费规则评估上限。切换模型仍配置 `LLM_*` 和 `EMBEDDING_*`，
保持 OpenAI-compatible API 与 JSON Mode 支持；研究不会实时联网抓取竞品，
结论只反映管理员已上传且通过核验的资料，不能当作未经复核的市场事实。
自动化测试中的模型与 Chroma 均为模拟；尚未进行产生真实费用的人工验收。

## RAG 知识库（单元 5）

知识库接口基址为 `/api/v1/knowledge-bases`，均需 JWT：

- `POST /`：仅 Admin 创建知识库；`GET /`、`GET /{id}`：所有角色查看；
- `POST /{id}/documents`：仅 Admin 上传并投递异步索引，返回 `202` 与任务 ID；
- `GET /{id}/documents`、`GET /{id}/documents/{document_id}`：所有角色查看索引状态；
- `POST /{id}/questions`：所有角色提问；`GET /{id}/questions` 与 `GET /{id}/questions/{query_id}`：查看 MySQL 问答历史。

上传只接受最大 10 MiB（可配置）的 UTF-8 `.txt`/`.md` 或可提取文字的 `.pdf`。加密 PDF、扫描图片型 PDF 不会自动 OCR，需先转成可提取文字。Worker 负责解析、分块、Embedding 与 Chroma 索引；`ready` 后才可成为问答证据。没有足够近、且与 MySQL `ready` 文档对应的证据时，直接拒答，不调用 Chat。回答中的文件名、页码和片段来自程序校验后的检索结果，而非模型自报。

MySQL 是知识库、文件状态与问答历史的业务真相；`KNOWLEDGE_FILE_ROOT` 保存原件；Chroma 保存可从原件重建的向量索引。三处数据要分别备份，不能只备份 MySQL。开发机可按 [Chroma 官方 Docker 文档](https://docs.trychroma.com/deployment/docker) 使用具名卷持久化（首次执行前确保 Docker 已启动）：

```powershell
docker volume create marketmind-chroma-data
docker run --name marketmind-chroma -p 127.0.0.1:8000:8000 -v marketmind-chroma-data:/data chromadb/chroma
```

后续停机/重启使用 `docker stop marketmind-chroma` / `docker start marketmind-chroma`。不要执行 Chroma reset。先执行上面的 Alembic `upgrade head`，再启动 API 与 Worker；`.env` 的 `CHROMA_HOST/PORT/SSL/TENANT/DATABASE` 必须与服务相符。部署到其他机器时要考虑 Chroma 身份认证、TLS 和网络隔离，不能把本地无认证示例直接暴露到公网。

Embedding 与 Chat 分别在 `.env` 的 `EMBEDDING_*` 和 `LLM_*` 设置兼容地址、模型 ID、密钥；`backend/app/core/config.py` 统一解析，`backend/app/services/document_ingestion.py` 用 Embedding，`backend/app/services/rag.py` 用 Chat。可选 OpenAI、Qwen、DeepSeek 等支持对应 API 的模型，但需按所选服务商官方文档核对 Embedding 和 JSON Mode。知识库创建时固定 Embedding 提供商、地址、模型与首次索引的向量维度；修改任一项后，应新建知识库并重新上传索引，不能直接复用旧向量。

质量评估用 JSONL，每行一个用例，例如：

```json
{"question":"如何退货？","relevant_document_ids":[3],"should_refuse":false}
```

只有确认允许真实 Embedding/Chat 请求及费用后，才执行：

```powershell
.venv\Scripts\python.exe scripts/evaluate_rag.py --knowledge-base-id 1 --cases cases.jsonl --output rag-report.json --live
```

缺少 `--live` 会在读取模型配置和创建外部客户端之前退出。报告包含 Hit@K、MRR、引用有效率、拒答正确率、失败数与平均耗时；问句写入指定 JSON 文件，不在终端输出。评估不写 MySQL 问答历史，避免把测试问题混入业务记录。自动化测试全部使用模拟客户端，不会产生付费调用；本项目尚未执行真实模型或 Chroma 联调。

## 启动 API

应用通过工厂函数创建。在 Windows PowerShell 中启动开发服务：

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8010
```

启动后可以访问：

- 存活检查：`http://127.0.0.1:8010/api/v1/health/live`
- 就绪检查：`http://127.0.0.1:8010/api/v1/health/ready`
- 接口文档：`http://127.0.0.1:8010/docs`
- OpenAPI：`http://127.0.0.1:8010/openapi.json`

## 环境变量

`.env.example` 只记录安全的配置示例。需要本地配置时，将它复制为 `.env` 并填写真实值；`.env` 已被 Git 忽略，不得提交任何 API Key。

### 切换 OpenAI-compatible 模型

业务代码只读取以下配置，不根据供应商名称分支：

```dotenv
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=<支持 Chat Completions 和 JSON Mode 的模型 ID>
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=60
LLM_MAX_OUTPUT_TOKENS=2000
```

切换服务商时只改 `LLM_PROVIDER/LLM_BASE_URL/LLM_MODEL/LLM_API_KEY`，然后重启 API 与
Worker。常见公开兼容入口示例：

- OpenAI：`https://api.openai.com/v1`
- SiliconFlow：`https://api.siliconflow.cn/v1`
- 阿里云百炼（Qwen）：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- DeepSeek：`https://api.deepseek.com`

不要把上述示例理解为模型可用性保证：模型 ID、价格和 JSON Mode 支持会变化，部署前应以
服务商当时的官方文档为准。代码不读取、不返回也不保存模型思维链或未经验证的原始响应。

## 阶段文档

- 实施计划：`docs/plans/phase-0-foundation.md`
- 学习基线：`docs/learning/phase-0-baseline.md`
