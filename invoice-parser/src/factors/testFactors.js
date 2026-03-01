/**
 * 排放因子模块测试
 *
 * 查询：华北电力因子、汽油因子、造纸业EEIO因子；
 * 验证返回格式与数值。
 */

const { getFactorByCategory, getFactorByName, getEEIOFactor } = require('./factorService');
const { toKgCO2e, withSourceTrace } = require('./factorManager');
const { FACTOR_CATEGORY } = require('./emissionFactors');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function runTest(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    return true;
  } catch (e) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${e.message}`);
    return false;
  }
}

function main() {
  console.log('排放因子数据库测试\n');

  let passed = 0;
  let total = 0;

  total++;
  if (runTest('华北电力因子 getFactorByCategory("电力", "华北")', () => {
    const f = getFactorByCategory(FACTOR_CATEGORY.ELECTRICITY, '华北');
    assert(f, '应返回因子');
    assert(f.category === '电力', `category 应为 电力，实际 ${f.category}`);
    assert(f.region === '华北', `region 应为 华北，实际 ${f.region}`);
    assert(typeof f.value === 'number' && f.value > 0, `value 应为正数，实际 ${f.value}`);
    assert(f.unit && f.unit.includes('kWh'), `unit 应含 kWh，实际 ${f.unit}`);
    console.log(`    → ${f.name}: ${f.value} ${f.unit}, 来源: ${f.source}`);
  })) passed++;

  total++;
  if (runTest('汽油因子 getFactorByName("汽油")', () => {
    const f = getFactorByName('汽油');
    assert(f, '应返回因子');
    assert(f.category === '燃料燃烧' || f.subCategory === '成品油', `应为燃料/成品油，实际 category=${f.category}`);
    assert(typeof f.value === 'number' && f.value > 0, `value 应为正数，实际 ${f.value}`);
    assert(f.unit && (f.unit.includes('L') || f.unit.includes('kg')), `unit 应含 L 或 kg，实际 ${f.unit}`);
    console.log(`    → ${f.name}: ${f.value} ${f.unit}, 来源: ${f.source}`);
  })) passed++;

  total++;
  if (runTest('造纸业EEIO因子 getEEIOFactor("造纸业")', () => {
    const f = getEEIOFactor('造纸业');
    assert(f, '应返回因子');
    assert(f.factorType === 'EEIO因子' || f.category === 'EEIO', `应为 EEIO 因子，实际 ${f.factorType || f.category}`);
    assert(typeof f.value === 'number', `value 应为数字，实际 ${f.value}`);
    assert(f.unit && f.unit.includes('CNY'), `unit 应含 CNY，实际 ${f.unit}`);
    console.log(`    → ${f.name}: ${f.value} ${f.unit}, 来源: ${f.source}`);
  })) passed++;

  total++;
  if (runTest('返回格式含 id/name/category/value/unit/source', () => {
    const f = getFactorByName('华北');
    assert(f, '应返回因子');
    assert('id' in f && 'name' in f && 'category' in f && 'value' in f && 'unit' in f, '应包含 id,name,category,value,unit');
  })) passed++;

  total++;
  if (runTest('toKgCO2e 计算：华北电力 1000 kWh', () => {
    const f = getFactorByCategory(FACTOR_CATEGORY.ELECTRICITY, '华北');
    assert(f, '应有华北电力因子');
    const result = toKgCO2e(f, 1000);
    assert(typeof result.emissionKg === 'number' && result.emissionKg > 0, `emissionKg 应为正数，实际 ${result.emissionKg}`);
    assert(result.source, '应有 source');
    console.log(`    → 1000 kWh × ${f.value} = ${result.emissionKg.toFixed(2)} kgCO2e`);
  })) passed++;

  total++;
  if (runTest('withSourceTrace 附加追溯信息', () => {
    const f = getFactorByName('汽油');
    const traced = withSourceTrace(f);
    assert(traced && traced._trace && traced._trace.includes('来源'), '_trace 应含来源');
  })) passed++;

  console.log('\n---');
  console.log(`通过: ${passed}/${total}`);
  process.exit(passed === total ? 0 : 1);
}

main();
