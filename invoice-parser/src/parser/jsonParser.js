/**
 * JSON 发票解析器
 * 从 JSON 结构化数据中直接提取发票字段，重点提取 19 位税收分类编码
 */

const fs = require('fs');
const path = require('path');
const { Invoice } = require('../models/Invoice');

/** 19 位税收分类编码正则 */
const TAX_CODE_19 = /^\d{19}$/;

/**
 * 从对象中递归收集所有 19 位税收分类编码
 * @param {any} obj
 * @returns {string[]}
 */
function findTaxCodes(obj) {
  const codes = [];
  if (!obj || typeof obj !== 'object') return codes;
  if (Array.isArray(obj)) {
    obj.forEach((item) => codes.push(...findTaxCodes(item)));
    return codes;
  }
  for (const value of Object.values(obj)) {
    if (typeof value === 'string' && TAX_CODE_19.test(value.trim())) {
      codes.push(value.trim());
    } else if (typeof value === 'object') {
      codes.push(...findTaxCodes(value));
    }
  }
  return codes;
}

/**
 * 从 JSON 对象中安全取字符串（支持多种常见键名）
 * @param {Object} data
 * @param {string[]} keys
 * @returns {string|null}
 */
function getString(data, keys) {
  if (!data || typeof data !== 'object') return null;
  for (const k of keys) {
    const v = data[k];
    if (v != null && typeof v === 'string' && v.trim()) return v.trim();
    if (typeof v === 'number') return String(v);
  }
  return null;
}

/**
 * 将 JSON 中的 items/lines 转为统一明细格式，并注入 19 位税收分类编码
 * @param {Object} data - 根对象
 * @param {Array} [itemsRaw] - 原始明细数组
 * @returns {{ items: Array<{name, taxCode, amount, quantity, unit, price}>, totalAmount: number }}
 */
function parseItemsFromJson(data, itemsRaw) {
  const items = [];
  let totalAmount = 0;
  const taxCodes = findTaxCodes(data);

  const list = itemsRaw || data.items || data.lines || data.details || data.FPDetail || data.fpDetail || [];

  if (Array.isArray(list) && list.length) {
    list.forEach((row, idx) => {
      const name = getString(row, ['name', 'goodsName', 'hwmc', 'spmc', '项目名称', '货物或应税劳务名称']) || '';
      const taxCode = getString(row, ['taxCode', 'tax_code', 'spbm', 'ssflbm', '税收分类编码']) || taxCodes[idx] || undefined;
      const amount = Number(getString(row, ['amount', 'je', '金额']) || 0) || 0;
      const quantity = getString(row, ['quantity', 'sl', '数量']) ?? row.quantity;
      const unit = getString(row, ['unit', 'dw', '单位']) ?? row.unit;
      const price = Number(getString(row, ['price', 'dj', '单价']) || 0) || 0;
      items.push({ name, taxCode, amount, quantity, unit, price });
      totalAmount += amount;
    });
  }

  const totalStr = getString(data, ['totalAmount', 'total_amount', 'hjje', '价税合计', '合计金额']);
  if (totalStr) totalAmount = parseFloat(totalStr) || totalAmount;

  return { items, totalAmount };
}

/**
 * 解析 JSON 文件为 Invoice 对象
 * @param {string} filePath - JSON 文件路径
 * @returns {Promise<Invoice>}
 */
function parseJsonFile(filePath) {
  return new Promise((resolve, reject) => {
    const fullPath = path.resolve(filePath);
    fs.readFile(fullPath, 'utf8', (err, text) => {
      if (err) {
        reject(new Error(`读取 JSON 文件失败: ${fullPath}, ${err.message}`));
        return;
      }
      try {
        const data = JSON.parse(text);
        const invoiceNumber = getString(data, ['invoiceNumber', 'invoice_number', 'fpdm', '发票号码']);
        const invoiceDate = getString(data, ['invoiceDate', 'invoice_date', 'kprq', '开票日期']);
        const sellerName = getString(data, ['sellerName', 'seller_name', 'xfmc', '销方名称']);
        const sellerTaxId = getString(data, ['sellerTaxId', 'seller_tax_id', 'xfsbh', '销方税号']);
        const buyerName = getString(data, ['buyerName', 'buyer_name', 'gfmc', '购方名称']);
        const buyerTaxId = getString(data, ['buyerTaxId', 'buyer_tax_id', 'gfsbh', '购方税号']);

        const itemsRaw = data.items || data.lines || data.details;
        const { items, totalAmount } = parseItemsFromJson(data, itemsRaw);

        const invoice = new Invoice({
          invoiceNumber,
          invoiceDate,
          sellerName,
          sellerTaxId,
          buyerName,
          buyerTaxId,
          items,
          totalAmount,
          fileType: 'JSON',
        });
        resolve(invoice);
      } catch (e) {
        reject(new Error(`解析 JSON 失败: ${e.message}`));
      }
    });
  });
}

module.exports = { parseJsonFile, findTaxCodes, parseItemsFromJson };
