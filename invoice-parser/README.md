# 发票解析与碳核算引擎

支持 **OFD / PDF / XML / JSON** 四种格式的发票结构化数据提取，并基于税收编码、货物名称与排放因子完成 **动态因子匹配** 与 **双模式核算**（活动数据法 + EEIO 支出法）。

## 目录结构

```
invoice-parser/
├── package.json
├── README.md
└── src/
    ├── models/
    │   ├── Invoice.js           # 发票数据模型
    │   └── EmissionResult.js    # 排放核算结果模型（总排放、scope1/2/3 汇总）
    ├── parser/                  # 发票解析
    │   ├── index.js             # 统一入口 parseInvoice(filePath, fileType)
    │   ├── ofdParser.js
    │   ├── pdfParser.js
    │   ├── xmlParser.js
    │   └── jsonParser.js
    ├── mapping/                 # 税收分类编码 → 碳排放范围
    │   ├── index.js
    │   ├── scopeMappingTable.js
    │   ├── classifyByTaxCode.js
    │   └── testMapping.js
    ├── nlp/                     # 货物名称 NLP 与分类
    │   ├── keywordExtractor.js
    │   ├── fuzzyMatcher.js
    │   ├── categoryLabels.js
    │   ├── trainingData.json
    │   ├── bertClassifier.js
    │   ├── hybridClassifier.js
    │   ├── demoHybrid.js
    │   ├── testNLP.js
    │   └── verifyBert.js
    ├── factors/                 # 排放因子库（电力/燃料/材料/EEIO）
    │   ├── index.js
    │   ├── emissionFactors.js
    │   ├── factorDatabase.js
    │   ├── factorService.js
    │   ├── factorManager.js
    │   └── testFactors.js
    ├── matching/                # 动态因子匹配引擎
    │   ├── index.js
    │   ├── factorMatcher.js     # matchFactor(invoiceItem, context)
    │   ├── confidenceScorer.js  # 置信度（高/中/低）
    │   ├── regionMapper.js      # 地址 → 区域电网
    │   ├── demoMatching.js
    │   └── testMatching.js
    ├── calculation/             # 双模式核算引擎
    │   ├── index.js
    │   ├── calculator.js        # 活动数据法 / 支出法
    │   ├── calculationService.js
    │   ├── batchCalculator.js   # 批量计算 → EmissionResult
    │   ├── unitUtils.js         # 单位换算（度→kWh、吨→t）
    │   └── testCalculator.js
    └── test/
        ├── testParser.js
        └── fixtures/
```

## 数据模型

### Invoice

- `invoiceNumber`, `invoiceDate` — 发票号码、开票日期  
- `sellerName` / `sellerTaxId`, `buyerName` / `buyerTaxId` — 销方/购方  
- `items` — 明细：`name`, `taxCode`(19 位), `amount`, `quantity`, `unit`, `price`  
- `totalAmount`, `fileType`

### EmissionResult（核算结果）

- `totalEmissions` — 总排放 (kgCO2e)  
- `items` — 每条：`invoiceId`, `scope`, `emissions`, `method`, `confidence`, `factorUsed`, `reason`, `itemName`  
- `summary` — `{ scope1, scope2, scope3 }` 分范围合计  

## 使用

### 解析发票

```js
const { parseInvoice } = require('./src/parser/index');

const invoice = await parseInvoice('./path/to/invoice.pdf');
// 或 parseInvoice('./path/to/file', 'XML');

console.log(invoice.invoiceNumber, invoice.items[0].taxCode);
```

### 因子匹配 + 核算

```js
const { matchFactor } = require('./src/matching/factorMatcher');
const { calculate } = require('./src/calculation/calculationService');
const { calculateBatch } = require('./src/calculation/batchCalculator');

// 单条：匹配因子后计算
const matched = matchFactor(invoice.items[0], { sellerAddress: '北京市' });
const result = calculate(invoice.items[0], matched);
// result: { value, unit, method, scope, confidence, factorUsed, reason }

// 批量：直接得到 EmissionResult
const emissionResult = calculateBatch(invoice.items, {
  sellerAddress: invoice.sellerName,
  buyerAddress: invoice.buyerName,
}, invoice.invoiceNumber);
console.log(emissionResult.totalEmissions, emissionResult.summary);
```

## 安装与测试

```bash
cd invoice-parser
npm install
npm test
npm run test:mapping    # 税收分类 → Scope 1/2/3
npm run test:nlp        # 关键词抽取与模糊匹配
npm run test:factors    # 排放因子查询
npm run test:matching   # 动态因子匹配（冷轧钢板/办公用品/杂项费用等）
npm run demo:matching   # 匹配演示
npm run test:calculation # 双模式核算（活动法/支出法、批量、单位换算）
```

## 税收分类 → 排放范围

- `classifyByTaxCode(taxCode, goodsName)` 返回 `{ scope: 1|2|3, confidence, reason }`。  
- 映射与例外规则（如润滑油 Scope 3）见 `src/mapping/`，依据 GHG Protocol。  
- 生产环境需对接税务总局 API 或官方税收分类编码表。

## 货物名称 NLP

- **keywordExtractor**：行业词典、`*xxx*` 识别、规则抽取。  
- **fuzzyMatcher**：natural 的 Levenshtein 相似度，映射到标准类。  
- **processGoodsName(goodsName)**：返回 `{ keywords, confidence, matches }`。  
- `npm run test:nlp`

## BERT 混合分类

- **classifyHybrid(text, taxCode)**：税号 → BERT → 关键词降级。  
- 模型：Xenova/paraphrase-multilingual-MiniLM-L12-v2；可本地缓存，设置 `TRANSFORMERS_CACHE`、`TRANSFORMERS_LOCAL_ONLY=1`。  
- 本地目录需能通过 `Xenova/paraphrase-multilingual-MiniLM-L12-v2/` 访问（可用 junction 或拷贝）。  
- `npm run demo:hybrid`，验证：`node src/nlp/verifyBert.js`。

## 排放因子库

- 数据：**Emission factors.csv**（CPCD）、**data/emission_factors.csv** 及内置电力/燃料/材料/EEIO。  
- **factorService**：`getFactorByCategory(category, region)`、`getFactorByName(name)`、`getEEIOFactor(industry)`。  
- **factorManager**：`toKgCO2e(factor, amount)` 统一为 kgCO2e。  
- `npm run test:factors`

## 动态因子匹配

- **matchFactor(invoiceItem, context)**：按优先级匹配物理因子 / EEIO / 默认因子，返回 `{ factor, matchType, confidence, reason }`。  
  - 优先 1：有物理量 + 明确物料 → LCA 物理因子（如钢材、电力）  
  - 优先 2：有税收编码 → 行业/区域因子  
  - 优先 3：仅金额 + 关键词 → 行业 EEIO  
  - 降级：默认因子，低置信度  
- **regionMapper**：销方/购方地址 → 区域电网（华北/华东等）。  
- **confidenceScorer**：高（物理量+物料+物理因子）/ 中（金额+行业+EEIO）/ 低（模糊或默认）。  
- `npm run test:matching`、`npm run demo:matching`

## 双模式核算

- **活动数据法**：`calculateByActivity(quantity, factor, unit)` — 排放 = 数量 × 物理因子。  
- **支出法**：`calculateByExpenditure(amount, factor)` — 排放 = 金额 × EEIO 因子。  
- **calculationService.calculate(item, matchedFactor)**：根据匹配类型自动选活动法或支出法，并推断 scope（电力→2，燃料→1，其余→3）。  
- **calculateBatch(invoiceItems, context?, invoiceId?)**：批量匹配+计算，返回 **EmissionResult**（含 totalEmissions、items、summary.scope1/2/3）。  
- **unitUtils**：度→kWh、吨→t、升→L 等，与因子单位对齐。  
- `npm run test:calculation`

## 依赖

- **PDF**：pdf-parse；扫描件可接 tesseract.js 等 OCR。  
- **OFD**：jszip + fast-xml-parser。  
- **NLP**：natural；BERT 为 @xenova/transformers。

## 错误与日志

解析错误通过 `Error` 抛出，日志带 `[InvoiceParser]` 前缀；核算在无效输入时返回 0 不抛错。
