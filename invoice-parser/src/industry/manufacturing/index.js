/**
 * 制造业插件模块入口
 */
const { matchMaterial, calculateProductUsage, calculateMaterialEmission } = require('./manufacturingPlugin');
const { getProductEnergy, getProductEnergyAsync } = require('./energylabelAdapter');

module.exports = {
  matchMaterial,
  calculateProductUsage,
  calculateMaterialEmission,
  getProductEnergy,
  getProductEnergyAsync,
};
