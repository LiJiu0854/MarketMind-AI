# 阶段 3：商品数据与 Excel 实施计划

> **给执行者：** 必须使用 `superpowers:executing-plans` 按 Task 执行。每个单元严格遵循 RED → GREEN → REFACTOR；学习者填写教程标出的核心逻辑，机械接线由 Agent 完成。

**目标：** 实现共享商品库、`.xlsx` 同步导入、逐行错误报告、确定性 Listing 检查和筛选导出。

**架构：** Router 负责 HTTP 与权限；Product Service 负责数据库事务；Product Excel Service 负责文件边界、Pandas 清洗和工作簿生成；Listing Rules 是无 I/O 的纯函数。导入先完成文件与行校验，再查询已有 SKU，用一次事务写入合格商品。

**技术栈：** Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic、MySQL、Pandas、openpyxl、pytest、HTTPX、Ruff、mypy。

**设计依据：** `docs/plans/phase-3-products-excel-design.md`

## 全局约束

- 固定 4 个 Task，每个 Task 5 个学习单元。
- 只支持 `.xlsx`；最大 5 MB，最大 5000 个数据行。
- 商品为团队共享资源，`created_by_id` 只用于审计。
- Admin、Operator 可写；Analyst 只读、检查和导出。
- 行级错误允许部分成功；文件级错误零写入；并发唯一冲突整体回滚。
- 金额使用 `Decimal` 和 `NUMERIC(12, 2)`，不得使用 `float` 作为业务金额类型。
- 不实现异步 Excel 导入、文件存储、商品缓存、LLM、RAG、Agent、SSE、MCP、Playwright 或前端。
- 教学文档保存到 `docs/learning/`，保持本地未跟踪，不纳入 Git。
- 不修改或提交 `docs/learning/phase-0-baseline.md` 和 `tests/unit/models/test_product_practice.py`。
- 每个 Task 通过 pytest、Ruff、mypy 和 `git diff --check` 后才能提交。

## 文件结构与职责

```text
backend/app/models/product.py          Product ORM
backend/app/schemas/product.py         CRUD、导入、Listing 数据契约
backend/app/services/products.py       CRUD、筛选、导入数据库事务
backend/app/services/product_excel.py  Excel 读取、清洗、校验、导出
backend/app/services/listing_rules.py  Listing 纯规则
backend/app/api/v1/products.py         HTTP、RBAC、上传、下载
alembic/versions/0002_create_products_table.py
tests/unit/models/test_product.py
tests/unit/schemas/test_product.py
tests/unit/services/test_product_excel.py
tests/unit/services/test_listing_rules.py
tests/integration/db/test_products.py
tests/integration/db/test_product_import.py
tests/api/test_products.py
```

修改：`pyproject.toml`、`backend/app/models/__init__.py`、`alembic/env.py`、`backend/app/main.py`、`tests/conftest.py`、`README.md`。

核心接口固定为：

- `create_product(session: AsyncSession, data: ProductCreate, created_by_id: int) -> Product`；
- `get_product(session: AsyncSession, product_id: int) -> Product`；
- `list_products(session: AsyncSession, filters: ProductFilters, page: int, page_size: int) -> ProductPage`；
- `import_products(session: AsyncSession, candidates: list[ProductImportCandidate], row_errors: list[ProductImportError], created_by_id: int) -> ProductImportResult`；
- `parse_product_workbook(content: bytes) -> tuple[list[ProductImportCandidate], list[ProductImportError]]`；
- `export_products_workbook(products: list[Product]) -> bytes`；
- `check_listing(product: Product) -> list[ListingIssue]`。

---

# Task 1：商品领域模型与 CRUD

## 学习目标

掌握新业务实体从 ORM、迁移、Schema、Service 到 Router 的纵向开发顺序，理解数据库约束、业务规则和 HTTP 权限的边界。

## 单元 1：Product Model 与创建人外键

**文件：** 新建 `tests/unit/models/test_product.py`、`backend/app/models/product.py`；修改 `backend/app/models/__init__.py`。

**RED：** 测试表名、字段、SKU 唯一索引、金额精度、JSON 卖点、`users.id` 外键和创建人索引。

```python
def test_product_columns() -> None:
    assert {column.name for column in Product.__table__.columns} == {
        "id", "sku", "title", "description", "bullet_points",
        "brand", "category", "price", "currency", "is_active",
        "created_by_id", "created_at", "updated_at",
    }
```

运行 `.venv\Scripts\python.exe -m pytest tests\unit\models\test_product.py -q`，预期因模块不存在而收集失败。

**GREEN：** Product 使用现有 `Base`。关键字段签名：

```python
class Product(Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    bullet_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
```

其余字段严格按设计文档定义；时间字段复用 User 模式；增加 `price > 0` 检查约束。JSON 默认值必须使用 `list`，不能使用共享的 `[]`。

**验收：** Product Model 测试、Ruff、mypy 通过。

## 单元 2：Alembic 商品表迁移

**文件：** 新建 `alembic/versions/0002_create_products_table.py`；修改 `alembic/env.py`、`tests/conftest.py`。

**RED：** 运行 `.venv\Scripts\alembic.exe -x database=test upgrade head`，迁移不存在时测试库没有 `products` 表。

**GREEN：** `revision="0002"`、`down_revision="0001"`；创建全部列、SKU 唯一索引、创建人索引、外键和价格约束。`downgrade()` 按索引、表的逆序删除。Alembic 使用 `Base.metadata` 并导入模型包完成注册。测试夹具先 `delete(Product)`，再 `delete(User)`。

**验收：**

```powershell
.venv\Scripts\alembic.exe -x database=test downgrade 0001
.venv\Scripts\alembic.exe -x database=test upgrade head
.venv\Scripts\alembic.exe -x database=development upgrade head
```

## 单元 3：Product Schema

**文件：** 新建 `tests/unit/schemas/test_product.py`、`backend/app/schemas/product.py`。

**RED：** 覆盖 SKU 去空格并大写、货币大写、Decimal、未知字段拒绝、部分更新和安全响应。

```python
def test_product_create_normalizes_business_fields() -> None:
    data = ProductCreate(
        sku=" sku-001 ", title="Test Product", description="",
        bullet_points=[], brand=" Brand ", category=" Category ",
        price="19.90", currency="cny", is_active=True,
    )
    assert data.sku == "SKU-001"
    assert data.price == Decimal("19.90")
    assert data.currency == "CNY"
```

**GREEN：** 定义 `ProductBase`、`ProductCreate`、`ProductUpdate`、`ProductRead`、`ProductPage`、`ProductFilters`。使用 `extra="forbid"`；SKU 1～50；标题 1～200；品牌/分类不超过 100；价格 `gt=0`、`max_digits=12`、`decimal_places=2`；货币匹配 `^[A-Z]{3}$`。`ProductRead` 开启 `from_attributes=True`。

## 单元 4：商品 CRUD 与筛选 Service

**文件：** 新建 `tests/integration/db/test_products.py`、`backend/app/services/products.py`。

**RED：** 覆盖创建人、读取不存在、分页、SKU/品牌/分类/状态筛选、部分更新、SKU 冲突、软停用和异常回滚。

**GREEN：** 实现 `create_product()`、`get_product()`、`list_products()`、`update_product()`、`deactivate_product()`。创建和更新先查询 SKU，仍捕获 `IntegrityError` 防止并发竞态；所有写异常必须回滚。列表与导出共用私有 `_product_filter_conditions(filters)`。

稳定错误：

```python
AppError(code="PRODUCT_NOT_FOUND", message="商品不存在", status_code=404)
AppError(code="PRODUCT_SKU_CONFLICT", message="SKU 已存在", status_code=409)
```

## 单元 5：商品 API 与 RBAC

**文件：** 新建 `tests/api/test_products.py`、`backend/app/api/v1/products.py`；修改 `backend/app/main.py`。

**RED：** Admin/Operator 写入成功、Analyst 写入 403、三种角色读取成功、未认证 401、分页筛选、更新和软停用。

**GREEN：** Router 前缀为 `/products`，全局依赖 `get_current_user`；写接口额外注入 `require_roles(Role.ADMIN, Role.OPERATOR)`。创建接口把当前用户 ID 传给 Service，并在 `create_app()` 注册 Router。本 Task 不接入 Redis，也不要求幂等请求头。

```python
ProductManager = Annotated[
    User,
    Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
]
```

**Task 1 验收：**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\models\test_product.py tests\unit\schemas\test_product.py tests\integration\db\test_products.py tests\api\test_products.py -q
.venv\Scripts\ruff.exe check backend\app\models\product.py backend\app\schemas\product.py backend\app\services\products.py backend\app\api\v1\products.py tests\unit\models\test_product.py tests\unit\schemas\test_product.py tests\integration\db\test_products.py tests\api\test_products.py
.venv\Scripts\mypy.exe backend\app\models\product.py backend\app\schemas\product.py backend\app\services\products.py backend\app\api\v1\products.py tests\unit\models\test_product.py tests\unit\schemas\test_product.py tests\integration\db\test_products.py tests\api\test_products.py
git diff --check
```

**提交：**

```powershell
git add backend/app/models/product.py backend/app/models/__init__.py backend/app/schemas/product.py backend/app/services/products.py backend/app/api/v1/products.py backend/app/main.py alembic/env.py alembic/versions/0002_create_products_table.py tests/conftest.py tests/unit/models/test_product.py tests/unit/schemas/test_product.py tests/integration/db/test_products.py tests/api/test_products.py
git commit -m "feat: add product catalog CRUD"
```

---

# Task 2：Excel 读取、清洗与校验

## 学习目标

掌握 UploadFile 信任边界、二进制大小限制、DataFrame、空值处理、纯函数清洗、Decimal 转换和 Excel 行号定位。

## 单元 1：依赖和文件边界

**文件：** 修改 `pyproject.toml`；新建 `tests/unit/services/test_product_excel.py`、`backend/app/services/product_excel.py`。

**RED：** 覆盖 `.xlsx` 大小写扩展名、错误扩展名、空文件和 `5 MB + 1 byte`。

**GREEN：** 增加：

```toml
"openpyxl>=3.1,<4.0",
"pandas>=2.3,<3.0",
```

定义 `MAX_XLSX_BYTES = 5 * 1024 * 1024`、`MAX_PRODUCT_ROWS = 5000` 和固定 `EXCEL_COLUMNS`。`validate_xlsx_upload(filename, content)` 只校验文件名、大小和空内容，错误均为 422 `AppError`。

## 单元 2：Pandas 读取、表头和行数

**RED：** 测试合法工作簿、缺列、未知列、重复列、空工作簿、损坏内容和 5001 行。

**GREEN：** `read_product_dataframe(content) -> pd.DataFrame` 使用 `pd.read_excel(BytesIO(content), engine="openpyxl", dtype=object)`。列顺序必须与 `EXCEL_COLUMNS` 完全一致；超过 5000 行抛 `EXCEL_TOO_MANY_ROWS`；仅捕获 Pandas/openpyxl 对损坏文件的公开异常。DataFrame 索引 0 映射 Excel 第 2 行。

## 单元 3：字段清洗

**RED：** 分别覆盖文本空值、SKU 大写、卖点换行、货币大写、Decimal 和布尔值允许形式。

**GREEN：** 实现 `clean_text(value: object) -> str`、`clean_sku(value: object) -> str`、`clean_bullet_points(value: object) -> list[str]`、`clean_currency(value: object) -> str`、`clean_boolean(value: object) -> bool` 和 `clean_decimal(value: object) -> Decimal` 六个纯函数，不创建清洗器类。

空值统一使用 `pd.isna()`；Decimal 从字符串创建；非法转换抛 `ValueError`，由本模块行解析边界转换为稳定错误。

## 单元 4：单行校验与 dataclass

**文件：** 修改 `backend/app/schemas/product.py`、`backend/app/services/product_excel.py`。

**RED：** 覆盖合法行、必填字段、长度、价格、货币、布尔值和 Excel 行号。

**GREEN：**

```python
@dataclass(frozen=True, slots=True)
class ProductImportCandidate:
    row: int
    data: ProductCreate

class ProductImportError(BaseModel):
    row: int = Field(ge=2)
    field: str
    code: str
    message: str
```

`parse_product_row(row_number, values)` 清洗后构造 `ProductCreate` 复用校验。清洗或 Pydantic 校验失败时转换成一个稳定的 `ProductImportError`，不暴露 Pydantic 内部错误结构。

## 单元 5：工作簿解析与文件内去重

**RED：** 覆盖混合正确/错误行、文件内重复 SKU、空白尾行、中间空行和总数守恒。

**GREEN：** `parse_product_workbook()` 维护 `seen_skus: set[str]`。第二个相同规范化 SKU 返回 `DUPLICATE_SKU_IN_FILE`，第一次合法行保留。一个错误行只产生一个汇总错误。

**Task 2 验收：**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\services\test_product_excel.py tests\unit\schemas\test_product.py -q
.venv\Scripts\ruff.exe check backend\app\services\product_excel.py backend\app\schemas\product.py tests\unit\services\test_product_excel.py
.venv\Scripts\mypy.exe backend\app\services\product_excel.py backend\app\schemas\product.py tests\unit\services\test_product_excel.py
git diff --check
```

**提交：**

```powershell
git add pyproject.toml backend/app/schemas/product.py backend/app/services/product_excel.py tests/unit/schemas/test_product.py tests/unit/services/test_product_excel.py
git commit -m "feat: add product Excel validation"
```

---

# Task 3：批量导入、去重与错误报告

## 学习目标

掌握纯文件处理与异步数据库事务的衔接、批量查询避免 N+1、应用层去重与数据库唯一约束的区别，以及部分成功和事务回滚的边界。

## 单元 1：导入结果契约

**文件：** 修改 `backend/app/schemas/product.py`；新建 `tests/integration/db/test_product_import.py`。

**RED：** 验证成功数、失败数、总数约束和逐行错误 JSON。

**GREEN：**

```python
class ProductImportResult(BaseModel):
    total_rows: int = Field(ge=0)
    imported_rows: int = Field(ge=0)
    failed_rows: int = Field(ge=0)
    errors: list[ProductImportError]

    @model_validator(mode="after")
    def validate_totals(self) -> Self:
        if self.total_rows != self.imported_rows + self.failed_rows:
            raise ValueError("导入行数统计不一致")
        return self
```

## 单元 2：数据库已有 SKU 批量查询

**文件：** 修改 `backend/app/services/products.py`。

**RED：** 准备已有 SKU 和多个候选行，证明只标记数据库重复行，并保留其他候选行。

**GREEN：** 实现 `find_existing_skus(session: AsyncSession, skus: set[str]) -> set[str]`。从候选列表提取 SKU 集合，使用一次 `select(Product.sku).where(Product.sku.in_(skus))`。空集合直接返回，不产生 `IN ()` 查询。

## 单元 3：合格商品批量写入与回滚

**RED：** 覆盖合格行写入、创建人记录、数据库重复跳过、全部无效时零写入，以及模拟 `IntegrityError` 后回滚并转换为 409。

**GREEN：** `import_products()` 合并解析错误与数据库重复错误，构造 Product 列表后调用 `session.add_all()`，只提交一次。捕获并发唯一冲突后回滚：

```python
raise AppError(
    code="PRODUCT_IMPORT_CONFLICT",
    message="导入期间 SKU 发生冲突，请重新导入",
    status_code=409,
) from exc
```

其他异常同样先回滚，再原样抛出，由已有数据库异常处理器转换成安全响应。

## 单元 4：导入 API

**文件：** 修改 `backend/app/api/v1/products.py`、`tests/api/test_products.py`。

**RED：** Admin/Operator 导入、Analyst 403、未认证 401、错误扩展名 422、超大文件 422、部分成功 JSON 和创建人记录。

**GREEN：**

```python
@router.post("/import", response_model=ProductImportResult)
async def import_product_workbook(
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: ProductManager,
) -> ProductImportResult:
    content = await file.read(MAX_XLSX_BYTES + 1)
    validate_xlsx_upload(file.filename, content)
    candidates, errors = parse_product_workbook(content)
    return await import_products(session, candidates, errors, actor.id)
```

只读取上限加一字节，不保存上传文件。

## 单元 5：导入故障与回归验收

覆盖以下完整链路：

- 缺表头和损坏文件不写数据库；
- 文件内重复与数据库重复使用不同错误码；
- 混合文件只写合法行；
- 并发冲突返回 409，不假报导入数量；
- 数据库错误响应不包含 SQL、连接串或密码；
- 同一文件再次导入时不重复创建商品。

**Task 3 验收：**

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\services\test_product_excel.py tests\integration\db\test_product_import.py tests\api\test_products.py -q
.venv\Scripts\ruff.exe check backend\app\services\product_excel.py backend\app\services\products.py backend\app\api\v1\products.py tests\integration\db\test_product_import.py tests\api\test_products.py
.venv\Scripts\mypy.exe backend\app\services\product_excel.py backend\app\services\products.py backend\app\api\v1\products.py tests\integration\db\test_product_import.py tests\api\test_products.py
git diff --check
```

**提交：**

```powershell
git add backend/app/schemas/product.py backend/app/services/products.py backend/app/api/v1/products.py tests/integration/db/test_product_import.py tests/api/test_products.py
git commit -m "feat: add partial product import"
```

---

# Task 4：Listing 规则、Excel 导出与阶段验收

## 学习目标

掌握纯规则函数、可解释错误结构、筛选逻辑复用、内存文件生成和 StreamingResponse，并验证生成文件能够被真实 Excel 引擎重新打开。

## 单元 1：ListingIssue 与纯规则函数

**文件：** 新建 `tests/unit/services/test_listing_rules.py`、`backend/app/services/listing_rules.py`；修改 `backend/app/schemas/product.py`。

**RED：** 每条规则一个失败用例，并包含一个全部通过的用例；禁用词覆盖标题、描述和卖点。

**GREEN：**

```python
class ListingIssue(BaseModel):
    code: str
    field: str
    message: str
    suggestion: str

class ListingCheckResult(BaseModel):
    product_id: int
    passed: bool
    issues: list[ListingIssue]

FORBIDDEN_TERMS = ("最便宜", "绝对有效", "永久有效", "100%保证")
```

实现 `check_listing(product: Product) -> list[ListingIssue]`，用普通条件判断追加问题，不创建 Rule 抽象基类。覆盖标题长度、描述、卖点数量与长度、价格、货币和禁用词。

## 单元 2：Listing 检查 API

**文件：** 修改 `backend/app/api/v1/products.py`、`tests/api/test_products.py`。

**RED：** 三种角色均可检查、未认证 401、不存在商品 404、响应不包含 ORM 内部字段。

**GREEN：** 读取 Product 后调用纯函数，返回：

```python
ListingCheckResult(
    product_id=product.id,
    passed=not issues,
    issues=issues,
)
```

不写数据库、不调用 Redis、不缓存结果。

## 单元 3：筛选导出查询

**文件：** 修改 `backend/app/services/products.py`、`tests/integration/db/test_products.py`。

**RED：** 覆盖无筛选、SKU、品牌、分类、状态和组合筛选；列表和导出必须使用相同语义和稳定 ID 顺序。

**GREEN：** `get_products_for_export(session, filters) -> list[Product]` 复用 `_product_filter_conditions()`，不分页，按 Product.id 升序返回。

## 单元 4：生成并下载 `.xlsx`

**文件：** 修改 `backend/app/services/product_excel.py`、`backend/app/api/v1/products.py`、`tests/unit/services/test_product_excel.py`、`tests/api/test_products.py`。

**RED：** 使用 `openpyxl.load_workbook(BytesIO(content))` 重新打开生成结果，断言列顺序、金额、卖点换行和空结果表头；API 测试 MIME、文件名和筛选结果。

**GREEN：** `export_products_workbook(products)` 按固定列顺序创建 DataFrame，卖点以换行连接，通过 `pd.ExcelWriter(output, engine="openpyxl")` 写入 `BytesIO`。Router 返回：

```python
StreamingResponse(
    BytesIO(content),
    media_type=(
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    headers={"Content-Disposition": 'attachment; filename="products.xlsx"'},
)
```

不创建临时文件或下载工具类。

## 单元 5：阶段总验收与学习闭环

**文件：** 修改 `README.md`；本地更新 `docs/learning/phase-3-task-4-listing-export.md`。

**自动化验收：**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
git diff --check
.venv\Scripts\alembic.exe -x database=test current
.venv\Scripts\alembic.exe -x database=development current
```

**人工业务验收：**

1. Operator 上传同时包含合法行、错误价格和文件内重复 SKU 的真实 `.xlsx`；
2. 核对成功数、失败数、实际行号和错误码；
3. 修正错误后重新导入；
4. 分页并按品牌、分类和状态筛选；
5. 修改商品后重新执行 Listing 检查；
6. Analyst 可以查看、检查、导出，但写入返回 403；
7. 下载 `.xlsx` 并用桌面 Excel 打开；
8. 核对导出列顺序、卖点换行和金额；
9. 确认日志、响应和 Git 差异没有密码、JWT 或数据库 URL；
10. 在本地教程追加阶段 3 的实际类与函数关系流程图。

**Task 4 验收：**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe backend tests
git diff --check
git status --short
```

**提交：**

```powershell
git add backend/app/schemas/product.py backend/app/services/listing_rules.py backend/app/services/products.py backend/app/services/product_excel.py backend/app/api/v1/products.py tests/unit/services/test_listing_rules.py tests/unit/services/test_product_excel.py tests/integration/db/test_products.py tests/api/test_products.py README.md
git commit -m "feat: add listing checks and Excel export"
```

---

# 每个 Task 的教学执行规则

开始一个 Task 时，只创建当前 Task 的本地中文教程，必须包含：

1. 业务效果和要掌握的能力；
2. 🔴必须手写、🟡理解即可、🔵了解用途；
3. 文件树和所有新旧文件的配合作用；
4. 真实编写顺序和请求/数据流；
5. 每个单元的 RED 测试、骨架代码和逐段解释；
6. 核心位置使用统一的“学习者实现”注释标记，不得提前填答案；
7. 机械接线和重复代码由 Agent 完成并解释；
8. 单元验收命令和完成口令；
9. 学习者完成后再追加参考实现、真实错误复盘和迁移练习；
10. Task 4 结束时追加阶段 3 实际关系流程图。

对应本地教程：

```text
docs/learning/phase-3-task-1-products-crud.md
docs/learning/phase-3-task-2-excel-validation.md
docs/learning/phase-3-task-3-product-import.md
docs/learning/phase-3-task-4-listing-export.md
```

不得一次生成四份教程。等待学习者完成当前 Task 的单元后再继续。

# Git 边界

预期工程提交：

```text
docs: plan phase 3 products and Excel
feat: add product catalog CRUD
feat: add product Excel validation
feat: add partial product import
feat: add listing checks and Excel export
```

阶段分支为 `phase/3-products-excel`。只有全量自动化、真实 Excel 人工验收和学习问答通过后，才允许推送阶段分支、合并到 `main` 并推送 `main`。
