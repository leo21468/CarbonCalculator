/**
 * 场景化核算模块入口（办公用电、用水、差旅、通勤、物流、废弃物等）
 */
const { processElectricity, processWater } = require('./officeEnergy');
const { extractCity, extractExplicitNights, estimateNights, calculateHotelEmission } = require('./hotelCalculator');
const { extractTransportData, fuelCalculator, publicTransportCalculator, taxiCalculator } = require('./transportCalculator');
const { extractLogisticsData, logisticsCalculator } = require('./logisticsCalculator');
const { extractWasteAmount, wasteCalculator } = require('./wasteCalculator');

/**
 * 处理通勤/交通发票：自动识别燃油、公共交通、出租车并计算排放
 * @param {Object} invoice
 * @returns {{ success: boolean, emissionsKg?: number, type?: 'fuel'|'public'|'taxi', quantity?: number, amount?: number, factor?: number, fuelType?: string, error?: string }}
 */
function processTransport(invoice) {
  const data = extractTransportData(invoice);
  if (!data.type) {
    return { success: false, error: '无法识别为燃油/公共交通/出租车发票' };
  }
  if (data.type === 'fuel') {
    const r = fuelCalculator(data.quantity, data.fuelType);
    return { success: true, emissionsKg: r.emissionsKg, type: 'fuel', quantity: r.quantity, factor: r.factor, fuelType: r.fuelType };
  }
  if (data.type === 'public') {
    const city = extractCity(invoice);
    const r = publicTransportCalculator(data.amount, city);
    return { success: true, emissionsKg: r.emissionsKg, type: 'public', amount: r.amount, factor: r.factor };
  }
  if (data.type === 'taxi') {
    const r = taxiCalculator(data.amount);
    return { success: true, emissionsKg: r.emissionsKg, type: 'taxi', amount: r.amount, factor: r.factor };
  }
  return { success: false, error: '未识别的交通类型' };
}

/**
 * 处理物流/运费发票：按关键词识别运输方式并计算排放
 * @param {Object} invoice
 * @returns {{ success: boolean, emissionsKg?: number, amount?: number, factor?: number, transportMode?: string, error?: string }}
 */
function processLogistics(invoice) {
  const { amount, transportMode } = extractLogisticsData(invoice);
  if (amount <= 0) return { success: false, error: '无法从发票提取物流金额' };
  const r = logisticsCalculator(amount, transportMode);
  return { success: true, emissionsKg: r.emissionsKg, amount: r.amount, factor: r.factor, transportMode: r.transportMode };
}

/**
 * 处理垃圾清运/废弃物处理发票
 * @param {Object} invoice
 * @returns {{ success: boolean, emissionsKg?: number, amount?: number, factor?: number, error?: string }}
 */
function processWaste(invoice) {
  const amount = extractWasteAmount(invoice);
  if (amount <= 0) return { success: false, error: '无法从发票提取垃圾清运/废弃物相关金额' };
  const r = wasteCalculator(amount);
  return { success: true, emissionsKg: r.emissionsKg, amount: r.amount, factor: r.factor };
}

module.exports = {
  processElectricity,
  processWater,
  extractCity,
  extractExplicitNights,
  estimateNights,
  calculateHotelEmission,
  processTransport,
  processLogistics,
  processWaste,
};
