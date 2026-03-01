/**
 * NLP 模块统一入口
 *
 * 提供 processGoodsName(goodsName)，对发票货物名称进行关键词抽取与模糊分类。
 * 模块化设计，便于后续集成 jieba 分词、BERT 或 LLM 模型。
 */

const { extractKeywords } = require('./keywordExtractor');
const { fuzzyMatchAll, DEFAULT_THRESHOLD } = require('./fuzzyMatcher');

/**
 * 处理货物名称：抽取关键词并做模糊匹配到标准分类
 * @param {string} goodsName - 发票货物或应税劳务名称
 * @param {Object} [options]
 * @param {number} [options.similarityThreshold=0.8] - 模糊匹配相似度阈值
 * @returns {{
 *   keywords: Array<{ keyword: string, category?: string, confidence: string }>,
 *   confidence: string,
 *   matches: Array<{ keyword: string, matched: string | null, similarity?: number }>,
 *   summary: string
 * }}
 */
function processGoodsName(goodsName, options = {}) {
  const threshold = options.similarityThreshold != null ? options.similarityThreshold : DEFAULT_THRESHOLD;
  const { keywords, confidence } = extractKeywords(goodsName);
  const matches = fuzzyMatchAll(keywords.map((k) => k.keyword), threshold);

  const matchedList = matches.filter((m) => m.matched != null);
  const summary =
    matchedList.length > 0
      ? matchedList.map((m) => `${m.keyword}→${m.matched}`).join('; ')
      : keywords.length > 0
        ? `仅抽取关键词: ${keywords.map((k) => k.keyword).join(', ')}`
        : '未识别到关键词';

  return {
    keywords,
    confidence,
    matches,
    summary,
  };
}

module.exports = {
  processGoodsName,
  extractKeywords: require('./keywordExtractor').extractKeywords,
  fuzzyMatch: require('./fuzzyMatcher').fuzzyMatch,
  fuzzyMatchAll: require('./fuzzyMatcher').fuzzyMatchAll,
  INDUSTRY_DICT: require('./keywordExtractor').INDUSTRY_DICT,
  STANDARD_CATEGORIES: require('./fuzzyMatcher').STANDARD_CATEGORIES,
};
