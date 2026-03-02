/**
 * OFD 发票解析器
 * OFD 为 ZIP 包，内含 XML（如 Document.xml、Pages/Page_*.xml、发票描述 XML 等）
 * 解压后解析 XML，提取发票结构化字段及 19 位税收分类编码
 */

const fs = require('fs');
const path = require('path');
const JSZip = require('jszip');
const { XMLParser } = require('fast-xml-parser');
const { Invoice } = require('../models/Invoice');

/** 19 位税收分类编码正则 */
const TAX_CODE_19 = /^\d{19}$/;

/**
 * 从 XML 对象中递归查找 19 位税收分类编码
 * @param {any} node
 * @returns {string[]}
 */
function findTaxCodes(node) {
  const codes = [];
  if (!node || typeof node !== 'object') return codes;
  if (Array.isArray(node)) {
    node.forEach((child) => codes.push(...findTaxCodes(child)));
    return codes;
  }
  for (const value of Object.values(node)) {
    if (typeof value === 'string' && TAX_CODE_19.test(value.trim())) codes.push(value.trim());
    else if (typeof value === 'object') codes.push(...findTaxCodes(value));
  }
  return codes;
}

function getString(node, keys) {
  if (!node || typeof node !== 'object') return null;
  for (const k of keys) {
    const v = node[k];
    if (v != null && typeof v === 'string' && v.trim()) return v.trim();
    if (v != null && typeof v === 'object' && v['#text']) return String(v['#text']).trim();
  }
  return null;
}

/**
 * 解析 OFD 包：解压并查找发票相关 XML，提取字段
 * @param {string} filePath - OFD 文件路径
 * @returns {Promise<Invoice>}
 */
async function parseOfdFile(filePath) {
  const fullPath = path.resolve(filePath);
  const buffer = await fs.promises.readFile(fullPath);
  const zip = await JSZip.loadAsync(buffer);
  const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_', trimValues: true });

  let invoiceNumber = null;
  let invoiceDate = null;
  let sellerName = null;
  let sellerTaxId = null;
  let buyerName = null;
  let buyerTaxId = null;
  const allTaxCodes = [];
  let items = [];
  let totalAmount = 0;

  // 常见 OFD 内路径：发票 XML 可能在 Doc_0/ 或 根目录
  const names = Object.keys(zip.files);
  const xmlNames = names.filter((n) => /\.xml$/i.test(n) && !n.includes('__MACOSX'));

  for (const name of xmlNames) {
    const entry = zip.file(name);
    if (!entry) continue;
    const content = await entry.async('string');
    let root;
    try {
      root = parser.parse(content);
    } catch (e) {
      continue;
    }
    const data = root && typeof root === 'object' ? (root.Invoice || root.invoice || root.Document || root.document || root) : {};
    const flat = data['ofd:Document'] || data['Document'] || data['Body'] || data['BODY'] || data;

    invoiceNumber = invoiceNumber || getString(flat, ['invoiceNumber', 'fpdm', 'FPDM', '发票号码']);
    invoiceDate = invoiceDate || getString(flat, ['invoiceDate', 'kprq', 'KPRQ', '开票日期']);
    sellerName = sellerName || getString(flat, ['sellerName', 'xfmc', 'XFMC', '销方名称']);
    sellerTaxId = sellerTaxId || getString(flat, ['sellerTaxId', 'xfsbh', 'XFSBH', '销方税号']);
    buyerName = buyerName || getString(flat, ['buyerName', 'gfmc', 'GFMC', '购方名称']);
    buyerTaxId = buyerTaxId || getString(flat, ['buyerTaxId', 'gfsbh', 'GFSBH', '购方税号']);

    allTaxCodes.push(...findTaxCodes(flat));

    const list = flat.FPDetail || flat.fpDetail || flat.Detail || flat.Items || flat.items ||
      (flat.COMMON_FPKJ_XMXXS && flat.COMMON_FPKJ_XMXXS.COMMON_FPKJ_XMXX) ||
      flat.COMMON_FPKJ_XMXX || [];
    const arr = Array.isArray(list) ? list : list.Item ? (Array.isArray(list.Item) ? list.Item : [list.Item]) : list.Row ? (Array.isArray(list.Row) ? list.Row : [list.Row]) : list.COMMON_FPKJ_XMXX ? (Array.isArray(list.COMMON_FPKJ_XMXX) ? list.COMMON_FPKJ_XMXX : [list.COMMON_FPKJ_XMXX]) : [];
    if (arr.length && items.length === 0) {
      arr.forEach((row, idx) => {
        const name = getString(row, ['name', 'hwmc', 'goodsName', '项目名称', 'XMMC', 'xmmc']) || '';
        const taxCode = getString(row, ['taxCode', 'spbm', '税收分类编码']) || allTaxCodes[idx] || undefined;
        const amount = parseFloat(getString(row, ['amount', 'je', '金额', 'XMJE', 'xmje']) || 0) || 0;
        const quantity = getString(row, ['quantity', 'sl', '数量', 'XMSL', 'xmsl']) || null;
        const unit = getString(row, ['unit', 'dw', '单位']) || null;
        const price = parseFloat(getString(row, ['price', 'dj', '单价', 'XMDJ', 'xmdj']) || 0) || 0;
        items.push({ name, taxCode, amount, quantity, unit, price });
        totalAmount += amount;
      });
    }

    const totalStr = getString(flat, ['totalAmount', 'hjje', '价税合计']);
    if (totalStr) totalAmount = parseFloat(totalStr) || totalAmount;
  }

  if (items.length === 0 && allTaxCodes.length > 0) {
    items = [{ name: '', taxCode: allTaxCodes[0], amount: 0, quantity: null, unit: null, price: 0 }];
  }

  const invoice = new Invoice({
    invoiceNumber,
    invoiceDate,
    sellerName,
    sellerTaxId,
    buyerName,
    buyerTaxId,
    items,
    totalAmount,
    fileType: 'OFD',
  });

  return invoice;
}

module.exports = { parseOfdFile };
