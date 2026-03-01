/**
 * 数据来源与依据记录
 *
 * 记录因子来源（物理/EEIO）、分类依据（税号规则、NLP 版本、关键词规则）
 */

/**
 * 物理因子来源描述
 * @param {Object} factor - 因子对象 { id, name, category, source, year, unit }
 * @returns {{ type: string, source: string, reference: string }}
 */
function getFactorProvenance(factor) {
  if (!factor) return { type: '因子来源', source: '未知', reference: '' };
  const src = factor.source || '内置/未知';
  const year = factor.year ? `（${factor.year}）` : '';
  const ref = factor.id ? `因子ID: ${factor.id}` : '';
  if (factor.category === '电力' || factor.category === '燃料燃烧' || factor.category === '材料') {
    return {
      type: '物理因子',
      source: `${factor.name || factor.id}，${src}${year}`,
      reference: ref || 'Emission factors.csv / factorDatabase',
    };
  }
  if (factor.category === 'EEIO') {
    return {
      type: 'EEIO因子',
      source: `${factor.name || factor.id}，行业/投入产出${year}`,
      reference: ref || '投入产出表/EEIO默认',
    };
  }
  return { type: '因子来源', source: src, reference: ref };
}

/**
 * 分类依据（税收编码规则）
 * @param {Object} classification - { scope, reason }
 * @returns {{ type: string, source: string, reference: string }}
 */
function getClassificationProvenance(classification) {
  if (!classification) return { type: '规则来源', source: '未知', reference: '' };
  return {
    type: '税收编码规则',
    source: classification.reason || `Scope ${classification.scope}`,
    reference: 'scopeMappingTable.js / 国家税务总局税收分类编码',
  };
}

/**
 * NLP 模型与关键词规则来源
 */
function getNLPProvenance() {
  return {
    type: 'NLP/关键词',
    source: 'processGoodsName 关键词抽取 + 可选 BERT 分类',
    reference: 'keywordExtractor.js / hybridClassifier (Xenova/paraphrase-multilingual-MiniLM-L12-v2)',
  };
}

/**
 * 匹配规则来源（factorMatcher）
 * @param {string} matchType - 物理因子/EEIO因子/默认因子
 */
function getMatchRuleProvenance(matchType) {
  return {
    type: '匹配规则',
    source: `factorMatcher 优先级：物理量+物料 → 税号 → 关键词 → 默认；匹配类型: ${matchType}`,
    reference: 'factorMatcher.js',
  };
}

/**
 * 从核算结果项汇总数据来源（去重）
 * @param {Array<{ factorUsed?: Object, reason?: string }>} items
 * @param {Object} [classification]
 * @returns {Array<{ type: string, source: string, reference: string }>}
 */
function collectDataSources(items, classification) {
  const seen = new Set();
  const out = [];
  const add = (ds) => {
    const key = `${ds.type}:${ds.source}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(ds);
  };
  if (classification) add(getClassificationProvenance(classification));
  add(getNLPProvenance());
  if (Array.isArray(items)) {
    items.forEach((it) => {
      if (it.factorUsed) add(getFactorProvenance(it.factorUsed));
      if (it.reason) add(getMatchRuleProvenance(it.method || 'expenditure'));
    });
  }
  return out;
}

module.exports = {
  getFactorProvenance,
  getClassificationProvenance,
  getNLPProvenance,
  getMatchRuleProvenance,
  collectDataSources,
};
