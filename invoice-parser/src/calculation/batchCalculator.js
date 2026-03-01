/**
 * 批量核算：对多条发票明细匹配因子并汇总为 EmissionResult
 */

const { matchFactor } = require('../matching/factorMatcher');
const { calculate } = require('./calculationService');
const { EmissionResult } = require('../models/EmissionResult');

/**
 * 批量计算
 * @param {Object[]} invoiceItems - 发票明细数组，每项含 name, amount, quantity, unit, taxCode 等
 * @param {Object} [context] - 可选上下文 { sellerAddress, buyerAddress, region }，用于区域因子与匹配
 * @param {string} [invoiceId] - 可选发票ID，写入每条 item 的 invoiceId
 * @returns {EmissionResult}
 */
function calculateBatch(invoiceItems, context = {}, invoiceId = null) {
  const items = Array.isArray(invoiceItems) ? invoiceItems : [];
  const resultItems = [];

  for (const item of items) {
    const matched = matchFactor(item, context);
    const calc = calculate(item, matched);
    resultItems.push({
      invoiceId: invoiceId != null ? String(invoiceId) : (item.invoiceId != null ? String(item.invoiceId) : undefined),
      scope: calc.scope,
      emissions: calc.value,
      method: calc.method,
      confidence: calc.confidence,
      factorUsed: calc.factorUsed,
      reason: calc.reason,
      itemName: calc.itemName,
    });
  }

  const result = new EmissionResult({
    items: resultItems,
    totalEmissions: 0,
    summary: { scope1: 0, scope2: 0, scope3: 0 },
  });
  result.recalcSummary();
  return result;
}

module.exports = {
  calculateBatch,
};
