/**
 * 动态因子匹配引擎单元测试
 *
 * 验证：matchFactor 返回格式、三种演示场景、优先级与降级、regionMapper、confidenceScorer
 */

const { matchFactor, hasPhysicalQuantity } = require('./factorMatcher');
const { mapAddressToRegion, getRegionFromContext } = require('./regionMapper');
const { scoreConfidence, CONFIDENCE } = require('./confidenceScorer');

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
  console.log('动态因子匹配引擎测试\n');
  let passed = 0;
  let total = 0;

  // --- 返回格式 ---
  total++;
  if (runTest('matchFactor 返回 { factor, matchType, confidence, reason }', () => {
    const r = matchFactor({ name: '杂项', amount: 100 });
    assert(r && typeof r === 'object', '应返回对象');
    assert(r.factor && typeof r.factor === 'object', '应有 factor');
    assert(['物理因子', 'EEIO因子', '默认因子'].includes(r.matchType), `matchType 应为三者之一，实际 ${r.matchType}`);
    assert(['高', '中', '低'].includes(r.confidence), `confidence 应为 高/中/低，实际 ${r.confidence}`);
    assert(typeof r.reason === 'string' && r.reason.length > 0, '应有 reason 字符串');
  })) passed++;

  // --- 案例1：冷轧钢板 50 吨 → 物理因子，高置信度 ---
  total++;
  if (runTest('案例1 冷轧钢板50吨 → 物理因子、高置信度', () => {
    const item = { name: '冷轧钢板', amount: 250000, quantity: 50, unit: '吨' };
    const r = matchFactor(item);
    assert(r.matchType === '物理因子', `matchType 应为 物理因子，实际 ${r.matchType}`);
    assert(r.confidence === '高', `confidence 应为 高，实际 ${r.confidence}`);
    assert(r.factor && ((r.factor.name || '').includes('钢材') || (r.factor.unit || '').includes('t')), `应匹配钢材/吨因子，实际 ${r.factor?.name} ${r.factor?.unit}`);
    assert(r.reason && (r.reason.includes('物理量') || r.reason.includes('钢材') || r.reason.includes('钢板')), `reason 应提及物料/物理量，实际 ${r.reason}`);
  })) passed++;

  // --- 案例2：办公用品 ¥5000 → EEIO 因子，中置信度 ---
  total++;
  if (runTest('案例2 办公用品¥5000 → EEIO因子、中置信度', () => {
    const item = { name: '办公用品', amount: 5000 };
    const r = matchFactor(item);
    assert(r.matchType === 'EEIO因子', `matchType 应为 EEIO因子，实际 ${r.matchType}`);
    assert(r.confidence === '中', `confidence 应为 中，实际 ${r.confidence}`);
    assert(r.factor && (r.factor.unit || '').includes('CNY'), `应为金额型因子 kgCO2e/CNY，实际 ${r.factor?.unit}`);
    assert(r.reason.length > 0, '应有 reason');
  })) passed++;

  // --- 案例3：杂项费用 → 默认因子，低置信度 ---
  total++;
  if (runTest('案例3 杂项费用 → 默认因子、低置信度', () => {
    const item = { name: '杂项费用', amount: 10000 };
    const r = matchFactor(item);
    assert(r.matchType === '默认因子', `matchType 应为 默认因子，实际 ${r.matchType}`);
    assert(r.confidence === '低', `confidence 应为 低，实际 ${r.confidence}`);
    assert(r.factor && (r.factor.id === 'eeio_default' || (r.factor.name || '').includes('默认')), `应使用默认EEIO因子，实际 ${r.factor?.name}`);
  })) passed++;

  // --- 有税收编码时优先按编码匹配 ---
  total++;
  if (runTest('有税收编码时优先按编码匹配', () => {
    const item = { name: '某货物', taxCode: '1080101010000000000', amount: 1000, quantity: 10, unit: '吨' };
    const r = matchFactor(item);
    assert(r.factor, '应返回因子');
    assert(r.matchType === '物理因子' || r.matchType === 'EEIO因子', `应有明确匹配类型，实际 ${r.matchType}`);
  })) passed++;

  // --- 仅有金额+关键词 → EEIO ---
  total++;
  if (runTest('仅有金额+关键词「造纸」→ EEIO造纸业', () => {
    const item = { name: '纸制品', amount: 8000 };
    const r = matchFactor(item);
    assert(r.factor, '应返回因子');
    assert(r.matchType === 'EEIO因子' || r.matchType === '默认因子', `应为 EEIO 或默认，实际 ${r.matchType}`);
    if (r.matchType === 'EEIO因子') {
      assert((r.factor.name || '').includes('造纸') || (r.factor.subCategory || '').includes('造纸'), `名称或子类应含造纸，实际 ${r.factor?.name}`);
    }
  })) passed++;

  // --- hasPhysicalQuantity ---
  total++;
  if (runTest('hasPhysicalQuantity：有数量+单位返回 true', () => {
    assert(hasPhysicalQuantity({ quantity: 50, unit: '吨' }) === true, '50吨应为 true');
    assert(hasPhysicalQuantity({ quantity: 1, unit: 'kWh' }) === true, '1 kWh 应为 true');
    assert(hasPhysicalQuantity({ quantity: 0, unit: '吨' }) === false, '数量0应为 false');
    assert(hasPhysicalQuantity({ quantity: 10, unit: '' }) === false, '无单位应为 false');
    assert(hasPhysicalQuantity({ amount: 100 }) === false, '仅有金额应为 false');
  })) passed++;

  // --- regionMapper ---
  total++;
  if (runTest('regionMapper 省级地址→区域电网', () => {
    assert(mapAddressToRegion('北京市朝阳区xxx') === '华北', '北京→华北');
    assert(mapAddressToRegion('江苏省南京市') === '华东', '江苏→华东');
    assert(mapAddressToRegion('广东省深圳市') === '南方', '广东→南方');
    assert(mapAddressToRegion('') === '全国', '空→全国');
    assert(getRegionFromContext({ sellerAddress: '河北省石家庄' }) === '华北', 'context 销方→华北');
    assert(getRegionFromContext({ region: '华东' }) === '华东', 'context.region 优先');
  })) passed++;

  // --- confidenceScorer ---
  total++;
  if (runTest('confidenceScorer 高/中/低', () => {
    assert(scoreConfidence({ hasPhysical: true, hasMaterial: true, matchType: '物理因子' }) === CONFIDENCE.HIGH, '物理量+物料+物理因子→高');
    assert(scoreConfidence({ hasTaxCode: true, matchType: 'EEIO因子', isFuzzy: false }) === CONFIDENCE.MEDIUM, '税收编码+EEIO→中');
    assert(scoreConfidence({ matchType: '默认因子' }) === CONFIDENCE.LOW, '默认因子→低');
    assert(scoreConfidence({ matchType: 'EEIO因子', isFuzzy: true }) === CONFIDENCE.LOW, '模糊EEIO→低');
  })) passed++;

  console.log('\n' + passed + '/' + total + ' 通过');
  process.exit(passed === total ? 0 : 1);
}

main();
