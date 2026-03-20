/**
 * 差旅住宿核算测试（国内：优先 core 基于支出金额）
 */

const { extractCity, extractExplicitNights, estimateNights, calculateHotelEmission } = require('./hotelCalculator');
const { getCityRate } = require('./cityRates');
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
  console.log('========== 差旅住宿智能核算测试 ==========\n');
  const { hotelDomesticKgPerCny, hotelDomesticKgPerNight } = getFactors();
  let passed = 0;
  let total = 0;

  // ----- 案例1：上海 ¥1200，无间夜数 → 按支出 -----
  console.log('【案例1】上海某酒店发票 ¥1200（无间夜数）→ 按支出核算\n');
  total++;
  if (runTest('calculateHotelEmission(1200, "上海") = 金额 × core 支出因子', () => {
    const r = calculateHotelEmission(1200, '上海', null);
    assert(!r.error, '应成功');
    assert(r.method === 'domestic_spend', `method 应为 domestic_spend，实际 ${r.method}`);
    const expectKg = 1200 * hotelDomesticKgPerCny;
    assert(Math.abs(r.emissionsKg - expectKg) < 0.02, `emissionsKg 应为 ${expectKg}，实际 ${r.emissionsKg}`);
    assert(r.factor === hotelDomesticKgPerCny, 'factor 应为国内住宿支出强度');
    assert(r.nights === null, '按支出时不应填 nights');
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 1200 元 × ${r.factor} kgCO2e/元`);
  })) passed++;

  total++;
  if (runTest('estimateNights(1200, "上海") 仍可作间夜参考（不参与排放）', () => {
    const r = estimateNights(1200, '上海');
    assert(!r.error, '应成功');
    assert(r.nights === 2, `nights 应为 2（1200/500=2.4 向下取整），实际 ${r.nights}`);
    assert(r.priceUsed === 500, `priceUsed 应为 500，实际 ${r.priceUsed}`);
    console.log(`    参考间夜: ${r.nights}, 标准价: ${r.priceUsed} 元/间·天`);
  })) passed++;

  // ----- 案例2：北京 ¥1600，备注「3晚」→ 仍以金额优先 -----
  console.log('\n【案例2】北京 ¥1600，备注「3晚」→ 支出优先（间夜仅作 nightsIndicated）\n');
  total++;
  if (runTest('extractExplicitNights 从备注提取 3 晚', () => {
    const invoice = { remark: '住宿3晚', totalAmount: 1600, sellerName: '北京某某酒店' };
    const n = extractExplicitNights(invoice);
    assert(n === 3, `应提取 3 晚，实际 ${n}`);
    console.log(`    提取间夜数: ${n}`);
  })) passed++;

  total++;
  if (runTest('extractCity 从销方名称提取北京', () => {
    const invoice = { sellerName: '北京某某酒店有限公司' };
    const city = extractCity(invoice);
    assert(city === '北京', `city 应为 北京，实际 ${city}`);
    console.log(`    提取城市: ${city}`);
  })) passed++;

  total++;
  if (runTest('calculateHotelEmission(1600, "北京", 3) 按金额，非 3×城市因子', () => {
    const r = calculateHotelEmission(1600, '北京', 3);
    assert(!r.error, '应成功');
    assert(r.method === 'domestic_spend', `method 应为 domestic_spend，实际 ${r.method}`);
    const expectKg = 1600 * hotelDomesticKgPerCny;
    assert(Math.abs(r.emissionsKg - expectKg) < 0.02, `emissionsKg 应为 ${expectKg}，实际 ${r.emissionsKg}`);
    assert(r.nightsIndicated === 3, '应保留发票所示间夜 nightsIndicated');
    console.log(`    排放: ${r.emissionsKg} kgCO2e（金额法）, 备注间夜: ${r.nightsIndicated}`);
  })) passed++;

  total++;
  if (runTest('传 invoice 时金额优先于备注间夜', () => {
    const invoice = { amount: 1600, totalAmount: 1600, sellerName: '上海某酒店', remark: '住宿2晚' };
    const r = calculateHotelEmission(invoice.amount || invoice.totalAmount, null, null, invoice);
    assert(!r.error, '应成功');
    assert(r.city === '上海', `city 应为 上海，实际 ${r.city}`);
    assert(r.method === 'domestic_spend', '有金额应走支出法');
    assert(r.nightsIndicated === 2, '应解析到 nightsIndicated=2');
  })) passed++;

  // ----- 案例3：无金额，仅有间夜 -----
  total++;
  if (runTest('金额 0 + 间夜 2 → 2 × 66.52', () => {
    const r = calculateHotelEmission(0, '上海', 2);
    assert(!r.error, '应成功');
    assert(r.method === 'domestic_nights', r.method);
    assert(r.nights === 2, `nights 应为 2，实际 ${r.nights}`);
    assert(r.factor === hotelDomesticKgPerNight, 'factor 应为 kg/晚');
    assert(Math.abs(r.emissionsKg - 2 * hotelDomesticKgPerNight) < 0.02, `排放应为 ${2 * hotelDomesticKgPerNight}`);
  })) passed++;

  total++;
  if (runTest('cityRates 上海 other=500', () => {
    assert(getCityRate('上海') === 500, '上海标准价应为 500');
  })) passed++;

  total++;
  if (runTest('getFactors 国内住宿晚数因子 = 66.52', () => {
    assert(hotelDomesticKgPerNight === 66.52, '应与 core 63290X001 一致');
    assert(Math.abs(hotelDomesticKgPerCny - 0.2036) < 1e-9, '2.036 t/万元 → 0.2036 kg/元');
  })) passed++;

  console.log('\n========== ' + passed + '/' + total + ' 通过 ==========');
  process.exit(passed === total ? 0 : 1);
}

main();
