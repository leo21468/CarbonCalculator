/**
 * 排放因子数据结构定义
 *
 * 数据来源：基于 CPCD / Emission factors.csv（原 cpcd_full_*.csv）及
 * data/emission_factors.csv 的因子表。单位统一转换逻辑见 factorManager.js。
 */

/** 因子类别 */
const FACTOR_CATEGORY = Object.freeze({
  ELECTRICITY: '电力',
  WATER: '用水',
  FUEL: '燃料燃烧',
  MATERIAL: '材料',
  TRANSPORT: '运输',
  WASTE: '废弃物',
  EEIO: 'EEIO',
});

/** 因子类型 */
const FACTOR_TYPE = Object.freeze({
  PHYSICAL: '物理因子',
  EEIO: 'EEIO因子',
});

/**
 * 单条排放因子数据结构
 * @typedef {Object} EmissionFactor
 * @property {string} id - 唯一标识
 * @property {string} name - 因子名称
 * @property {string} category - 类别(电力/燃料/材料/运输/废弃物等)
 * @property {string} [subCategory] - 子类别
 * @property {number} value - 数值（换算后为 kgCO2e  per unit，见 factorManager）
 * @property {string} unit - 单位(如 kgCO2e/kWh、kgCO2e/t)
 * @property {string} [region] - 区域(全国/华北/华东等)
 * @property {string} [source] - 数据来源
 * @property {number|string} [year] - 数据年份
 * @property {string} [factorType] - 物理因子 | EEIO因子
 */

/**
 * 从 CPCD 风格 CSV 行解析碳足迹字符串（如 "0.8952tCO2e / 兆瓦时"）为数值与单位
 * @param {string} footprintStr
 * @returns {{ value: number, rawUnit: string } | null}
 */
function parseFootprint(footprintStr) {
  if (!footprintStr || typeof footprintStr !== 'string') return null;
  const s = footprintStr.trim();
  const match = s.match(/^([\d.]+)\s*(tCO2e|kgCO2e|gCO2e)\s*\/\s*(.+)$/i);
  if (!match) return null;
  let value = parseFloat(match[1]);
  if (Number.isNaN(value)) return null;
  const massUnit = (match[2] || '').toLowerCase();
  if (massUnit === 'tco2e') value *= 1000;
  else if (massUnit === 'gco2e') value /= 1000;
  return { value, rawUnit: (match[3] || '').trim() };
}

/**
 * 构建标准因子对象
 * @param {Object} raw
 * @returns {EmissionFactor}
 */
function createFactor(raw) {
  return {
    id: raw.id || raw.产品ID || '',
    name: raw.name || raw.产品名称 || raw.name || '',
    category: raw.category || '',
    subCategory: raw.subCategory,
    value: typeof raw.value === 'number' ? raw.value : parseFloat(raw.value) || 0,
    unit: raw.unit || 'kgCO2e/unit',
    region: raw.region,
    source: raw.source || raw.数据类型,
    year: raw.year ?? raw.数据年份,
    factorType: raw.factorType || FACTOR_TYPE.PHYSICAL,
  };
}

module.exports = {
  FACTOR_CATEGORY,
  FACTOR_TYPE,
  parseFootprint,
  createFactor,
};
