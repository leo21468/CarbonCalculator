/**
 * 动态因子匹配演示脚本
 *
 * 案例1：冷轧钢板 50 吨 → 应匹配物理因子（钢材），高置信度
 * 案例2：办公用品 ¥5000 → 应匹配 EEIO 因子，中置信度
 * 案例3：杂项费用 → 应降级为默认因子，低置信度
 */

const { matchFactor } = require('./factorMatcher');
const { toKgCO2e } = require('../factors/factorManager');

function runDemo() {
  console.log('========== 动态因子匹配演示 ==========\n');

  // 案例1：冷轧钢板 50 吨 → 物理因子
  const case1 = {
    name: '冷轧钢板',
    taxCode: '1080101010000000000',
    amount: 250000,
    quantity: 50,
    unit: '吨',
    price: 5000,
  };
  const r1 = matchFactor(case1, { sellerAddress: '河北省石家庄市' });
  console.log('【案例1】冷轧钢板 50 吨');
  console.log('  匹配类型:', r1.matchType);
  console.log('  置信度:', r1.confidence);
  console.log('  因子:', r1.factor?.name, r1.factor?.unit);
  console.log('  依据:', r1.reason);
  const e1 = toKgCO2e(r1.factor, 50, '吨');
  console.log('  排放量:', e1.emissionKg.toFixed(2), 'kgCO2e\n');

  // 案例2：办公用品 ¥5000 → EEIO
  const case2 = {
    name: '办公用品',
    amount: 5000,
    quantity: null,
    unit: '',
  };
  const r2 = matchFactor(case2);
  console.log('【案例2】办公用品 ¥5000');
  console.log('  匹配类型:', r2.matchType);
  console.log('  置信度:', r2.confidence);
  console.log('  因子:', r2.factor?.name, r2.factor?.unit);
  console.log('  依据:', r2.reason);
  const e2 = toKgCO2e(r2.factor, 5000, 'CNY');
  console.log('  排放量:', e2.emissionKg.toFixed(2), 'kgCO2e\n');

  // 案例3：杂项费用 → 默认因子，低置信度
  const case3 = {
    name: '杂项费用',
    amount: 10000,
  };
  const r3 = matchFactor(case3);
  console.log('【案例3】杂项费用');
  console.log('  匹配类型:', r3.matchType);
  console.log('  置信度:', r3.confidence);
  console.log('  因子:', r3.factor?.name, r3.factor?.unit);
  console.log('  依据:', r3.reason);
  const e3 = toKgCO2e(r3.factor, 10000, 'CNY');
  console.log('  排放量:', e3.emissionKg.toFixed(2), 'kgCO2e\n');

  console.log('========== 演示结束 ==========');
}

if (require.main === module) {
  runDemo();
}

module.exports = { runDemo };
