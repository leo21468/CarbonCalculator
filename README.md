# CarbonCalculator 企业碳核算与碳利润表系统

基于电子发票与 GHG Protocol 的企业碳排放核算与碳利润表演示系统，用于将环境数据资产化：从「核算排放多少吨」到「这些排放让企业少赚了多少钱」。

## 功能概览

1. **第一步：数据采集 — 发票结构化提取**  
   从电子发票（OFD/PDF/XML）或 API 返回的 JSON 中提取：货物或应税劳务名称、商品和服务税收分类编码（19 位）、金额/单价/数量、销方信息。

2. **第二步：按排放范围分类**  
   - 按中国税收分类编码与 GHG Protocol 映射至 Scope 1（直接燃料）/ Scope 2（电热冷）/ Scope 3（其他商品与服务）。  
   - 支持排除规则（如石油加工类中的沥青、蜡、碳黑、润滑油归 Scope 3）。  
   - 租赁默认 Scope 3；服务/劳务一刀切 Scope 3。  
   - 关键词与可选语义（NLP/LLM）扩展，用于宽泛类目。

3. **第三步：排放量化**  
   - **活动数据法**：有数量+单位时，E = 活动数据 × 排放因子。  
   - **EEIO**：仅金额时，按金额 × 排放强度（kg/元）。

4. **第四步：碳利润表与双账本**  
   - 碳价：支持市场价（如上海环境能源交易所 CEA）或内部设定价。  
   - 成本归集到制造费用/销售费用/管理费用 - 碳成本。  
   - 碳利润表：营业收入、传统成本、毛利、直接/隐含碳成本、经碳调整后毛利、碳资产损益、净碳损益。  
   - 双账本：与财务凭证平行的碳会计分录。  
   - 报表洞察：产品线伪利润识别、供应链 Scope 3 议价依据。

## 项目结构

```
CarbonCalculator/
├── reference table.xlsx           # 税收分类编码→排放范围映射表（优先加载）
├── data/
│   ├── tax_code_to_scope.csv      # 税号前缀 → Scope 简表（回退）
│   ├── scope_mapping_rules.yaml   # 详细映射与排除/关键词规则（回退 + 关键词）
│   └── emission_factors.csv       # 排放因子表（19位税号→因子）
├── src/
│   ├── config.py                  # 碳价、排放因子等配置
│   ├── models.py                  # 发票、Scope、碳账本、碳利润表数据模型
│   ├── invoice_parser.py          # 发票解析接口（JSON/XML/dict）
│   ├── scope_mapping.py           # 税收编码→Scope 映射表与查询
│   ├── classifier.py              # 发票明细→Scope 分类（规则+关键词）
│   ├── emission_factors.py        # 排放因子加载
│   ├── emission_calculator.py     # 活动数据法 + EEIO
│   ├── carbon_ledger.py           # 碳利润表、双账本、成本归集
│   ├── carbon_price_fetcher.py    # 碳价抓取占位（上海交易所）
│   ├── insights.py                # 产品线伪利润、供应链议价分析
│   ├── pipeline.py                # 端到端流水线
│   └── cpcd_matcher.py            # NLP 匹配 CPCD 产品类别（jieba+TF-IDF）
├── cpcd_full_*.csv                # CPCD 产品碳足迹数据库
├── examples/
│   ├── run_pipeline_demo.py       # 从发票 dict 到碳利润表演示
│   └── cpcd_match_demo.py         # CPCD NLP 匹配演示
├── requirements.txt
└── README.md
```

## 依赖与运行

- Python 3.9+
- 核心依赖：`PyYAML`、`pandas`、`openpyxl`、`jieba`、`scikit-learn`（CPCD NLP 匹配）；可选：`numpy`、发票解析库、`requests`/`beautifulsoup4`（碳价抓取）

```bash
pip install -r requirements.txt
python examples/run_pipeline_demo.py
```

## 使用方式

### 从 API 解析后的发票 dict 跑通流水线

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

### CPCD NLP 匹配（agent 输入 → 产品类别）

将用户输入文本与 `cpcd_full_*.csv` 中的产品名称进行语义匹配，返回最相似的产品及其碳足迹：

```python
from src.cpcd_matcher import CPCDNLPMatcher, CPCDMatch

matcher = CPCDNLPMatcher()  # 默认加载 cpcd_full_20260213_164705.csv
for m in matcher.match("电力", top_k=3):
    print(f"{m.similarity:.3f} | {m.product_name} | {m.carbon_footprint}")
```

或命令行：`python -m src.cpcd_matcher 电力`

### 碳利润表

```python
st = pipeline.build_statement(
    revenue=1_000_000,
    traditional_cost=600_000,
    emission_results=out["emission_results"],
)
# st.carbon_adjusted_gross, st.net_carbon_pnl 等
```

### 映射表与因子

- **19 位税号 → Scope**：优先从项目根目录 `reference table.xlsx` 加载（支持列名：税收分类编码、排放范围、排除关键词、排放因子）；若文件不存在则回退到 `data/scope_mapping_rules.yaml` 与 `data/tax_code_to_scope.csv`。可通过 `AppConfig.scope_mapping.ref_table_path` 指定自定义路径。
- **碳价**：不参与碳市场时使用内部价（如 100–300 元/吨）；履约时可对接上海环境能源交易所每日收盘价（见 `carbon_price_fetcher.py` 占位）。

## 设计依据

- 排放范围与分类逻辑：GHG Protocol（温室气体核算体系）。  
- 中国税收分类编码：作为国家标准锚点，优先使用 19 位编码字段。  
- 双账本与碳利润表结构：与您提供的「成本归集与碳利润表」设计一致。

## License

MIT
