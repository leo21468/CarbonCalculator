/**
 * 审计日志：记录每一步、查询、导出报告
 */

const path = require('path');
const fs = require('fs');
const { createAuditTrail, appendStep, appendDataSource, setFinalResult } = require('./auditTrail');
const { collectDataSources } = require('./dataProvenance');

/** 按 invoiceId 存储的审计记录（生产可换 DB） */
const trailStore = new Map();
/** 按 auditId 存储，便于通过 id 查 */
const trailById = new Map();

const STEP_NAMES = {
  '1_parse': '解析',
  '2_scope': '分类',
  '3_nlp': '语义增强',
  '4_match': '匹配',
  '5_calculate': '计算',
  '6_scenario': '场景专项',
};

/**
 * 创建并登记一条审计追踪
 * @param {string} [invoiceId]
 * @returns {Object} trail 对象，供后续 logStep / finalize 使用
 */
function createTrail(invoiceId = '') {
  const trail = createAuditTrail(invoiceId);
  trailStore.set(trail.invoiceId || trail.id, trail);
  trailById.set(trail.id, trail);
  return trail;
}

/**
 * 记录一步
 * @param {Object} trail - createTrail 返回的对象
 * @param {Object} stepData - { stepName, input, output, rules, confidence }
 */
function logStep(trail, stepData) {
  if (!trail) return;
  appendStep(trail, {
    stepName: stepData.stepName || stepData.step || '未知',
    input: stepData.input,
    output: stepData.output,
    rules: stepData.rules,
    confidence: stepData.confidence,
  });
}

/**
 * 结束审计并写入最终结果与数据来源
 * @param {Object} trail
 * @param {Object} result - EmissionResult 或 toObject()
 * @param {Object} [opts] - { classification, items }
 */
function finalize(trail, result, opts = {}) {
  if (!trail) return;
  const resultObj = result && typeof result.toObject === 'function' ? result.toObject() : result;
  setFinalResult(trail, resultObj);
  const items = (resultObj && resultObj.items) || opts.items || [];
  const sources = collectDataSources(items, opts.classification);
  sources.forEach((ds) => appendDataSource(trail, ds));
}

/**
 * 根据发票ID查询审计记录
 * @param {string} invoiceId
 * @returns {Object|null} AuditTrailRecord 或 null
 */
function getAuditTrail(invoiceId) {
  return trailStore.get(invoiceId) || trailById.get(invoiceId) || null;
}

/**
 * 导出审计报告
 * @param {string} invoiceId
 * @param {'json'|'html'} [format='json']
 * @returns {string} 报告内容
 */
function exportAuditReport(invoiceId, format = 'json') {
  const trail = getAuditTrail(invoiceId);
  if (!trail) return format === 'html' ? '<p>未找到该发票的审计记录</p>' : 'null';
  if (format === 'json') {
    return JSON.stringify(trail, null, 2);
  }
  if (format === 'html') {
    const templatePath = path.join(__dirname, 'templates', 'auditReport.html');
    let html = '';
    try {
      html = fs.readFileSync(templatePath, 'utf8');
    } catch (e) {
      html = getDefaultHtmlTemplate();
    }
    return fillAuditTemplate(html, trail);
  }
  return JSON.stringify(trail);
}

/**
 * 填充 HTML 模板占位符
 */
function fillAuditTemplate(html, trail) {
  const stepsHtml = (trail.steps || []).map((s, i) => `
    <tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(s.stepName)}</td>
      <td><pre>${escapeHtml(JSON.stringify(s.input, null, 2))}</pre></td>
      <td><pre>${escapeHtml(JSON.stringify(s.output, null, 2))}</pre></td>
      <td>${escapeHtml(s.rules || '-')}</td>
      <td>${escapeHtml(s.confidence || '-')}</td>
    </tr>`).join('');
  const sourcesHtml = (trail.dataSources || []).map((d) => `
    <li><strong>${escapeHtml(d.type)}</strong>: ${escapeHtml(d.source)} ${d.reference ? `（${escapeHtml(d.reference)}）` : ''}</li>`).join('');
  const resultStr = trail.finalResult ? JSON.stringify(trail.finalResult, null, 2) : '';
  return html
    .replace(/\{\{AUDIT_ID\}\}/g, escapeHtml(trail.id))
    .replace(/\{\{TIMESTAMP\}\}/g, escapeHtml(trail.timestamp))
    .replace(/\{\{INVOICE_ID\}\}/g, escapeHtml(trail.invoiceId))
    .replace(/\{\{STEPS\}\}/g, stepsHtml)
    .replace(/\{\{DATA_SOURCES\}\}/g, sourcesHtml)
    .replace(/\{\{FINAL_RESULT\}\}/g, escapeHtml(resultStr));
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function getDefaultHtmlTemplate() {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>审计报告</title></head><body>
  <h1>碳核算审计报告</h1>
  <p>ID: {{AUDIT_ID}} | 时间: {{TIMESTAMP}} | 发票: {{INVOICE_ID}}</p>
  <h2>处理步骤</h2><table border="1"><thead><tr><th>#</th><th>步骤</th><th>输入</th><th>输出</th><th>规则</th><th>置信度</th></tr></thead><tbody>{{STEPS}}</tbody></table>
  <h2>数据来源</h2><ul>{{DATA_SOURCES}}</ul>
  <h2>最终结果</h2><pre>{{FINAL_RESULT}}</pre>
  <p><button onclick="window.print()">打印 / 另存为 PDF</button></p>
  </body></html>`;
}

module.exports = {
  createTrail,
  logStep,
  finalize,
  getAuditTrail,
  exportAuditReport,
  trailStore,
  STEP_NAMES,
};
