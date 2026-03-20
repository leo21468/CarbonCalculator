/**
 * 差旅住宿核算（国内）
 *
 * - **优先**：发票金额 × `data/core.csv` 快照「国内住宿差旅-基于支出金额核算」（2.036 tCO2e/万元 → kgCO2e/元），见 `cpcd_scene_factors.json`。
 * - **兜底**：无金额时，间夜数 ×「国内住宿差旅-基于消费数量核算」66.52 kgCO2e/晚。
 * - `estimateNights`（城市标准价反推间夜）仍可用于展示参考，不再用于默认排放计算（有金额时一律按支出）。
 */

const { getCityRate } = require('./cityRates');
const { getFactors } = require('./cpcdSceneFactors');

/** 城市关键词：销方名称/地址中出现的片段 → 标准城市名 */
const CITY_KEYWORDS = [
  { keywords: ['北京', '北京市'], city: '北京' },
  { keywords: ['上海', '上海市'], city: '上海' },
  { keywords: ['广州', '广州市'], city: '广州' },
  { keywords: ['深圳', '深圳市'], city: '深圳' },
  { keywords: ['杭州', '杭州市'], city: '杭州' },
  { keywords: ['南京', '南京市'], city: '南京' },
  { keywords: ['成都', '成都市'], city: '成都' },
  { keywords: ['武汉', '武汉市'], city: '武汉' },
  { keywords: ['西安', '西安市'], city: '西安' },
  { keywords: ['重庆', '重庆市'], city: '重庆' },
  { keywords: ['天津', '天津市'], city: '天津' },
  { keywords: ['苏州', '苏州市'], city: '苏州' },
  { keywords: ['宁波', '宁波市'], city: '宁波' },
  { keywords: ['青岛', '青岛市'], city: '青岛' },
  { keywords: ['厦门', '厦门市'], city: '厦门' },
  { keywords: ['长沙', '长沙市'], city: '长沙' },
  { keywords: ['郑州', '郑州市'], city: '郑州' },
  { keywords: ['济南', '济南市'], city: '济南' },
  { keywords: ['哈尔滨', '哈尔滨市'], city: '哈尔滨' },
  { keywords: ['沈阳', '沈阳市'], city: '沈阳' },
  { keywords: ['上海酒店', '上海宾馆', '上海旅馆'], city: '上海' },
  { keywords: ['北京酒店', '北京宾馆', '北京旅馆'], city: '北京' },
  { keywords: ['广州酒店', '广州宾馆'], city: '广州' },
  { keywords: ['深圳酒店', '深圳宾馆'], city: '深圳' },
  { keywords: ['杭州酒店', '杭州宾馆'], city: '杭州' },
  { keywords: ['南京酒店', '南京宾馆'], city: '南京' },
];

/** 间夜数显式匹配：备注/名称中的 "3晚"、"2间夜"、"住宿3晚" 等 */
const NIGHTS_REGEX = /(\d+)\s*[晚夜天]\s*[宿房]?|住宿[：:\s]*(\d+)\s*[晚夜天]?|(\d+)\s*间夜/gi;

/**
 * 从发票销方名称/地址提取城市
 * @param {Object} invoice - 含 sellerName、sellerAddress 或 seller 对象
 * @returns {string|null} 城市名，未识别返回 null
 */
function extractCity(invoice) {
  const sellerName = invoice?.sellerName || invoice?.seller?.name || '';
  const sellerAddr = invoice?.sellerAddress || invoice?.seller?.address || invoice?.sellerAddr || '';
  const text = [sellerName, sellerAddr].filter(Boolean).join(' ');

  for (const { keywords, city } of CITY_KEYWORDS) {
    if (keywords.some((kw) => text.includes(kw))) return city;
  }
  return null;
}

/**
 * 从发票备注/明细中提取明确间夜数
 * @param {Object} invoice
 * @returns {number|null} 间夜数，未找到返回 null
 */
function extractExplicitNights(invoice) {
  const remark = invoice?.remark || invoice?.remarks || '';
  const items = Array.isArray(invoice?.items) ? invoice.items : [];
  const texts = [remark];
  items.forEach((it) => {
    texts.push((it.name || it.goodsName || '').toString());
    texts.push((it.remark || it.remarks || '').toString());
    texts.push((it.spec || it.specification || '').toString());
  });
  const combined = texts.filter(Boolean).join(' ');
  let match;
  NIGHTS_REGEX.lastIndex = 0;
  while ((match = NIGHTS_REGEX.exec(combined)) !== null) {
    const n = parseInt(match[1] || match[2] || match[3], 10);
    if (!Number.isNaN(n) && n > 0) return n;
  }
  return null;
}

/**
 * 根据发票金额与城市标准价反推间夜数
 * 使用 "other" 级别标准作为平均单价，向下取整，至少 1 晚
 * @param {number} amount - 发票金额（元）
 * @param {string} city - 城市名
 * @returns {{ nights: number, priceUsed: number, method: "estimated" } | { error: string }}
 */
function estimateNights(amount, city) {
  const amt = Number(amount);
  if (Number.isNaN(amt) || amt <= 0) {
    return { error: '无效金额' };
  }
  const priceUsed = getCityRate(city);
  if (priceUsed == null || priceUsed <= 0) {
    return { error: `未配置城市「${city}」的差旅标准价，无法反推间夜数` };
  }
  const raw = amt / priceUsed;
  const nights = Math.max(1, Math.floor(raw));
  return { nights, priceUsed, method: 'estimated' };
}

/**
 * 计算住宿排放（国内，core 口径）
 * 有金额时优先按支出；否则使用明确间夜 × 66.52；再无则尝试用城市标准价从金额反推间夜（仅当金额>0 且无显式间夜时，仍按支出核算，不再用城市因子×晚数）。
 * @param {number} amount - 发票金额（元）
 * @param {string} [city] - 城市（可先通过 extractCity(invoice) 获取）
 * @param {number|null} [explicitNights] - 明确间夜数（可先通过 extractExplicitNights(invoice) 获取）
 * @param {Object} [invoice] - 可选，若传则自动 extractCity / extractExplicitNights / 补全金额
 * @returns {{ emissionsKg: number, nights: number|null, factor: number, city: string|null, method: string, priceUsed?: number, nightsIndicated?: number } | { error: string }}
 */
function calculateHotelEmission(amount, city, explicitNights, invoice) {
  let resolvedCity = (city || '').trim() || null;
  let resolvedNights = explicitNights != null ? Number(explicitNights) : null;

  if (invoice) {
    if (!resolvedCity) resolvedCity = extractCity(invoice);
    if (resolvedNights == null || Number.isNaN(resolvedNights)) resolvedNights = extractExplicitNights(invoice);
    if ((amount == null || amount === '') && (invoice.totalAmount != null || invoice.amount != null)) {
      amount = invoice.totalAmount ?? invoice.amount;
    }
  }

  let amt = amount != null && amount !== '' ? Number(amount) : NaN;
  if (Number.isNaN(amt)) amt = 0;
  if (amt < 0) {
    return { error: '无效金额' };
  }

  const { hotelDomesticKgPerCny, hotelDomesticKgPerNight } = getFactors();
  const spendKgPerCny = hotelDomesticKgPerCny;
  const kgPerNight = hotelDomesticKgPerNight;

  const nightsIndicated =
    resolvedNights != null && !Number.isNaN(resolvedNights) && resolvedNights > 0
      ? Math.floor(resolvedNights)
      : null;

  // 国内住宿：有金额则一律按 core「基于支出金额」，与是否标注间夜无关
  if (amt > 0) {
    const emissionsKg = amt * spendKgPerCny;
    return {
      emissionsKg: Math.round(emissionsKg * 100) / 100,
      nights: null,
      factor: spendKgPerCny,
      city: resolvedCity,
      method: 'domestic_spend',
      nightsIndicated: nightsIndicated || undefined,
    };
  }

  if (nightsIndicated != null) {
    const emissionsKg = nightsIndicated * kgPerNight;
    return {
      emissionsKg: Math.round(emissionsKg * 100) / 100,
      nights: nightsIndicated,
      factor: kgPerNight,
      city: resolvedCity,
      method: 'domestic_nights',
    };
  }

  return { error: '请提供住宿发票金额（优先按支出核算）或间夜数' };
}

module.exports = {
  extractCity,
  extractExplicitNights,
  estimateNights,
  calculateHotelEmission,
  CITY_KEYWORDS,
  NIGHTS_REGEX,
};
