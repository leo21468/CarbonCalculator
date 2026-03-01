/**
 * 动态因子匹配引擎：根据发票条目与上下文自动选择最合适的排放因子
 *
 * 匹配优先级：
 * 1) 有物理量 + 明确物料 → LCA 物理因子
 * 2) 有税收编码 → 行业/区域 EEIO 或电力因子
 * 3) 仅有金额 + 关键词 → 最相似行业 EEIO
 * 4) 降级 → 默认因子，低置信度
 */

const { getFactorByCategory, getFactorByName, getEEIOFactor } = require('../factors/factorService');
const { FACTOR_CATEGORY } = require('../factors/emissionFactors');
const { getRegionFromContext } = require('./regionMapper');
const { scoreConfidence } = require('./confidenceScorer');

/** 物料关键词 → 物理因子名称或类别（用于优先1） */
const MATERIAL_TO_PHYSICAL = [
  { keywords: ['冷轧', '热轧', '钢板', '钢材', '钢带', '钢铁'], factorName: '钢材', category: FACTOR_CATEGORY.MATERIAL, unitMatch: ['吨', 't', 'tons'] },
  { keywords: ['水泥'], factorName: '水泥', category: FACTOR_CATEGORY.MATERIAL, unitMatch: ['吨', 't'] },
  { keywords: ['电', '电力', '电费'], factorName: '电力', category: FACTOR_CATEGORY.ELECTRICITY, unitMatch: ['kWh', '度', '千瓦时'] },
  { keywords: ['汽油', '柴油', '成品油', '燃料油'], factorName: '汽油', category: FACTOR_CATEGORY.FUEL, unitMatch: ['升', 'L', '吨', 't'] },
  { keywords: ['煤', '原煤', '洗煤'], factorName: '原煤', category: FACTOR_CATEGORY.FUEL, unitMatch: ['吨', 't'] },
  { keywords: ['天然气', '燃气', '煤气'], factorName: '天然气', category: FACTOR_CATEGORY.FUEL, unitMatch: ['m3', '立方米', '方'] },
];

/** 名称关键词 → EEIO 行业（用于优先3） */
const NAME_TO_EEIO_INDUSTRY = [
  { keywords: ['造纸', '纸制品', '纸浆'], industry: '造纸业' },
  { keywords: ['钢铁', '钢材', '钢板', '冶金'], industry: '钢铁业' },
  { keywords: ['水泥', '建材', '混凝土'], industry: '水泥业' },
  { keywords: ['办公', '文具', '用品', '耗材'], industry: '制造业' },
  { keywords: ['运输', '物流', '快递', '运费'], industry: '制造业' },
  { keywords: ['服务', '咨询', '劳务', '维修'], industry: '制造业' },
];

/**
 * 判断是否有有效物理量（数量+单位）
 * @param {Object} item
 * @returns {boolean}
 */
function hasPhysicalQuantity(item) {
  const q = item.quantity;
  const u = item.unit;
  if (q == null || q === '' || Number.isNaN(Number(q))) return false;
  if (Number(q) <= 0) return false;
  return !!(u && String(u).trim());
}

/**
 * 根据名称匹配物理因子（优先1）
 * @param {string} name
 * @param {string} [unit]
 * @param {string} [region]
 * @returns {{ factor: object, matchType: string, reason: string } | null}
 */
function tryMatchPhysical(name, unit, region) {
  const n = (name || '').trim();
  const u = (unit || '').trim().toLowerCase();
  for (const { keywords, factorName, category, unitMatch } of MATERIAL_TO_PHYSICAL) {
    if (!keywords.some((kw) => n.includes(kw))) continue;
    const unitOk = !unitMatch || unitMatch.some((um) => u.includes(um.toLowerCase()));
    if (!unitOk && unitMatch && unitMatch.length) continue;
    let factor;
    if (category === FACTOR_CATEGORY.ELECTRICITY) {
      factor = getFactorByCategory(FACTOR_CATEGORY.ELECTRICITY, region || '全国');
    } else {
      factor = getFactorByName(factorName) || getFactorByCategory(category, '全国');
    }
    if (factor) {
      return {
        factor,
        matchType: '物理因子',
        reason: `有物理量且货物名称含「${keywords[0]}」等，匹配${factor.name}`,
      };
    }
  }
  return null;
}

/**
 * 根据税收编码推断行业或电力并匹配因子（优先2）
 * @param {string} taxCode
 * @param {string} [region]
 * @returns {{ factor: object, matchType: string, reason: string } | null}
 */
function tryMatchByTaxCode(taxCode, region) {
  const code = (taxCode || '').trim();
  if (!code) return null;
  const prefix = code.substring(0, 1);
  if (['1', '2', '3', '4'].includes(prefix) || code.startsWith('10') || code.startsWith('107') || code.startsWith('108')) {
    const fuel = getFactorByCategory(FACTOR_CATEGORY.FUEL, '全国');
    if (fuel) return { factor: fuel, matchType: '物理因子', reason: `税收编码${code}属燃料类，匹配${fuel.name}` };
  }
  if (['5'].includes(prefix) || code.startsWith('109') || code.startsWith('110')) {
    const elec = getFactorByCategory(FACTOR_CATEGORY.ELECTRICITY, region || '全国');
    if (elec) return { factor: elec, matchType: '物理因子', reason: `税收编码${code}属电力/热力，匹配区域因子${elec.name}` };
  }
  const eeio = getEEIOFactor(null);
  return { factor: eeio, matchType: 'EEIO因子', reason: `税收编码${code}对应行业EEIO，匹配${eeio.name}` };
}

/**
 * 仅金额 + 关键词匹配行业 EEIO（优先3）
 * @param {string} name
 * @returns {{ factor: object, matchType: string, reason: string, isFuzzy: boolean } | null}
 */
function tryMatchEEIOByKeyword(name) {
  const n = (name || '').trim();
  if (!n) return null;
  for (const { keywords, industry } of NAME_TO_EEIO_INDUSTRY) {
    if (keywords.some((kw) => n.includes(kw))) {
      const factor = getEEIOFactor(industry);
      if (factor) {
        return {
          factor,
          matchType: 'EEIO因子',
          reason: `货物名称含「${keywords[0]}」等，匹配行业EEIO ${factor.name}`,
          isFuzzy: false,
        };
      }
    }
  }
  return null;
}

/**
 * 匹配发票条目的排放因子
 * @param {Object} invoiceItem - 发票明细：{ name, taxCode, amount, quantity, unit, price }
 * @param {Object} [context] - { sellerAddress, buyerAddress, region }
 * @returns {{ factor: object, matchType: string, confidence: string, reason: string }}
 */
function matchFactor(invoiceItem, context = {}) {
  const name = invoiceItem.name || invoiceItem.goodsName || '';
  const taxCode = invoiceItem.taxCode || invoiceItem.tax_classification_code;
  const amount = invoiceItem.amount != null ? Number(invoiceItem.amount) : NaN;
  const quantity = invoiceItem.quantity != null ? Number(invoiceItem.quantity) : NaN;
  const unit = invoiceItem.unit || '';
  const region = getRegionFromContext(context);

  const hasPhysical = hasPhysicalQuantity({ quantity, unit });
  let result = null;
  let matchType = '默认因子';
  let reason = '无匹配，使用默认因子';
  let isFuzzy = true;

  // 优先1：有物理量 + 明确物料 → 物理因子
  if (hasPhysical) {
    result = tryMatchPhysical(name, unit, region);
    if (result) {
      matchType = result.matchType;
      reason = result.reason;
      isFuzzy = false;
    }
  }

  // 优先2：有税收编码 → 行业/区域因子
  if (!result && taxCode) {
    const byCode = tryMatchByTaxCode(taxCode, region);
    if (byCode) {
      result = byCode;
      matchType = result.matchType;
      reason = result.reason;
      isFuzzy = false;
    }
  }

  // 优先3：仅有金额 + 关键词 → EEIO
  if (!result && !Number.isNaN(amount) && amount > 0) {
    const byKeyword = tryMatchEEIOByKeyword(name);
    if (byKeyword) {
      result = byKeyword;
      matchType = result.matchType;
      reason = result.reason;
      isFuzzy = !!byKeyword.isFuzzy;
    }
  }

  // 降级：默认因子
  if (!result) {
    const defaultFactor = getEEIOFactor('默认');
    result = { factor: defaultFactor, matchType: '默认因子', reason: '无明确物料/编码/关键词，使用行业平均默认因子' };
    matchType = '默认因子';
    reason = result.reason;
  }

  const hasMaterial = !!(
    MATERIAL_TO_PHYSICAL.some((m) => m.keywords.some((kw) => (name || '').includes(kw))) ||
    NAME_TO_EEIO_INDUSTRY.some((m) => m.keywords.some((kw) => (name || '').includes(kw)))
  );
  const confidence = scoreConfidence({
    hasPhysical,
    hasMaterial,
    hasTaxCode: !!(taxCode && String(taxCode).trim()),
    matchType,
    isFuzzy,
  });

  return {
    factor: result.factor,
    matchType,
    confidence,
    reason,
  };
}

module.exports = {
  matchFactor,
  tryMatchPhysical,
  tryMatchByTaxCode,
  tryMatchEEIOByKeyword,
  hasPhysicalQuantity,
  MATERIAL_TO_PHYSICAL,
  NAME_TO_EEIO_INDUSTRY,
};
