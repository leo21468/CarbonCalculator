/**
 * 单位转换工具：将常见中文/别名单位统一为因子所用单位，便于活动数据法计算
 */

/** 活动数据单位 → 标准单位（与 factor.unit 分母一致） */
const ACTIVITY_UNIT_TO_STANDARD = Object.freeze({
  度: 'kWh',
  kWh: 'kWh',
  千瓦时: 'kWh',
  兆瓦时: 'MWh',
  MWh: 'MWh',
  吨: 't',
  t: 't',
  tons: 't',
  升: 'L',
  L: 'L',
  立方米: 'm3',
  m3: 'm3',
  方: 'm3',
  GJ: 'GJ',
});

/** 从 factor.unit（如 kgCO2e/kWh）提取分母 */
const FACTOR_UNIT_DENOMINATORS = Object.freeze({
  'kgCO2e/kWh': 'kWh',
  'kgCO2e/MWh': 'MWh',
  'kgCO2e/t': 't',
  'kgCO2e/L': 'L',
  'kgCO2e/m3': 'm3',
  'kgCO2e/GJ': 'GJ',
  'kgCO2e/CNY': 'CNY',
  'kgCO2e/unit': 'unit',
});

/**
 * 将活动数据单位转为标准单位
 * @param {string} [activityUnit] - 用户输入单位，如 "度"、"吨"
 * @returns {string} 标准单位 kWh/t/L/m3/MWh/GJ/CNY/unit
 */
function normalizeActivityUnit(activityUnit) {
  const u = (activityUnit || '').trim();
  if (!u) return 'unit';
  const lower = u.toLowerCase();
  const standard = ACTIVITY_UNIT_TO_STANDARD[u] || ACTIVITY_UNIT_TO_STANDARD[lower];
  if (standard) return standard;
  if (/度|kwh|千瓦时/i.test(u)) return 'kWh';
  if (/吨|t\b|tons/i.test(u)) return 't';
  if (/升|l\s*$/i.test(u)) return 'L';
  if (/方|立方米|m3/i.test(u)) return 'm3';
  if (/元|yuan|cny/i.test(u)) return 'CNY';
  return lower || 'unit';
}

/**
 * 从因子单位字符串提取分母（用于与活动单位比对）
 * @param {string} [factorUnit] - 如 "kgCO2e/kWh"
 * @returns {string}
 */
function getFactorDenominator(factorUnit) {
  const u = (factorUnit || '').trim();
  return FACTOR_UNIT_DENOMINATORS[u] || (u.split('/')[1] || 'unit').trim();
}

/**
 * 将数量转换为因子所需单位（若单位一致或可换算则返回换算后数量）
 * @param {number} quantity - 原始数量
 * @param {string} [activityUnit] - 原始单位
 * @param {string} [factorUnit] - 因子单位，如 kgCO2e/kWh
 * @returns {{ quantity: number, unit: string, converted: boolean }}
 */
function convertQuantityToFactorUnit(quantity, activityUnit, factorUnit) {
  const actStd = normalizeActivityUnit(activityUnit);
  const factorDenom = getFactorDenominator(factorUnit);
  if (actStd === factorDenom) return { quantity: Number(quantity), unit: factorDenom, converted: false };
  if (quantity == null || Number.isNaN(Number(quantity))) return { quantity: 0, unit: factorDenom, converted: false };
  const q = Number(quantity);
  if (actStd === 'MWh' && factorDenom === 'kWh') return { quantity: q * 1000, unit: 'kWh', converted: true };
  if (actStd === 'kWh' && factorDenom === 'MWh') return { quantity: q / 1000, unit: 'MWh', converted: true };
  return { quantity: q, unit: actStd, converted: actStd === factorDenom };
}

module.exports = {
  normalizeActivityUnit,
  getFactorDenominator,
  convertQuantityToFactorUnit,
  ACTIVITY_UNIT_TO_STANDARD,
  FACTOR_UNIT_DENOMINATORS,
};
