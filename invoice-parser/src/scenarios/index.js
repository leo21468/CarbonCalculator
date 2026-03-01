/**
 * 场景化核算模块入口（办公用电、用水等）
 */
const { processElectricity, processWater } = require('./officeEnergy');

module.exports = {
  processElectricity,
  processWater,
};
