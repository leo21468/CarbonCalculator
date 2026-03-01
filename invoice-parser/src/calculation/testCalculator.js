/**
 * 双模式核算引擎测试
 *
 * - 用电发票：10000 kWh × 0.581 = 5810 kgCO2e（活动数据法）
 * - 办公用品：¥5000 × 0.85 = 4250 kgCO2e（支出法，使用给定因子验证公式）
 * - 使用真实因子验证计算逻辑与批量汇总
 */

const { calculateByActivity, calculateByExpenditure, isActivityFactor } = require('./calculator');
const { calculate, scopeFromFactor } = require('./calculationService');
const { calculateBatch } = require('./batchCalculator');
const { getFactorByCategory, getEEIOFactor } = require('../factors/factorService');
const { FACTOR_CATEGORY } = require('../factors/emissionFactors');
const { normalizeActivityUnit, convertQuantityToFactorUnit } = require('./unitUtils');
const { EmissionResult } = require('../models/EmissionResult');

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
  console.log('双模式核算引擎测试\n');
  let passed = 0;
  let total = 0;

  // --- 用电发票：10000 kWh × 0.581 = 5810 kgCO2e ---
  total++;
  if (runTest('活动数据法：10000 kWh × 0.581 = 5810 kgCO2e', () => {
    const factor = { value: 0.581, unit: 'kgCO2e/kWh', category: '电力' };
    const r = calculateByActivity(10000, factor, 'kWh');
    assert(r.method === 'activity', `method 应为 activity，实际 ${r.method}`);
    assert(r.unit === 'kgCO2e', `unit 应为 kgCO2e，实际 ${r.unit}`);
    assert(Math.abs(r.value - 5810) < 0.01, `value 应为 5810，实际 ${r.value}`);
  })) passed++;

  // --- 办公用品：¥5000 × 0.85 = 4250 kgCO2e（给定因子验证公式）---
  total++;
  if (runTest('支出法：¥5000 × 0.85 = 4250 kgCO2e', () => {
    const factor = { value: 0.85, unit: 'kgCO2e/CNY' };
    const r = calculateByExpenditure(5000, factor);
    assert(r.method === 'expenditure', `method 应为 expenditure，实际 ${r.method}`);
    assert(r.unit === 'kgCO2e', `unit 应为 kgCO2e，实际 ${r.unit}`);
    assert(Math.abs(r.value - 4250) < 0.01, `value 应为 4250，实际 ${r.value}`);
  })) passed++;

  // --- 使用真实电力因子 ---
  total++;
  if (runTest('真实因子：全国电力 10000 kWh 计算', () => {
    const factor = getFactorByCategory(FACTOR_CATEGORY.ELECTRICITY, '全国');
    assert(factor && factor.value > 0, '应能获取全国电力因子');
    const r = calculateByActivity(10000, factor, '度');
    assert(r.value > 0, `排放量应 > 0，实际 ${r.value}`);
    assert(Math.abs(r.value - 10000 * factor.value) < 1, `应为 10000 × ${factor.value} ≈ ${10000 * factor.value}`);
  })) passed++;

  // --- 使用真实 EEIO 因子 ---
  total++;
  if (runTest('真实因子：办公用品 EEIO ¥5000 计算', () => {
    const factor = getEEIOFactor('制造业');
    assert(factor && factor.unit && factor.unit.includes('CNY'), '应能获取 EEIO 因子');
    const r = calculateByExpenditure(5000, factor);
    assert(r.value >= 0, `排放量应 ≥ 0，实际 ${r.value}`);
    assert(Math.abs(r.value - 5000 * factor.value) < 0.01, `应为 5000 × ${factor.value}`);
  })) passed++;

  // --- calculationService 自动选择方法 ---
  total++;
  if (runTest('calculationService：用电条目 → 活动数据法', () => {
    const item = { name: '电费', quantity: 1000, unit: 'kWh', amount: 600 };
    const matched = { factor: getFactorByCategory(FACTOR_CATEGORY.ELECTRICITY, '全国'), matchType: '物理因子', confidence: '高', reason: '电力' };
    const r = calculate(item, matched);
    assert(r.method === 'activity', `method 应为 activity，实际 ${r.method}`);
    assert(r.scope === 2, `scope 应为 2（电力），实际 ${r.scope}`);
    assert(r.value > 0, `value 应 > 0，实际 ${r.value}`);
  })) passed++;

  total++;
  if (runTest('calculationService：办公用品条目 → 支出法', () => {
    const item = { name: '办公用品', amount: 5000 };
    const matched = { factor: getEEIOFactor('制造业'), matchType: 'EEIO因子', confidence: '中', reason: '办公' };
    const r = calculate(item, matched);
    assert(r.method === 'expenditure', `method 应为 expenditure，实际 ${r.method}`);
    assert(r.scope === 3, `scope 应为 3，实际 ${r.scope}`);
    assert(r.value >= 0, `value 应 ≥ 0，实际 ${r.value}`);
  })) passed++;

  // --- 批量计算与 EmissionResult ---
  total++;
  if (runTest('calculateBatch 返回 EmissionResult 含 summary', () => {
    const items = [
      { name: '电费', quantity: 1000, unit: 'kWh', amount: 600 },
      { name: '杂项', amount: 2000 },
    ];
    const result = calculateBatch(items, {}, 'INV-001');
    assert(result instanceof EmissionResult, '应返回 EmissionResult 实例');
    assert(Array.isArray(result.items) && result.items.length === 2, `items 长度应为 2，实际 ${result.items.length}`);
    assert(typeof result.summary === 'object', '应有 summary');
    assert('scope1' in result.summary && 'scope2' in result.summary && 'scope3' in result.summary, 'summary 应含 scope1/2/3');
    assert(result.totalEmissions >= 0, `totalEmissions 应 ≥ 0，实际 ${result.totalEmissions}`);
    assert(result.items[0].scope === 2 && result.items[0].method === 'activity', '第一条应为电力 scope2 activity');
  })) passed++;

  // --- 单位转换 ---
  total++;
  if (runTest('单位转换：度→kWh、吨→t', () => {
    assert(normalizeActivityUnit('度') === 'kWh', '度→kWh');
    assert(normalizeActivityUnit('吨') === 't', '吨→t');
    const { quantity } = convertQuantityToFactorUnit(50, '吨', 'kgCO2e/t');
    assert(quantity === 50, '吨与 t 一致应为 50');
  })) passed++;

  // --- 错误处理：无效输入 ---
  total++;
  if (runTest('错误处理：无效 quantity/amount 返回 0', () => {
    const f = { value: 0.58, unit: 'kgCO2e/kWh' };
    assert(calculateByActivity(NaN, f, 'kWh').value === 0, 'NaN quantity → 0');
    assert(calculateByActivity(-1, f).value === 0, '负数 quantity → 0');
    assert(calculateByExpenditure(NaN, { value: 0.00015, unit: 'kgCO2e/CNY' }).value === 0, 'NaN amount → 0');
    assert(calculateByActivity(100, null).value === 0, 'null factor → 0');
  })) passed++;

  // --- scopeFromFactor ---
  total++;
  if (runTest('scopeFromFactor：电力→2、燃料→1、EEIO→3', () => {
    assert(scopeFromFactor({ category: '电力' }) === 2, '电力→scope2');
    assert(scopeFromFactor({ category: '燃料燃烧' }) === 1, '燃料→scope1');
    assert(scopeFromFactor({ category: 'EEIO' }) === 3, 'EEIO→scope3');
  })) passed++;

  console.log('\n' + passed + '/' + total + ' 通过');
  process.exit(passed === total ? 0 : 1);
}

main();
