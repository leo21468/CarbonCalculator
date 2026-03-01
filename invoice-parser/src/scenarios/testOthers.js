/**
 * 通勤、物流、废弃物核算测试
 *
 * - 加油发票：汽油 100L
 * - 公交充值：¥200
 * - 物流运费：¥1500
 * - 垃圾清运费：¥800
 */

const { fuelCalculator, publicTransportCalculator, taxiCalculator, extractTransportData } = require('./transportCalculator');
const { logisticsCalculator, detectTransportMode, extractLogisticsData } = require('./logisticsCalculator');
const { wasteCalculator, extractWasteAmount } = require('./wasteCalculator');
const { processTransport, processLogistics, processWaste } = require('./index');

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
  console.log('========== 通勤/物流/废弃物核算测试 ==========\n');
  let passed = 0;
  let total = 0;

  // ----- 加油发票：汽油 100L -----
  console.log('【加油发票】汽油 100L\n');
  total++;
  if (runTest('fuelCalculator(100, "汽油") = 298 kgCO2e', () => {
    const r = fuelCalculator(100, '汽油');
    assert(r.fuelType === '汽油', `fuelType 应为 汽油，实际 ${r.fuelType}`);
    assert(r.factor === 2.98, `因子应为 2.98，实际 ${r.factor}`);
    assert(Math.abs(r.emissionsKg - 298) < 0.02, `emissionsKg 应为 298，实际 ${r.emissionsKg}`);
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 100L × ${r.factor} kgCO2e/升`);
  })) passed++;

  total++;
  if (runTest('processTransport 识别加油发票并计算', () => {
    const invoice = { items: [{ name: '汽油', quantity: 100, unit: '升', amount: 750 }], totalAmount: 750 };
    const r = processTransport(invoice);
    assert(r.success === true, '应成功');
    assert(r.type === 'fuel', `type 应为 fuel，实际 ${r.type}`);
    assert(Math.abs(r.emissionsKg - 298) < 0.02, `emissionsKg 应为 298，实际 ${r.emissionsKg}`);
  })) passed++;

  // ----- 公交充值：¥200 -----
  console.log('\n【公交充值】¥200\n');
  total++;
  if (runTest('publicTransportCalculator(200) = 24 kgCO2e', () => {
    const r = publicTransportCalculator(200);
    assert(r.factor === 0.12, '因子应为 0.12');
    assert(Math.abs(r.emissionsKg - 24) < 0.02, `emissionsKg 应为 24，实际 ${r.emissionsKg}`);
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 200 元 × ${r.factor} kgCO2e/元`);
  })) passed++;

  total++;
  if (runTest('processTransport 识别公交充值并计算', () => {
    const invoice = { items: [{ name: '一卡通充值', amount: 200 }], totalAmount: 200 };
    const r = processTransport(invoice);
    assert(r.success === true && r.type === 'public', '应识别为 public');
    assert(Math.abs(r.emissionsKg - 24) < 0.02, `emissionsKg 应为 24，实际 ${r.emissionsKg}`);
  })) passed++;

  // ----- 物流运费：¥1500 -----
  console.log('\n【物流运费】¥1500\n');
  total++;
  if (runTest('logisticsCalculator(1500, "road") 公路因子 0.28', () => {
    const r = logisticsCalculator(1500, 'road');
    assert(r.transportMode === 'road', `transportMode 应为 road，实际 ${r.transportMode}`);
    assert(r.factor === 0.28, '公路因子应为 0.28');
    assert(Math.abs(r.emissionsKg - 1500 * 0.28) < 0.02, `emissionsKg 应为 420，实际 ${r.emissionsKg}`);
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 1500 元 × ${r.factor} kgCO2e/元`);
  })) passed++;

  total++;
  if (runTest('detectTransportMode 关键词识别公路/铁路/航空', () => {
    assert(detectTransportMode('快递费') === 'road', '快递→road');
    assert(detectTransportMode('铁路货运') === 'rail', '铁路→rail');
    assert(detectTransportMode('航空运输') === 'air', '航空→air');
  })) passed++;

  total++;
  if (runTest('processLogistics 物流发票 ¥1500', () => {
    const invoice = { items: [{ name: '物流运输费', amount: 1500 }], totalAmount: 1500 };
    const r = processLogistics(invoice);
    assert(r.success === true, '应成功');
    assert(r.amount === 1500, `amount 应为 1500，实际 ${r.amount}`);
    assert(r.transportMode === 'road', '应识别为公路');
    assert(Math.abs(r.emissionsKg - 420) < 0.02, `emissionsKg 应为 420，实际 ${r.emissionsKg}`);
  })) passed++;

  // ----- 垃圾清运费：¥800 -----
  console.log('\n【垃圾清运费】¥800\n');
  total++;
  if (runTest('wasteCalculator(800) = 360 kgCO2e', () => {
    const r = wasteCalculator(800);
    assert(r.factor === 0.45, '因子应为 0.45');
    assert(Math.abs(r.emissionsKg - 360) < 0.02, `emissionsKg 应为 360，实际 ${r.emissionsKg}`);
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 800 元 × ${r.factor} kgCO2e/元`);
  })) passed++;

  total++;
  if (runTest('processWaste 垃圾清运发票 ¥800', () => {
    const invoice = { items: [{ name: '垃圾清运费', amount: 800 }], totalAmount: 800 };
    const r = processWaste(invoice);
    assert(r.success === true, '应成功');
    assert(r.amount === 800, `amount 应为 800，实际 ${r.amount}`);
    assert(Math.abs(r.emissionsKg - 360) < 0.02, `emissionsKg 应为 360，实际 ${r.emissionsKg}`);
  })) passed++;

  // ----- 柴油 -----
  total++;
  if (runTest('fuelCalculator(50, "柴油") 使用柴油因子 3.16', () => {
    const r = fuelCalculator(50, '柴油');
    assert(r.fuelType === '柴油' && r.factor === 3.16);
    assert(Math.abs(r.emissionsKg - 50 * 3.16) < 0.02);
  })) passed++;

  console.log('\n========== ' + passed + '/' + total + ' 通过 ==========');
  process.exit(passed === total ? 0 : 1);
}

main();
