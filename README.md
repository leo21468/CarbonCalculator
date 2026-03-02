# CarbonCalculator 企业碳核算与碳利润表系统

基于电子发票与 GHG Protocol 的企业碳排放核算与碳利润表演示系统，用于将环境数据资产化：从「核算排放多少吨」到「这些排放让企业少赚了多少钱」。

## 功能概览

1. **第一步：数据采集 — 发票结构化提取**  
   - **Python 侧**：从 API 返回的 JSON/XML 或 dict 中解析发票行（货物名称、19 位税收分类编码、金额/数量/单位、销方信息）。  
   - **Node 侧（invoice-parser）**：支持 OFD/PDF/XML/JSON 四种格式的电子发票解析，提取 19 位税号及票面关键字段；可选 BERT + 关键词做货物名称分类。

2. **第二步：按排放范围分类**  
   - 按中国税收分类编码与 GHG Protocol 映射至 Scope 1（直接燃料）/ Scope 2（电热冷）/ Scope 3（其他商品与服务）。  
   - 支持排除规则（如石油加工类中的沥青、蜡、碳黑、润滑油归 Scope 3）。  
   - 租赁默认 Scope 3；服务/劳务归 Scope 3。  
   - 关键词与可选语义（NLP/LLM）扩展。

3. **第三步：排放量化**  
   - **活动数据法**：有数量+单位时，E = 活动数据 × 排放因子（电力/燃料/材料等）。  
   - **EEIO 支出法**：仅金额时，E = 金额 × 排放强度（kgCO2e/元）。  
   - **invoice-parser** 提供动态因子匹配（物理因子 / 行业 EEIO / 默认因子）、区域电网映射与双模式核算，输出总排放及 scope1/2/3 汇总。

4. **审计追踪（invoice-parser）**  
   - 可选记录每一步计算的来源与依据：解析 → 分类 → 语义增强 → 匹配 → 计算（或场景专项）。  
   - 审计记录含步骤输入/输出、规则/模型、置信度及因子与分类的数据来源（物理因子库、EEIO 行业与版本、税收编码规则等）。  
   - 支持按发票 ID 查询审计、导出 JSON/HTML 报告，HTML 模板可打印另存为 PDF。

5. **第四步：碳利润表与双账本**  
   - 碳价：支持市场价（如上海环境能源交易所 CEA）或内部设定价。  
   - 成本归集到制造费用/销售费用/管理费用 - 碳成本。  
   - 碳利润表：营业收入、传统成本、毛利、直接/隐含碳成本、经碳调整后毛利、碳资产损益、净碳损益。  
   - 双账本：与财务凭证平行的碳会计分录。  
   - 报表洞察：产品线伪利润识别、供应链 Scope 3 议价依据。

```
CarbonCalculator/
├── README.md
├── requirements.txt
├── run_server.py                 # 启动碳足迹 Agent 前后端（FastAPI + 前端）
├── reference table.xlsx           # 税收分类编码→排放范围映射表（可导入 SQLite）
├── Emission factors.csv           # CPCD 电网等排放因子（invoice-parser 可读）
├── data/
│   ├── reference_table.db        # （可选）由脚本从 xlsx 导入的 SQLite
│   ├── reference_schema.sql
│   ├── tax_code_to_scope.csv
│   ├── scope_mapping_rules.yaml
│   └── emission_factors.csv
├── src/                          # Python 核心
│   ├── config.py
│   ├── models.py
│   ├── invoice_parser.py         # 发票解析接口（JSON/XML/dict）
│   ├── scope_mapping.py          # 税收编码→Scope（优先 DB）
│   ├── classifier.py
│   ├── emission_factors.py
│   ├── emission_calculator.py    # 活动数据法 + EEIO
│   ├── carbon_ledger.py          # 碳利润表、双账本
│   ├── carbon_price_fetcher.py
│   ├── insights.py
│   ├── pipeline.py               # 端到端流水线
│   └── cpcd_matcher.py           # CPCD 产品匹配（jieba+TF-IDF）
├── backend/
│   ├── app.py                    # FastAPI 后端
│   ├── database.py
│   └── carbon_utils.py
├── frontend/
│   └── index.html                # Agent 前端
├── invoice-parser/               # Node.js 发票解析与碳核算子项目
│   ├── README.md
│   ├── package.json
│   └── src/
│       ├── parser/               # OFD/PDF/XML/JSON 解析
│       ├── mapping/              # 税号→Scope
│       ├── nlp/                  # 关键词、模糊匹配、BERT 分类
│       ├── factors/              # 排放因子库（电力/燃料/EEIO）
│       ├── matching/             # 动态因子匹配、置信度、区域电网
│       ├── calculation/          # 活动数据法 + 支出法、批量核算
│       ├── orchestrator/         # 端到端流程编排 processSingleInvoice / processBatchInvoice
│       ├── audit/                # 审计追踪：auditTrail、auditLogger、dataProvenance、报告模板
│       ├── scenarios/            # 场景专项（水电/住宿/交通等）
│       └── models/               # Invoice、EmissionResult
├── scripts/
│   └── import_reference_table_to_db.py   # xlsx → SQLite
├── examples/
│   ├── run_pipeline_demo.py
│   └── cpcd_match_demo.py
└── tests/
```

## 依赖与运行

### Python（主流程、后端、碳利润表）

- Python 3.9+
- 依赖：`PyYAML`、`pandas`、`openpyxl`、`jieba`、`scikit-learn` 等（见 `requirements.txt`）

```bash
pip install -r requirements.txt
python run_server.py              # 启动前后端，访问 http://localhost:8000
python examples/run_pipeline_demo.py
python -m pytest tests/ -v
```

### Node.js（invoice-parser：多格式发票解析 + 因子匹配 + 核算）

- Node.js 16+
- 用于 OFD/PDF/XML/JSON 解析、动态因子匹配、双模式核算（活动法/EEIO）。可与 Python 流水线配合：先由 invoice-parser 解析并算出排放，再将结果以 JSON 形式交给 Python 做碳利润表；也可单独使用。

```bash
cd invoice-parser
npm install
npm test
npm run test:mapping              # 税号→Scope
npm run test:factors              # 排放因子
npm run test:matching             # 因子匹配
npm run demo:matching             # 匹配演示
npm run test:calculation          # 双模式核算
node src/audit/testAudit.js      # 审计追踪测试（生成 JSON/HTML 报告）
```

详见 [invoice-parser/README.md](invoice-parser/README.md)。

## 使用方式

### 从 API 解析后的发票 dict 跑通流水线（Python）

```python
from src.pipeline import CarbonAccountingPipeline
from src.config import AppConfig, CarbonPriceConfig

config = AppConfig(
    carbon_price=CarbonPriceConfig(source="internal", price_per_ton=100.0),
)
pipeline = CarbonAccountingPipeline(config=config)

invoice_data = {
    "lines": [
        {"name": "电力*电费*", "tax_classification_code": "10901...", "quantity": 5000, "unit": "度", "amount": 4000.0},
        {"name": "办公用品", "amount": 11000.0},
    ],
    "seller": {"name": "国网上海"},
}
out = pipeline.process_invoice_from_dict(invoice_data)
# out["classified"]       # 每行 Scope
# out["emission_results"] # 每行排放 kg
# out["ledger_entries"]   # 碳账本分录
# out["aggregate_kg"]     # 按 Scope 汇总
```

### 发票解析与碳核算（Node invoice-parser）

端到端单张/批量处理（解析 → 分类 → 语义增强 → 匹配 → 计算，或场景专项），可选审计追踪：

```js
const { processSingleInvoice } = require('./invoice-parser/src/orchestrator/processInvoice');
const auditLogger = require('./invoice-parser/src/audit/auditLogger');

// 传入文件路径或发票对象，enableAudit 开启审计
const { result, invoice, logs, auditTrail } = await processSingleInvoice('./path/to/invoice.pdf', {
  region: '华东',
  enableAudit: true,
});

// result.totalEmissions, result.summary.scope1/2/3
// 导出审计报告
const jsonReport = auditLogger.exportAuditReport(invoice.invoiceNumber, 'json');
const htmlReport = auditLogger.exportAuditReport(invoice.invoiceNumber, 'html');  // 可打印为 PDF
```

### 碳足迹 Agent 前后端

启动服务后访问 http://localhost:8000：

- **查询**：输入产品名称（如电力、汽油、鸡蛋），返回碳种类、二氧化碳当量及碳成本价格  
- **新增数据**：添加自定义产品碳足迹到 SQLite  
- **自定义列表**：查看已添加的产品  

```bash
python run_server.py
```

### CPCD NLP 匹配（Python）

```python
from src.cpcd_matcher import CPCDNLPMatcher

matcher = CPCDNLPMatcher()
for m in matcher.match("电力", top_k=3):
    print(f"{m.similarity:.3f} | {m.product_name} | {m.carbon_footprint}")
```

或命令行：`python -m src.cpcd_matcher 电力`

### 碳利润表（Python）

```python
st = pipeline.build_statement(
    revenue=1_000_000,
    traditional_cost=600_000,
    emission_results=out["emission_results"],
)
# st.carbon_adjusted_gross, st.net_carbon_pnl 等
```

## 碳排放计算输入字段说明

### 金额字段（amount）为唯一 EEIO 计算输入

碳排放核算中，EEIO 支出法的输入**始终为发票金额（amount）字段**，公式为：

```
碳排放量(kgCO2e) = 金额(CNY元) × 碳排放强度(kgCO2e/元)
```

**重要**：税率字段（`税率`、`tax_rate`，如 `13%`、`9%`）**不参与**碳排放量化，仅用于发票税费校验等财务场景。系统在 OCR 识别与字段映射时已明确排除税率列，防止误用。

### 金额解析格式（`parse_amount_cny`）

`src/invoice_parser.py` 中的 `parse_amount_cny(val)` 函数统一解析带货币符号的金额字符串：

| 输入格式 | 输出 |
|---------|------|
| `"¥1,234.56"` | `1234.56` |
| `"￥1,234.56"` | `1234.56` |
| `"RMB 5000"` | `5000.0` |
| `"1,234.56元"` | `1234.56` |
| `"1 234,56"`（欧式） | `1234.56` |
| `"1,234,567.89"` | `1234567.89` |
| `"13%"`（税率） | `None`（拒绝，不作为金额） |
| `""` / `None` | `None` |

OCR 识别结果处理：若 PaddleOCR 返回的发票行文本包含税率列（如 `*电力*电费 100 度 0.80 80.00 13% 10.40`），系统会先过滤百分比值再按列序提取金额，确保 `amount = 80.00` 而非税率数值 `13`。

### 字段缺失降级策略

- `amount` 字段缺失或无法解析时，碳计算返回 `None` 并跳过该行（不使用税率代替）。
- 如需排查字段来源，请检查发票 `lines[i].amount` 是否正确提取。



## 映射表与因子

- **19 位税号 → Scope**：优先从 **SQLite** `data/reference_table.db` 加载（需先执行 `python scripts/import_reference_table_to_db.py`）；若无 DB 则从 `reference table.xlsx` 或 `data/scope_mapping_rules.yaml`、`data/tax_code_to_scope.csv` 回退。  
- **排放因子**：Python 使用 `data/emission_factors.csv` 等；invoice-parser 使用项目根目录 `Emission factors.csv`（CPCD）及内置电力/燃料/EEIO 因子，支持区域电网与动态匹配。  
- **碳价**：内部价或对接上海环境能源交易所（见 `carbon_price_fetcher.py`）。

## 设计依据

- 排放范围与分类：GHG Protocol。  
- 中国税收分类编码：19 位编码为锚点。  
- 双账本与碳利润表：与成本归集与碳利润表设计一致。

## License

MIT
