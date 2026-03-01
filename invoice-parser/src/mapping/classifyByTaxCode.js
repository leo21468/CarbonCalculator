/**
 * 税收分类编码 → 碳排放范围 分类函数
 *
 * 根据 reference table.xlsx 逻辑（本实现使用模拟映射表 scopeMappingTable.js）
 * 将 19 位税号 + 货物名称 映射到 GHG Protocol Scope 1/2/3，并处理例外规则
 *（如润滑油虽属石油加工类税号，但归入 Scope 3）。
 *
 * 【数据来源】模拟数据；生产环境需对接国家税务总局 API 或官方编码表。
 */

const { PREFIX_RULES, KEYWORD_SCOPE, DEFAULT_SCOPE, CONFIDENCE } = require('./scopeMappingTable');

/** 按前缀长度降序，保证最长匹配优先 */
const SORTED_RULES = [...PREFIX_RULES].sort((a, b) => (b.prefix.length - a.prefix.length));

/**
 * 分类结果
 * @typedef {Object} ClassificationResult
 * @property {1|2|3} scope - 排放范围
 * @property {'高'|'中'|'低'} confidence - 置信度
 * @property {string} reason - 分类依据说明
 */

/**
 * 根据 19 位税收分类编码与货物名称，判定碳排放范围（Scope 1/2/3）
 *
 * 映射逻辑：
 * 1) 优先按税号前缀匹配（长前缀优先），若命中规则且货物名称不包含该规则的排除关键词，则返回对应 Scope。
 * 2) 若货物名称包含排除关键词（如“润滑油”“沥青”等），则不论税号，归入 Scope 3（例外规则，GHG Protocol 下多为价值链间接排放）。
 * 3) 若税号未命中前缀规则，则尝试按货物名称关键词推断 Scope。
 * 4) 均未命中则归入 Scope 3，置信度低。
 *
 * @param {string} taxCode - 19 位税收分类编码（或有效前缀）
 * @param {string} [goodsName] - 货物或应税劳务名称，用于排除规则与关键词兜底
 * @returns {ClassificationResult}
 */
function classifyByTaxCode(taxCode, goodsName) {
  const code = (taxCode != null ? String(taxCode).trim() : '') || '';
  const name = (goodsName != null ? String(goodsName).trim() : '') || '';

  // 1) 先检查货物名称是否命中“排除关键词”（例外规则：润滑油等 → Scope 3）
  for (const rule of SORTED_RULES) {
    if (rule.excludeKeywords && rule.excludeKeywords.length) {
      for (const kw of rule.excludeKeywords) {
        if (name.includes(kw)) {
          return {
            scope: 3,
            confidence: CONFIDENCE.HIGH,
            reason: `货物名称含排除词「${kw}」，按例外规则归入 Scope 3（价值链间接排放）。依据：GHG Protocol 排除非燃料用途的石油制品。`,
          };
        }
      }
    }
  }

  // 2) 按税号前缀匹配（长前缀优先）
  for (const rule of SORTED_RULES) {
    if (code.startsWith(rule.prefix) || code === rule.prefix) {
      return {
        scope: rule.scope,
        confidence: rule.confidence || CONFIDENCE.MEDIUM,
        reason: `按 19 位税号前缀「${rule.prefix}」匹配：${rule.description}，归入 Scope ${rule.scope}。依据：GHG Protocol ${rule.scope === 1 ? '直接排放' : rule.scope === 2 ? '能源间接排放' : '价值链其他间接排放'}。`,
      };
    }
  }

  // 3) 税号未命中时，按货物名称关键词推断
  for (const { keywords, scope } of KEYWORD_SCOPE) {
    for (const kw of keywords) {
      if (name.includes(kw)) {
        return {
          scope,
          confidence: CONFIDENCE.MEDIUM,
          reason: `税号未命中映射表，按货物名称关键词「${kw}」推断归入 Scope ${scope}。生产环境建议对接国家税务总局 API 获取权威分类。`,
        };
      }
    }
  }

  // 4) 兜底：Scope 3，置信度低
  return {
    scope: DEFAULT_SCOPE,
    confidence: CONFIDENCE.LOW,
    reason: `税号与货物名称均未命中映射规则，默认归入 Scope 3（价值链其他间接排放）。数据来源为模拟；生产环境需对接国家税务总局 API。`,
  };
}

module.exports = { classifyByTaxCode, CONFIDENCE };
