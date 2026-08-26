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

任务 2 只建立测试工程入口，尚未创建测试用例，因此此时直接运行 pytest 会显示 `collected 0 items` 并返回退出码 5。任务 3 将先创建 Settings 的失败测试，再开始正式的红—绿 TDD 循环。

阶段 0 后续加入 FastAPI 应用工厂后，开发服务将使用 8010 端口启动。

## 环境变量

`.env.example` 只记录安全的配置示例。需要本地配置时，将它复制为 `.env` 并填写真实值；`.env` 已被 Git 忽略，不得提交任何 API Key。

## 阶段文档

- 实施计划：`docs/plans/phase-0-foundation.md`
- 学习基线：`docs/learning/phase-0-baseline.md`
