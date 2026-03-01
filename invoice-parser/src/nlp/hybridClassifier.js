/**
 * 混合分类策略：税收编码 → BERT → 关键词
 *
 * 一级：若有税收分类编码且能映射到 10 类之一，直接采用；
 * 二级：否则调用 BERT 分类；
 * 三级：若 BERT 置信度 < 0.7，降级为关键词匹配。
 *
 * 生产环境可改为调用云端 LLM API，本实现使用本地 BERT 便于演示。
 */

const { extractKeywords } = require('./keywordExtractor');
const { fuzzyMatch } = require('./fuzzyMatcher');
const { classifyWithBERT } = require('./bertClassifier');
const { getCategoryName, NUM_CATEGORIES } = require('./categoryLabels');

/** BERT 置信度低于此值时降级为关键词 */
const BERT_CONFIDENCE_THRESHOLD = 0.7;

/**
 * 税收分类编码前缀 → 类别 ID（0-9）
 * 仅覆盖常见几类，其余走 BERT/关键词
 */
const TAX_CODE_TO_CATEGORY = Object.freeze({
  '101': 5, '102': 5, '103': 5, '104': 5, '105': 5, '106': 5, '107': 5, '108': 5,  // 能源 -> 燃料能源
  '109': 5, '110': 5,  // 电热 -> 燃料能源
  '5': 5,
  '1': 5, '2': 5, '3': 5, '4': 5,
  '6': 8,  // 农业 -> 食品饮料
  '7': 7,  // 机械设备等
  '8': 9,  // 租赁 -> 其他
  '9': 9,  // 服务 -> 其他
  '300': 9, '301': 9, '302': 9, '303': 9, '304': 9, '305': 9,
});

/**
 * 关键词匹配结果（标准类名）→ 类别 ID
 */
const KEYWORD_MATCH_TO_CATEGORY = Object.freeze({
  '办公-设备': 0,
  '办公-家具': 1,
  '办公-用品': 2,
  '运输-物流': 3,
  '服务-维修': 4,
  '能源-成品油': 5,
  '能源-煤炭': 5,
  '能源-天然气': 5,
  '原材料-钢材': 6,
  '原材料-水泥': 6,
  '原材料-木材': 6,
  '原材料-塑料': 6,
  '服务-咨询': 9,
  '服务-租赁': 9,
});

/**
 * 从税收编码解析前缀（最长匹配）
 * @param {string} taxCode
 * @returns {number | null} 类别 ID 或 null
 */
function categoryFromTaxCode(taxCode) {
  const code = (taxCode != null ? String(taxCode).trim() : '') || '';
  if (!code) return null;
  const prefixes = Object.keys(TAX_CODE_TO_CATEGORY).sort((a, b) => b.length - a.length);
  for (const p of prefixes) {
    if (code.startsWith(p) || code === p) {
      return TAX_CODE_TO_CATEGORY[p];
    }
  }
  return null;
}

/**
 * 关键词匹配得到类别 ID（基于 extractKeywords + fuzzyMatch，再映射到 0-9）
 * @param {string} text
 * @returns {{ category: number, source: 'keyword', confidence: number } | null}
 */
function categoryFromKeywords(text) {
  const { keywords } = extractKeywords(text);
  if (keywords.length === 0) return null;
  let bestCategory = null;
  let bestSim = 0;
  for (const k of keywords) {
    const kw = k.keyword || k;
    const m = fuzzyMatch(kw, 0.6);
    if (m && KEYWORD_MATCH_TO_CATEGORY[m.matched] !== undefined) {
      const c = KEYWORD_MATCH_TO_CATEGORY[m.matched];
      if (m.similarity > bestSim) {
        bestSim = m.similarity;
        bestCategory = c;
      }
    }
  }
  if (bestCategory != null) {
    return { category: bestCategory, source: 'keyword', confidence: bestSim };
  }
  return null;
}

/**
 * 混合分类
 * @param {string} text - 发票明细文本
 * @param {string} [taxCode] - 19 位税收分类编码（可选）
 * @param {Object} [options]
 * @param {number} [options.bertThreshold=0.7] - BERT 置信度低于此则降级关键词
 * @returns {Promise<{ category: number, categoryName: string, confidence: number, source: 'tax_code'|'bert'|'keyword' }>}
 */
async function classifyHybrid(text, taxCode, options = {}) {
  const threshold = options.bertThreshold != null ? options.bertThreshold : BERT_CONFIDENCE_THRESHOLD;

  // 一级：税收编码
  if (taxCode) {
    const c = categoryFromTaxCode(taxCode);
    if (c !== null) {
      return {
        category: c,
        categoryName: getCategoryName(c),
        confidence: 0.95,
        source: 'tax_code',
      };
    }
  }

  // 二级：BERT
  let bertResult;
  try {
    bertResult = await classifyWithBERT(text, options);
  } catch (e) {
    bertResult = { category: 9, categoryName: getCategoryName(9), confidence: 0 };
  }
  if (bertResult.confidence >= threshold) {
    return {
      category: bertResult.category,
      categoryName: bertResult.categoryName,
      confidence: bertResult.confidence,
      source: 'bert',
    };
  }

  // 三级：关键词
  const kwResult = categoryFromKeywords(text);
  if (kwResult) {
    return {
      category: kwResult.category,
      categoryName: getCategoryName(kwResult.category),
      confidence: kwResult.confidence,
      source: 'keyword',
    };
  }

  // 仍用 BERT 结果（或 BERT 失败时的关键词/BERT 低置信度结果）
  return {
    category: bertResult.category,
    categoryName: bertResult.categoryName,
    confidence: bertResult.confidence,
    source: 'bert',
  };
}

module.exports = {
  classifyHybrid,
  categoryFromTaxCode,
  categoryFromKeywords,
  BERT_CONFIDENCE_THRESHOLD,
  TAX_CODE_TO_CATEGORY,
  KEYWORD_MATCH_TO_CATEGORY,
};
