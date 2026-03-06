/**
 * PDF 发票解析器
 * 使用 pdf-parse 提取文本；扫描件时使用 Tesseract.js 做 OCR
 * 通过正则提取：发票号码、开票日期、销方/购方、明细及 19 位税收分类编码
 *
 * 依赖（扫描件 OCR 需要）：
 *   npm install tesseract.js pdf2pic
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
 * 中国增值税发票列顺序：名称、规格型号、单位、数量、单价、金额（不含税）、税率、税额
 * 碳排放核算使用不含税金额（倒数第二列），不使用税额（最后一列）
 * @param {string} text
 * @returns {{ items: Array<{name, taxCode, amount, quantity, unit, price}>, totalAmount: number }}
 */
function extractItemsFromText(text) {
  const items = [];
  const taxCodes = extractTaxCodes(text);
  const lines = text.split(/\n/).map((s) => s.trim()).filter(Boolean);

  // 表头关键词
  const nameKeywords = ['货物或应税劳务名称', '项目名称', '名称', '劳务'];

  let totalAmount = 0;
  let headerLineIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    if (nameKeywords.some((k) => lines[i].includes(k))) {
      headerLineIdx = i;
      break;
    }
  }

  if (headerLineIdx >= 0) {
    // 合并跨行明细名称：以 '*' 开头的行，将后续纯文本续行（无金额/税率/纯数字）合并
    const mergedLines = [];
    let i = headerLineIdx + 1;
    while (i < lines.length) {
      const line = lines[i];
      if (line.startsWith('*')) {
        // 提取名称部分（第一个空格前的 *cat*name）和数据部分
        const starMatch = line.match(/^(\*[^*]+\*[^\s]*)(.*)/);
        const namePart = starMatch ? starMatch[1] : line;
        const dataPart = starMatch ? starMatch[2] : '';
        const dataHasChinese = /[\u4e00-\u9fff]/.test(dataPart);
        // 若数据部分不含中文（纯数字行），向前看续行并合并
        if (!dataHasChinese) {
          let continuation = '';
          let j = i + 1;
          while (j < lines.length) {
            const nxt = lines[j].trim();
            if (!nxt) { j++; continue; }
            if (nxt.startsWith('*')) break;
            if (/合计|价税合计|小计|名称|项目名称/.test(nxt.replace(/\s/g, ''))) break;
            // 续行条件：不含小数金额、不含税率、不是纯数字行
            if (/\d+(?:\.\d+)?%/.test(nxt) || /(?<![a-zA-Z])\d+\.\d+/.test(nxt) || /^[\d\s,.]+$/.test(nxt)) break;
            continuation += nxt;
            j++;
          }
          mergedLines.push(namePart + continuation + dataPart);
          i = j;
        } else {
          mergedLines.push(line);
          i++;
        }
      } else {
        mergedLines.push(line);
        i++;
      }
    }

    for (const line of mergedLines) {
      if (/合计|价税合计|小计/.test(line)) break;
      // 先移除税率列（如 "13%"、"9%"），避免税率数字被误认为金额
      const lineNoRate = line.replace(/\d+(?:\.\d+)?%/g, '');
      // 按空白分词后保留纯数字 token，排除混合字母+数字的规格字符串（如 400g、12V）
      const numParts = lineNoRate.split(/\s+/).filter(t => /^[\d,，]+(?:\.\d+)?$/.test(t.trim())).map(t => t.trim()).filter(Boolean);
      const codeMatch = line.match(/\d{19}/);
      const taxCode = codeMatch ? codeMatch[0] : (taxCodes[items.length] || undefined);
      // 中国增值税发票列顺序：数量、单价、金额（不含税）、税额
      // 取倒数第二个数字为不含税金额，与 Python 端 _extract_lines_from_text 逻辑一致
      // 只有一个数字时，该数字即为金额（index 0）
      const amountIdx = numParts.length >= 2 ? numParts.length - 2 : 0;
      const amount = numParts.length ? parseFloat(numParts[amountIdx].replace(/,|，/g, '')) : 0;
      const namePart = line.replace(/\d{19}/g, '').replace(/[\d.]+%?/g, '').trim();
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
 * 使用 Tesseract.js 对 PDF 首页图片做 OCR（扫描件兜底）
 * 需要：npm install tesseract.js pdf2pic
 * @param {string} filePath
 * @returns {Promise<string>} OCR 文本
 */
async function ocrPdfWithTesseract(filePath) {
  let pdf2pic, Tesseract;
  try {
    pdf2pic = require('pdf2pic');
    Tesseract = require('tesseract.js');
  } catch (e) {
    throw new Error('扫描件 OCR 需安装依赖: npm install tesseract.js pdf2pic');
  }

  const convert = pdf2pic.fromPath(filePath, {
    density: 150,
    saveFilename: '_invoice_ocr_tmp',
    savePath: require('os').tmpdir(),
    format: 'png',
    width: 1654,
    height: 2339,
  });

  const page = await convert(1, { responseType: 'image' });
  const imgPath = page.path;

  try {
    const { data } = await Tesseract.recognize(imgPath, 'chi_sim+eng', {
      logger: () => {},
    });
    return data.text || '';
  } finally {
    try { fs.unlinkSync(imgPath); } catch (_) {}
  }
}

/**
 * 解析 PDF 文件：pdf-parse 取文本，扫描件时用 Tesseract.js OCR
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

  // 文本过少（扫描件）且启用 OCR 时，使用 Tesseract.js
  if (text.trim().length < 50 && options.useOcr !== false) {
    try {
      text = await ocrPdfWithTesseract(fullPath);
    } catch (ocrErr) {
      console.warn('[pdfParser] OCR 失败，将使用空文本继续:', ocrErr.message);
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

module.exports = { parsePdfFile, extractByRegex, extractItemsFromText, extractTaxCodes, ocrPdfWithTesseract };
