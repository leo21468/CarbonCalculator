/**
 * 验证 BERT 模型是否加载成功并输出一次分类结果
 *
 * 使用本地已准备模型时请设置：
 *   TRANSFORMERS_CACHE=模型根目录（其下需有 Xenova/paraphrase-multilingual-MiniLM-L12-v2/ 及 tokenizer.json、*.onnx 等）
 *   TRANSFORMERS_LOCAL_ONLY=1
 * 然后运行：node src/nlp/verifyBert.js
 */

const { classifyWithBERT } = require('./bertClassifier');

async function main() {
  console.log('正在加载 BERT 模型...');
  const testText = '办公用品-订书机5个';
  try {
    const result = await classifyWithBERT(testText);
    console.log('BERT 加载成功。');
    console.log(`测试文本: "${testText}"`);
    console.log(`  预测类别: ${result.categoryName} (id=${result.category})`);
    console.log(`  置信度: ${(result.confidence * 100).toFixed(1)}%`);
  } catch (e) {
    console.error('BERT 加载或推理失败:', e.message);
    if (e.message && e.message.includes('fetch')) {
      console.error('请确认：1) 模型已放入 TRANSFORMERS_CACHE 或默认缓存目录；2) 或设置环境变量 TRANSFORMERS_CACHE 指向模型目录');
    }
    process.exit(1);
  }
}

main();
