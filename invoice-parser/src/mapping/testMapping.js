/**
 * 税收分类编码 → 碳排放范围 映射测试
 *
 * 测试用例覆盖：
 * - 燃料类发票（煤炭、汽油）→ Scope 1
 * - 电力发票 → Scope 2
 * - 润滑油发票（例外规则）→ Scope 3
 * - 服务类发票 → Scope 3
 * - 普通商品发票 → Scope 3
 *
 * GHG Protocol 依据见 scopeMappingTable.js 与 classifyByTaxCode.js 注释。
 * 数据来源为模拟；生产环境需对接国家税务总局 API。
 */

const { classifyByTaxCode } = require('./classifyByTaxCode');

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
  console.log('税收分类编码 → 排放范围 映射测试\n');

  let passed = 0;
  let total = 0;

  // 1. 燃料类（煤炭）→ Scope 1
  total++;
  if (runTest('燃料类-煤炭 → Scope 1', () => {
    const r = classifyByTaxCode('1010100000000000000', '原煤');
    assert(r.scope === 1, `expected scope 1, got ${r.scope}`);
    assert(r.reason.includes('煤炭') || r.reason.includes('101'), 'reason 应包含匹配依据');
  })) passed++;

  // 2. 燃料类（汽油）→ Scope 1
  total++;
  if (runTest('燃料类-汽油 → Scope 1', () => {
    const r = classifyByTaxCode('1070100000000000000', '汽油');
    assert(r.scope === 1, `expected scope 1, got ${r.scope}`);
    assert(r.reason.length > 0, '应有 reason');
  })) passed++;

  // 3. 电力发票 → Scope 2
  total++;
  if (runTest('电力发票 → Scope 2', () => {
    const r = classifyByTaxCode('1090100000000000000', '电力');
    assert(r.scope === 2, `expected scope 2, got ${r.scope}`);
    assert(r.reason.includes('Scope 2') || r.reason.includes('电力') || r.reason.includes('109'), 'reason 应包含 Scope 2 或电力');
  })) passed++;

  // 4. 润滑油发票（例外规则）→ Scope 3
  total++;
  if (runTest('润滑油发票（例外规则）→ Scope 3', () => {
    // 税号属石油加工（默认 Scope 1），但货物名含「润滑油」应排除 → Scope 3
    const r = classifyByTaxCode('1070200000000000000', '润滑油');
    assert(r.scope === 3, `expected scope 3 (exception), got ${r.scope}`);
    assert(r.reason.includes('润滑油') || r.reason.includes('排除'), 'reason 应说明排除规则');
  })) passed++;

  // 5. 服务类发票 → Scope 3
  total++;
  if (runTest('服务类发票 → Scope 3', () => {
    const r = classifyByTaxCode('3040502000000000000', '技术服务');
    assert(r.scope === 3, `expected scope 3, got ${r.scope}`);
  })) passed++;

  // 6. 普通商品发票 → Scope 3
  total++;
  if (runTest('普通商品发票 → Scope 3', () => {
    const r = classifyByTaxCode('6010100000000000000', '办公用品');
    assert(r.scope === 3, `expected scope 3, got ${r.scope}`);
  })) passed++;

  // 7. 无税号、无名称时兜底 Scope 3
  total++;
  if (runTest('无税号兜底 → Scope 3', () => {
    const r = classifyByTaxCode('', '');
    assert(r.scope === 3, `expected scope 3 default, got ${r.scope}`);
    assert(r.confidence === '低', `expected 低 confidence, got ${r.confidence}`);
  })) passed++;

  console.log('\n---');
  console.log(`通过: ${passed}/${total}`);
  process.exit(passed === total ? 0 : 1);
}

main();
