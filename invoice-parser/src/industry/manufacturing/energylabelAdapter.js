/**
 * 中国能效标识网数据对接适配器
 *
 * 官网：https://www.energylabel.com.cn/productFiling
 * 说明：中国能效标识网目前未提供公开 API，官方查询方式为网站「产品备案查询」与
 * 「绿色低碳码」微信小程序（参见中国标准化研究院通知与公告）。本适配器提供三种数据源：
 *
 * 1. local：从本地 JSON 文件读取（可从官网手动查询后整理，或使用未来可能的数据导出）
 * 2. api：预留调用授权/内部 API（若日后获得接口，可配置 ENERGylabel_API_URL 等）
 * 3. builtin：使用内置典型值回退
 *
 * 如需正式 API 对接，建议联系中国标准化研究院：010-58811754。
 */

const path = require('path');
const fs = require('fs');

const ENERGYLABEL_WEBSITE = 'https://www.energylabel.com.cn/productFiling';
const DEFAULT_LOCAL_PATH = path.join(__dirname, '../../../data/energylabel_products.json');

/** 内置典型值（与 productUsageCalculator 的 PRODUCT_ENERGY_TABLE 一致，作回退） */
const BUILTIN_TABLE = Object.freeze({
  空调: { lifetimeYears: 10, annualKWh: 800 },
  房间空调器: { lifetimeYears: 10, annualKWh: 800 },
  冰箱: { lifetimeYears: 12, annualKWh: 300 },
  电冰箱: { lifetimeYears: 12, annualKWh: 300 },
  洗衣机: { lifetimeYears: 10, annualKWh: 80 },
  电视机: { lifetimeYears: 8, annualKWh: 150 },
  电视: { lifetimeYears: 8, annualKWh: 150 },
  电脑: { lifetimeYears: 5, annualKWh: 150 },
  计算机: { lifetimeYears: 5, annualKWh: 150 },
  显示器: { lifetimeYears: 5, annualKWh: 50 },
  打印机: { lifetimeYears: 5, annualKWh: 30 },
  复印机: { lifetimeYears: 5, annualKWh: 80 },
  饮水机: { lifetimeYears: 5, annualKWh: 200 },
  热水器: { lifetimeYears: 8, annualKWh: 600 },
  电热水器: { lifetimeYears: 8, annualKWh: 600 },
});

let localCache = null;
let localCacheMtime = 0;

/**
 * 从本地 JSON 文件读取能效数据
 * 文件格式示例：[{ "productType": "空调", "model": "KFR-35", "annualKWh": 850, "lifetimeYears": 10 }]
 * 或按产品类型：{ "空调": { "lifetimeYears": 10, "annualKWh": 800 }, ... }
 * @param {string} [filePath]
 * @returns {{ [productType: string]: { lifetimeYears: number, annualKWh: number, model?: string, source?: string } } | Array | null}
 */
function loadLocalData(filePath) {
  const p = filePath || process.env.ENERGYLABEL_LOCAL_PATH || DEFAULT_LOCAL_PATH;
  try {
    const stat = fs.statSync(p);
    if (localCache && stat.mtimeMs === localCacheMtime) return localCache;
    const raw = fs.readFileSync(p, 'utf8');
    const data = JSON.parse(raw);
    localCache = data;
    localCacheMtime = stat.mtimeMs;
    return data;
  } catch (e) {
    if (e.code !== 'ENOENT') console.warn('[energylabelAdapter] loadLocalData:', e.message);
    return null;
  }
}

/**
 * 从本地数据结构中按产品类型/型号查找
 * @param {Object|Array} data - loadLocalData 的返回值
 * @param {string} productType - 产品类型
 * @param {string} [model] - 型号（可选，用于精确匹配）
 */
function findInLocalData(data, productType, model) {
  if (!data || !productType) return null;
  const key = (productType || '').trim();
  if (Array.isArray(data)) {
    const withModel = model && String(model).trim();
    if (withModel) {
      const hit = data.find((r) => (r.model && r.model.includes(withModel)) || (r.productType && r.productType.includes(key)));
      if (hit && hit.annualKWh != null) return { lifetimeYears: hit.lifetimeYears ?? 10, annualKWh: hit.annualKWh, source: 'energylabel_local', model: hit.model };
    }
    const byType = data.find((r) => r.productType === key || (r.productType && r.productType.includes(key)));
    if (byType && byType.annualKWh != null) return { lifetimeYears: byType.lifetimeYears ?? 10, annualKWh: byType.annualKWh, source: 'energylabel_local', model: byType.model };
    return null;
  }
  if (typeof data === 'object' && data[key]) {
    const v = data[key];
    if (v.annualKWh != null) return { lifetimeYears: v.lifetimeYears ?? 10, annualKWh: v.annualKWh, source: 'energylabel_local' };
  }
  for (const [k, v] of Object.entries(data)) {
    if (key.includes(k) && v && v.annualKWh != null) return { lifetimeYears: v.lifetimeYears ?? 10, annualKWh: v.annualKWh, source: 'energylabel_local' };
  }
  return null;
}

/**
 * 调用外部 API 获取能效参数（预留）
 * 若配置了 ENERGylabel_API_URL，则 GET {url}?productType=xx&model=yy，期望返回 { lifetimeYears, annualKWh } 或 { data: { ... } }
 * @param {string} productType
 * @param {string} [model]
 * @returns {Promise<{ lifetimeYears: number, annualKWh: number, source: string } | null>}
 */
async function fetchFromApi(productType, model) {
  const baseUrl = process.env.ENERGYLABEL_API_URL || '';
  if (!baseUrl) return null;
  const url = new URL(baseUrl);
  url.searchParams.set('productType', (productType || '').trim());
  if (model) url.searchParams.set('model', String(model).trim());
  try {
    const headers = { 'Accept': 'application/json' };
    if (process.env.ENERGYLABEL_API_KEY) headers['Authorization'] = `Bearer ${process.env.ENERGYLABEL_API_KEY}`;
    const res = await fetch(url.toString(), { headers });
    if (!res.ok) return null;
    const json = await res.json();
    const d = json.data || json;
    if (d.annualKWh != null) return { lifetimeYears: d.lifetimeYears ?? 10, annualKWh: d.annualKWh, source: 'energylabel_api' };
    return null;
  } catch (e) {
    console.warn('[energylabelAdapter] fetchFromApi:', e.message);
    return null;
  }
}

/**
 * 从内置表获取
 */
function getFromBuiltin(productType) {
  const key = (productType || '').trim();
  if (BUILTIN_TABLE[key]) return { ...BUILTIN_TABLE[key], source: 'builtin' };
  for (const [k, v] of Object.entries(BUILTIN_TABLE)) {
    if (key.includes(k)) return { ...v, source: 'builtin' };
  }
  return null;
}

/**
 * 获取产品能效参数（同步：local → builtin）
 * @param {string} productType - 产品类型，如 "空调"
 * @param {string} [model] - 型号（可选，local 下可精确匹配）
 * @param {{ source?: 'local'|'api'|'builtin', localPath?: string }} [options] - 数据源优先顺序可传 source，默认先 local 再 builtin
 * @returns {{ lifetimeYears: number, annualKWh: number, source: string } | null}
 */
function getProductEnergy(productType, model, options = {}) {
  const sourceOrder = options.source ? [options.source] : ['local', 'builtin'];
  for (const src of sourceOrder) {
    if (src === 'local') {
      const data = loadLocalData(options.localPath);
      const found = findInLocalData(data, productType, model);
      if (found) return found;
    } else if (src === 'builtin') {
      const found = getFromBuiltin(productType);
      if (found) return found;
    }
  }
  return null;
}

/**
 * 异步获取（含 API）：先尝试 api，再 local，最后 builtin
 * @param {string} productType
 * @param {string} [model]
 * @param {{ source?: 'local'|'api'|'builtin', localPath?: string }} [options]
 * @returns {Promise<{ lifetimeYears: number, annualKWh: number, source: string } | null>}
 */
async function getProductEnergyAsync(productType, model, options = {}) {
  if (process.env.ENERGYLABEL_API_URL) {
    const fromApi = await fetchFromApi(productType, model);
    if (fromApi) return fromApi;
  }
  return getProductEnergy(productType, model, options);
}

function clearLocalCache() {
  localCache = null;
  localCacheMtime = 0;
}

module.exports = {
  getProductEnergy,
  getProductEnergyAsync,
  loadLocalData,
  findInLocalData,
  fetchFromApi,
  getFromBuiltin,
  clearLocalCache,
  ENERGYLABEL_WEBSITE,
  DEFAULT_LOCAL_PATH,
  BUILTIN_TABLE,
};
