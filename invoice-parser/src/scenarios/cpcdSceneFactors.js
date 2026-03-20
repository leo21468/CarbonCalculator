/**
 * CPCD 核心库（core.csv 快照）衍生场景因子：统一从 data/cpcd_scene_factors.json 读取。
 */

const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '../../..');
const JSON_PATH = path.join(ROOT, 'data', 'cpcd_scene_factors.json');

let _cache = null;

function loadRaw() {
  if (_cache) return _cache;
  if (!fs.existsSync(JSON_PATH)) {
    throw new Error(`缺少 ${JSON_PATH}，请从仓库 data/ 目录同步 cpcd_scene_factors.json`);
  }
  _cache = JSON.parse(fs.readFileSync(JSON_PATH, 'utf8'));
  return _cache;
}

/** tCO2e / 万元人民币 → kgCO2e / 元 */
function tPer10kToKgPerCny(t) {
  const k = loadRaw().tco2e_per_10k_cny_to_kg_per_cny;
  return Number(t) * Number(k);
}

/** kgCO2e / 万元人民币 → kgCO2e / 元 */
function kgPer10kToKgPerCny(kg) {
  return Number(kg) / 10000;
}

function spendFactorKgPerCny(entry) {
  if (!entry) return null;
  if (entry.t_co2e_per_10k_cny != null) {
    return tPer10kToKgPerCny(entry.t_co2e_per_10k_cny);
  }
  if (entry.kg_co2e_per_10k_cny != null) {
    return kgPer10kToKgPerCny(entry.kg_co2e_per_10k_cny);
  }
  return null;
}

module.exports = {
  loadRaw,
  tPer10kToKgPerCny,
  kgPer10kToKgPerCny,
  spendFactorKgPerCny,
  JSON_PATH,
  getFactors() {
    const d = loadRaw();
    return {
      publicTransitKgPerCny: spendFactorKgPerCny(d.public_transit_spend_proxy),
      taxiKgPerCny: spendFactorKgPerCny(d.domestic_taxi_rideshare_spend),
      taxiFuelKgPerCny: spendFactorKgPerCny(d.domestic_taxi_fuel_spend),
      taxiEvKgPerCny: spendFactorKgPerCny(d.domestic_taxi_ev_spend),
      logisticsAirKgPerCny: spendFactorKgPerCny(d.domestic_air_travel_spend),
      logisticsRailKgPerCny: spendFactorKgPerCny(d.domestic_rail_hsr_travel_spend),
      logisticsRoadKgPerCny: spendFactorKgPerCny(d.logistics_road_spend_proxy),
      wasteKgPerCny: spendFactorKgPerCny(d.municipal_infrastructure_spend_proxy),
      hotelDomesticKgPerCny: spendFactorKgPerCny(d.domestic_accommodation_spend),
      hotelDomesticKgPerNight:
        d.domestic_accommodation_night && d.domestic_accommodation_night.kg_co2e_per_night != null
          ? Number(d.domestic_accommodation_night.kg_co2e_per_night)
          : 66.52,
      waterKgPerM3: d.office_water_m3 && d.office_water_m3.kg_co2e_per_m3 != null ? Number(d.office_water_m3.kg_co2e_per_m3) : 0.168,
      gasolineL: d.gasoline_liter,
      dieselL: d.diesel_liter,
    };
  },
};
