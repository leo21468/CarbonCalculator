/**
 * 通勤与交通：燃油按 CPCD 汽油/柴油「摇篮到大门」kgCO2e/公吨 × 升→吨；
 * 公交/出租按支出金额用 core 差旅「tCO2e/万元人民币」换算为 kgCO2e/元（见 data/cpcd_scene_factors.json）。
 */

const { getFactors } = require('./cpcdSceneFactors');

function _gasolineFactorPerLiter() {
  const g = getFactors().gasolineL;
  return (g.kg_co2e_per_tonne * g.assumed_liquid_kg_per_liter) / 1000;
}

function _dieselFactorPerLiter() {
  const d = getFactors().dieselL;
  return (d.kg_co2e_per_tonne * d.assumed_liquid_kg_per_liter) / 1000;
}

/**
 * 燃油排放计算（CPCD 摇篮到大门 + 升密度）
 */
function fuelCalculator(quantity, fuelType) {
  const q = Number(quantity);
  const validQ = !Number.isNaN(q) && q >= 0 ? q : 0;
  const type = (fuelType || '').trim();
  const factor = /柴油/i.test(type) ? _dieselFactorPerLiter() : _gasolineFactorPerLiter();
  const fuelName = /柴油/i.test(type) ? '柴油' : '汽油';
  return {
    emissionsKg: Math.round(validQ * factor * 100) / 100,
    quantity: validQ,
    factor,
    fuelType: fuelName,
  };
}

/**
 * 公共交通（公交卡/地铁充值等）：核心库无单独万元因子 → 采用「国内高铁差旅-基于支出金额核算」同口径。
 */
function publicTransportCalculator(amount, city) {
  const a = Number(amount);
  const validA = !Number.isNaN(a) && a >= 0 ? a : 0;
  const factor = getFactors().publicTransitKgPerCny;
  return {
    emissionsKg: Math.round(validA * factor * 100) / 100,
    amount: validA,
    factor,
  };
}

/**
 * 出租/网约车：默认「国内出租/网约车差旅-基于支出金额核算」；发票含 燃油/油车 时用燃油车条目，含 电动/电车 用电车条目。
 */
function taxiCalculator(amount, invoiceHint = '') {
  const a = Number(amount);
  const validA = !Number.isNaN(a) && a >= 0 ? a : 0;
  const F = getFactors();
  const h = (invoiceHint || '').toString();
  let factor = F.taxiKgPerCny;
  if (/电动|电车|新能源/i.test(h)) factor = F.taxiEvKgPerCny;
  else if (/燃油|汽油|柴油|油车/i.test(h)) factor = F.taxiFuelKgPerCny;
  return {
    emissionsKg: Math.round(validA * factor * 100) / 100,
    amount: validA,
    factor,
  };
}

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
    if (!Number.isNaN(amount) && amount > 0) return { type: 'taxi', amount, hint: combined };
  }
  return { type: null };
}

const FUEL_FACTOR_GASOLINE = _gasolineFactorPerLiter();
const FUEL_FACTOR_DIESEL = _dieselFactorPerLiter();
const PUBLIC_TRANSPORT_FACTOR = getFactors().publicTransitKgPerCny;
const TAXI_FACTOR = getFactors().taxiKgPerCny;

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
