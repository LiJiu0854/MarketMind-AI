# 阶段 3：商品数据与 Excel 设计

## 1. 阶段目标

阶段 3 建立 MarketMind AI 的商品数据主链路：具有权限的用户可以维护共享商品库、上传 `.xlsx` 文件批量导入商品、获得逐行错误报告、执行可解释的 Listing 确定性检查，并把筛选后的商品重新导出为 `.xlsx`。

本阶段固定拆分为 4 个 Task，每个 Task 5 个学习单元。所有功能继续使用既有 FastAPI、Pydantic、SQLAlchemy、Alembic、MySQL、JWT、RBAC、统一异常和测试基础设施。

## 2. 范围边界

### 2.1 本阶段实现

- Product ORM Model、Alembic 迁移和数据库约束；
- 商品创建、读取、分页、筛选、部分更新和软停用；
- Admin、Operator、Analyst 的商品权限；
- 最大 5 MB、最大 5000 行的 `.xlsx` 同步上传；
- Pandas Excel 读取、字段清洗、逐行校验和去重；
- 合格行批量写入、错误行 JSON 报告；
- Listing 确定性规则；
- 按筛选条件导出 `.xlsx`；
- 单元测试、数据库集成测试、API 测试和人工验收。

### 2.2 本阶段不实现

- `.xls`、CSV 或其他文件格式；
- Celery 异步 Excel 导入；
- 上传文件长期保存或对象存储；
- 商品 Redis 缓存；
- Listing 检查结果持久化；
- LLM 语义审核、RAG、Agent、SSE、MCP、Playwright 或前端；
- 平台、商品 URL、图片、库存等尚无业务消费者的字段。

## 3. 依赖决策

新增直接依赖：

- `pandas`：读取、清洗和生成表格数据；
- `openpyxl`：作为 Pandas 的 `.xlsx` 读写引擎。

不为 NumPy 增加直接业务调用。Pandas 内部可以依赖 NumPy，但项目代码只在出现独立数值计算需求时再直接使用它。

## 4. 商品数据模型

正式表名为 `products`，字段如下：

| 字段 | 数据库类型 | 规则 |
|---|---|---|
| `id` | 整数 | 自增主键 |
| `sku` | `VARCHAR(50)` | 必填、唯一、索引，应用层统一转大写 |
| `title` | `VARCHAR(200)` | 必填 |
| `description` | `TEXT` | 非空，默认空字符串 |
| `bullet_points` | `JSON` | 非空，保存字符串列表，默认空列表 |
| `brand` | `VARCHAR(100)` | 非空，默认空字符串 |
| `category` | `VARCHAR(100)` | 非空，默认空字符串 |
| `price` | `NUMERIC(12, 2)` | 必填且大于 0，不使用二进制浮点数 |
| `currency` | `VARCHAR(3)` | 三位大写字母 |
| `is_active` | 布尔值 | 默认启用，删除操作只做软停用 |
| `created_by_id` | 整数外键 | 指向 `users.id`，只用于审计，不限制可见范围 |
| `created_at` | 时间 | 数据库生成 |
| `updated_at` | 时间 | 数据库生成并在更新时刷新 |

`created_by_id` 不配置 ORM Relationship。当前功能只需要保存创建人 ID，引入双向关系不会减少查询或代码复杂度。

数据库唯一约束是 SKU 并发一致性的最终防线；应用层预查询用于生成友好的逐行错误，但不能替代数据库约束。

## 5. 商品权限

商品库属于内部团队共享资源：

| 操作 | Admin | Operator | Analyst |
|---|---:|---:|---:|
| 查看、分页、筛选 | 允许 | 允许 | 允许 |
| Listing 检查 | 允许 | 允许 | 允许 |
| Excel 导出 | 允许 | 允许 | 允许 |
| 创建、更新、软停用 | 允许 | 允许 | 禁止 |
| Excel 导入 | 允许 | 允许 | 禁止 |

所有商品接口都要求有效 JWT。写操作复用 `require_roles(Role.ADMIN, Role.OPERATOR)`；只读操作只依赖 `get_current_user`。

## 6. 商品 API

接口如下：

```text
POST   /api/v1/products
GET    /api/v1/products
GET    /api/v1/products/export
POST   /api/v1/products/import
GET    /api/v1/products/{product_id}
PATCH  /api/v1/products/{product_id}
DELETE /api/v1/products/{product_id}
GET    /api/v1/products/{product_id}/listing-check
```

静态路径 `/export` 和 `/import` 必须先于 `/{product_id}` 注册，避免被动态路径当作整数 ID 解析。

列表和导出共用以下筛选语义：

- `sku`：规范化后精确匹配；
- `brand`：精确匹配；
- `category`：精确匹配；
- `is_active`：布尔过滤；
- 列表使用 `page` 和 `page_size`，按 `id` 升序稳定分页；
- 导出使用相同筛选条件，但不分页。

不增加通用动态过滤框架。字段数量固定，显式 SQL 条件更容易阅读、测试和维护。

## 7. Excel 文件契约

只读取工作簿的第一个工作表，表头固定为：

```text
sku
title
description
bullet_points
brand
category
price
currency
is_active
```

`created_by_id`、数据库 ID 和时间字段不得由 Excel 提供。表头缺失或出现未知字段时，整份文件返回 422，避免拼写错误被静默忽略。

文件边界：

- 扩展名必须为 `.xlsx`，比较时不区分大小写；
- 最大 5 MB，读取时最多接收 `5 MB + 1 byte`，超出立即拒绝；
- 数据行最多 5000 行；
- 空工作簿、损坏工作簿、重复表头和无法解析的内容属于文件级错误；
- 原始文件只在当前请求内以字节流存在，不写入磁盘。

## 8. 清洗与逐行校验

清洗规则：

- SKU：转字符串、去首尾空格、转大写；
- 标题、描述、品牌、分类：空值转空字符串并去首尾空格；
- 卖点：空值转空列表，否则按单元格内换行拆分，去除空行和首尾空格；
- 价格：通过字符串转换为 `Decimal`，保留最多两位小数；
- 货币：转字符串、去空格、转大写；
- 是否启用：接受布尔值以及 `true/false`、`yes/no`、`1/0`，比较时不区分大小写。

逐行校验至少覆盖：

- SKU 必填且不超过 50 个字符；
- 标题必填且不超过 200 个字符；
- 品牌和分类分别不超过 100 个字符；
- 价格能够转换为 Decimal、大于 0、整数部分和小数位不超出数据库精度；
- 货币符合 `^[A-Z]{3}$`；
- 是否启用属于允许值；
- 文件内 SKU 不重复；
- SKU 在数据库中尚不存在。

每个 Excel 数据行最多产生一个汇总错误对象，以免一个错误行返回大量重复信息。错误包含 Excel 实际行号、字段、稳定错误码和中文说明。

## 9. 导入算法与事务

同步导入顺序：

```text
校验文件边界
  → Pandas 读取第一个工作表
  → 校验表头和行数
  → 按 Excel 行号逐行清洗、校验
  → 标记文件内重复 SKU
  → 一次查询数据库已有 SKU
  → 形成错误列表和合格 Product 列表
  → 一次事务提交全部合格商品
  → 返回统计与逐行错误
```

返回模型：

```json
{
  "total_rows": 5,
  "imported_rows": 3,
  "failed_rows": 2,
  "errors": [
    {
      "row": 3,
      "field": "price",
      "code": "INVALID_PRICE",
      "message": "价格必须大于 0"
    }
  ]
}
```

行为约束：

- 文件级错误返回 422，数据库零写入；
- 行级错误返回 200，所有合格行在一次事务中写入；
- 数据库预查询后若仍发生 SKU 并发唯一冲突，本次合格行整体回滚并返回 409；
- 不使用 `INSERT IGNORE`，避免数据库静默吞掉长度、类型等其他错误；
- 其他数据库异常复用统一 503 处理；
- `total_rows = imported_rows + failed_rows` 必须成立。

## 10. Listing 确定性规则

Listing 检查为纯函数，对 Product 或等价输入返回问题列表，不访问网络、不写数据库。

规则如下：

| 错误码 | 条件 |
|---|---|
| `TITLE_TOO_SHORT` | 标题少于 10 个字符 |
| `DESCRIPTION_MISSING` | 描述为空 |
| `DESCRIPTION_TOO_SHORT` | 非空描述少于 50 个字符 |
| `DESCRIPTION_TOO_LONG` | 描述超过 5000 个字符 |
| `BULLET_COUNT_INVALID` | 卖点数量不在 3 到 5 条之间 |
| `BULLET_TOO_SHORT` | 任一卖点少于 10 个字符 |
| `BULLET_TOO_LONG` | 任一卖点超过 200 个字符 |
| `PRICE_INVALID` | 价格不大于 0 |
| `CURRENCY_INVALID` | 货币不是三位大写字母 |
| `FORBIDDEN_TERM` | 文本包含明确禁用词 |

禁用词固定为一个小型常量集合：`最便宜`、`绝对有效`、`永久有效`、`100%保证`。比较时不区分英文大小写，并检查标题、描述和卖点。

每个问题包含：

- `code`：稳定规则编号；
- `field`：问题字段；
- `message`：发生了什么；
- `suggestion`：怎样修改。

响应包含 `product_id`、`passed` 和 `issues`。`passed` 由 `issues` 是否为空计算，不单独存储。阶段 4 的 LLM 语义审核将作为另一种检查结果加入，不替换本确定性规则。

## 11. Excel 导出

导出复用商品列表的筛选构造逻辑，避免 API 列表和导出出现筛选语义差异。查询结果转换为 DataFrame 后，使用 `BytesIO` 和 `openpyxl` 生成 `.xlsx`。

响应要求：

- Content-Type 为标准 `.xlsx` MIME；
- Content-Disposition 提供稳定文件名；
- 列顺序与导入模板一致；
- `bullet_points` 重新以单元格内换行连接；
- `Decimal` 以十进制值写入，不先转换成二进制浮点数；
- 空结果仍生成只有表头的合法工作簿；
- 不在服务器文件系统保存导出文件。

## 12. 错误码

新增稳定业务错误码：

- `PRODUCT_NOT_FOUND`：商品不存在，404；
- `PRODUCT_SKU_CONFLICT`：创建或更新时 SKU 冲突，409；
- `EXCEL_INVALID_TYPE`：不是 `.xlsx`，422；
- `EXCEL_TOO_LARGE`：超过 5 MB，422；
- `EXCEL_INVALID_WORKBOOK`：工作簿损坏或无法解析，422；
- `EXCEL_INVALID_HEADERS`：表头缺失、重复或未知，422；
- `EXCEL_TOO_MANY_ROWS`：超过 5000 行，422；
- `PRODUCT_IMPORT_CONFLICT`：并发唯一冲突导致写入回滚，409。

逐行错误码不抛 HTTP 异常，而是放入导入结果，例如：

- `REQUIRED_FIELD`；
- `FIELD_TOO_LONG`；
- `INVALID_PRICE`；
- `INVALID_CURRENCY`；
- `INVALID_BOOLEAN`；
- `DUPLICATE_SKU_IN_FILE`；
- `DUPLICATE_SKU_IN_DATABASE`。

## 13. 文件职责

计划使用以下最小文件边界：

```text
backend/app/models/product.py          Product ORM 定义
backend/app/schemas/product.py         CRUD、导入和 Listing 响应结构
backend/app/services/products.py       CRUD、筛选和数据库导入事务
backend/app/services/product_excel.py  Excel 读取、清洗、校验和导出
backend/app/services/listing_rules.py  纯确定性 Listing 规则
backend/app/api/v1/products.py         HTTP、权限、上传和下载响应
alembic/versions/0002_create_products_table.py
```

不为单一实现创建 Repository、抽象接口、策略类或通用导入框架。

## 14. 测试策略

### 14.1 单元测试

- Product 表名、字段、唯一约束和外键；
- Product Schema 的 Decimal、货币、长度和部分更新；
- 文件类型、大小、表头和行数；
- 各字段清洗和错误行号；
- 文件内重复检测；
- Listing 每条规则；
- 空列表和筛选数据的 Excel 导出。

### 14.2 数据库集成测试

- 创建、读取、分页、筛选、更新和软停用；
- SKU 大小写规范化与唯一冲突；
- 创建人 ID；
- 数据库已有 SKU 的导入跳过；
- 合格行一次提交；
- 并发唯一冲突时整体回滚。

所有数据库测试继续只允许连接 `marketmind_test`。

### 14.3 API 测试

- Admin 和 Operator 可以写入、导入；
- Analyst 写操作返回 403；
- 三种角色都可以读取、检查和导出；
- 未认证返回 401；
- 文件级错误返回 422 且零写入；
- 部分成功结果计数和错误行正确；
- 下载响应能被 openpyxl 重新打开；
- 统一错误响应继续包含 request_id。

### 14.4 人工验收

- 使用真实 `.xlsx` 导入混合正确行和错误行；
- 根据返回行号修改 Excel 后重新导入；
- 分页和筛选查询商品；
- 修改商品后重新执行 Listing 检查；
- 导出筛选结果并用 Excel 打开；
- 验证 Analyst 不能写入；
- 全量 pytest、Ruff、mypy 和 `git diff --check` 通过。

## 15. Task 与学习单元

### Task 1：商品领域模型与 CRUD（5 个单元）

1. Product Model 与创建人外键；
2. Alembic 商品表迁移；
3. Product 创建、更新、读取 Schema；
4. 商品 CRUD、分页、筛选和软停用 Service；
5. API、RBAC 和数据库集成验收。

### Task 2：Excel 读取、清洗与校验（5 个单元）

1. 文件扩展名和 5 MB 上传边界；
2. Pandas 读取、表头和 5000 行限制；
3. SKU、文本、卖点、货币和布尔值清洗；
4. 单行类型与业务字段校验；
5. 纯内存 Excel 测试和错误定位验收。

### Task 3：批量导入、去重与错误报告（5 个单元）

1. 文件内重复 SKU 检测；
2. 数据库已有 SKU 批量查询；
3. 合格商品批量写入与事务回滚；
4. 导入 API 和逐行 JSON 错误报告；
5. 部分成功、并发冲突和数据库异常验收。

### Task 4：Listing 规则、Excel 导出与阶段验收（5 个单元）

1. ListingIssue Schema 与纯规则函数；
2. Listing 检查 API；
3. 按筛选条件查询导出数据；
4. `BytesIO + StreamingResponse` 生成 `.xlsx`；
5. 全量测试、人工运行、面试题和阶段 3 关系流程图。

## 16. 阶段完成条件

- 4 个 Task、每个 Task 5 个单元全部完成；
- Product 数据库约束、CRUD 和权限行为与本文一致；
- `.xlsx` 文件边界、清洗、校验、去重和部分成功行为经过测试；
- Listing 规则全部可解释且不调用 LLM；
- 导出文件可被 openpyxl 和桌面 Excel 打开；
- 不提交真实上传文件、导出文件、`.env` 或密钥；
- 教学教程保留在本地，不进入 Git；
- 阶段末提供实际类与函数之间的流程图；
- 自动化和人工验收通过后，才允许合并 `main`。
