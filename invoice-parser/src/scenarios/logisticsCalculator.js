/**
 * 物流运输核算：
 * 1) 优先：吨公里（活动数据）× CPCD/transport.xlsx 因子（kgCO2e/公吨·公里）
 * 2) 兜底：仅有运费金额时用 core 差旅「万元→元」因子（cpcd_scene_factors.json）
 *
 * 铁路/航空物理因子：data/transport_factors.json
 * 公路：data/transport.xlsx → 同上 JSON（tools/sync_transport_factors.py）
 */

const {
  getFreightFactorKgPerTonneKm,
  extractCpcdProductId,
} = require('./transportFactorsData');
const { getFactors } = require('./cpcdSceneFactors');

/** 仅有金额时：航空/高铁/公路（公路用出租网约车差旅万元因子）— 摘自 cpcd_scene_factors.json */
function amountEeioKgPerCny(mode) {
  const F = getFactors();
  const m = (mode || 'road').toLowerCase();
  if (m === 'air') return F.logisticsAirKgPerCny;
  if (m === 'rail') return F.logisticsRailKgPerCny;
  return F.logisticsRoadKgPerCny;
}

/** 运输方式关键词 */
const MODE_KEYWORDS = [
  { keywords: ['航空', '空运', '航班', '飞机', '货运航空'], mode: 'air' },
  { keywords: ['铁路', '火车', '高铁', '动车', '货运专列'], mode: 'rail' },
  { keywords: ['公路', '汽运', '货车', '卡车', '物流', '快递', '配送', '运输'], mode: 'road' },
];

function detectTransportMode(text) {
  const t = (text || '').trim();
  for (const { keywords, mode } of MODE_KEYWORDS) {
    if (keywords.some((kw) => t.includes(kw))) return mode;
  }
  return 'road';
}

/**
 * 从文本中提取 吨·公里 或 (吨 + 公里)
 * @returns {{ tonKm?: number, tonnes?: number, distanceKm?: number }}
 */
function extractTonneKmFromText(text) {
  const raw = (text || '').toString();
  const t = raw.replace(/\u00a0/g, ' ');

  let m = t.match(/(\d+\.?\d*)\s*吨\s*公里/);
  if (m) {
    const tonKm = parseFloat(m[1]);
    if (!Number.isNaN(tonKm) && tonKm > 0) return { tonKm };
  }

  m = t.match(/(\d+\.?\d*)\s*吨[-·]?公里/);
  if (m) {
    const tonKm = parseFloat(m[1]);
    if (!Number.isNaN(tonKm) && tonKm > 0) return { tonKm };
  }

  m = t.match(/(\d+\.?\d*)\s*吨[^\d]{0,30}?(\d+\.?\d*)\s*公里/);
  if (m) {
    const tonnes = parseFloat(m[1]);
    const distanceKm = parseFloat(m[2]);
    if (!Number.isNaN(tonnes) && !Number.isNaN(distanceKm) && tonnes > 0 && distanceKm > 0) {
      return { tonnes, distanceKm, tonKm: tonnes * distanceKm };
    }
  }

  m = t.match(/(\d+\.?\d*)\s*t\s*[x×*]\s*(\d+\.?\d*)\s*km/i);
  if (m) {
    const tonnes = parseFloat(m[1]);
    const distanceKm = parseFloat(m[2]);
    if (!Number.isNaN(tonnes) && !Number.isNaN(distanceKm) && tonnes > 0 && distanceKm > 0) {
      return { tonnes, distanceKm, tonKm: tonnes * distanceKm };
    }
  }

  return {};
}

/**
 * @param {Object} invoice
 * @returns {{ amount: number, transportMode: string, productId: string|null, combinedText: string, tonKm?: number, tonnes?: number, distanceKm?: number }}
 */
function extractLogisticsData(invoice) {
  const items = Array.isArray(invoice?.items) ? invoice.items : [];
  const totalAmount = invoice?.totalAmount != null ? Number(invoice.totalAmount) : NaN;
  const texts = items
    .map((it) =>
      [
        (it.name || it.goodsName || '').toString(),
        (it.remark || '').toString(),
        (it.spec || it.specification || '').toString(),
      ].join(' '),
    )
    .join(' ');
  const remark = (invoice?.remark || invoice?.remarks || '').toString();
  const combined = `${texts} ${remark}`.trim();

  let amount = !Number.isNaN(totalAmount) && totalAmount > 0 ? totalAmount : (items[0]?.amount != null ? Number(items[0].amount) : 0);
  amount = amount > 0 ? amount : 0;

  const mode = detectTransportMode(combined);
  const productId = extractCpcdProductId(combined) || extractCpcdProductId(texts) || extractCpcdProductId(remark);

  let tonKm;
  let tonnes;
  let distanceKm;

  for (const it of items) {
    const q = it.quantity != null ? Number(it.quantity) : NaN;
    const u = (it.unit || it.unitOfMeasure || '').toString();
    if (!Number.isNaN(q) && q > 0 && /吨[-·]?公里|吨公里/i.test(u)) {
      tonKm = q;
      break;
    }
    if (!Number.isNaN(q) && q > 0 && /吨|t\b/i.test(u) && /公里|km/i.test((it.name || '') + (it.remark || ''))) {
      const line = `${it.name || ''} ${it.remark || ''} ${it.spec || ''}`;
      const sub = extractTonneKmFromText(line);
      if (sub.tonKm) {
        tonKm = sub.tonKm;
        tonnes = sub.tonnes;
        distanceKm = sub.distanceKm;
        break;
      }
    }
  }

  if (tonKm == null) {
    const fromText = extractTonneKmFromText(combined);
    if (fromText.tonKm) {
      tonKm = fromText.tonKm;
      tonnes = fromText.tonnes;
      distanceKm = fromText.distanceKm;
    }
  }

  return {
    amount,
    transportMode: mode,
    productId,
    combinedText: combined,
    tonKm,
    tonnes,
    distanceKm,
  };
}

/**
 * 吨公里法
 * @returns {{ emissionsKg: number, factor: number, transportMode: string, method: string, factorName?: string, source?: string, productId?: string, tonKm: number } | null}
 */
function logisticsCalculatorTonneKm(tonKm, transportMode, opts) {
  const tk = Number(tonKm);
  if (Number.isNaN(tk) || tk <= 0) return null;
  const mode = (transportMode || 'road').toLowerCase();
  const invoiceText = (opts && opts.invoiceText) || '';
  const pid = (opts && opts.productId) || null;
  const detail = getFreightFactorKgPerTonneKm(mode, {
    productId: pid,
    invoiceText,
  });
  if (!detail || Number.isNaN(detail.kgPerTonneKm)) return null;
  const emissionsKg = tk * detail.kgPerTonneKm;
  return {
    emissionsKg: Math.round(emissionsKg * 10000) / 10000,
    factor: detail.kgPerTonneKm,
    transportMode: mode,
    method: 'tonne_km',
    factorName: detail.modeCn || mode,
    source: detail.source,
    productId: detail.productId,
    tonKm: tk,
  };
}

/**
 * 金额 EEIO 兜底
 */
function logisticsCalculator(amount, transportMode) {
  const a = Number(amount);
  const validA = !Number.isNaN(a) && a >= 0 ? a : 0;
  const mode = (transportMode || 'road').toLowerCase();
  const factor = amountEeioKgPerCny(mode);
  return {
    emissionsKg: Math.round(validA * factor * 100) / 100,
    amount: validA,
    factor,
    transportMode: mode,
    method: 'eeio_amount',
  };
}

module.exports = {
  logisticsCalculator,
  logisticsCalculatorTonneKm,
  detectTransportMode,
  extractLogisticsData,
  extractTonneKmFromText,
  amountEeioKgPerCny,
  get FACTOR_ROAD() {
    return getFactors().logisticsRoadKgPerCny;
  },
  get FACTOR_RAIL() {
    return getFactors().logisticsRailKgPerCny;
  },
  get FACTOR_AIR() {
    return getFactors().logisticsAirKgPerCny;
  },
  get FACTOR_DEFAULT() {
    return getFactors().logisticsRoadKgPerCny;
  },
  get FACTOR_ROAD_EEIO() {
    return getFactors().logisticsRoadKgPerCny;
  },
  get FACTOR_RAIL_EEIO() {
    return getFactors().logisticsRailKgPerCny;
  },
  get FACTOR_AIR_EEIO() {
    return getFactors().logisticsAirKgPerCny;
  },
  MODE_KEYWORDS,
};
