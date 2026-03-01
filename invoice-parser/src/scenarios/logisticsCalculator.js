/**
 * 物流运输专用核算：按运输方式使用不同 EEIO 因子
 *
 * 因子为模拟值，生产环境建议使用行业或企业认可的物流碳足迹因子。
 */

/** 公路运输 EEIO 因子 kgCO2e/元 */
const FACTOR_ROAD = 0.28;
/** 铁路运输 EEIO 因子 kgCO2e/元 */
const FACTOR_RAIL = 0.09;
/** 航空运输 EEIO 因子 kgCO2e/元 */
const FACTOR_AIR = 0.85;
/** 默认（未识别时）使用公路 */
const FACTOR_DEFAULT = FACTOR_ROAD;

/** 运输方式关键词 */
const MODE_KEYWORDS = [
  { keywords: ['航空', '空运', '航班', '飞机', '货运航空'], mode: 'air' },
  { keywords: ['铁路', '火车', '高铁', '动车', '货运专列'], mode: 'rail' },
  { keywords: ['公路', '汽运', '货车', '卡车', '物流', '快递', '配送', '运输'], mode: 'road' },
];

/**
 * 根据关键词识别运输方式
 * @param {string} text - 货物名称/备注等
 * @returns {'road'|'rail'|'air'}
 */
function detectTransportMode(text) {
  const t = (text || '').trim();
  for (const { keywords, mode } of MODE_KEYWORDS) {
    if (keywords.some((kw) => t.includes(kw))) return mode;
  }
  return 'road';
}

/**
 * 物流运输排放计算
 * @param {number} amount - 金额（元）
 * @param {string} [transportMode] - "road" | "rail" | "air"，不传则按 amount 无法区分时用 road
 * @returns {{ emissionsKg: number, amount: number, factor: number, transportMode: string }}
 */
function logisticsCalculator(amount, transportMode) {
  const a = Number(amount);
  const validA = !Number.isNaN(a) && a >= 0 ? a : 0;
  const mode = (transportMode || 'road').toLowerCase();
  let factor = FACTOR_ROAD;
  if (mode === 'air') factor = FACTOR_AIR;
  else if (mode === 'rail') factor = FACTOR_RAIL;
  else factor = FACTOR_ROAD;
  return {
    emissionsKg: Math.round(validA * factor * 100) / 100,
    amount: validA,
    factor,
    transportMode: mode,
  };
}

/**
 * 从发票提取金额并识别运输方式
 * @param {Object} invoice
 * @returns {{ amount: number, transportMode: string }}
 */
function extractLogisticsData(invoice) {
  const items = Array.isArray(invoice?.items) ? invoice.items : [];
  const totalAmount = invoice?.totalAmount != null ? Number(invoice.totalAmount) : NaN;
  const texts = items.map((it) => (it.name || it.goodsName || '').toString()).join(' ');
  const remark = (invoice?.remark || invoice?.remarks || '').toString();
  const combined = texts + ' ' + remark;
  const mode = detectTransportMode(combined);
  const amount = !Number.isNaN(totalAmount) && totalAmount > 0 ? totalAmount : (items[0]?.amount != null ? Number(items[0].amount) : 0);
  return { amount: amount > 0 ? amount : 0, transportMode: mode };
}

module.exports = {
  logisticsCalculator,
  detectTransportMode,
  extractLogisticsData,
  FACTOR_ROAD,
  FACTOR_RAIL,
  FACTOR_AIR,
  FACTOR_DEFAULT,
  MODE_KEYWORDS,
};
