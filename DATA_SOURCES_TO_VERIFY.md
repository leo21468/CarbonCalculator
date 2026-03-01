# 需补充/网上查询的数据清单

本文件记录项目中**当前为模拟或典型值、尚未对接权威数据源**的项，便于后续到网上或官方渠道查询并替换。

---

## 一、发票解析与税收分类（invoice-parser）

| 数据项 | 当前状态 | 建议查询/对接来源 | 位置 |
|--------|----------|-------------------|------|
| 税收分类编码 → Scope 1/2/3 映射 | 模拟规则表 | **国家税务总局 API** 或《商品和服务税收分类编码表》 | `invoice-parser/src/mapping/scopeMappingTable.js`、`classifyByTaxCode.js` |
| 19 位税号与货物名称的权威分类 | 模拟 | 同上 | `invoice-parser/src/mapping/` |

---

## 二、排放因子（invoice-parser / 主项目）

| 数据项 | 当前状态 | 建议查询/对接来源 | 位置 |
|--------|----------|-------------------|------|
| 区域电网排放因子（华北/华东/南方等） | 部分来自 CPCD CSV，部分内置 | **生态环境部**、**全国电网/区域电网** 最新公布因子；CPCD 产品碳足迹库 | `invoice-parser/src/factors/factorDatabase.js`、`Emission factors.csv` |
| 全国电网平均因子 | 0.5839 kgCO2e/kWh（2019） | 生态环境部年度公布值 | 同上 |
| 自来水供应 / 污水处理因子 | 文献默认值 | 地方水务/住建部门或行业文献 | `factorDatabase.js`（water_supply, water_wastewater） |
| 汽油/柴油/天然气/原煤因子 | 内置或 data/emission_factors.csv | **国家发改委/生态环境部** 发布的燃料排放因子 | `factorDatabase.js` |
| 造纸/钢铁/水泥/制造业 EEIO 因子 | 投入产出表默认值 | **中国投入产出表**、行业 EEIO 数据库 | `factorDatabase.js`（eeio_*） |
| 钢材/水泥/塑料/铜/铝/电机等物料因子 | LCA 文献典型值 | 权威 LCA 数据库、EPD、CPCD | `factorDatabase.js`（material_*）、`invoice-parser/src/industry/manufacturing/materialMatcher.js` |
| 办公用水因子（0.168 kgCO2e/吨） | 固定值 | 自来水/水务碳足迹研究或地方因子 | `invoice-parser/src/scenarios/waterCalculator.js` |

---

## 三、能效与产品使用阶段（制造业插件）

| 数据项 | 当前状态 | 建议查询/对接来源 | 位置 |
|--------|----------|-------------------|------|
| 产品能效（寿命、年耗电量） | 内置典型值 + 本地 JSON | **中国能效标识网** [productFiling](https://www.energylabel.com.cn/productFiling)（无公开 API，需手动整理或联系中国标准化研究院 010-58811754） | `invoice-parser/src/industry/manufacturing/productUsageCalculator.js`、`energylabelAdapter.js`、`data/energylabel_products.json` |

---

## 四、差旅住宿（场景化核算）

| 数据项 | 当前状态 | 建议查询/对接来源 | 位置 |
|--------|----------|-------------------|------|
| 城市差旅住宿费标准（元/间·天） | 模拟，参考财政部办法 | **财政部《中央和国家机关差旅费管理办法》** 及各省最新差旅住宿费标准 | `invoice-parser/src/scenarios/cityRates.js` |
| 酒店住宿碳足迹（kgCO2e/间夜） | 模拟 | **CHSB（中国酒店可持续基准）** 或企业认可的酒店碳足迹/行业研究 | `invoice-parser/src/scenarios/hotelFactors.js` |

---

## 五、通勤与交通（场景化核算）

| 数据项 | 当前状态 | 建议查询/对接来源 | 位置 |
|--------|----------|-------------------|------|
| 汽油/柴油因子（通勤用，2.98 / 3.16 kgCO2e/升） | 模拟 | 与“二、排放因子”中燃料因子统一，可查 **发改委/生态环境部** 成品油因子 | `invoice-parser/src/scenarios/transportCalculator.js` |
| 公共交通 EEIO（0.12 kgCO2e/元） | 模拟 | 城市公交/地铁碳足迹研究或行业 EEIO | 同上 |
| 出租车/网约车 EEIO（0.35 kgCO2e/元） | 模拟 | 出行碳足迹或交通行业 EEIO | 同上 |

---

## 六、物流运输（场景化核算）

| 数据项 | 当前状态 | 建议查询/对接来源 | 位置 |
|--------|----------|-------------------|------|
| 公路/铁路/航空 EEIO（0.28 / 0.09 / 0.85 kgCO2e/元） | 模拟 | **交通运输行业** 碳足迹或投入产出表物流相关因子 | `invoice-parser/src/scenarios/logisticsCalculator.js` |

---

## 七、废弃物处理（场景化核算）

| 数据项 | 当前状态 | 建议查询/对接来源 | 位置 |
|--------|----------|-------------------|------|
| 废弃物处理 EEIO（0.45 kgCO2e/元） | 模拟 | 环卫/固废行业碳足迹或地方公布因子 | `invoice-parser/src/scenarios/wasteCalculator.js` |

---

## 八、主项目 Python 侧

| 数据项 | 当前状态 | 建议查询/对接来源 | 位置 |
|--------|----------|-------------------|------|
| 税收分类 → Scope 映射（reference table） | 从 xlsx/DB 读，内容为项目自制 | 同“一”、对接税务总局或官方编码表 | `data/reference_table.db`、`reference table.xlsx`、`src/scope_mapping.py` |
| 碳价（元/吨 CO2e） | 配置或占位 | **上海环境能源交易所** 等碳市场行情 | `src/carbon_price_fetcher.py`、`src/config.py` |
| 默认电力/热力/EEIO 因子 | 配置默认值 | 同“二” | `src/config.py`、`src/emission_factors.py` |

---

## 查询与替换建议

1. **优先**：电网因子、燃料因子、税收分类与 Scope 映射 → 影响面大，建议先对接官方或权威发布。
2. **能效**：能效标识网无公开 API，可手动从 [能效标识网](https://www.energylabel.com.cn/productFiling) 查询后填入 `invoice-parser/data/energylabel_products.json`，或联系中国标准化研究院咨询接口。
3. **差旅**：财政部与各省财政厅会发布差旅费标准，可按年度更新 `cityRates.js`。
4. **CHSB / 酒店**：若有 CHSB 或酒店业碳足迹数据库，可替换 `hotelFactors.js` 中的数值。
5. **EEIO / 物流 / 废弃物**：可查阅中国投入产出表、行业碳足迹研究或地方公布的排放因子，替换对应场景模块中的常数。

替换时请在代码中**更新注释**并注明数据来源与年份，便于追溯与复核。
