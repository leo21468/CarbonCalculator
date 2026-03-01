/**
 * 制造业专用插件：统一导出物料 BOM 匹配与产品能效计算接口
 *
 * - 物料匹配：matchMaterial / calculateMaterialEmission（采购原材料/零部件）
 * - 产品使用：calculateProductUsage（售出产品使用阶段，Scope 3 Cat.11）
 *
 * LCA 数据来源与局限性见各子模块注释；生产环境建议对接能效标识网与企业 BOM/PCF。
 */

const { matchMaterial } = require('./materialMatcher');
const { calculateProductUsage } = require('./productUsageCalculator');
const { toKgCO2e } = require('../../factors/factorManager');
const { convertQuantityToFactorUnit } = require('../../calculation/unitUtils');

/**
 * 物料排放计算：匹配物料因子后按数量×因子计算（用于采购物料/BOM）
 * @param {string} goodsName - 货物名称
 * @param {number} quantity - 数量
 * @param {string} [unit] - 单位
 * @returns {{ emissions: number, unit: string, factor: Object|null, confidence: string, reason: string }}
 */
function calculateMaterialEmission(goodsName, quantity, unit) {
  const matched = matchMaterial(goodsName, quantity, unit);
  if (!matched.factor) {
    return {
      emissions: 0,
      unit: 'kgCO2e',
      factor: null,
      confidence: matched.confidence,
      reason: matched.reason,
    };
  }
  const q = quantity != null ? Number(quantity) : 0;
  const { quantity: normalizedQ } = convertQuantityToFactorUnit(q, unit, matched.factor.unit);
  const { emissionKg } = toKgCO2e(matched.factor, normalizedQ);
  return {
    emissions: Math.max(0, emissionKg),
    unit: 'kgCO2e',
    factor: matched.factor,
    confidence: matched.confidence,
    reason: matched.reason,
  };
}

module.exports = {
  matchMaterial,
  calculateProductUsage,
  calculateMaterialEmission,
};
