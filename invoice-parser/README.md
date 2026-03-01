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
    │   ├── ofdParser.js        # OFD 解析
    │   ├── pdfParser.js        # PDF 解析（文本 + 可选 OCR）
    │   ├── xmlParser.js        # XML 解析
    │   └── jsonParser.js       # JSON 解析
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
