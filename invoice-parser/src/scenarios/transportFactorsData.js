/**
 * 货运碳因子：data/transport_factors.json
 * — 铁路/航空：CPCD 2024（gCO2e/公吨·公里，JSON 内为 kgCO2e/公吨·公里）
 * — 公路：data/transport.xlsx 同步至 JSON
 */

const path = require('path');
const fs = require('fs');

const PROJECT_ROOT = path.resolve(__dirname, '../../..');
const TRANSPORT_JSON = path.join(PROJECT_ROOT, 'data', 'transport_factors.json');

/** CPCD 产品 ID 形态 */
const CPCD_PRODUCT_ID_RE = /65\d{3}X\d{6}[0-9A-Z]/gi;

let _cache = { raw: null, path: TRANSPORT_JSON };

function loadTransportFactors() {
  if (!fs.existsSync(TRANSPORT_JSON)) {
    return null;
  }
  try {
    const txt = fs.readFileSync(TRANSPORT_JSON, 'utf8');
    return JSON.parse(txt);
  } catch (e) {
    return null;
  }
}

/**
 * 从备注/品名中抓取 CPCD 产品 ID
 * @param {string} text
 * @returns {string|null}
 */
function extractCpcdProductId(text) {
  if (!text) return null;
  const m = String(text).match(CPCD_PRODUCT_ID_RE);
  return m && m[0] ? m[0] : null;
}

/**
 * 在文本中匹配最适宜的公路条目（最长名称命中）
 * @param {string} invoiceText
 * @param {Array} roadModes
 * @param {object|null} roadDefault
 */
function pickRoadMode(invoiceText, productId, roadModes, roadDefault) {
  const modes = Array.isArray(roadModes) ? roadModes : [];
  if (productId) {
    const hit = modes.find((r) => r.product_id === productId);
    if (hit) return hit;
  }
  const text = String(invoiceText || '').replace(/\s/g, '');
  let best = null;
  let bestLen = 0;
  for (const r of modes) {
    const name = (r.mode_cn || '').replace(/\u00a0/g, ' ').trim();
    const compact = name.replace(/\s/g, '');
    if (compact.length < 4) continue;
    if (text.includes(compact)) {
      if (compact.length > bestLen) {
        bestLen = compact.length;
        best = r;
      }
    }
  }
  return best || roadDefault || null;
}

/**
 * @param {'road'|'rail'|'air'} mode
 * @param {{ productId?: string, invoiceText?: string }} [opts]
 * @returns {{ kgPerTonneKm: number, source: string, modeCn?: string, productId?: string, method: string } | null}
 */
function getFreightFactorKgPerTonneKm(mode, opts) {
  const d = loadTransportFactors();
  const o = opts || {};
  if (!d) {
    return null;
  }
  const m = (mode || 'road').toLowerCase();
  if (m === 'rail' && d.rail) {
    return {
      kgPerTonneKm: Number(d.rail.kg_co2e_per_tonne_km),
      source: d.rail.source || 'CPCD 铁路运输',
      modeCn: d.rail.mode_cn,
      method: 'tonne_km_cpcd',
    };
  }
  if (m === 'air' && d.air) {
    return {
      kgPerTonneKm: Number(d.air.kg_co2e_per_tonne_km),
      source: d.air.source || 'CPCD 航空运输',
      modeCn: d.air.mode_cn,
      method: 'tonne_km_cpcd',
    };
  }
  const road = pickRoadMode(
    o.invoiceText,
    o.productId,
    d.road_modes,
    d.road_default,
  );
  if (road && road.kg_co2e_per_tonne_km != null) {
    return {
      kgPerTonneKm: Number(road.kg_co2e_per_tonne_km),
      source: road.source || 'data/transport.xlsx',
      modeCn: road.mode_cn,
      productId: road.product_id,
      method: 'tonne_km_xlsx',
    };
  }
  return null;
}

module.exports = {
  loadTransportFactors,
  extractCpcdProductId,
  pickRoadMode,
  getFreightFactorKgPerTonneKm,
  TRANSPORT_JSON,
};
