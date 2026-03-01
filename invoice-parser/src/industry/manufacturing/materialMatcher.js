/**
 * 制造业 BOM 物料匹配：根据货物名称关键词匹配物料排放因子
 *
 * 数据来源与局限性：
 * - 物料因子来自 LCA 文献及行业平均（见 factorDatabase），按“单位产品”或“单位质量”给出。
 * - 电机等按“台/个”的因子为估算值，实际应优先使用产品碳足迹（EPD/CPCD）或具体 BOM 重量×材料因子。
 * - 生产环境建议对接企业 BOM 主数据或 PCF 数据库，本模块仅作关键词兜底。
 */

const { getFactorByName, getFactorByCategory } = require('../../factors/factorService');
const { FACTOR_CATEGORY } = require('../../factors/emissionFactors');

/** 物料关键词 → 因子名称或类别；unitMatch 为可选单位（空则任意单位均可） */
const MATERIAL_KEYWORDS = [
  { keywords: ['微型电机', '微电机', '电机', '马达', '电动机'], factorName: '电机', unitMatch: ['个', '台', '件'], confidence: '高' },
  { keywords: ['钢材', '钢板', '钢带', '冷轧', '热轧', '钢铁'], factorName: '钢材', unitMatch: ['吨', 't', 'kg', '千克'], confidence: '高' },
  { keywords: ['水泥'], factorName: '水泥', unitMatch: ['吨', 't', 'kg'], confidence: '高' },
  { keywords: ['塑料', 'PVC', 'PE', 'PP', 'ABS'], factorName: '塑料', unitMatch: ['吨', 't', 'kg', '千克'], confidence: '中' },
  { keywords: ['铜', '铜材', '铜线', '铜丝'], factorName: '铜', unitMatch: ['吨', 't', 'kg', '千克'], confidence: '中' },
  { keywords: ['铝', '铝材', '铝合金'], factorName: '铝', unitMatch: ['吨', 't', 'kg', '千克'], confidence: '中' },
  { keywords: ['电缆', '电线', '线缆'], factorName: '电缆', unitMatch: ['米', 'm', '千米', 'km'], confidence: '中' },
];

/** 因子名称 → 在 factorService 中的查询名（getFactorByName）；部分需用 category 回退 */
const FACTOR_QUERY = {
  电机: '电机',
  钢材: '钢材',
  水泥: '水泥',
  塑料: '塑料',
  铜: '铜',
  铝: '铝',
  电缆: '电缆',
};

/**
 * 获取物料因子（若 factorDatabase 无则返回 null，由调用方降级）
 */
function getMaterialFactor(factorName) {
  const q = FACTOR_QUERY[factorName] || factorName;
  let f = getFactorByName(q);
  if (f) return f;
  if (factorName === '钢材') return getFactorByCategory(FACTOR_CATEGORY.MATERIAL, '全国');
  return null;
}

/**
 * 物料匹配：关键词匹配物料名称，返回匹配的物料因子和置信度
 * @param {string} goodsName - 货物/物料名称，如 "微型电机"、"冷轧钢板"
 * @param {number} [quantity] - 数量（可选，用于后续计算）
 * @param {string} [unit] - 单位（可选，与 unitMatch 一致时置信度更高）
 * @returns {{ factor: Object|null, confidence: '高'|'中'|'低', reason: string }}
 */
function matchMaterial(goodsName, quantity, unit) {
  const name = (goodsName || '').trim();
  const u = (unit || '').trim().toLowerCase();

  if (!name) {
    return { factor: null, confidence: '低', reason: '未提供物料名称' };
  }

  for (const { keywords, factorName, unitMatch, confidence } of MATERIAL_KEYWORDS) {
    if (!keywords.some((kw) => name.includes(kw))) continue;

    const factor = getMaterialFactor(factorName);
    if (!factor) {
      return { factor: null, confidence: '低', reason: `匹配到物料「${factorName}」但无对应排放因子，请扩展 factorDatabase` };
    }

    const unitOk = !unitMatch || unitMatch.length === 0 || unitMatch.some((um) => u.includes(um.toLowerCase()));
    const finalConfidence = unitOk ? confidence : '中';
    const reason = unitOk
      ? `关键词匹配「${keywords[0]}」等，使用因子：${factor.name}（${factor.unit}）`
      : `关键词匹配「${keywords[0]}」，单位「${unit}」与常用单位不完全一致，置信度降为「中」`;

    return {
      factor,
      confidence: finalConfidence,
      reason,
    };
  }

  return { factor: null, confidence: '低', reason: `未匹配到已知物料关键词：「${name}` };
}

module.exports = {
  matchMaterial,
  getMaterialFactor,
  MATERIAL_KEYWORDS,
};
