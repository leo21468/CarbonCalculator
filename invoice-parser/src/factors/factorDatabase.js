/**
 * 排放因子数据库初始化
 *
 * 数据来源：
 * - 电力/区域因子：Emission factors.csv（CPCD，原 cpcd_full_*.csv）中电网排放因子等
 * - 用水、燃料、EEIO：data/emission_factors.csv 及常用文献默认值
 * 生产环境建议从数据库或 API 加载，此处为文件 + 内置默认。
 */

const path = require('path');
const fs = require('fs');
const { FACTOR_CATEGORY, FACTOR_TYPE, parseFootprint, createFactor } = require('./emissionFactors');

/** 项目根目录（CarbonCalculator），用于定位 Emission factors.csv */
const PROJECT_ROOT = path.resolve(__dirname, '../../..');
const EMISSION_CSV_PATH = path.join(PROJECT_ROOT, 'Emission factors.csv');
const SIMPLE_FACTORS_PATH = path.join(PROJECT_ROOT, 'data', 'emission_factors.csv');

/** 内置默认因子：电力、用水、燃料、制造业 EEIO */
const BUILTIN_FACTORS = [
  { id: 'electricity_national', name: '全国电网平均排放因子', category: FACTOR_CATEGORY.ELECTRICITY, subCategory: '电网', value: 0.5839, unit: 'kgCO2e/kWh', region: '全国', source: '生态环境部/全国平均', year: 2019, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'electricity_north_china', name: '华北电网排放因子', category: FACTOR_CATEGORY.ELECTRICITY, subCategory: '电网', value: 0.8952, unit: 'kgCO2e/kWh', region: '华北', source: 'Emission factors.csv(CPCD)', year: 2019, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'electricity_east_china', name: '华东电网排放因子', category: FACTOR_CATEGORY.ELECTRICITY, subCategory: '电网', value: 0.6496, unit: 'kgCO2e/kWh', region: '华东', source: 'Emission factors.csv(CPCD)', year: 2019, factorType: FACTOR_TYPE.PHYSICAL },
  { id: 'electricity_south', name: '南方电网排放因子', category: FACTOR_CATEGORY.ELECTRICITY, subCategory: '电网', value: 0.4701, unit: 'kgCO2e/kWh', region: '南方', source: 'CPCD/文献', year: 2020, factorType: FACTOR_TYPE.PHYSICAL },
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
 * 从 Emission factors.csv（CPCD 格式）中加载电网等因子，与内置列表合并
 * 碳足迹列格式：0.8952tCO2e / 兆瓦时 → 换算为 kgCO2e/kWh（1 兆瓦时=1000 kWh，t=1000kg → 0.8952*1000/1000=0.8952 kg/kWh）
 */
function loadFromCpcdCsv() {
  if (loadedFromCsv) return factorList;
  if (!fs.existsSync(EMISSION_CSV_PATH)) {
    factorList = BUILTIN_FACTORS.map(createFactor);
    return factorList;
  }
  const byId = new Map(BUILTIN_FACTORS.map((f) => [f.id, createFactor(f)]));
  const content = fs.readFileSync(EMISSION_CSV_PATH, 'utf8');
  const lines = content.split(/\r?\n/).filter((line) => line.trim());
  const header = lines[0].split(',');
  const nameIdx = header.findIndex((h) => h === '产品名称' || h.includes('名称'));
  const footprintIdx = header.findIndex((h) => h === '碳足迹');
  const yearIdx = header.findIndex((h) => h === '数据年份');
  const typeIdx = header.findIndex((h) => h === '数据类型');
  const idIdx = header.findIndex((h) => h === '产品ID');

  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',').map((c) => c.trim());
    const name = nameIdx >= 0 ? cols[nameIdx] : '';
    const footprint = footprintIdx >= 0 ? cols[footprintIdx] : '';
    const year = yearIdx >= 0 ? cols[yearIdx] : '';
    const dataType = typeIdx >= 0 ? cols[typeIdx] : '';
    const productId = idIdx >= 0 ? cols[idIdx] : '';

    const parsed = parseFootprint(footprint);
    if (!parsed) continue;
    let value = parsed.value;
    const rawUnit = parsed.rawUnit;
    let unit = 'kgCO2e/unit';
    let region = '';
    if (/电网|排放因子|碳足迹/.test(name)) {
      if (/华北/.test(name)) region = '华北';
      else if (/华东/.test(name)) region = '华东';
      else if (/东北/.test(name)) region = '东北';
      else if (/华中/.test(name)) region = '华中';
      else if (/南方/.test(name)) region = '南方';
      else if (/全国/.test(name)) region = '全国';
      else if (/北京/.test(name)) region = '北京';
      else if (/上海/.test(name)) region = '上海';
      if (/兆瓦时|MWh/.test(rawUnit)) {
        value = value / 1000;
        unit = 'kgCO2e/kWh';
      }
      const id = productId || `elec_${region}_${year}`.replace(/\s/g, '_');
      if (!byId.has(id)) byId.set(id, createFactor({ id, name, category: FACTOR_CATEGORY.ELECTRICITY, subCategory: '电网', value, unit, region, source: dataType || 'Emission factors.csv', year, factorType: FACTOR_TYPE.PHYSICAL }));
    }
  }
  factorList = Array.from(byId.values());
  loadedFromCsv = true;
  return factorList;
}

/**
 * 初始化并返回因子列表（先内置，再叠加 CSV）
 */
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
};
