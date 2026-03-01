/**
 * 动态因子匹配模块入口
 */
const { matchFactor } = require('./factorMatcher');
const { mapAddressToRegion, getRegionFromContext } = require('./regionMapper');
const { scoreConfidence, CONFIDENCE } = require('./confidenceScorer');

module.exports = {
  matchFactor,
  mapAddressToRegion,
  getRegionFromContext,
  scoreConfidence,
  CONFIDENCE,
};
