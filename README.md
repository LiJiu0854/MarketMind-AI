# MarketMind AI

MarketMind AI 是面向电商运营团队的 AI 商品运营与竞品研究平台。

当前已完成阶段 3 后端主链路：用户认证与 RBAC、共享商品 CRUD、`.xlsx`
同步导入、确定性 Listing 检查和筛选导出。

## 环境要求

- Python 3.12
- MySQL 8（开发库和只用于测试的 `marketmind_test`）
- Redis（健康检查、限流、缓存和 Celery 相关测试需要）
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
.venv\Scripts\mypy.exe backend tests
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

导入和导出只使用请求内存，不保存工作簿文件。导入允许合法行成功、错误行返回稳定错误；并发 SKU 冲突会整体回滚。

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
