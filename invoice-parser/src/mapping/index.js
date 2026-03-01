/**
 * 税收分类编码 → 碳排放范围 映射模块入口
 * 导出 classifyByTaxCode(taxCode, goodsName) 及常量
 */

const { classifyByTaxCode, CONFIDENCE } = require('./classifyByTaxCode');
const { PREFIX_RULES, KEYWORD_SCOPE, DEFAULT_SCOPE } = require('./scopeMappingTable');

module.exports = {
  classifyByTaxCode,
  CONFIDENCE,
  PREFIX_RULES,
  KEYWORD_SCOPE,
  DEFAULT_SCOPE,
};
