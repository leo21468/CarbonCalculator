/**
 * NLP 关键词抽取与模糊匹配 - 测试
 *
 * 测试用例：
 * - "采购*办公桌*10张" -> 关键词 办公桌，匹配 办公-家具
 * - "支付*成品油*费用" -> 关键词 成品油，匹配 能源-成品油
 * - "维修费-电脑主板" -> 关键词 维修/电脑，匹配 服务-维修 / 办公-设备
 * - "办公用品-订书机5个" -> 关键词 办公用品/订书机，匹配 办公-用品
 *
 * 输出关键词、匹配结果，并计算准确率。
 */

const { processGoodsName } = require('./index');

const TEST_CASES = [
  { input: '采购*办公桌*10张', expectKeywords: ['办公桌'], expectMatch: '办公-家具' },
  { input: '支付*成品油*费用', expectKeywords: ['成品油'], expectMatch: '能源-成品油' },
  { input: '维修费-电脑主板', expectKeywords: ['维修', '电脑'], expectMatchAny: ['服务-维修', '办公-设备'] },
  { input: '办公用品-订书机5个', expectKeywords: ['办公用品', '订书机'], expectMatch: '办公-用品' },
];

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
  console.log('NLP 关键词抽取与模糊匹配测试\n');

  let passed = 0;
  let total = 0;
  let keywordHits = 0;
  let matchHits = 0;

  TEST_CASES.forEach((tc, i) => {
    console.log(`\n--- 案例 ${i + 1}: "${tc.input}" ---`);
    const result = processGoodsName(tc.input);
    console.log('  关键词:', result.keywords.map((k) => k.keyword).join(', ') || '(无)');
    console.log('  置信度:', result.confidence);
    console.log('  匹配结果:', result.matches.map((m) => (m.matched ? `${m.keyword}→${m.matched}(${m.similarity?.toFixed(2)})` : `${m.keyword}→(无)`)).join('; '));
    console.log('  摘要:', result.summary);

    total++;
    const hasExpectedKeywords =
      !tc.expectKeywords ||
      tc.expectKeywords.every((ek) => result.keywords.some((k) => k.keyword === ek || k.keyword.includes(ek)));
    if (runTest(`案例${i + 1} 关键词抽取`, () => {
      if (!hasExpectedKeywords) {
        throw new Error(`期望含关键词 ${tc.expectKeywords?.join('/')}，实际 ${result.keywords.map((k) => k.keyword).join(',')}`);
      }
    })) {
      passed++;
      keywordHits += hasExpectedKeywords ? 1 : 0;
    }

    total++;
    const hasMatch =
      tc.expectMatch
        ? result.matches.some((m) => m.matched === tc.expectMatch)
        : tc.expectMatchAny
          ? result.matches.some((m) => m.matched && tc.expectMatchAny.includes(m.matched))
          : result.matches.some((m) => m.matched != null);
    if (runTest(`案例${i + 1} 模糊匹配`, () => {
      if (!hasMatch) {
        throw new Error(`期望匹配 ${tc.expectMatch || tc.expectMatchAny?.join('/')}，实际 ${result.matches.map((m) => m.matched).join(',')}`);
      }
    })) {
      passed++;
      matchHits += hasMatch ? 1 : 0;
    }
  });

  const accuracy = total > 0 ? ((passed / total) * 100).toFixed(1) : 0;
  console.log('\n==========');
  console.log(`通过: ${passed}/${total}`);
  console.log(`准确率: ${accuracy}%`);
  process.exit(passed === total ? 0 : 1);
}

main();
