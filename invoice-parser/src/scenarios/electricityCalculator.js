/**
 * 办公用电专用核算：从发票提取用电量(kWh)并按区域电力因子计算排放
 *
 * 提取位置：数量栏、备注栏、规格型号栏（含明细 name/remark/spec）
 * 正则：/(\d+\.?\d*)\s*(kwh|度|千瓦时)/i
 */

const { getFactorByCategory } = require('../factors/factorService');
const { FACTOR_CATEGORY } = require('../factors/emissionFactors');

/** 用电量匹配正则：数字 + 可选空白 + 单位(kwh|度|千瓦时) */
const ELECTRICITY_REGEX = /(\d+\.?\d*)\s*(kwh|度|千瓦时)/gi;

/** 单位标准化为 kWh */
function normalizeToKWh(value, unit) {
  const v = Number(value);
  if (Number.isNaN(v) || v < 0) return NaN;
  const u = (unit || '').toLowerCase().trim();
  if (/度|千瓦时|kwh/.test(u)) return v;
  return v;
}

/**
 * 从发票中提取用电量（kWh）
 * 查找位置：数量栏、备注栏、规格型号栏（items[].quantity/unit/name/remark/spec，以及 invoice.remark）
 * @param {Object} invoice - 发票对象，含 items[]，可选 remark、items[].remark、items[].spec
 * @returns {{ usageKWh: number, source: string, matchedFrom: string } | { error: string, suggestion: string }}
 */
function extractElectricityData(invoice) {
  const items = Array.isArray(invoice?.items) ? invoice.items : [];
  const invRemark = invoice?.remark != null ? String(invoice.remark) : (invoice?.remarks != null ? String(invoice.remarks) : '');

  // 1) 数量栏：item.quantity + item.unit 为 度/kWh/千瓦时
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    const q = it.quantity != null ? Number(it.quantity) : NaN;
    const unit = (it.unit || it.unitOfMeasure || '').toString().trim();
    const name = (it.name || it.goodsName || '').toString();
    if (!Number.isNaN(q) && q > 0 && /度|千瓦时|kwh/i.test(unit)) {
      const kWh = normalizeToKWh(q, unit);
      if (!Number.isNaN(kWh)) {
        return { usageKWh: kWh, source: 'quantity', matchedFrom: `items[${i}].quantity+unit (${q} ${unit})` };
      }
    }
    if (!Number.isNaN(q) && q > 0 && /电|电力|电费/i.test(name) && (!unit || /度|kwh|千瓦时/i.test(unit))) {
      const kWh = Number.isNaN(q) ? NaN : q;
      if (!Number.isNaN(kWh)) {
        return { usageKWh: kWh, source: 'quantity', matchedFrom: `items[${i}].quantity (电费行，${q})` };
      }
    }
  }

  // 2) 备注栏、规格型号栏、名称栏：正则匹配
  const texts = [invRemark];
  items.forEach((it, i) => {
    texts.push((it.name || it.goodsName || '').toString());
    texts.push((it.remark || it.remarks || '').toString());
    texts.push((it.spec || it.specification || it.model || it.规格型号 || '').toString());
  });
  const combined = texts.filter(Boolean).join(' ');
  let bestMatch = null;
  let match;
  ELECTRICITY_REGEX.lastIndex = 0;
  while ((match = ELECTRICITY_REGEX.exec(combined)) !== null) {
    const num = parseFloat(match[1]);
    if (!Number.isNaN(num) && num > 0 && (!bestMatch || num > bestMatch.usageKWh)) {
      bestMatch = { usageKWh: num, source: 'regex', matchedFrom: `正则匹配: ${match[0].trim()}` };
    }
  }
  if (bestMatch) return bestMatch;

  return {
    error: '无法从发票中提取用电量',
    suggestion: '请确认发票包含数量栏(数量+单位度/kWh)或备注/规格型号中含如"5000kWh"、"10000度"等；若无法提供，可使用估算模式(按金额或历史用量估算)。',
  };
}

/**
 * 办公用电排放计算
 * @param {Object} invoice - 发票对象
 * @param {string} [region] - 区域（全国/华北/华东等），用于电力因子
 * @returns {{ emissionsKg: number, usageKWh: number, factor: number, factorName: string, source: string, matchedFrom: string } | { error: string, suggestion: string }}
 */
function calculateElectricity(invoice, region = '全国') {
  const extracted = extractElectricityData(invoice);
  if (extracted.error) return extracted;

  const factorObj = getFactorByCategory(FACTOR_CATEGORY.ELECTRICITY, (region || '全国').trim() || '全国');
  const factorValue = factorObj && typeof factorObj.value === 'number' ? factorObj.value : 0.5839;
  const factorName = factorObj ? factorObj.name : '全国电网平均(默认)';

  const usageKWh = extracted.usageKWh;
  const emissionsKg = usageKWh * factorValue;

  return {
    emissionsKg: Math.max(0, Math.round(emissionsKg * 100) / 100),
    usageKWh,
    factor: factorValue,
    factorName,
    source: extracted.source,
    matchedFrom: extracted.matchedFrom,
  };
}

module.exports = {
  extractElectricityData,
  calculateElectricity,
  ELECTRICITY_REGEX,
};
