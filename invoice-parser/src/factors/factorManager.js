/**
 * 排放因子标准化：统一换算为 kgCO2e，并做数据来源标记与追溯
 *
 * 单位转换逻辑（均换算为 kgCO2e）：
 * - 电力：kgCO2e/kWh 已为 kgCO2e，无需换算
 * - 热力：GJ → 1 GJ = 0.0036e6 kWh 等价，此处按 110 kgCO2e/GJ 直接使用
 * - 燃料：t → *1000 得 kg；L、m3 已为 kgCO2e/L 或 kgCO2e/m3，用量×因子即 kgCO2e
 * - EEIO：kgCO2e/CNY，金额(元)×因子=kgCO2e
 * 数据来源：每条因子保留 source、year，便于追溯。
 */

const { getFactorList } = require('./factorDatabase');

/** 常用单位与 kgCO2e 的换算（用于将“每单位”因子与“用量”相乘后得到 kgCO2e） */
const UNIT_NORMALIZE = {
  'kgCO2e/kWh': (factorValue, amount) => factorValue * amount,
  'kgCO2e/MWh': (factorValue, amount) => (factorValue / 1000) * amount,
  'kgCO2e/t': (factorValue, amount) => factorValue * amount,
  'kgCO2e/L': (factorValue, amount) => factorValue * amount,
  'kgCO2e/m3': (factorValue, amount) => factorValue * amount,
  'kgCO2e/GJ': (factorValue, amount) => factorValue * amount,
  'kgCO2e/CNY': (factorValue, amount) => factorValue * amount,
  'kgCO2e/unit': (factorValue, amount) => factorValue * amount,
};

/**
 * 根据因子与活动数据计算排放量（kgCO2e）
 * @param {Object} factor - 因子对象 { value, unit }
 * @param {number} amount - 活动数据（用量）
 * @param {string} [activityUnit] - 活动数据单位，若与 factor.unit 一致则直接相乘
 * @returns {{ emissionKg: number, source: string, unitUsed: string }}
 */
function toKgCO2e(factor, amount, activityUnit) {
  if (!factor || typeof amount !== 'number' || Number.isNaN(amount)) {
    return { emissionKg: 0, source: factor?.source || '', unitUsed: factor?.unit || '' };
  }
  const v = factor.value;
  const u = (factor.unit || 'kgCO2e/unit').trim();
  const fn = UNIT_NORMALIZE[u] || ((val, amt) => val * amt);
  const emissionKg = fn(v, amount);
  return {
    emissionKg: Math.max(0, emissionKg),
    source: factor.source || '未知',
    unitUsed: u,
  };
}

/**
 * 为因子对象附加数据来源标记（便于追溯）
 * @param {Object} factor
 * @returns {Object} 含 _trace 的副本
 */
function withSourceTrace(factor) {
  if (!factor) return null;
  return {
    ...factor,
    _trace: `来源: ${factor.source || '未知'}${factor.year ? ` (${factor.year})` : ''}; 单位: ${factor.unit || ''}`,
  };
}

module.exports = {
  toKgCO2e,
  withSourceTrace,
  UNIT_NORMALIZE,
};
