/**
 * 办公用电与用水核算测试
 *
 * - 电费发票1：数量栏 10000（单位度/kWh）
 * - 电费发票2：备注栏 "读数5000kWh"
 * - 水费发票：数量栏 100 吨
 * - 无法提取时返回错误并建议估算模式
 */

const { extractElectricityData, calculateElectricity } = require('./electricityCalculator');
const { extractWaterData, calculateWater } = require('./waterCalculator');
const { processElectricity, processWater } = require('./officeEnergy');

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
  console.log('========== 办公用电/用水核算测试 ==========\n');
  let passed = 0;
  let total = 0;

  // ----- 电费发票1：数量栏 10000 -----
  console.log('【电费发票1】数量栏显示 10000（单位 kWh）\n');
  total++;
  if (runTest('extractElectricityData 从数量+单位提取 10000 kWh', () => {
    const invoice = {
      items: [{ name: '电费', quantity: 10000, unit: 'kWh', amount: 6000 }],
    };
    const r = extractElectricityData(invoice);
    assert(!r.error, '应成功提取');
    assert(r.usageKWh === 10000, `usageKWh 应为 10000，实际 ${r.usageKWh}`);
    assert(r.source === 'quantity', `source 应为 quantity，实际 ${r.source}`);
    console.log(`    提取: ${r.usageKWh} kWh, 来源: ${r.matchedFrom}`);
  })) passed++;

  total++;
  if (runTest('calculateElectricity 10000 kWh × 华东因子', () => {
    const invoice = { items: [{ name: '电费', quantity: 10000, unit: 'kWh', amount: 6000 }] };
    const r = calculateElectricity(invoice, '华东');
    assert(!r.error, '应成功计算');
    assert(r.usageKWh === 10000, `usageKWh 应为 10000，实际 ${r.usageKWh}`);
    assert(r.emissionsKg > 0, `emissionsKg 应 > 0，实际 ${r.emissionsKg}`);
    assert(Math.abs(r.emissionsKg - 10000 * r.factor) < 1, '排放量 = 用电量 × 因子');
    console.log(`    排放: ${r.emissionsKg} kgCO2e, 因子: ${r.factorName} ${r.factor} kgCO2e/kWh`);
  })) passed++;

  // ----- 电费发票2：备注栏 "读数5000kWh" -----
  console.log('\n【电费发票2】备注栏显示 "读数5000kWh"\n');
  total++;
  if (runTest('extractElectricityData 从备注正则匹配 5000 kWh', () => {
    const invoice = {
      items: [{ name: '电力*电费*', quantity: 1, unit: '项', amount: 3000 }],
      remark: '本月读数5000kWh，单价0.6元',
    };
    const r = extractElectricityData(invoice);
    assert(!r.error, '应成功提取');
    assert(r.usageKWh === 5000, `usageKWh 应为 5000，实际 ${r.usageKWh}`);
    assert(r.source === 'regex', `source 应为 regex，实际 ${r.source}`);
    console.log(`    提取: ${r.usageKWh} kWh, 来源: ${r.matchedFrom}`);
  })) passed++;

  total++;
  if (runTest('processElectricity 电费2 返回 success 与 emissionsKg', () => {
    const invoice = { items: [{ name: '电费', amount: 3000 }], remark: '读数5000kWh' };
    const r = processElectricity(invoice, '全国');
    assert(r.success === true, 'success 应为 true');
    assert(r.usageKWh === 5000 && r.emissionsKg > 0, '应有 usageKWh 与 emissionsKg');
  })) passed++;

  // ----- 水费发票：数量栏 100 吨 -----
  console.log('\n【水费发票】数量栏 100 吨\n');
  total++;
  if (runTest('extractWaterData 从数量+单位提取 100 吨', () => {
    const invoice = {
      items: [{ name: '水费', quantity: 100, unit: '吨', amount: 500 }],
    };
    const r = extractWaterData(invoice);
    assert(!r.error, '应成功提取');
    assert(r.usageTons === 100, `usageTons 应为 100，实际 ${r.usageTons}`);
    assert(r.source === 'quantity', `source 应为 quantity，实际 ${r.source}`);
    console.log(`    提取: ${r.usageTons} 吨, 来源: ${r.matchedFrom}`);
  })) passed++;

  total++;
  if (runTest('calculateWater 100 吨 × 0.168 = 16.8 kgCO2e', () => {
    const invoice = { items: [{ name: '水费', quantity: 100, unit: '吨', amount: 500 }] };
    const r = calculateWater(invoice);
    assert(!r.error, '应成功计算');
    assert(r.usageTons === 100, `usageTons 应为 100，实际 ${r.usageTons}`);
    assert(Math.abs(r.emissionsKg - 16.8) < 0.01, `emissionsKg 应为 16.8，实际 ${r.emissionsKg}`);
    assert(r.factor === 0.168, '因子应为 0.168');
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 100 吨 × ${r.factor} kgCO2e/吨`);
  })) passed++;

  total++;
  if (runTest('processWater 水费返回 success 与 emissionsKg', () => {
    const invoice = { items: [{ name: '自来水', quantity: 100, unit: '吨' }] };
    const r = processWater(invoice);
    assert(r.success === true && r.usageTons === 100 && r.emissionsKg === 16.8);
  })) passed++;

  // ----- 错误处理：无法提取时返回错误并建议估算 -----
  console.log('\n【错误处理】无法提取数量时返回错误与建议\n');
  total++;
  if (runTest('无法提取用电量时返回 error 与 suggestion', () => {
    const invoice = { items: [{ name: '办公用品', quantity: 1, unit: '批', amount: 5000 }] };
    const r = extractElectricityData(invoice);
    assert(r.error != null, '应返回 error');
    assert(r.suggestion != null && r.suggestion.length > 0, '应返回 suggestion');
    assert(/估算|估算模式/i.test(r.suggestion), 'suggestion 应建议使用估算模式');
    console.log(`    error: ${r.error}`);
    console.log(`    suggestion: ${r.suggestion.slice(0, 60)}...`);
  })) passed++;

  total++;
  if (runTest('无法提取用水量时 processWater 返回 success: false', () => {
    const invoice = { items: [{ name: '维修费', amount: 1000 }] };
    const r = processWater(invoice);
    assert(r.success === false, 'success 应为 false');
    assert(r.error && r.suggestion, '应有 error 与 suggestion');
  })) passed++;

  console.log('\n========== ' + passed + '/' + total + ' 通过 ==========');
  process.exit(passed === total ? 0 : 1);
}

main();
