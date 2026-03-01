/**
 * 审计记录结构定义
 *
 * 用于记录每一步计算的来源和依据，支持追溯与导出。
 */

const crypto = require('crypto');

/**
 * 单步审计
 * @typedef {Object} AuditStep
 * @property {string} stepName - 解析/分类/匹配/计算/场景
 * @property {Object} [input] - 输入数据摘要
 * @property {Object} [output] - 输出数据摘要
 * @property {string} [rules] - 使用的规则/模型描述
 * @property {string} [confidence] - 置信度 高/中/低
 */

/**
 * 数据来源条目
 * @typedef {Object} DataSource
 * @property {string} type - 因子来源/规则来源
 * @property {string} source - 具体来源
 * @property {string} [reference] - 参考链接或文档
 */

/**
 * 审计追踪记录
 * @typedef {Object} AuditTrailRecord
 * @property {string} id - 唯一ID
 * @property {string} timestamp - ISO 时间戳
 * @property {string} invoiceId - 发票ID
 * @property {AuditStep[]} steps - 各步骤记录
 * @property {Object} finalResult - 最终排放结果摘要
 * @property {DataSource[]} dataSources - 数据来源列表
 */

/**
 * 生成唯一 ID
 */
function generateId() {
  return `audit_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
}

/**
 * 创建空审计记录
 * @param {string} [invoiceId] - 发票ID
 * @returns {AuditTrailRecord}
 */
function createAuditTrail(invoiceId = '') {
  return {
    id: generateId(),
    timestamp: new Date().toISOString(),
    invoiceId: String(invoiceId),
    steps: [],
    finalResult: null,
    dataSources: [],
  };
}

/**
 * 添加步骤到审计记录
 * @param {AuditTrailRecord} trail
 * @param {AuditStep} step
 */
function appendStep(trail, step) {
  if (!trail.steps) trail.steps = [];
  trail.steps.push({
    stepName: step.stepName,
    input: step.input,
    output: step.output,
    rules: step.rules,
    confidence: step.confidence,
  });
}

/**
 * 添加数据来源
 * @param {AuditTrailRecord} trail
 * @param {DataSource} ds
 */
function appendDataSource(trail, ds) {
  if (!trail.dataSources) trail.dataSources = [];
  trail.dataSources.push({ type: ds.type, source: ds.source, reference: ds.reference });
}

/**
 * 设置最终结果
 * @param {AuditTrailRecord} trail
 * @param {Object} resultSummary - result.toObject() 或摘要
 */
function setFinalResult(trail, resultSummary) {
  trail.finalResult = resultSummary;
}

module.exports = {
  createAuditTrail,
  appendStep,
  appendDataSource,
  setFinalResult,
  generateId,
};
