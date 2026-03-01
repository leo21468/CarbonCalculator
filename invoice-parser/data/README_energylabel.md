# 能效标识网数据对接说明

[中国能效标识网·产品备案查询](https://www.energylabel.com.cn/productFiling) 目前**未提供公开 API**，官方查询方式为网站「产品备案查询」与「绿色低碳码」微信小程序。本目录用于存放**本地能效数据文件**，供 `energylabelAdapter` 优先读取。

## 使用方式

1. **本地 JSON 文件**（当前方式）  
   将 `energylabel_products.json` 作为数据源：在能效标识网或企业自有数据中查询到产品的**年耗电量(kWh/年)**、**使用寿命(年)** 后，按下面格式追加或修改即可。

2. **文件格式**  
   - 数组格式（推荐）：每条记录可含 `productType`、`model`、`annualKWh`、`lifetimeYears`、`source`。
   - 对象格式：`{ "空调": { "lifetimeYears": 10, "annualKWh": 800 }, ... }`

   示例（数组）：
   ```json
   [
     { "productType": "空调", "model": "KFR-35", "annualKWh": 850, "lifetimeYears": 10 },
     { "productType": "冰箱", "annualKWh": 300, "lifetimeYears": 12 }
   ]
   ```

3. **自定义路径**  
   可通过环境变量指定路径：  
   `ENERGYLABEL_LOCAL_PATH=/path/to/your/energylabel_products.json`

4. **预留 API**  
   若日后获得授权接口，可设置：  
   `ENERGYLABEL_API_URL=https://...`、`ENERGYLABEL_API_KEY=...`  
   适配器会优先请求 API，再回退到本地文件与内置典型值。

## 数据来源与合规

- 官网未授权第三方批量抓取，请通过[产品备案查询](https://www.energylabel.com.cn/productFiling)或「绿色低碳码」小程序手动查询后整理为 JSON。
- 如需正式 API 对接，建议联系**中国标准化研究院**：010-58811754。
