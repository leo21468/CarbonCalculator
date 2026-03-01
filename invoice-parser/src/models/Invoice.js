/**
 * 发票结构化数据模型
 * 用于 OFD/PDF/XML/JSON 解析结果的统一表示
 */

/**
 * 发票明细行（货物或应税劳务）
 * @typedef {Object} InvoiceItem
 * @property {string} name - 货物或应税劳务名称
 * @property {string} [taxCode] - 19位税收分类编码
 * @property {number} [amount] - 金额
 * @property {number|string} [quantity] - 数量
 * @property {string} [unit] - 单位
 * @property {number} [price] - 单价
 */

/**
 * 发票结构化数据模型
 * @class Invoice
 */
class Invoice {
  /**
   * @param {Object} [data] - 可选初始数据
   */
  constructor(data = {}) {
    /** @type {string} 发票号码 */
    this.invoiceNumber = data.invoiceNumber ?? null;
    /** @type {string} 开票日期 (YYYY-MM-DD) */
    this.invoiceDate = data.invoiceDate ?? null;
    /** @type {string} 销方名称 */
    this.sellerName = data.sellerName ?? null;
    /** @type {string} 销方税号 */
    this.sellerTaxId = data.sellerTaxId ?? null;
    /** @type {string} 购方名称 */
    this.buyerName = data.buyerName ?? null;
    /** @type {string} 购方税号 */
    this.buyerTaxId = data.buyerTaxId ?? null;
    /** @type {InvoiceItem[]} 明细行 */
    this.items = Array.isArray(data.items) ? data.items : [];
    /** @type {number} 总金额 */
    this.totalAmount = data.totalAmount != null ? Number(data.totalAmount) : 0;
    /** @type {string} 原始文件类型 (OFD|PDF|XML|JSON) */
    this.fileType = data.fileType ?? null;
  }

  /**
   * 转为普通对象（便于 JSON 序列化）
   * @returns {Object}
   */
  toObject() {
    return {
      invoiceNumber: this.invoiceNumber,
      invoiceDate: this.invoiceDate,
      sellerName: this.sellerName,
      sellerTaxId: this.sellerTaxId,
      buyerName: this.buyerName,
      buyerTaxId: this.buyerTaxId,
      items: this.items,
      totalAmount: this.totalAmount,
      fileType: this.fileType,
    };
  }
}

module.exports = { Invoice };
