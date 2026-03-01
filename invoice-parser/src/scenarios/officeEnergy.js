/**
 * 办公用电与用水核算统一入口
 *
 * - processElectricity(invoice, region)：提取用电量并计算排放
 * - processWater(invoice)：提取用水量并计算排放
 */

const { calculateElectricity } = require('./electricityCalculator');
const { calculateWater } = require('./waterCalculator');

/**
 * 处理电费发票：提取用电量 + 区域电力因子计算
 * @param {Object} invoice - 发票对象
 * @param {string} [region] - 区域（全国/华北/华东等）
 * @returns {{ success: boolean, emissionsKg?: number, usageKWh?: number, factor?: number, factorName?: string, source?: string, matchedFrom?: string, error?: string, suggestion?: string }}
 */
function processElectricity(invoice, region = '全国') {
  const result = calculateElectricity(invoice, region);
  if (result.error) {
    return { success: false, error: result.error, suggestion: result.suggestion };
  }
  return {
    success: true,
    emissionsKg: result.emissionsKg,
    usageKWh: result.usageKWh,
    factor: result.factor,
    factorName: result.factorName,
    source: result.source,
    matchedFrom: result.matchedFrom,
  };
}

/**
 * 处理水费发票：提取用水量 + 固定因子计算
 * @param {Object} invoice - 发票对象
 * @returns {{ success: boolean, emissionsKg?: number, usageTons?: number, factor?: number, source?: string, matchedFrom?: string, error?: string, suggestion?: string }}
 */
function processWater(invoice) {
  const result = calculateWater(invoice);
  if (result.error) {
    return { success: false, error: result.error, suggestion: result.suggestion };
  }
  return {
    success: true,
    emissionsKg: result.emissionsKg,
    usageTons: result.usageTons,
    factor: result.factor,
    source: result.source,
    matchedFrom: result.matchedFrom,
  };
}

module.exports = {
  processElectricity,
  processWater,
};
