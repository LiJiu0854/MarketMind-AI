# MarketMind AI

MarketMind AI 是面向电商运营团队的 AI 商品运营与竞品研究平台。

当前项目处于阶段 0，只建立 Python 与 FastAPI 工程基础，不连接 MySQL、Redis、LLM、前端或 Docker。

## 环境要求

- Python 3.12
- 开发端口：`8010`
- 项目根目录下的独立虚拟环境：`.venv`

## 本地开发

在 Windows PowerShell 中执行：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
```

运行阶段 0 质量检查：

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
```

阶段 0 的功能变更均遵循红—绿—重构循环：先观察聚焦测试因缺少目标行为而失败，再添加最小实现，最后运行完整质量检查。

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

## 阶段文档

- 实施计划：`docs/plans/phase-0-foundation.md`
- 学习基线：`docs/learning/phase-0-baseline.md`
