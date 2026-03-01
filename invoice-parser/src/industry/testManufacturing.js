/**
 * 制造业插件测试脚本
 *
 * 测试1：采购「微型电机10000个」→ 物料匹配计算
 * 测试2：销售「空调500台」（华东区域）→ 产品使用计算（Scope 3 Cat.11）
 */

const { matchMaterial, calculateMaterialEmission, calculateProductUsage } = require('./manufacturing/manufacturingPlugin');

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
  console.log('========== 制造业专用插件测试 ==========\n');

  let passed = 0;
  let total = 0;

  // ---------- 测试1：采购「微型电机10000个」----------
  console.log('【测试1】采购「微型电机10000个」→ 物料匹配计算\n');
  total++;
  if (runTest('matchMaterial("微型电机", 10000, "个") 返回因子与置信度', () => {
    const r = matchMaterial('微型电机', 10000, '个');
    assert(r.factor != null, '应匹配到因子');
    assert(r.factor.unit === 'kgCO2e/个' || (r.factor.unit || '').includes('个'), '因子单位应为按个');
    assert(['高', '中', '低'].includes(r.confidence), `confidence 应为 高/中/低，实际 ${r.confidence}`);
    assert(r.reason && r.reason.length > 0, '应有 reason');
    console.log(`    因子: ${r.factor.name}, ${r.factor.value} ${r.factor.unit}`);
    console.log(`    置信度: ${r.confidence}, 依据: ${r.reason}`);
  })) passed++;

  total++;
  if (runTest('calculateMaterialEmission("微型电机", 10000, "个") 计算排放', () => {
    const r = calculateMaterialEmission('微型电机', 10000, '个');
    assert(r.emissions >= 0, `emissions 应 ≥ 0，实际 ${r.emissions}`);
    assert(r.factor != null, '应有 factor');
    assert(Math.abs(r.emissions - 10000 * r.factor.value) < 0.01, `应为 10000 × 因子值 = ${10000 * r.factor.value}`);
    console.log(`    排放量: ${r.emissions.toFixed(2)} kgCO2e`);
    console.log(`    计算过程: 10000 个 × ${r.factor.value} kgCO2e/个 = ${r.emissions.toFixed(2)} kgCO2e`);
  })) passed++;

  // ---------- 测试2：销售「空调500台」华东 ----------
  console.log('\n【测试2】销售「空调500台」（华东区域）→ 产品使用计算\n');
  total++;
  if (runTest('calculateProductUsage("空调", 500, "华东") 返回总排放与参数', () => {
    const r = calculateProductUsage('空调', 500, '华东');
    assert(r.scope === 3, `scope 应为 3，实际 ${r.scope}`);
    assert(r.totalEmissions > 0, `totalEmissions 应 > 0，实际 ${r.totalEmissions}`);
    assert(r.lifetimeYears > 0 && r.annualKWh > 0, '应有寿命与年耗电量');
    assert(r.electricityFactor > 0, '应有区域电力因子');
    console.log(`    产品类型: ${r.productType}, 数量: ${r.quantity} 台`);
    console.log(`    使用寿命: ${r.lifetimeYears} 年, 年耗电量: ${r.annualKWh} kWh/年`);
    console.log(`    区域: ${r.region}, 电力因子: ${r.electricityFactor} kgCO2e/kWh`);
    console.log(`    公式: 排放量 = 数量 × 寿命 × 年耗电量 × 电力因子`);
    console.log(`    计算: ${r.quantity} × ${r.lifetimeYears} × ${r.annualKWh} × ${r.electricityFactor} = ${r.totalEmissions.toFixed(2)} kgCO2e`);
  })) passed++;

  total++;
  if (runTest('产品使用结果包含 dataSourceNote（能效数据来源说明）', () => {
    const r = calculateProductUsage('空调', 100, '全国');
    assert(r.dataSourceNote && r.dataSourceNote.includes('能效'), '应包含能效数据来源说明');
  })) passed++;

  // ---------- 额外：钢材物料匹配 ----------
  total++;
  if (runTest('物料匹配「冷轧钢板」+ 单位「吨」', () => {
    const r = matchMaterial('冷轧钢板', 50, '吨');
    assert(r.factor != null, '应匹配到钢材因子');
    assert((r.factor.unit || '').includes('t') || (r.factor.unit || '').includes('吨'), '单位应为吨');
    const calc = calculateMaterialEmission('冷轧钢板', 50, '吨');
    assert(calc.emissions > 0, '排放量应 > 0');
  })) passed++;

  console.log('\n========== ' + passed + '/' + total + ' 通过 ==========');
  process.exit(passed === total ? 0 : 1);
}

main();
