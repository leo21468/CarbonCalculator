/**
 * 发票货物名称 - 关键词抽取模块
 *
 * 功能：
 * 1) 识别星号标注内容（如 *成品油*）
 * 2) 基于行业词典的规则抽取
 * 3) 返回关键词数组及置信度
 *
 * 模块化设计：便于后续集成 jieba 中文分词（如 nodejieba）或 BERT/LLM 模型
 * 替代当前规则抽取；可在此处接入分词结果再走同一套词典/模糊匹配流程。
 */

/** 置信度枚举 */
const CONFIDENCE = Object.freeze({ HIGH: '高', MEDIUM: '中', LOW: '低' });

/**
 * 行业词典：类别 -> 关键词列表
 * 能源类、原材料类、运输类、办公类、服务类
 */
const INDUSTRY_DICT = Object.freeze({
  能源类: ['成品油', '汽油', '柴油', '煤炭', '天然气', '燃料油', '液化气', '煤气', '电力', '热力'],
  原材料类: ['钢材', '钢板', '水泥', '木材', '塑料', '铝材', '铜材', '橡胶', '玻璃', '涂料'],
  运输类: ['运费', '物流', '快递', '运输服务', '配送', '货运', '仓储'],
  办公类: ['办公用品', '纸张', '文具', '电脑', '打印机', '办公桌', '订书机', '复印纸', '文件夹', '笔'],
  服务类: ['咨询', '劳务', '维修', '租赁', '技术服务', '设计', '检测', '安装'],
});

/** 词典扁平列表：{ word, category }，用于顺序匹配 */
const FLAT_TERMS = (() => {
  const list = [];
  for (const [category, words] of Object.entries(INDUSTRY_DICT)) {
    for (const w of words) {
      list.push({ word: w, category });
    }
  }
  return list;
})();

/** 星号标注正则：*xxx*，支持中文与数字 */
const ASTERISK_REGEX = /\*([^*]+)\*/g;

/**
 * 从文本中抽取星号标注内容
 * @param {string} text
 * @returns {Array<{ keyword: string, confidence: string }>}
 */
function extractAsteriskKeywords(text) {
  if (!text || typeof text !== 'string') return [];
  const results = [];
  let m;
  const re = new RegExp(ASTERISK_REGEX.source, 'g');
  while ((m = re.exec(text)) !== null) {
    const keyword = m[1].trim();
    if (keyword) {
      results.push({ keyword, confidence: CONFIDENCE.HIGH });
    }
  }
  return results;
}

/**
 * 基于词典的规则抽取：在文本中查找词典词（长词优先）
 * @param {string} text
 * @returns {Array<{ keyword: string, category: string, confidence: string }>}
 */
function extractByDictionary(text) {
  if (!text || typeof text !== 'string') return [];
  const results = [];
  const sortedTerms = [...FLAT_TERMS].sort((a, b) => b.word.length - a.word.length);
  let remaining = text;
  for (const { word, category } of sortedTerms) {
    if (remaining.includes(word)) {
      results.push({ keyword: word, category, confidence: CONFIDENCE.MEDIUM });
      remaining = remaining.replace(word, '\u0000'); // 避免重复匹配
    }
  }
  return results;
}

/**
 * 抽取关键词：先星号标注，再词典匹配，去重合并
 * @param {string} text - 货物名称等文本
 * @returns {{ keywords: Array<{ keyword: string, category?: string, confidence: string }>, confidence: string }}
 */
function extractKeywords(text) {
  const normalized = (text != null ? String(text).trim() : '') || '';
  const asteriskResults = extractAsteriskKeywords(normalized);
  const dictResults = extractByDictionary(normalized);

  const seen = new Set();
  const keywords = [];
  for (const r of asteriskResults) {
    const k = r.keyword;
    if (!seen.has(k)) {
      seen.add(k);
      keywords.push({ keyword: k, confidence: r.confidence });
    }
  }
  for (const r of dictResults) {
    const k = r.keyword;
    if (!seen.has(k)) {
      seen.add(k);
      keywords.push({ keyword: k, category: r.category, confidence: r.confidence });
    }
  }

  const overallConfidence =
    keywords.length === 0 ? CONFIDENCE.LOW : asteriskResults.length > 0 ? CONFIDENCE.HIGH : CONFIDENCE.MEDIUM;

  return { keywords, confidence: overallConfidence };
}

module.exports = {
  extractKeywords,
  extractAsteriskKeywords,
  extractByDictionary,
  INDUSTRY_DICT,
  FLAT_TERMS,
  CONFIDENCE,
};
