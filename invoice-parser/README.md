# 发票解析引擎

支持 **OFD / PDF / XML / JSON** 四种格式的发票结构化数据提取，重点提取 19 位税收分类编码及票面关键字段。

## 目录结构

```
invoice-parser/
├── package.json
├── README.md
└── src/
    ├── models/
    │   └── Invoice.js          # 发票数据模型
    ├── mapping/                 # 税收分类编码 → 碳排放范围
    │   ├── index.js
    │   ├── scopeMappingTable.js # 映射表（模拟数据，生产需对接税务总局 API）
    │   ├── classifyByTaxCode.js  # classifyByTaxCode(taxCode, goodsName)
    │   └── testMapping.js       # 映射测试
    ├── parser/
    │   ├── index.js            # 统一入口 parseInvoice(filePath, fileType)
    │   ├── keywordExtractor.js  # 行业词典、*xxx* 与规则抽取
    │   ├── fuzzyMatcher.js      # Levenshtein 模糊匹配到标准分类
    │   ├── categoryLabels.js   # 10 类标签（电子产品/办公家具/…/其他）
    │   ├── trainingData.json   # 100+ 条标注样本（供 BERT 质心）
    │   ├── bertClassifier.js   # BERT 分类（@xenova/transformers，无训练）
    │   ├── hybridClassifier.js # 混合策略：税号 → BERT → 关键词
    │   ├── demoHybrid.js       # 混合分类演示
    │   └── testNLP.js          # NLP 测试
    ├── parser/
    │   ├── index.js            # 统一入口 parseInvoice(filePath, fileType)
    │   ├── ofdParser.js        # OFD 解析
    │   ├── pdfParser.js        # PDF 解析（文本 + 可选 OCR）
    │   ├── xmlParser.js        # XML 解析
    │   └── jsonParser.js       # JSON 解析
    ├── factors/                 # 排放因子数据库（基于 Emission factors.csv）
    │   ├── index.js
    │   ├── emissionFactors.js  # 因子数据结构、CPCD 碳足迹解析
    │   ├── factorDatabase.js   # 电力/用水/燃料/EEIO 初始化与 CSV 加载
    │   ├── factorService.js    # getFactorByCategory、getFactorByName、getEEIOFactor
    │   ├── factorManager.js    # 单位换算为 kgCO2e、来源追溯
    │   └── testFactors.js      # 因子查询与格式测试
    └── test/
        ├── testParser.js       # 测试脚本
        └── fixtures/
            ├── sample.json
            └── sample.xml
```

## 数据模型 (Invoice)

- `invoiceNumber` - 发票号码  
- `invoiceDate` - 开票日期  
- `sellerName` / `sellerTaxId` - 销方名称、税号  
- `buyerName` / `buyerTaxId` - 购方名称、税号  
- `items` - 明细行：`name`, `taxCode`(19 位), `amount`, `quantity`, `unit`, `price`  
- `totalAmount` - 总金额  
- `fileType` - 原始文件类型 (OFD|PDF|XML|JSON)

## 使用

```js
const { parseInvoice } = require('./src/parser/index');

// 按扩展名自动识别类型
const invoice = await parseInvoice('./path/to/invoice.pdf');

// 或显式指定类型
const invoice = await parseInvoice('./path/to/file', 'XML');

console.log(invoice.invoiceNumber, invoice.items[0].taxCode);
```

## 安装与测试

```bash
cd invoice-parser
npm install
npm test
npm run test:mapping   # 税收分类 → Scope 1/2/3 映射测试
npm run test:nlp       # 货物名称关键词抽取与模糊匹配测试
npm run test:factors  # 排放因子查询与单位换算测试
```

测试覆盖：JSON、XML 解析，以及（若存在）PDF、OFD 文件；并包含文件不存在、不支持类型等错误处理。映射测试覆盖燃料(Scope 1)、电力(Scope 2)、润滑油/服务/商品(Scope 3)及例外规则。

## 依赖说明

- **PDF**：`pdf-parse` 提取文本；扫描件可后续接入 `tesseract.js` 或 `paddle-ocr-node` 做 OCR。  
- **OFD**：`jszip` + `fast-xml-parser` 解包并解析内嵌 XML。  
- **XML/JSON**：`fast-xml-parser` / 原生 `JSON.parse`，并从内容中提取 19 位税收分类编码。

## 错误与日志

解析过程中的错误会抛出 `Error`，并通过 `[InvoiceParser]` 前缀输出到控制台（info/warn/error）。调用方可通过 `try/catch` 统一处理。

## 税收分类 → 排放范围映射

- `classifyByTaxCode(taxCode, goodsName)`：根据 19 位税号与货物名称返回 `{ scope: 1|2|3, confidence: '高'|'中'|'低', reason }`。
- 映射逻辑与例外规则（如润滑油归 Scope 3）见 `src/mapping/`，依据 GHG Protocol。
- **数据来源**：当前为模拟数据；生产环境需对接国家税务总局 API 或官方《商品和服务税收分类编码表》。

## 货物名称 NLP（关键词抽取与模糊匹配）

- `processGoodsName(goodsName)`：对发票货物名称做关键词抽取并模糊匹配到标准分类，返回 `{ keywords, confidence, matches, summary }`。
- **keywordExtractor.js**：行业词典（能源/原材料/运输/办公/服务）、星号标注 `*xxx*` 识别、规则抽取；可后续接入 **jieba**（如 nodejieba）或 BERT/LLM。
- **fuzzyMatcher.js**：基于 **natural** 的 Levenshtein 相似度，阈值默认 0.8，将关键词映射到标准类（如「办公桌」→「办公-家具」）。
- 运行测试：`npm run test:nlp`。

## BERT 混合分类（模糊发票类目）

- **classifyWithBERT(text)**：使用 **@xenova/transformers** 加载预训练模型（默认 Xenova/paraphrase-multilingual-MiniLM-L12-v2），对发票明细文本做向量化后与训练集类别质心比相似度，返回 `{ category, categoryName, confidence }`。无训练，轻量级。
- **classifyHybrid(text, taxCode)**：一级优先税收编码映射，二级 BERT，三级当 BERT 置信度低于 0.7 时降级为关键词匹配。
- **trainingData.json**：100+ 条标注样本（10 类），用于 BERT 各类质心计算。
- 运行演示（首次会下载模型约 30MB）：`npm run demo:hybrid`。
- **使用本地已准备的模型**：
  - 库会在 `TRANSFORMERS_CACHE` 下查找 **Xenova/paraphrase-multilingual-MiniLM-L12-v2/**（即需存在 `tokenizer.json`、`config.json`、`*.onnx` 等）。
  - **目录结构**：若你的模型在 `<模型根>/paraphrase-multilingual-MiniLM-L12-v2/`，需让库能访问到 `<模型根>/Xenova/paraphrase-multilingual-MiniLM-L12-v2/`。可二选一：
    1. 将模型放到 `<模型根>/Xenova/paraphrase-multilingual-MiniLM-L12-v2/`；或  
    2. 保留 `<模型根>/paraphrase-multilingual-MiniLM-L12-v2/`，在 `<模型根>` 下新建 `Xenova` 目录，并建立目录联接（Windows）：  
       `mklink /J "<模型根>\Xenova\paraphrase-multilingual-MiniLM-L12-v2" "<模型根>\paraphrase-multilingual-MiniLM-L12-v2"`
  - **运行前设置环境变量**（PowerShell）：
    ```powershell
    $env:TRANSFORMERS_CACHE = "D:\my_models"   # 改为你的模型根目录
    $env:TRANSFORMERS_LOCAL_ONLY = "1"
    cd invoice-parser
    npm run demo:hybrid
    ```
  - **验证模型是否加载成功**：`node src/nlp/verifyBert.js`（需同样设置上述两个环境变量）。
- 生产环境可替换为云端 LLM API。

## 排放因子数据库

- **数据来源**：基于 **Emission factors.csv**（CPCD，原 cpcd_full_*.csv）及 **data/emission_factors.csv**，并内置电力/用水/燃料/制造业 EEIO 默认因子。
- **factorService**：`getFactorByCategory(category, region)`、`getFactorByName(name)`、`getEEIOFactor(industry)`。
- **factorManager**：`toKgCO2e(factor, amount)` 统一换算为 kgCO2e；数据来源标记与追溯。
- 运行测试：`npm run test:factors`。
