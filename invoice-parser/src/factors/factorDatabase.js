/**
 * 排放因子数据库初始化
 *
 * 数据来源：
 * - 电力（全国平均 + 区域 + 省级）：data/grid_carbon_factors.json
 *     · 全国平均：data/2024.pdf 表1
 *     · 区域/省级：data/2023.pdf 表2、表3
 * - CPCD data/Emission factors.csv：本项目 **不再合并** 入因子库（电力以 JSON 为准；其它产品由 Python CPCD 匹配等路径处理）。
 * - 用水、燃料、EEIO：data/emission_factors.csv 及内置非电力默认项
 */

const path = require('path');
const fs = require('fs');
const { FACTOR_CATEGORY, FACTOR_TYPE, createFactor } = require('./emissionFactors');

const PROJECT_ROOT = path.resolve(__dirname, '../../..');
const EMISSION_CSV_PATH = path.join(PROJECT_ROOT, 'data', 'Emission factors.csv');
const SIMPLE_FACTORS_PATH = path.join(PROJECT_ROOT, 'data', 'emission_factors.csv');
const GRID_JSON_PATH = path.join(PROJECT_ROOT, 'data', 'grid_carbon_factors.json');

/** 区域电网 → 稳定 id（与 getFactorByCategory 的 region 字段一致） */
const REGION_ID_MAP = {
  华北: 'electricity_north_china',
  东北: 'electricity_northeast',
  华东: 'electricity_east_china',
  华中: 'electricity_central_china',
  西北: 'electricity_northwest',
  南方: 'electricity_south',
  西南: 'electricity_southwest',
};

/** 非电力内置默认（电力全部由 grid_carbon_factors.json 提供） */
const BUILTIN_FACTORS = [
  { id: 'water_supply', name: '自来水供应排放因子', category: FACTOR_CATEGORY.WATER, subCategory: '自来水', value: 0.344, unit: 'kgCO2e/m3', region: '全国', source: '常用文献默认', year: 2020, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'water_wastewater', name: '污水处理排放因子', category: FACTOR_CATEGORY.WATER, subCategory: '污水', value: 0.272, unit: 'kgCO2e/m3', region: '全国', source: '常用文献默认', year: 2020, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'fuel_coal', name: '原煤因子', category: FACTOR_CATEGORY.FUEL, subCategory: '煤炭', value: 2550, unit: 'kgCO2e/t', region: '全国', source: 'data/emission_factors.csv', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'fuel_gasoline', name: '汽油因子', category: FACTOR_CATEGORY.FUEL, subCategory: '成品油', value: 2.3, unit: 'kgCO2e/L', region: '全国', source: 'data/emission_factors.csv(refined_oil)', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'fuel_diesel', name: '柴油因子', category: FACTOR_CATEGORY.FUEL, subCategory: '成品油', value: 2.63, unit: 'kgCO2e/L', region: '全国', source: '常用文献', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'fuel_natural_gas', name: '天然气因子', category: FACTOR_CATEGORY.FUEL, subCategory: '燃气', value: 2.0, unit: 'kgCO2e/m3', region: '全国', source: 'data/emission_factors.csv', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'eeio_paper', name: '造纸业EEIO因子', category: FACTOR_CATEGORY.EEIO, subCategory: '造纸', value: 0.00018, unit: 'kgCO2e/CNY', region: '全国', source: '投入产出表/EEIO默认', year: null, factorType: FACTOR_TYPE.EEIO },
  { id: 'eeio_steel', name: '钢铁业EEIO因子', category: FACTOR_CATEGORY.EEIO, subCategory: '钢铁', value: 0.00035, unit: 'kgCO2e/CNY', region: '全国', source: '投入产出表/EEIO默认', year: null, factorType: FACTOR_TYPE.EEIO },
  { id: 'eeio_cement', name: '水泥业EEIO因子', category: FACTOR_CATEGORY.EEIO, subCategory: '水泥', value: 0.00042, unit: 'kgCO2e/CNY', region: '全国', source: '投入产出表/EEIO默认', year: null, factorType: FACTOR_TYPE.EEIO },
  { id: 'eeio_default', name: '制造业EEIO默认因子', category: FACTOR_CATEGORY.EEIO, subCategory: '默认', value: 0.00015, unit: 'kgCO2e/CNY', region: '全国', source: 'data/emission_factors.csv(scope3_default)', year: null, factorType: FACTOR_TYPE.EEIO },
  { id: 'material_steel', name: '钢材/钢板物理因子', category: FACTOR_CATEGORY.MATERIAL, subCategory: '钢材', value: 2000, unit: 'kgCO2e/t', region: '全国', source: 'LCA文献/钢铁行业平均', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'material_cement', name: '水泥物理因子', category: FACTOR_CATEGORY.MATERIAL, subCategory: '水泥', value: 720, unit: 'kgCO2e/t', region: '全国', source: 'LCA文献', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'material_motor', name: '微型电机/电机物理因子（按台）', category: FACTOR_CATEGORY.MATERIAL, subCategory: '电机', value: 6, unit: 'kgCO2e/个', region: '全国', source: 'LCA文献/电机行业平均（按台估算，见制造业插件注释）', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'material_plastic', name: '塑料物理因子', category: FACTOR_CATEGORY.MATERIAL, subCategory: '塑料', value: 3, unit: 'kgCO2e/kg', region: '全国', source: 'LCA文献/典型值（品种差异大，生产建议用EPD）', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'material_copper', name: '铜/铜材物理因子', category: FACTOR_CATEGORY.MATERIAL, subCategory: '铜', value: 4, unit: 'kgCO2e/kg', region: '全国', source: 'LCA文献/典型值', year: null, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'material_aluminum', name: '铝/铝材物理因子', category: FACTOR_CATEGORY.MATERIAL, subCategory: '铝', value: 10, unit: 'kgCO2e/kg', region: '全国', source: 'LCA文献/典型值（电解铝较高）', year: null, factorType: FACTOR_TYPE.PHYSICAL },
];

let factorList = [];
let loadedFromCsv = false;

/**
 * 从 grid_carbon_factors.json 构建电力类因子（全国 + 区域 + 省级）
 */
function buildOfficialElectricityFactors() {
  if (!fs.existsSync(GRID_JSON_PATH)) {
    return [
      createFactor({
        id: 'electricity_national',
        name: '全国电网平均排放因子',
        category: FACTOR_CATEGORY.ELECTRICITY,
        subCategory: '电网',
        value: 0.5777,
        unit: 'kgCO2e/kWh',
        region: '全国',
        source: '缺省回退（请放置 data/grid_carbon_factors.json）',
        year: 2024,
        factorType: FACTOR_TYPE.PHYSICAL,
      }),
    ];
  }
  const j = JSON.parse(fs.readFileSync(GRID_JSON_PATH, 'utf8'));
  const out = [];
  const na = j.national_average || {};
  out.push(
    createFactor({
      id: 'electricity_national',
      name: '全国电网平均排放因子',
      category: FACTOR_CATEGORY.ELECTRICITY,
      subCategory: '电网',
      value: Number(na.kg_co2e_per_kwh) || 0.5777,
      unit: 'kgCO2e/kWh',
      region: '全国',
      source: [na.source_pdf, na.source_table].filter(Boolean).join(' ').trim() || 'data/2024.pdf',
      year: na.year || 2024,
      factorType: FACTOR_TYPE.PHYSICAL,
    }),
  );

  const rg = j.regional_grids || {};
  const rYear = rg._year || 2023;
  const rSrc = [rg._source_pdf, rg._source_table].filter(Boolean).join(' ').trim();
  Object.keys(rg).forEach((key) => {
    if (key.startsWith('_')) return;
    const id = REGION_ID_MAP[key];
    if (!id) return;
    out.push(
      createFactor({
        id,
        name: `${key}区域电网排放因子`,
        category: FACTOR_CATEGORY.ELECTRICITY,
        subCategory: '电网',
        value: Number(rg[key]),
        unit: 'kgCO2e/kWh',
        region: key,
        source: rSrc || 'data/2023.pdf 表2',
        year: rYear,
        factorType: FACTOR_TYPE.PHYSICAL,
      }),
    );
  });

  const pv = j.provinces || {};
  const pYear = pv._year || 2023;
  const pSrc = [pv._source_pdf, pv._source_table].filter(Boolean).join(' ').trim();
  Object.keys(pv).forEach((prov) => {
    if (prov.startsWith('_')) return;
    const id = `electricity_province_${prov}`;
    out.push(
      createFactor({
        id,
        name: `${prov}省级电力平均排放因子`,
        category: FACTOR_CATEGORY.ELECTRICITY,
        subCategory: '电网',
        value: Number(pv[prov]),
        unit: 'kgCO2e/kWh',
        region: prov,
        source: pSrc || 'data/2023.pdf 表3',
        year: pYear,
        factorType: FACTOR_TYPE.PHYSICAL,
      }),
    );
  });

  return out;
}

/**
 * 组装因子表：官方电力 JSON + 内置非电力项（不合并 CPCD 全表，避免错误归类与重复电网因子）
 */
function loadFromCpcdCsv() {
  if (loadedFromCsv) return factorList;

  const byId = new Map();

  for (const f of buildOfficialElectricityFactors()) {
    byId.set(f.id, f);
  }
  for (const raw of BUILTIN_FACTORS) {
    byId.set(raw.id, createFactor(raw));
  }

  factorList = Array.from(byId.values());
  loadedFromCsv = true;
  return factorList;
}

function initFactorDatabase() {
  loadFromCpcdCsv();
  return factorList;
}

function getFactorList() {
  if (factorList.length === 0) initFactorDatabase();
  return factorList;
}

module.exports = {
  initFactorDatabase,
  getFactorList,
  BUILTIN_FACTORS,
  EMISSION_CSV_PATH,
  SIMPLE_FACTORS_PATH,
  GRID_JSON_PATH,
};
