# 本地密钥文件（示例）

在仓库根目录创建被 Git 忽略的 `deploy/secrets/`，其中必须有以下十个 UTF-8 文件，文件名与 Compose secret 名一致：

`mysql_root_password`、`mysql_app_password`、`database_url`、`jwt_secret`、`redis_password`、`redis_url`、`celery_broker_url`、`celery_result_backend`、`llm_api_key`、`embedding_api_key`。

`database_url` 使用 `mysql+asyncmy://marketmind:<应用密码>@mysql:3306/marketmind`；`redis_url` 使用 `redis://:<Redis 密码>@redis:6379/0`；Celery broker/result 分别使用 `/1`、`/2`。URL 中的密码须正确编码，不能包含未编码的 `@`、`:` 或 `/`。`jwt_secret` 应由密码学安全的随机生成器生成，并避免换行。

尚未配置真实模型时，把 `llm_api_key` 和 `embedding_api_key` 文件留空，并不设置 `LLM_MODEL`/`EMBEDDING_MODEL`。这时商品等非 AI 功能可用，AI 功能会明确报配置缺失，不会自动调用供应商。要启用 Qwen、DeepSeek 或其他 OpenAI-compatible 模型时，分别设置模型名和 Base URL，并填入对应密钥文件；切换位置见 `README.md` 的模型配置部分。

`tests/fixtures/deploy-secrets/` 仅包含显著标注的无效测试凭据，只能用于隔离的测试 Compose 项目。不要把真实凭据写入 fixture、`deploy.env`、GitHub Actions 或镜像。
