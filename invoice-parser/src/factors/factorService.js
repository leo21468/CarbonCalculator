/**
 * 排放因子查询接口
 *
 * - getFactorByCategory(category, region)：按类别与区域查询
 * - getFactorByName(name)：按名称模糊匹配
 * - getEEIOFactor(industry)：按行业取 EEIO 因子
 */

const { getFactorList } = require('./factorDatabase');
const { FACTOR_CATEGORY } = require('./emissionFactors');

/**
 * 按类别与区域查询因子（优先匹配 region，再回退到全国）
 * @param {string} category - 类别：电力/用水/燃料燃烧/材料/运输/废弃物/EEIO
 * @param {string} [region] - 区域：全国/华北/华东等
 * @returns {EmissionFactor|null}
 */
function getFactorByCategory(category, region) {
  const list = getFactorList();
  if (region) {
    const byRegion = list.find((f) => f.category === category && (f.region || '') === region);
    if (byRegion) return byRegion;
  }
  return list.find((f) => f.category === category && (f.region || '全国') === '全国') || null;
}

/**
 * 按名称查询因子（精确或包含匹配）
 * @param {string} name - 因子名称，如 "华北电网排放因子"、"汽油因子"
 * @returns {EmissionFactor|null}
 */
function getFactorByName(name) {
  const n = (name || '').trim();
  if (!n) return null;
  const list = getFactorList();
  const exact = list.find((f) => (f.name || '') === n || (f.id || '') === n);
  if (exact) return exact;
  return list.find((f) => (f.name || '').includes(n) || (f.id || '').includes(n)) || null;
}

/** 行业名称 → EEIO 因子 id 或 subCategory 映射 */
const INDUSTRY_EEIO_MAP = {
  造纸: 'eeio_paper',
  造纸业: 'eeio_paper',
  钢铁: 'eeio_steel',
  钢铁业: 'eeio_steel',
  水泥: 'eeio_cement',
  水泥业: 'eeio_cement',
  制造业: 'eeio_default',
  默认: 'eeio_default',
};

/**
 * 按行业获取 EEIO 因子
 * @param {string} industry - 行业名称，如 "造纸业"、"钢铁"
 * @returns {EmissionFactor|null}
 */
function getEEIOFactor(industry) {
  const key = (industry || '').trim();
  if (!key) return getFactorByCategory(FACTOR_CATEGORY.EEIO, '全国');
  const id = INDUSTRY_EEIO_MAP[key] || INDUSTRY_EEIO_MAP[Object.keys(INDUSTRY_EEIO_MAP).find((k) => key.includes(k))];
  if (id) {
    const list = getFactorList();
    const f = list.find((x) => x.id === id);
    if (f) return f;
  }
  return getFactorByCategory(FACTOR_CATEGORY.EEIO, '全国');
}

module.exports = {
  getFactorByCategory,
  getFactorByName,
  getEEIOFactor,
};
