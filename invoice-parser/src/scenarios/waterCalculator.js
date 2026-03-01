/**
 * 办公用水专用核算：从发票提取用水量(吨/m³)并按固定因子计算排放
 *
 * 提取位置：数量栏、备注栏、规格型号栏
 * 正则：/(\d+\.?\d*)\s*(吨|m3|立方米)/i
 * 因子：0.168 kgCO2e/吨（自来水供应相关排放，可根据数据来源调整）
 */

/** 用水量匹配正则 */
const WATER_REGEX = /(\d+\.?\d*)\s*(吨|m3|立方米|方)/gi;

/** 固定因子：kgCO2e/吨（与立方米 1:1 换算） */
const WATER_FACTOR_KG_PER_TON = 0.168;

function normalizeToTons(value, unit) {
  const v = Number(value);
  if (Number.isNaN(v) || v < 0) return NaN;
  const u = (unit || '').toLowerCase().trim();
  if (/吨|t\b|tons/i.test(u)) return v;
  if (/m3|立方米|方/i.test(u)) return v;
  return v;
}

/**
 * 从发票中提取用水量（吨）
 * @param {Object} invoice - 发票对象，含 items[]，可选 remark、items[].remark、items[].spec
 * @returns {{ usageTons: number, source: string, matchedFrom: string } | { error: string, suggestion: string }}
 */
function extractWaterData(invoice) {
  const items = Array.isArray(invoice?.items) ? invoice.items : [];
  const invRemark = invoice?.remark != null ? String(invoice.remark) : (invoice?.remarks != null ? String(invoice.remarks) : '');

  // 1) 数量栏（仅当名称或备注暗示用水时，才将数量+单位吨/m³ 视为用水量，避免误判钢材等）
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    const q = it.quantity != null ? Number(it.quantity) : NaN;
    const unit = (it.unit || it.unitOfMeasure || '').toString().trim();
    const name = (it.name || it.goodsName || '').toString();
    if (!Number.isNaN(q) && q > 0 && /吨|m3|立方米|方/i.test(unit) && /水|用水|水费|自来水/i.test(name)) {
      const tons = normalizeToTons(q, unit);
      if (!Number.isNaN(tons)) {
        return { usageTons: tons, source: 'quantity', matchedFrom: `items[${i}].quantity+unit (${q} ${unit})` };
      }
    }
    if (!Number.isNaN(q) && q > 0 && /水|用水|水费/i.test(name) && (!unit || /吨|m3|立方米|方/i.test(unit))) {
      const tons = Number.isNaN(q) ? NaN : q;
      if (!Number.isNaN(tons)) {
        return { usageTons: tons, source: 'quantity', matchedFrom: `items[${i}].quantity (水费行，${q})` };
      }
    }
  }

  // 2) 备注、规格、名称：正则
  const texts = [invRemark];
  items.forEach((it, i) => {
    texts.push((it.name || it.goodsName || '').toString());
    texts.push((it.remark || it.remarks || '').toString());
    texts.push((it.spec || it.specification || it.model || it.规格型号 || '').toString());
  });
  const combined = texts.filter(Boolean).join(' ');
  let bestMatch = null;
  let match;
  WATER_REGEX.lastIndex = 0;
  while ((match = WATER_REGEX.exec(combined)) !== null) {
    const num = parseFloat(match[1]);
    if (!Number.isNaN(num) && num > 0 && (!bestMatch || num > bestMatch.usageTons)) {
      bestMatch = { usageTons: num, source: 'regex', matchedFrom: `正则匹配: ${match[0].trim()}` };
    }
  }
  if (bestMatch) return bestMatch;

  return {
    error: '无法从发票中提取用水量',
    suggestion: '请确认发票包含数量栏(数量+单位吨/m³)或备注/规格中含如"100吨"、"50立方米"等；若无法提供，可使用估算模式(按金额或历史用量估算)。',
  };
}

/**
 * 办公用水排放计算
 * @param {Object} invoice - 发票对象
 * @returns {{ emissionsKg: number, usageTons: number, factor: number, source: string, matchedFrom: string } | { error: string, suggestion: string }}
 */
function calculateWater(invoice) {
  const extracted = extractWaterData(invoice);
  if (extracted.error) return extracted;

  const usageTons = extracted.usageTons;
  const emissionsKg = usageTons * WATER_FACTOR_KG_PER_TON;

  return {
    emissionsKg: Math.max(0, Math.round(emissionsKg * 100) / 100),
    usageTons,
    factor: WATER_FACTOR_KG_PER_TON,
    source: extracted.source,
    matchedFrom: extracted.matchedFrom,
  };
}

module.exports = {
  extractWaterData,
  calculateWater,
  WATER_REGEX,
  WATER_FACTOR_KG_PER_TON,
};
