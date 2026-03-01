/**
 * 产品使用阶段排放计算（Scope 3 类别 11：售出产品的使用）
 *
 * 公式：排放量 = 产品数量 × 使用寿命(年) × 年耗电量(kWh/年) × 区域电力因子
 *
 * 能效数据来源与局限性：
 * - 理想数据来源：中国能效标识网备案公开数据
 *   https://www.energylabel.com.cn/productFiling
 *   官网未提供公开 API，本模块通过 energylabelAdapter 支持：本地 JSON、预留 API、内置典型值。
 * - 正式核算建议使用产品实测或备案数据；API 对接可联系中国标准化研究院。
 */

const { getFactorByCategory } = require('../../factors/factorService');
const { FACTOR_CATEGORY } = require('../../factors/emissionFactors');
const { getProductEnergy } = require('./energylabelAdapter');

/**
 * 产品类型 → 能效参数（典型值，非实时能效标识网数据）
 * 生产环境建议从 https://www.energylabel.com.cn/productFiling 或企业自有数据接入
 * @type {{ lifetimeYears: number, annualKWh: number, label?: string }}
 */
const PRODUCT_ENERGY_TABLE = Object.freeze({
  空调: { lifetimeYears: 10, annualKWh: 800, label: '家用空调典型值，能效等级不同差异大' },
  房间空调器: { lifetimeYears: 10, annualKWh: 800, label: '同上' },
  冰箱: { lifetimeYears: 12, annualKWh: 300, label: '家用冰箱典型值' },
  电冰箱: { lifetimeYears: 12, annualKWh: 300, label: '同上' },
  洗衣机: { lifetimeYears: 10, annualKWh: 80, label: '家用洗衣机典型值' },
  电视机: { lifetimeYears: 8, annualKWh: 150, label: '平板电视典型值' },
  电视: { lifetimeYears: 8, annualKWh: 150, label: '同上' },
  电脑: { lifetimeYears: 5, annualKWh: 150, label: '台式机/笔记本典型值' },
  计算机: { lifetimeYears: 5, annualKWh: 150, label: '同上' },
  显示器: { lifetimeYears: 5, annualKWh: 50, label: '显示器典型值' },
  打印机: { lifetimeYears: 5, annualKWh: 30, label: '办公打印机典型值' },
  复印机: { lifetimeYears: 5, annualKWh: 80, label: '复印机典型值' },
  饮水机: { lifetimeYears: 5, annualKWh: 200, label: '饮水机典型值' },
  热水器: { lifetimeYears: 8, annualKWh: 600, label: '电热水器典型值' },
  电热水器: { lifetimeYears: 8, annualKWh: 600, label: '同上' },
});

/**
 * 根据产品类型（及可选数据源）获取能效参数
 * 优先从 energylabelAdapter（本地文件/API）获取，否则回退到内置表
 * @param {string} productType - 产品类型，如 "空调"、"房间空调器"
 * @param {{ source?: 'local'|'api'|'builtin', localPath?: string }} [adapterOptions]
 * @returns {{ lifetimeYears: number, annualKWh: number, source?: string } | null}
 */
function getProductEnergyParams(productType, adapterOptions) {
  const fromAdapter = getProductEnergy(productType, null, adapterOptions);
  if (fromAdapter) return fromAdapter;
  return getProductEnergyParamsBuiltin(productType);
}

/**
 * 仅从内置表匹配（供 getProductEnergyParams 回退）
 */
function getProductEnergyParamsBuiltin(productType) {
  const key = (productType || '').trim();
  if (!key) return null;
  if (PRODUCT_ENERGY_TABLE[key]) return PRODUCT_ENERGY_TABLE[key];
  for (const [k, v] of Object.entries(PRODUCT_ENERGY_TABLE)) {
    if (key.includes(k)) return v;
  }
  return null;
}

/**
 * 产品使用阶段排放计算（Scope 3 Category 11）
 * @param {string} productType - 产品类型，如 "空调"、"冰箱"
 * @param {number} quantity - 产品数量（台/件）
 * @param {string} [region] - 区域（全国/华北/华东/南方等），用于选取区域电力因子
 * @param {{ source?: 'local'|'api'|'builtin', localPath?: string }} [adapterOptions] - 能效数据源，见 energylabelAdapter
 * @returns {{ totalEmissions: number, unit: string, scope: 3, category: string, productType: string, quantity: number, lifetimeYears: number, annualKWh: number, electricityFactor: number, region: string, dataSourceNote: string, dataSource?: string }}
 */
function calculateProductUsage(productType, quantity, region = '全国', adapterOptions) {
  const params = getProductEnergyParams(productType, adapterOptions);
  const q = quantity != null ? Number(quantity) : 0;
  const reg = (region || '全国').trim() || '全国';
  const { ENERGYLABEL_WEBSITE } = require('./energylabelAdapter');

  const result = {
    totalEmissions: 0,
    unit: 'kgCO2e',
    scope: 3,
    category: 'Scope3 Category 11: Use of sold products',
    productType: (productType || '').trim(),
    quantity: q,
    lifetimeYears: 0,
    annualKWh: 0,
    electricityFactor: 0,
    region: reg,
    dataSourceNote: '能效参数来自 energylabelAdapter（本地/API/内置）；官网 ' + ENERGYLABEL_WEBSITE,
  };

  if (!params || q <= 0) {
    return result;
  }

  const electricityFactor = getFactorByCategory(FACTOR_CATEGORY.ELECTRICITY, reg);
  const factorValue = electricityFactor && typeof electricityFactor.value === 'number' ? electricityFactor.value : 0.5839;

  result.lifetimeYears = params.lifetimeYears;
  result.annualKWh = params.annualKWh;
  result.electricityFactor = factorValue;
  result.totalEmissions = Math.max(0, q * params.lifetimeYears * params.annualKWh * factorValue);
  if (params.source) result.dataSource = params.source;

  return result;
}

module.exports = {
  calculateProductUsage,
  getProductEnergyParams,
  PRODUCT_ENERGY_TABLE,
};
