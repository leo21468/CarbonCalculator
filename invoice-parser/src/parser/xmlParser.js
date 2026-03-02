/**
 * XML 发票解析器
 * 从 XML 结构化数据中提取发票字段，重点提取 19 位税收分类编码
 */

const { XMLParser } = require('fast-xml-parser');
const fs = require('fs');
const path = require('path');
const { Invoice } = require('../models/Invoice');

/** 19 位税收分类编码正则 */
const TAX_CODE_19 = /^\d{19}$/;

/**
 * 从节点或对象中递归查找 19 位税收分类编码
 * @param {any} node - XML 解析后的节点（对象或数组）
 * @returns {string[]}
 */
function findTaxCodes(node) {
  const codes = [];
  if (!node || typeof node !== 'object') return codes;
  if (Array.isArray(node)) {
    node.forEach((child) => codes.push(...findTaxCodes(child)));
    return codes;
  }
  for (const [key, value] of Object.entries(node)) {
    if (typeof value === 'string' && TAX_CODE_19.test(value.trim())) {
      codes.push(value.trim());
    }
    if (typeof value === 'object') {
      codes.push(...findTaxCodes(value));
    }
  }
  return codes;
}

/**
 * 从扁平或嵌套结构中取字符串
 * @param {any} node
 * @param {string[]} keys - 候选键名（按优先级）
 * @returns {string|null}
 */
function getString(node, keys) {
  if (!node || typeof node !== 'object') return null;
  for (const k of keys) {
    const v = node[k];
    if (v != null && typeof v === 'string' && v.trim()) return v.trim();
    if (v != null && typeof v === 'object' && v['#text']) return String(v['#text']).trim();
    if (typeof v === 'number') return String(v);
  }
  return null;
}

/**
 * 解析常见中文发票 XML 中的明细行（含 19 位税收分类编码）
 * @param {any} root - 解析后的 XML 根
 * @returns {{ items: Array<{name, taxCode, amount, quantity, unit, price}>, totalAmount: number }}
 */
function parseItemsFromXml(root) {
  const items = [];
  let totalAmount = 0;
  const taxCodes = findTaxCodes(root);

  // 常见 XML 路径：FPDetail / FPMX / Item / Goods / COMMON_FPKJ_XMXXS 等
  const listPaths = [
    root.FPDetail,
    root.FPMX,
    root.fpDetail,
    root.fpmx,
    root.Detail,
    root.Items,
    root.items,
    root.Goods,
    root.goods,
    root.REQUEST && root.REQUEST.BODY && root.REQUEST.BODY.COMMON_FPKJ_XMXXS,
    root.BODY && root.BODY.COMMON_FPKJ_XMXXS,
    root.COMMON_FPKJ_XMXXS,
  ].filter(Boolean);

  let list = null;
  for (const p of listPaths) {
    const arr = Array.isArray(p) ? p
      : p?.Item ? (Array.isArray(p.Item) ? p.Item : [p.Item])
      : p?.Row ? (Array.isArray(p.Row) ? p.Row : [p.Row])
      : p?.COMMON_FPKJ_XMXX ? (Array.isArray(p.COMMON_FPKJ_XMXX) ? p.COMMON_FPKJ_XMXX : [p.COMMON_FPKJ_XMXX])
      : null;
    if (arr && arr.length) {
      list = arr;
      break;
    }
  }

  if (list && list.length) {
    list.forEach((row, idx) => {
      const name = getString(row, ['name', 'Name', 'hwmc', 'HWMC', 'goodsName', 'spmc', 'SPMC', '项目名称', 'XMMC', 'xmmc']) || getString(row, ['xmmc', 'XMMC']);
      let taxCode = getString(row, ['taxCode', 'TaxCode', 'spbm', 'SPBM', 'ssbm', 'ssflbm', '税收分类编码']);
      if (!taxCode && row.taxCode != null) {
        const raw = row.taxCode;
        taxCode = typeof raw === 'number' ? String(raw) : (typeof raw === 'object' && raw['#text'] ? String(raw['#text']) : (typeof raw === 'string' ? raw : null));
      }
      if (!taxCode && taxCodes[idx]) taxCode = taxCodes[idx];
      if (taxCode && !/^\d{19}$/.test(taxCode)) taxCode = taxCode.replace(/\D/g, '').length === 19 ? taxCode.replace(/\D/g, '') : null;
      const amount = parseFloat(getString(row, ['amount', 'Amount', 'je', 'JE', '金额', 'XMJE', 'xmje']) || 0) || 0;
      const quantity = getString(row, ['quantity', 'Quantity', 'sl', 'SL', '数量', 'XMSL', 'xmsl']) || null;
      const unit = getString(row, ['unit', 'Unit', 'dw', 'DW', '单位']) || null;
      const price = parseFloat(getString(row, ['price', 'Price', 'dj', 'DJ', '单价', 'XMDJ', 'xmdj']) || 0) || 0;
      items.push({ name: name || '', taxCode: taxCode && taxCode.length === 19 ? taxCode : undefined, amount, quantity, unit, price });
      totalAmount += amount;
    });
  }

  if (items.length === 0 && taxCodes.length > 0) {
    items.push({ name: '', taxCode: taxCodes[0], amount: 0, quantity: null, unit: null, price: 0 });
  }

  const totalStr = getString(root, ['totalAmount', 'TotalAmount', 'hjje', 'HJJE', '价税合计', '合计金额']);
  if (totalStr) totalAmount = parseFloat(totalStr) || totalAmount;

  return { items, totalAmount };
}

/**
 * 解析 XML 文件为 Invoice 对象
 * @param {string} filePath - XML 文件路径
 * @returns {Promise<Invoice>}
 */
function parseXmlFile(filePath) {
  return new Promise((resolve, reject) => {
    const fullPath = path.resolve(filePath);
    fs.readFile(fullPath, 'utf8', (err, xmlText) => {
      if (err) {
        reject(new Error(`读取 XML 文件失败: ${fullPath}, ${err.message}`));
        return;
      }
      try {
        const parser = new XMLParser({
          ignoreAttributes: false,
          attributeNamePrefix: '@_',
          trimValues: true,
        });
        const root = parser.parse(xmlText);
        // 取根元素（跳过 <?xml ?> 等声明）
        let data = root;
        if (root && typeof root === 'object') {
          const rootKey = Object.keys(root).find((k) => !k.startsWith('?'));
          if (rootKey) data = root[rootKey];
        }

        const invoiceNumber = getString(data, ['invoiceNumber', 'fpdm', 'FPDM', 'invoiceNo', '发票代码', '发票号码']);
        const invoiceDate = getString(data, ['invoiceDate', 'kprq', 'KPRQ', 'date', '开票日期']);
        const sellerName = getString(data, ['sellerName', 'xfmc', 'XFMC', 'gfmc', '销方名称', '销售方']);
        const sellerTaxId = getString(data, ['sellerTaxId', 'xfsbh', 'XFSBH', '销方税号', '销售方税号']);
        const buyerName = getString(data, ['buyerName', 'gfmc', 'GFMC', '购方名称', '购买方']);
        const buyerTaxId = getString(data, ['buyerTaxId', 'gfsbh', 'GFSBH', '购方税号', '购买方税号']);

        const { items, totalAmount } = parseItemsFromXml(data);

        const invoice = new Invoice({
          invoiceNumber,
          invoiceDate,
          sellerName,
          sellerTaxId,
          buyerName,
          buyerTaxId,
          items,
          totalAmount,
          fileType: 'XML',
        });
        resolve(invoice);
      } catch (e) {
        reject(new Error(`解析 XML 失败: ${e.message}`));
      }
    });
  });
}

module.exports = { parseXmlFile, findTaxCodes, parseItemsFromXml };
