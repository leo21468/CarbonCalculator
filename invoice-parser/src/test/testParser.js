/**
 * 发票解析引擎测试脚本
 * 测试 OFD / PDF / XML / JSON 四种格式的解析，以及错误处理
 * 运行: npm test 或 node src/test/testParser.js
 */

const path = require('path');
const { parseInvoice, Invoice } = require('../parser/index');

const FIXTURES = path.join(__dirname, 'fixtures');

async function runTest(name, fn) {
  try {
    await fn();
    console.log(`  ✓ ${name}`);
    return true;
  } catch (e) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${e.message}`);
    return false;
  }
}

async function main() {
  console.log('发票解析引擎测试\n');

  let passed = 0;
  let total = 0;

  // 1. JSON 格式
  total++;
  const jsonPath = path.join(FIXTURES, 'sample.json');
  if (await runTest('JSON 解析 (sample.json)', async () => {
    const inv = await parseInvoice(jsonPath);
    if (!(inv instanceof Invoice)) throw new Error('未返回 Invoice 实例');
    if (inv.fileType !== 'JSON') throw new Error(`fileType 应为 JSON，实际 ${inv.fileType}`);
    if (!inv.invoiceNumber || inv.invoiceNumber !== '12345678') throw new Error('invoiceNumber 解析错误');
    if (!inv.items || inv.items.length === 0) throw new Error('items 为空');
    const code = inv.items[0].taxCode;
    if (!code || code.length !== 19) throw new Error('19 位税收分类编码未正确提取');
  })) passed++;

  // 2. XML 格式
  total++;
  const xmlPath = path.join(FIXTURES, 'sample.xml');
  if (await runTest('XML 解析 (sample.xml)', async () => {
    const inv = await parseInvoice(xmlPath);
    if (!(inv instanceof Invoice)) throw new Error('未返回 Invoice 实例');
    if (inv.fileType !== 'XML') throw new Error(`fileType 应为 XML，实际 ${inv.fileType}`);
    if (!inv.sellerName || !inv.buyerName) throw new Error('销方/购方未解析');
    if (!inv.items || inv.items.length === 0) throw new Error('items 为空');
    const code = inv.items[0].taxCode;
    if (!code || code.length !== 19) throw new Error('19 位税收分类编码未正确提取');
  })) passed++;

  // 3. PDF 格式（若存在 fixture）
  const pdfPath = path.join(FIXTURES, 'sample.pdf');
  total++;
  if (await runTest('PDF 解析 (sample.pdf，若存在)', async () => {
    const fs = require('fs');
    if (!fs.existsSync(pdfPath)) {
      console.log('    (跳过：无 sample.pdf)');
      return;
    }
    const inv = await parseInvoice(pdfPath);
    if (!(inv instanceof Invoice)) throw new Error('未返回 Invoice 实例');
    if (inv.fileType !== 'PDF') throw new Error(`fileType 应为 PDF，实际 ${inv.fileType}`);
  })) passed++;

  // 4. OFD 格式（若存在 fixture）
  const ofdPath = path.join(FIXTURES, 'sample.ofd');
  total++;
  if (await runTest('OFD 解析 (sample.ofd，若存在)', async () => {
    const fs = require('fs');
    if (!fs.existsSync(ofdPath)) {
      console.log('    (跳过：无 sample.ofd)');
      return;
    }
    const inv = await parseInvoice(ofdPath);
    if (!(inv instanceof Invoice)) throw new Error('未返回 Invoice 实例');
    if (inv.fileType !== 'OFD') throw new Error(`fileType 应为 OFD，实际 ${inv.fileType}`);
  })) passed++;

  // 5. 错误处理：文件不存在
  total++;
  if (await runTest('错误处理：不存在的文件', async () => {
    try {
      await parseInvoice(path.join(FIXTURES, 'not-exist.json'));
    } catch (e) {
      if (e.message.includes('不存在')) return;
      throw e;
    }
    throw new Error('应抛出“文件不存在”错误');
  })) passed++;

  // 6. 错误处理：不支持的类型
  total++;
  if (await runTest('错误处理：不支持的类型', async () => {
    try {
      await parseInvoice(path.join(FIXTURES, 'sample.json'), 'TXT');
    } catch (e) {
      if (e.message.includes('不支持')) return;
      throw e;
    }
    throw new Error('应抛出“不支持”错误');
  })) passed++;

  console.log('\n---');
  console.log(`通过: ${passed}/${total}`);
  process.exit(passed === total ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
