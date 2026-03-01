/**
 * 核算服务：集成因子匹配，根据 matchedFactor 类型自动选择活动数据法或支出法
 */

const { calculateByActivity, calculateByExpenditure, isActivityFactor } = require('./calculator');
const { FACTOR_CATEGORY } = require('../factors/emissionFactors');

/**
 * 根据因子类别推断 GHG 范围
 * @param {Object} factor - 因子对象
 * @returns {1|2|3}
 */
function scopeFromFactor(factor) {
  if (!factor || !factor.category) return 3;
  const cat = factor.category.toString();
  if (cat === '燃料燃烧') return 1;
  if (cat === '电力' || cat.indexOf('热') !== -1) return 2;
  return 3;
}

/**
 * 单条核算：根据 matchedFactor 自动选择计算方法
 * @param {Object} invoiceItem - 发票明细 { name, amount, quantity, unit, taxCode, ... }
 * @param {Object} matchedFactor - 匹配结果 { factor, matchType, confidence, reason }
 * @returns {{ value: number, unit: string, method: string, scope: number, confidence: string, factorUsed: Object, reason: string, itemName: string }}
 */
function calculate(invoiceItem, matchedFactor) {
  const name = invoiceItem.name || invoiceItem.goodsName || '';
  const amount = invoiceItem.amount != null ? Number(invoiceItem.amount) : NaN;
  const quantity = invoiceItem.quantity != null ? Number(invoiceItem.quantity) : NaN;
  const unit = invoiceItem.unit || '';

  const factor = matchedFactor && matchedFactor.factor;
  const confidence = (matchedFactor && matchedFactor.confidence) || '低';
  const reason = (matchedFactor && matchedFactor.reason) || '';

  const useActivity = factor && (matchedFactor.matchType === '物理因子' || isActivityFactor(factor));
  const hasValidQuantity = !Number.isNaN(quantity) && quantity > 0 && (unit || factor?.unit);

  let result;
  if (useActivity && hasValidQuantity) {
    result = calculateByActivity(quantity, factor, unit);
  } else {
    result = calculateByExpenditure(Number.isNaN(amount) ? 0 : amount, factor || { value: 0, unit: 'kgCO2e/CNY' });
  }

  const scope = scopeFromFactor(factor);

  return {
    value: result.value,
    unit: result.unit,
    method: result.method,
    scope,
    confidence,
    factorUsed: factor || null,
    reason,
    itemName: name,
  };
}

module.exports = {
  calculate,
  scopeFromFactor,
};
