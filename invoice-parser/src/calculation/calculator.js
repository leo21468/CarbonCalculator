/**
 * 双模式核算引擎：活动数据法 + EEIO 支出法
 *
 * - 活动数据法：排放量 = 数量 × 物理因子
 * - 支出法(EEIO)：排放量 = 金额 × EEIO因子
 */

const { toKgCO2e } = require('../factors/factorManager');
const { convertQuantityToFactorUnit } = require('./unitUtils');

const RESULT_UNIT = 'kgCO2e';

/**
 * 活动数据法计算
 * @param {number} quantity - 活动数据数量（如 kWh、吨）
 * @param {Object} factor - 物理因子 { value, unit }
 * @param {string} [unit] - 数量单位（与 factor.unit 分母一致或可换算，如 "度"→kWh）
 * @returns {{ value: number, unit: string, method: "activity" }}
 * @throws 当 factor 无效或 quantity 非正数时返回 value: 0，不抛错
 */
function calculateByActivity(quantity, factor, unit) {
  if (!factor || typeof factor !== 'object') {
    return { value: 0, unit: RESULT_UNIT, method: 'activity' };
  }
  const q = quantity != null ? Number(quantity) : NaN;
  if (Number.isNaN(q) || q < 0) {
    return { value: 0, unit: RESULT_UNIT, method: 'activity' };
  }
  const { quantity: normalizedQ } = convertQuantityToFactorUnit(q, unit, factor.unit);
  const { emissionKg } = toKgCO2e(factor, normalizedQ);
  return {
    value: Math.max(0, emissionKg),
    unit: RESULT_UNIT,
    method: 'activity',
  };
}

/**
 * 支出法(EEIO)计算
 * @param {number} amount - 金额（元）
 * @param {Object} factor - EEIO 因子 { value, unit }，单位通常为 kgCO2e/CNY
 * @returns {{ value: number, unit: string, method: "expenditure" }}
 */
function calculateByExpenditure(amount, factor) {
  if (!factor || typeof factor !== 'object') {
    return { value: 0, unit: RESULT_UNIT, method: 'expenditure' };
  }
  const a = amount != null ? Number(amount) : NaN;
  if (Number.isNaN(a) || a < 0) {
    return { value: 0, unit: RESULT_UNIT, method: 'expenditure' };
  }
  const { emissionKg } = toKgCO2e(factor, a);
  return {
    value: Math.max(0, emissionKg),
    unit: RESULT_UNIT,
    method: 'expenditure',
  };
}

/**
 * 根据因子类型选择计算方法（供 calculationService 调用）
 * @param {Object} factor - 因子对象，含 factorType 或 category
 * @returns {boolean} true 表示使用活动数据法，false 表示支出法
 */
function isActivityFactor(factor) {
  if (!factor) return false;
  const type = (factor.factorType || factor.category || '').toString();
  if (type.includes('物理') || type === '电力' || type === '燃料燃烧' || type === '材料' || type === '用水' || type === '运输' || type === '废弃物') return true;
  return false;
}

module.exports = {
  calculateByActivity,
  calculateByExpenditure,
  isActivityFactor,
  RESULT_UNIT,
};
