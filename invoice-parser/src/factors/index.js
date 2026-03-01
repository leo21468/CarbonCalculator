/**
 * 排放因子模块统一入口
 *
 * 数据来源：Emission factors.csv（CPCD，原 cpcd_full_*.csv）、data/emission_factors.csv 及内置默认。
 * 单位转换与追溯见 factorManager。
 */

const { getFactorByCategory, getFactorByName, getEEIOFactor } = require('./factorService');
const { toKgCO2e, withSourceTrace } = require('./factorManager');
const { initFactorDatabase, getFactorList } = require('./factorDatabase');
const { FACTOR_CATEGORY, FACTOR_TYPE, createFactor, parseFootprint } = require('./emissionFactors');

module.exports = {
  getFactorByCategory,
  getFactorByName,
  getEEIOFactor,
  toKgCO2e,
  withSourceTrace,
  initFactorDatabase,
  getFactorList,
  FACTOR_CATEGORY,
  FACTOR_TYPE,
  createFactor,
  parseFootprint,
};
