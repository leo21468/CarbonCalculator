/**
 * 通勤与交通专用核算：燃油、公共交通、出租车/网约车
 *
 * 因子为模拟值，生产环境建议使用国家/行业发布因子或企业实测数据。
 */

/** 汽油因子 kgCO2e/升 */
const FUEL_FACTOR_GASOLINE = 2.98;
/** 柴油因子 kgCO2e/升 */
const FUEL_FACTOR_DIESEL = 3.16;
/** 公共交通 EEIO 因子 kgCO2e/元（模拟） */
const PUBLIC_TRANSPORT_FACTOR = 0.12;
/** 出租车/网约车 EEIO 因子 kgCO2e/元（模拟） */
const TAXI_FACTOR = 0.35;

/**
 * 燃油排放计算
 * @param {number} quantity - 升数
 * @param {string} fuelType - "汽油" | "柴油"
 * @returns {{ emissionsKg: number, quantity: number, factor: number, fuelType: string }}
 */
function fuelCalculator(quantity, fuelType) {
  const q = Number(quantity);
  const validQ = !Number.isNaN(q) && q >= 0 ? q : 0;
  const type = (fuelType || '').trim();
  const factor = /柴油/i.test(type) ? FUEL_FACTOR_DIESEL : FUEL_FACTOR_GASOLINE;
  const fuelName = /柴油/i.test(type) ? '柴油' : '汽油';
  return {
    emissionsKg: Math.round(validQ * factor * 100) / 100,
    quantity: validQ,
    factor,
    fuelType: fuelName,
  };
}

/**
 * 公共交通排放计算（公交卡/地铁充值等）
 * @param {number} amount - 金额（元）
 * @param {string} [city] - 城市（预留，当前因子未按城市区分）
 * @returns {{ emissionsKg: number, amount: number, factor: number }}
 */
function publicTransportCalculator(amount, city) {
  const a = Number(amount);
  const validA = !Number.isNaN(a) && a >= 0 ? a : 0;
  return {
    emissionsKg: Math.round(validA * PUBLIC_TRANSPORT_FACTOR * 100) / 100,
    amount: validA,
    factor: PUBLIC_TRANSPORT_FACTOR,
  };
}

/**
 * 出租车/网约车排放计算
 * @param {number} amount - 金额（元）
 * @returns {{ emissionsKg: number, amount: number, factor: number }}
 */
function taxiCalculator(amount) {
  const a = Number(amount);
  const validA = !Number.isNaN(a) && a >= 0 ? a : 0;
  return {
    emissionsKg: Math.round(validA * TAXI_FACTOR * 100) / 100,
    amount: validA,
    factor: TAXI_FACTOR,
  };
}

/**
 * 从发票推断交通类型并提取金额/数量
 * @param {Object} invoice
 * @returns {{ type: 'fuel'|'public'|'taxi'|null, quantity?: number, fuelType?: string, amount?: number }}
 */
function extractTransportData(invoice) {
  const items = Array.isArray(invoice?.items) ? invoice.items : [];
  const totalAmount = invoice?.totalAmount != null ? Number(invoice.totalAmount) : NaN;
  const texts = items.map((it) => (it.name || it.goodsName || '').toString()).join(' ');
  const remark = (invoice?.remark || invoice?.remarks || '').toString();
  const combined = texts + ' ' + remark;

  if (/汽油|柴油|加油|燃油|成品油/i.test(combined)) {
    for (const it of items) {
      const q = it.quantity != null ? Number(it.quantity) : NaN;
      const unit = (it.unit || '').toString();
      const name = (it.name || it.goodsName || '').toString();
      if (!Number.isNaN(q) && q > 0 && (/升|L/i.test(unit) || /汽油|柴油|油/i.test(name))) {
        const fuelType = /柴油/i.test(name) || /柴油/i.test(unit) ? '柴油' : '汽油';
        return { type: 'fuel', quantity: q, fuelType };
      }
    }
  }
  if (/公交|地铁|一卡通|交通卡|轨道交通|充值/i.test(combined)) {
    const amount = !Number.isNaN(totalAmount) && totalAmount > 0 ? totalAmount : (items[0]?.amount != null ? Number(items[0].amount) : NaN);
    if (!Number.isNaN(amount) && amount > 0) return { type: 'public', amount };
  }
  if (/出租车|网约车|滴滴|快车|专车|打车/i.test(combined)) {
    const amount = !Number.isNaN(totalAmount) && totalAmount > 0 ? totalAmount : (items[0]?.amount != null ? Number(items[0].amount) : NaN);
    if (!Number.isNaN(amount) && amount > 0) return { type: 'taxi', amount };
  }
  return { type: null };
}

module.exports = {
  fuelCalculator,
  publicTransportCalculator,
  taxiCalculator,
  extractTransportData,
  FUEL_FACTOR_GASOLINE,
  FUEL_FACTOR_DIESEL,
  PUBLIC_TRANSPORT_FACTOR,
  TAXI_FACTOR,
};
