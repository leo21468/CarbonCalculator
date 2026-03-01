/**
 * 差旅住宿核算测试
 *
 * 案例1：上海某酒店发票 ¥1200（无间夜数）→ 反推约 2.4 晚，取整 2 晚
 * 案例2：北京某酒店发票 ¥1600，备注「3晚」→ 直接使用 3 晚
 */

const { extractCity, extractExplicitNights, estimateNights, calculateHotelEmission } = require('./hotelCalculator');
const { getCityRate } = require('./cityRates');
const { getHotelFactor } = require('./hotelFactors');

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
  let passed = 0;
  let total = 0;

  // ----- 案例1：上海 ¥1200，无间夜数 -----
  console.log('【案例1】上海某酒店发票 ¥1200（无间夜数）→ 反推间夜数\n');
  total++;
  if (runTest('estimateNights(1200, "上海") 反推 2 晚', () => {
    const r = estimateNights(1200, '上海');
    assert(!r.error, '应成功');
    assert(r.nights === 2, `nights 应为 2（1200/500=2.4 向下取整），实际 ${r.nights}`);
    assert(r.priceUsed === 500, `priceUsed 应为 500，实际 ${r.priceUsed}`);
    assert(r.method === 'estimated', `method 应为 estimated，实际 ${r.method}`);
    console.log(`    间夜数: ${r.nights}, 标准价: ${r.priceUsed} 元/间·天, 方法: ${r.method}`);
  })) passed++;

  total++;
  if (runTest('calculateHotelEmission(1200, "上海") 排放 = 2 × 65.2', () => {
    const r = calculateHotelEmission(1200, '上海', null);
    assert(!r.error, '应成功');
    assert(r.nights === 2, `nights 应为 2，实际 ${r.nights}`);
    assert(r.factor === 65.2, `上海因子应为 65.2，实际 ${r.factor}`);
    assert(Math.abs(r.emissionsKg - 2 * 65.2) < 0.02, `emissionsKg 应为 130.4，实际 ${r.emissionsKg}`);
    assert(r.method === 'estimated', 'method 应为 estimated');
    console.log(`    排放: ${r.emissionsKg} kgCO2e = ${r.nights} 晚 × ${r.factor} kgCO2e/间夜`);
  })) passed++;

  // ----- 案例2：北京 ¥1600，备注「3晚」 -----
  console.log('\n【案例2】北京某酒店发票 ¥1600，备注「3晚」→ 直接使用 3 晚\n');
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
  if (runTest('calculateHotelEmission(1600, "北京", 3) 使用 3 晚，排放 = 3 × 68.5', () => {
    const r = calculateHotelEmission(1600, '北京', 3);
    assert(!r.error, '应成功');
    assert(r.nights === 3, `nights 应为 3，实际 ${r.nights}`);
    assert(r.method === 'explicit', `method 应为 explicit，实际 ${r.method}`);
    assert(Math.abs(r.emissionsKg - 3 * 68.5) < 0.02, `emissionsKg 应为 205.5，实际 ${r.emissionsKg}`);
    console.log(`    排放: ${r.emissionsKg} kgCO2e = 3 晚 × ${r.factor} kgCO2e/间夜`);
  })) passed++;

  total++;
  if (runTest('传 invoice 时自动 extractCity 与 extractExplicitNights', () => {
    const invoice = { amount: 1600, totalAmount: 1600, sellerName: '上海某酒店', remark: '住宿2晚' };
    const r = calculateHotelEmission(invoice.amount || invoice.totalAmount, null, null, invoice);
    assert(!r.error, '应成功');
    assert(r.city === '上海', `city 应为 上海，实际 ${r.city}`);
    assert(r.nights === 2, `nights 应为 2（备注），实际 ${r.nights}`);
    assert(r.method === 'explicit', '应使用备注间夜数');
  })) passed++;

  // ----- 数据来源校验 -----
  total++;
  if (runTest('cityRates 上海 other=500', () => {
    assert(getCityRate('上海') === 500, '上海标准价应为 500');
  })) passed++;

  total++;
  if (runTest('hotelFactors 北京 68.5', () => {
    assert(getHotelFactor('北京') === 68.5, '北京酒店因子应为 68.5');
  })) passed++;

  console.log('\n========== ' + passed + '/' + total + ' 通过 ==========');
  process.exit(passed === total ? 0 : 1);
}

main();
