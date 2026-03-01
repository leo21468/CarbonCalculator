/**
 * 排放核算结果模型
 *
 * 用于批量计算后的汇总与分类统计，符合 GHG Protocol 范围 1/2/3。
 */

/**
 * 单条核算结果
 * @typedef {Object} EmissionItemResult
 * @property {string} [invoiceId] - 发票ID/号码
 * @property {number} scope - 1 | 2 | 3
 * @property {number} emissions - 排放量 (kgCO2e)
 * @property {string} method - 计算方法 "activity" | "expenditure"
 * @property {string} confidence - 置信度 "高" | "中" | "低"
 * @property {Object} factorUsed - 使用的因子对象
 * @property {string} [reason] - 匹配依据
 * @property {string} [itemName] - 货物/劳务名称
 */

/**
 * 排放核算结果
 */
class EmissionResult {
  /**
   * @param {Object} [data]
   * @param {number} [data.totalEmissions] - 总排放量 (kgCO2e)
   * @param {EmissionItemResult[]} [data.items] - 明细
   * @param {Object} [data.summary] - { scope1, scope2, scope3 }
   */
  constructor(data = {}) {
    this.totalEmissions = data.totalEmissions != null ? Number(data.totalEmissions) : 0;
    this.items = Array.isArray(data.items) ? data.items : [];
    this.summary = Object.assign(
      { scope1: 0, scope2: 0, scope3: 0 },
      data.summary
    );
  }

  /**
   * 从 items 重算汇总
   */
  recalcSummary() {
    const s = { scope1: 0, scope2: 0, scope3: 0 };
    for (const it of this.items) {
      const scope = Number(it.scope);
      if (scope === 1) s.scope1 += Number(it.emissions) || 0;
      else if (scope === 2) s.scope2 += Number(it.emissions) || 0;
      else s.scope3 += Number(it.emissions) || 0;
    }
    this.summary = s;
    this.totalEmissions = s.scope1 + s.scope2 + s.scope3;
    return this;
  }

  toObject() {
    return {
      totalEmissions: this.totalEmissions,
      items: this.items,
      summary: this.summary,
    };
  }
}

module.exports = { EmissionResult };
