/**
 * 核算模块入口
 */
const { calculateByActivity, calculateByExpenditure, isActivityFactor } = require('./calculator');
const { calculate, scopeFromFactor } = require('./calculationService');
const { calculateBatch } = require('./batchCalculator');

module.exports = {
  calculateByActivity,
  calculateByExpenditure,
  isActivityFactor,
  calculate,
  scopeFromFactor,
  calculateBatch,
};
