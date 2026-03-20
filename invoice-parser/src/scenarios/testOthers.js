/**
 * 通勤、物流、废弃物核算测试
 *
 * - 加油发票：汽油 100L
 * - 公交充值：¥200
 * - 物流运费：¥1500
 * - 垃圾清运费：¥800
 */

const { fuelCalculator, publicTransportCalculator, taxiCalculator, extractTransportData } = require('./transportCalculator');
const {
  logisticsCalculator,
  logisticsCalculatorTonneKm,
  detectTransportMode,
  extractLogisticsData,
} = require('./logisticsCalculator');
const { wasteCalculator, extractWasteAmount } = require('./wasteCalculator');
const { processTransport, processLogistics, processWaste } = require('./index');
const { getFactors } = require('./cpcdSceneFactors');

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
  if (runTest('fuelCalculator(100, "汽油") CPCD 摇篮到大门×升', () => {
    const g = getFactors().gasolineL;
    const expF = (g.kg_co2e_per_tonne * g.assumed_liquid_kg_per_liter) / 1000;
    const r = fuelCalculator(100, '汽油');
    assert(r.fuelType === '汽油', `fuelType 应为 汽油，实际 ${r.fuelType}`);
    assert(Math.abs(r.factor - expF) < 1e-6, `因子应为 ${expF}，实际 ${r.factor}`);
    assert(Math.abs(r.emissionsKg - 100 * expF) < 0.02, `emissionsKg 应为 ${100 * expF}，实际 ${r.emissionsKg}`);
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 100L × ${r.factor} kgCO2e/升 (core 汽油/吨×密度)`);
  })) passed++;

  total++;
  if (runTest('processTransport 识别加油发票并计算', () => {
    const invoice = { items: [{ name: '汽油', quantity: 100, unit: '升', amount: 750 }], totalAmount: 750 };
    const r = processTransport(invoice);
    assert(r.success === true, '应成功');
    assert(r.type === 'fuel', `type 应为 fuel，实际 ${r.type}`);
    const g = getFactors().gasolineL;
    const exp = 100 * (g.kg_co2e_per_tonne * g.assumed_liquid_kg_per_liter) / 1000;
    assert(Math.abs(r.emissionsKg - exp) < 0.02, `emissionsKg 应为 ${exp}，实际 ${r.emissionsKg}`);
  })) passed++;

  // ----- 公交充值：¥200 -----
  console.log('\n【公交充值】¥200\n');
  total++;
  if (runTest('publicTransportCalculator(200) core 高铁差旅万元→元', () => {
    const f = getFactors().publicTransitKgPerCny;
    const r = publicTransportCalculator(200);
    assert(Math.abs(r.factor - f) < 1e-9, `因子应为 ${f}`);
    assert(Math.abs(r.emissionsKg - 200 * f) < 0.02, `emissionsKg 应为 ${200 * f}，实际 ${r.emissionsKg}`);
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 200 元 × ${r.factor} kgCO2e/元`);
  })) passed++;

  total++;
  if (runTest('processTransport 识别公交充值并计算', () => {
    const invoice = { items: [{ name: '一卡通充值', amount: 200 }], totalAmount: 200 };
    const r = processTransport(invoice);
    assert(r.success === true && r.type === 'public', '应识别为 public');
    const f = getFactors().publicTransitKgPerCny;
    assert(Math.abs(r.emissionsKg - 200 * f) < 0.02, `emissionsKg 应为 ${200 * f}，实际 ${r.emissionsKg}`);
  })) passed++;

  // ----- 物流运费：¥1500 -----
  console.log('\n【物流运费】¥1500\n');
  total++;
  if (runTest('logisticsCalculator(1500, "road") core 出租网约车万元→元', () => {
    const ef = getFactors().logisticsRoadKgPerCny;
    const r = logisticsCalculator(1500, 'road');
    assert(r.transportMode === 'road', `transportMode 应为 road，实际 ${r.transportMode}`);
    assert(Math.abs(r.factor - ef) < 1e-9, `公路因子应为 ${ef}`);
    assert(Math.abs(r.emissionsKg - 1500 * ef) < 0.02, `emissionsKg 应为 ${1500 * ef}，实际 ${r.emissionsKg}`);
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
    const ef = getFactors().logisticsRoadKgPerCny;
    assert(Math.abs(r.emissionsKg - 1500 * ef) < 0.02, `emissionsKg 应为 ${1500 * ef}，实际 ${r.emissionsKg}`);
  })) passed++;

  total++;
  if (runTest('logisticsCalculatorTonneKm 铁路 100 t·km × 0.006502', () => {
    const r = logisticsCalculatorTonneKm(100, 'rail', {});
    assert(r && r.method === 'tonne_km', '应为吨公里法');
    assert(Math.abs(r.factor - 0.006502) < 1e-9, `factor ${r.factor}`);
    assert(Math.abs(r.emissionsKg - 0.6502) < 0.0001, `emissions ${r.emissionsKg}`);
  })) passed++;

  total++;
  if (runTest('logisticsCalculatorTonneKm 航空 2×1000 t·km', () => {
    const r = logisticsCalculatorTonneKm(2000, 'air', {});
    assert(r && Math.abs(r.emissionsKg - 1842) < 0.01, `航空 2000 t·km 应约 1842 kg，实际 ${r.emissionsKg}`);
  })) passed++;

  total++;
  if (runTest('extractLogisticsData 备注「10吨500公里」', () => {
    const invoice = { items: [{ name: '运费', amount: 100 }], remark: '运输10吨500公里', totalAmount: 100 };
    const d = extractLogisticsData(invoice);
    assert(d.tonKm === 5000, `tonKm 应为 5000，实际 ${d.tonKm}`);
  })) passed++;

  total++;
  if (runTest('processLogistics 吨公里 公路 默认因子', () => {
    const invoice = {
      items: [{ name: '公路运输', amount: 500, remark: '5吨200公里' }],
      remark: '',
      totalAmount: 500,
    };
    const r = processLogistics(invoice);
    assert(r.success === true && r.method === 'tonne_km', '应用吨公里法');
    assert(Math.abs(r.tonKm - 1000) < 0.01, `tonKm 1000，实际 ${r.tonKm}`);
    assert(r.emissionsKg > 200 && r.emissionsKg < 300, `1000 t·km×天然气默认约 247.8 kg，实际 ${r.emissionsKg}`);
  })) passed++;

  // ----- 垃圾清运费：¥800 -----
  console.log('\n【垃圾清运费】¥800\n');
  total++;
  if (runTest('wasteCalculator(800) 市政基础设施万元→元（core 近似）', () => {
    const wf = getFactors().wasteKgPerCny;
    const r = wasteCalculator(800);
    assert(Math.abs(r.factor - wf) < 1e-9, `因子应为 ${wf}`);
    assert(Math.abs(r.emissionsKg - 800 * wf) < 0.02, `emissionsKg 应为 ${800 * wf}，实际 ${r.emissionsKg}`);
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 800 元 × ${r.factor} kgCO2e/元`);
  })) passed++;

  total++;
  if (runTest('processWaste 垃圾清运发票 ¥800', () => {
    const invoice = { items: [{ name: '垃圾清运费', amount: 800 }], totalAmount: 800 };
    const r = processWaste(invoice);
    assert(r.success === true, '应成功');
    assert(r.amount === 800, `amount 应为 800，实际 ${r.amount}`);
    const wf = getFactors().wasteKgPerCny;
    assert(Math.abs(r.emissionsKg - 800 * wf) < 0.02, `emissionsKg 应为 ${800 * wf}，实际 ${r.emissionsKg}`);
  })) passed++;

  // ----- 柴油 -----
  total++;
  if (runTest('fuelCalculator(50, "柴油") CPCD 柴油摇篮到大门×升', () => {
    const d = getFactors().dieselL;
    const expF = (d.kg_co2e_per_tonne * d.assumed_liquid_kg_per_liter) / 1000;
    const r = fuelCalculator(50, '柴油');
    assert(r.fuelType === '柴油' && Math.abs(r.factor - expF) < 1e-6);
    assert(Math.abs(r.emissionsKg - 50 * expF) < 0.02);
  })) passed++;

  console.log('\n========== ' + passed + '/' + total + ' 通过 ==========');
  process.exit(passed === total ? 0 : 1);
}

main();
