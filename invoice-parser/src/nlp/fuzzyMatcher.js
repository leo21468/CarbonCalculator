/**
 * 关键词模糊匹配模块
 *
 * 将抽取到的关键词映射到标准分类（如 "办公桌" -> "木制家具"），
 * 使用 Levenshtein 距离计算相似度，超过阈值则返回最佳匹配。
 * 便于后续替换为 BERT 语义相似度或 LLM 分类。
 */

const natural = require('natural');

/** 默认相似度阈值 */
const DEFAULT_THRESHOLD = 0.8;

/**
 * 标准分类及可选别名（用于模糊匹配的候选集）
 * 格式：标准类名 -> 别名列表
 */
const STANDARD_CATEGORIES = Object.freeze({
  '能源-成品油': ['成品油', '汽油', '柴油', '燃料油'],
  '能源-煤炭': ['煤炭', '原煤', '洗煤', '型煤'],
  '能源-天然气': ['天然气', '煤气', '液化气'],
  '原材料-钢材': ['钢材', '钢板', '钢带'],
  '原材料-水泥': ['水泥'],
  '原材料-木材': ['木材', '木料'],
  '原材料-塑料': ['塑料'],
  '运输-物流': ['运费', '物流', '快递', '运输服务', '配送', '货运'],
  '办公-用品': ['办公用品', '纸张', '文具', '订书机', '复印纸', '文件夹', '笔'],
  '办公-设备': ['电脑', '打印机', '复印机', '扫描仪'],
  '办公-家具': ['办公桌', '办公椅', '文件柜', '木制家具'],
  '服务-维修': ['维修', '维修费', '检修'],
  '服务-咨询': ['咨询', '劳务', '技术服务', '设计', '检测'],
  '服务-租赁': ['租赁', '租用'],
});

/** 扁平候选列表：{ standard: string, alias: string } */
const FLAT_CANDIDATES = (() => {
  const list = [];
  for (const [standard, aliases] of Object.entries(STANDARD_CATEGORIES)) {
    list.push({ standard, alias: standard });
    for (const a of aliases) {
      list.push({ standard, alias: a });
    }
  }
  return list;
})();

/**
 * 使用 Levenshtein 距离计算相似度 (0~1)
 * similarity = 1 - distance / max(len(a), len(b))
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
function levenshteinSimilarity(a, b) {
  if (!a || !b) return 0;
  const d = natural.LevenshteinDistance(a, b);
  const maxLen = Math.max(a.length, b.length);
  return maxLen === 0 ? 1 : 1 - d / maxLen;
}

/**
 * 模糊匹配：在标准分类候选中找与 keyword 相似度最高的项
 * @param {string} keyword - 待匹配关键词
 * @param {number} [threshold=0.8] - 最低相似度阈值
 * @returns {{ matched: string, similarity: number } | null}
 */
function fuzzyMatch(keyword, threshold = DEFAULT_THRESHOLD) {
  const k = (keyword != null ? String(keyword).trim() : '') || '';
  if (!k) return null;

  let best = { standard: null, similarity: 0 };
  for (const { standard, alias } of FLAT_CANDIDATES) {
    const sim = levenshteinSimilarity(k, alias);
    if (sim > best.similarity) {
      best = { standard, similarity: sim };
    }
  }
  if (best.similarity >= threshold) {
    return { matched: best.standard, similarity: best.similarity };
  }
  return null;
}

/**
 * 对多个关键词分别模糊匹配
 * @param {string[]} keywords
 * @param {number} [threshold=0.8]
 * @returns {Array<{ keyword: string, matched: string, similarity: number } | { keyword: string, matched: null }>}
 */
function fuzzyMatchAll(keywords, threshold = DEFAULT_THRESHOLD) {
  const list = Array.isArray(keywords) ? keywords : [keywords];
  return list.map((kw) => {
    const k = typeof kw === 'string' ? kw : (kw && kw.keyword) ? kw.keyword : '';
    const result = fuzzyMatch(k, threshold);
    if (result) {
      return { keyword: k, matched: result.matched, similarity: result.similarity };
    }
    return { keyword: k, matched: null };
  });
}

module.exports = {
  fuzzyMatch,
  fuzzyMatchAll,
  levenshteinSimilarity,
  STANDARD_CATEGORIES,
  FLAT_CANDIDATES,
  DEFAULT_THRESHOLD,
};
