/**
 * 废弃物处理专用核算
 *
 * 使用废弃物处理 EEIO 因子（模拟），生产环境建议使用地方或行业发布因子。
 */

/** 废弃物处理 EEIO 因子 kgCO2e/元（模拟） */
const WASTE_FACTOR = 0.45;

/**
 * 垃圾清运/废弃物处理排放计算
 * @param {number} amount - 金额（元）
 * @returns {{ emissionsKg: number, amount: number, factor: number }}
 */
function wasteCalculator(amount) {
  const a = Number(amount);
  const validA = !Number.isNaN(a) && a >= 0 ? a : 0;
  return {
    emissionsKg: Math.round(validA * WASTE_FACTOR * 100) / 100,
    amount: validA,
    factor: WASTE_FACTOR,
  };
}

/**
 * 从发票提取垃圾清运/废弃物相关金额
 * @param {Object} invoice
 * @returns {number} 金额，无法提取返回 0
 */
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
  WASTE_FACTOR,
};
