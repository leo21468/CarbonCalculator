/**
 * 混合分类演示：税收编码 → BERT → 关键词
 *
 * 测试模糊发票：办公用品、维修费、采购电脑、物流运费。
 * 首次运行会下载 BERT 模型（约 30MB），请保持网络畅通。
 *
 * 运行：node src/nlp/demoHybrid.js
 */

const { classifyHybrid } = require('./hybridClassifier');

const DEMO_TEXTS = [
  '办公用品-订书机5个',
  '维修费',
  '采购电脑一台',
  '物流运费',
];

async function main() {
  console.log('混合分类演示（税收编码 → BERT → 关键词）\n');
  console.log('说明：无税号时使用 BERT；置信度<0.7 时降级为关键词匹配。\n');

  for (const text of DEMO_TEXTS) {
    console.log(`--- "${text}" ---`);
    try {
      const result = await classifyHybrid(text);
      console.log(`  类别: ${result.categoryName} (id=${result.category})`);
      console.log(`  置信度: ${(result.confidence * 100).toFixed(1)}%`);
      console.log(`  来源: ${result.source}`);
    } catch (e) {
      console.error(`  错误: ${e.message}`);
      if (e.message && e.message.includes('fetch')) {
        console.error('  提示：首次运行需下载模型，请检查网络或代理。');
      }
    }
    console.log('');
  }

  console.log('演示结束。');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
