/**
 * 废弃物处理：按发票金额 × CPCD 近似因子（核心库无环卫「元」专用行时，
 * 采用「市政基础设施」kgCO2e/万元人民币 → kgCO2e/元，见 cpcd_scene_factors.json）。
 */

const { getFactors } = require('./cpcdSceneFactors');

function wasteFactorKgPerCny() {
  return getFactors().wasteKgPerCny;
}

function wasteCalculator(amount) {
  const a = Number(amount);
  const validA = !Number.isNaN(a) && a >= 0 ? a : 0;
  const factor = wasteFactorKgPerCny();
  return {
    emissionsKg: Math.round(validA * factor * 100) / 100,
    amount: validA,
    factor,
  };
}

function extractWasteAmount(invoice) {
  const items = Array.isArray(invoice?.items) ? invoice.items : [];
  const totalAmount = invoice?.totalAmount != null ? Number(invoice.totalAmount) : NaN;
  const texts = items.map((it) => (it.name || it.goodsName || '').toString()).join(' ');
  const remark = (invoice?.remark || invoice?.remarks || '').toString();
  const combined = texts + ' ' + remark;
  if (!/垃圾|清运|废弃物|环卫|固废|处置费/i.test(combined)) return 0;
  if (!Number.isNaN(totalAmount) && totalAmount > 0) return totalAmount;
  for (const it of items) {
    const amt = it.amount != null ? Number(it.amount) : NaN;
    if (!Number.isNaN(amt) && amt > 0) return amt;
  }
  return 0;
}

module.exports = {
  wasteCalculator,
  extractWasteAmount,
  wasteFactorKgPerCny,
  get WASTE_FACTOR() {
    return wasteFactorKgPerCny();
  },
};
