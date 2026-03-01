/**
 * PDF 发票解析器
 * 使用 pdf-parse 提取文本，若为扫描件则可用 Tesseract.js 做 OCR（可选）
 * 通过正则提取：发票号码、开票日期、销方/购方、明细及 19 位税收分类编码
 */

const fs = require('fs');
const path = require('path');
const { Invoice } = require('../models/Invoice');

/** 19 位税收分类编码正则 */
const TAX_CODE_19 = /(\d{19})/g;

/**
 * 从文本中提取所有 19 位税收分类编码
 * @param {string} text
 * @returns {string[]}
 */
function extractTaxCodes(text) {
  if (!text || typeof text !== 'string') return [];
  const matches = text.match(TAX_CODE_19);
  return matches ? [...new Set(matches)] : [];
}

/**
 * 用正则从全文提取关键字段（中国增值税发票常见版式）
 * @param {string} text - 票面全文
 * @returns {Object} 键为 Invoice 字段名
 */
function extractByRegex(text) {
  const result = {};
  const t = text.replace(/\s+/g, ' ');

  // 发票号码 / 发票代码
  const fpNum = t.match(/发票号码\s*[：:\s]*(\d+)/);
  if (fpNum) result.invoiceNumber = fpNum[1];
  const fpCode = t.match(/发票代码\s*[：:\s]*(\d+)/);
  if (fpCode) result.invoiceCode = fpCode[1];

  // 开票日期：YYYY年MM月DD日 或 YYYY-MM-DD
  const date1 = t.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/);
  if (date1) {
    result.invoiceDate = `${date1[1]}-${date1[2].padStart(2, '0')}-${date1[3].padStart(2, '0')}`;
  } else {
    const date2 = t.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (date2) result.invoiceDate = date2[0];
  }

  // 销方名称、税号
  const sellerName = t.match(/销[售]*方[：:\s]*名[称]*[：:\s]*([^\s]+(?:\s+[^\s]+)*?)(?=\s*税\s*号|纳税人识别号|$)/);
  if (sellerName) result.sellerName = sellerName[1].trim();
  const sellerTax = t.match(/销[售]*方[^\d]*税[号]*[：:\s]*(\d{15}|\d{17}|\d{18}|\d{19})/);
  if (sellerTax) result.sellerTaxId = sellerTax[1];

  // 购方名称、税号
  const buyerName = t.match(/购[买]*方[：:\s]*名[称]*[：:\s]*([^\s]+(?:\s+[^\s]+)*?)(?=\s*税\s*号|纳税人识别号|$)/);
  if (buyerName) result.buyerName = buyerName[1].trim();
  const buyerTax = t.match(/购[买]*方[^\d]*税[号]*[：:\s]*(\d{15}|\d{17}|\d{18}|\d{19})/);
  if (buyerTax) result.buyerTaxId = buyerTax[1];

  // 价税合计 / 总金额
  const total = t.match(/价税合计[（(]*小写[）)]*[：:\s]*[\d,，.．]+\s*[＊*]?\s*([\d.]+)/);
  if (total) result.totalAmount = parseFloat(total[1].replace(/,|，/g, '')) || 0;

  return result;
}

/**
 * 从表格/多行文本中尝试解析明细行（名称、税收分类编码、金额、数量、单位、单价）
 * @param {string} text
 * @returns {{ items: Array<{name, taxCode, amount, quantity, unit, price}>, totalAmount: number }}
 */
function extractItemsFromText(text) {
  const items = [];
  const taxCodes = extractTaxCodes(text);
  const lines = text.split(/\n/).map((s) => s.trim()).filter(Boolean);

  // 表头关键词
  const nameKeywords = ['货物或应税劳务名称', '项目名称', '名称', '劳务'];
  const taxCodeKeywords = ['税收分类编码', '编码', 'spbm', 'SSBM'];
  const amountKeywords = ['金额', 'je', 'JE'];
  const qtyKeywords = ['数量', 'sl', 'SL'];
  const unitKeywords = ['单位', 'dw', 'DW'];
  const priceKeywords = ['单价', 'dj', 'DJ'];

  let totalAmount = 0;
  let headerLineIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (nameKeywords.some((k) => line.includes(k))) {
      headerLineIdx = i;
      break;
    }
  }

  if (headerLineIdx >= 0) {
    // Merge cross-line item names: a line starting with '*' but not ending with a digit may be
    // continued on the next line (e.g. "*研发和技术服务*技术服" + "务费 1 157.43")
    const mergedLines = [];
    let i = headerLineIdx + 1;
    while (i < lines.length) {
      const line = lines[i];
      if (line.startsWith('*') && !/\d/.test(line)) {
        // Looks like an incomplete item name line — merge with next
        const next = lines[i + 1] || '';
        mergedLines.push(line + next);
        i += 2;
      } else {
        mergedLines.push(line);
        i++;
      }
    }

    for (const line of mergedLines) {
      if (/合计|价税合计|小计/.test(line)) break;
      const numParts = line.match(/[\d.]+/g) || [];
      const codeMatch = line.match(/\d{19}/);
      const taxCode = codeMatch ? codeMatch[0] : (taxCodes[items.length] || undefined);
      const amount = numParts.length ? parseFloat(numParts[numParts.length - 1].replace(/,|，/g, '')) : 0;
      const namePart = line.replace(/\d{19}/g, '').replace(/[\d.]+/g, '').trim();
      const name = namePart || '';
      if (!name && !taxCode && amount === 0) continue;
      items.push({
        name,
        taxCode,
        amount: amount || 0,
        quantity: numParts[1] ?? null,
        unit: null,
        price: numParts[0] ?? 0,
      });
      totalAmount += amount || 0;
    }
  }

  if (items.length === 0 && taxCodes.length > 0) {
    items.push({ name: '', taxCode: taxCodes[0], amount: 0, quantity: null, unit: null, price: 0 });
  }

  return { items, totalAmount };
}

/**
 * 解析 PDF 文件：先 pdf-parse 取文本，不足时可用 Tesseract.js OCR（此处仅占位，可按需接入）
 * @param {string} filePath - PDF 文件路径
 * @param {Object} [options] - { useOcr: boolean } 是否在文本过少时启用 OCR
 * @returns {Promise<Invoice>}
 */
async function parsePdfFile(filePath, options = {}) {
  const fullPath = path.resolve(filePath);
  let pdfParse;
  try {
    pdfParse = require('pdf-parse');
  } catch (e) {
    throw new Error('请安装 pdf-parse: npm install pdf-parse');
  }

  const dataBuffer = await fs.promises.readFile(fullPath);
  const pdfData = await pdfParse(dataBuffer);
  let text = (pdfData && pdfData.text) || '';

  // 若文本过少且启用 OCR，可用 tesseract.js 对首页渲染图做 OCR（需配合 pdf-to-img 等）
  if (text.length < 50 && options.useOcr) {
    try {
      const Tesseract = require('tesseract.js');
      const { createCanvas } = require('canvas');
      // 此处简化：仅当 pdf-parse 无文本时记录日志，实际可接 pdf2pic 等生成图片再 OCR
      console.warn('[pdfParser] 文本过少，建议使用带 OCR 的流程或 paddle-ocr-node 处理扫描件');
    } catch (ocrErr) {
      console.warn('[pdfParser] OCR 未配置:', ocrErr.message);
    }
  }

  const fields = extractByRegex(text);
  const { items, totalAmount: itemsTotal } = extractItemsFromText(text);
  const totalAmount = fields.totalAmount != null && fields.totalAmount > 0 ? fields.totalAmount : itemsTotal;

  const invoice = new Invoice({
    invoiceNumber: fields.invoiceNumber ?? null,
    invoiceDate: fields.invoiceDate ?? null,
    sellerName: fields.sellerName ?? null,
    sellerTaxId: fields.sellerTaxId ?? null,
    buyerName: fields.buyerName ?? null,
    buyerTaxId: fields.buyerTaxId ?? null,
    items,
    totalAmount,
    fileType: 'PDF',
  });

  return invoice;
}

module.exports = { parsePdfFile, extractByRegex, extractItemsFromText, extractTaxCodes };
