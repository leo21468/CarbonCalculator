/**
 * 单张/批量发票完整处理流程编排
 *
 * - processSingleInvoice(input)：返回 EmissionResult + 中间步骤日志
 * - processBatchInvoice(inputs)：批量处理，返回汇总报表
 */

const path = require('path');
const {
  step1ParseInvoice,
  step2ClassifyScope,
  step3SemanticEnhance,
  step4MatchFactors,
  step5Calculate,
  step6ScenarioHandling,
  getRegionFromContext,
  EmissionResult,
} = require('../index');
const auditLogger = require('../audit/auditLogger');

/**
 * 处理单张发票（支持文件路径或发票对象）
 * @param {string|Object} input - 文件路径 或 已解析的发票对象 { items, totalAmount, sellerName, ... }
 * @param {{ region?: string, enableAudit?: boolean }} [options]
 * @returns {Promise<{ result: EmissionResult, invoice: Object, logs: Array<{ step: string, message: string, data?: any }>, auditTrail?: Object }>}
 */
async function processSingleInvoice(input, options = {}) {
  const logs = [];
  let invoice;
  const enableAudit = options.enableAudit === true;
  let trail = null;

  try {
    // 步骤1：解析发票
    if (typeof input === 'string') {
      const ext = path.extname(input).toLowerCase();
      const fileType = ext === '.json' ? 'JSON' : ext === '.xml' ? 'XML' : ext === '.pdf' ? 'PDF' : ext === '.ofd' ? 'OFD' : null;
      invoice = await step1ParseInvoice(input, fileType);
      logs.push({ step: '1_parse', message: `已解析文件: ${input}`, data: { fileType: fileType || path.extname(input) } });
    } else if (input && typeof input === 'object') {
      invoice = input.items ? input : { items: [], totalAmount: input.totalAmount || 0, sellerName: input.sellerName, buyerName: input.buyerName };
      logs.push({ step: '1_parse', message: '使用传入的发票对象', data: { itemCount: invoice.items ? invoice.items.length : 0 } });
    } else {
      throw new Error('input 必须为文件路径(string)或发票对象(object)');
    }

    const invObj = invoice && typeof invoice.toObject === 'function' ? invoice.toObject() : invoice;
    const invoiceId = invObj.invoiceNumber || invObj.invoiceId || `inv_${Date.now()}`;
    if (enableAudit) {
      trail = auditLogger.createTrail(invoiceId);
      auditLogger.logStep(trail, {
        stepName: '解析',
        input: { filePath: typeof input === 'string' ? input : null, itemCount: invObj.items ? invObj.items.length : 0 },
        output: { invoiceNumber: invObj.invoiceNumber, totalAmount: invObj.totalAmount },
        rules: 'parser (OFD/PDF/XML/JSON)',
      });
    }

    const context = { region: options.region, sellerAddress: invObj.sellerAddress || invObj.sellerName, buyerAddress: invObj.buyerAddress || invObj.buyerName };
    context.region = context.region || getRegionFromContext(context);

    // 步骤6 优先：场景专项（整单水电/住宿/交通等）
    const scenario = step6ScenarioHandling(invoice, context);
    if (scenario && scenario.result && scenario.result.success !== false) {
      const emissionsKg = scenario.result.emissionsKg != null ? scenario.result.emissionsKg : 0;
      let scope = 3;
      if (scenario.type === 'electricity') scope = 2;
      else if (scenario.type === 'fuel') scope = 1;
      else if (scenario.result.scope != null) scope = scenario.result.scope;
      const result = new EmissionResult({
        items: [{
          invoiceId: invObj.invoiceNumber || 'unknown',
          scope,
          emissions: emissionsKg,
          method: scenario.type === 'electricity' || scenario.type === 'fuel' ? 'activity' : 'expenditure',
          confidence: '中',
          factorUsed: null,
          reason: `场景专项: ${scenario.type}`,
          itemName: scenario.type,
        }],
        totalEmissions: 0,
        summary: { scope1: 0, scope2: 0, scope3: 0 },
      });
      result.recalcSummary();
      logs.push({ step: '6_scenario', message: `场景识别: ${scenario.type}`, data: scenario.result });
      if (trail) {
        auditLogger.logStep(trail, { stepName: '场景专项', input: invObj, output: scenario.result, rules: `scenarios.${scenario.type}`, confidence: '中' });
        auditLogger.finalize(trail, result);
      }
      return { result, invoice: invObj, logs, auditTrail: trail || undefined };
    }

    // 步骤2～5：按明细分类、增强、匹配、计算
    const classified = step2ClassifyScope(invObj);
    logs.push({ step: '2_scope', message: `范围分类: ${classified.length} 条`, data: classified.map((c) => ({ scope: c.classification.scope, reason: c.classification.reason })) });
    if (trail) {
      auditLogger.logStep(trail, {
        stepName: '分类',
        input: invObj.items,
        output: classified.map((c) => ({ scope: c.classification.scope, reason: c.classification.reason })),
        rules: 'classifyByTaxCode / scopeMappingTable',
        confidence: classified[0]?.classification?.confidence,
      });
    }

    const enhanced = await step3SemanticEnhance(classified);
    logs.push({ step: '3_nlp', message: `语义增强: ${enhanced.length} 条` });
    if (trail) {
      auditLogger.logStep(trail, { stepName: '语义增强', input: classified.map((c) => c.item.name), output: enhanced.length, rules: 'processGoodsName / NLP', confidence: null });
    }

    const matched = step4MatchFactors(enhanced.map((e) => ({ item: e.item, classification: e.classification })), context);
    logs.push({ step: '4_match', message: `因子匹配: ${matched.length} 条` });
    if (trail) {
      auditLogger.logStep(trail, {
        stepName: '匹配',
        input: enhanced.map((e) => ({ name: e.item.name, amount: e.item.amount })),
        output: matched.map((m) => ({ matchType: m.matched.matchType, factorName: m.matched.factor?.name, confidence: m.matched.confidence })),
        rules: 'factorMatcher',
        confidence: matched[0]?.matched?.confidence,
      });
    }

    const calculated = step5Calculate(matched);
    const resultItems = calculated.map((c) => ({
      invoiceId: invObj.invoiceNumber || undefined,
      scope: c.scope,
      emissions: c.emissions,
      method: c.method,
      confidence: c.confidence,
      factorUsed: c.factorUsed,
      reason: c.reason,
      itemName: c.itemName,
    }));
    const result = new EmissionResult({ items: resultItems, totalEmissions: 0, summary: { scope1: 0, scope2: 0, scope3: 0 } });
    result.recalcSummary();
    logs.push({ step: '5_calculate', message: `排放计算完成, 总排放: ${result.totalEmissions.toFixed(2)} kgCO2e` });
    if (trail) {
      auditLogger.logStep(trail, {
        stepName: '计算',
        input: matched.length,
        output: { totalEmissions: result.totalEmissions, summary: result.summary, items: resultItems },
        rules: 'calculator / calculationService',
        confidence: resultItems.map((i) => i.confidence).join(','),
      });
      auditLogger.finalize(trail, result, { items: resultItems, classification: classified[0]?.classification });
    }

    return { result, invoice: invObj, logs, auditTrail: trail || undefined };
  } catch (err) {
    logs.push({ step: 'error', message: err.message, data: { stack: err.stack } });
    if (trail) auditLogger.logStep(trail, { stepName: '错误', input: null, output: err.message, rules: null, confidence: null });
    const empty = new EmissionResult({ items: [], totalEmissions: 0, summary: { scope1: 0, scope2: 0, scope3: 0 } });
    return { result: empty, invoice: invoice || null, logs, auditTrail: trail || undefined };
  }
}

/**
 * 批量处理多张发票
 * @param {string[]|Object[]} inputs - 文件路径数组或发票对象数组
 * @param {{ region?: string }} [options]
 * @returns {Promise<{ results: EmissionResult[], summary: { totalEmissions: number, scope1: number, scope2: number, scope3: number, invoiceCount: number }, reports: Array<{ result: EmissionResult, invoice: Object, logs: any[] }> }>}
 */
async function processBatchInvoice(inputs, options = {}) {
  const reports = [];
  for (const input of inputs) {
    const report = await processSingleInvoice(input, options);
    reports.push(report);
  }
  const results = reports.map((r) => r.result);
  const summary = {
    totalEmissions: results.reduce((s, r) => s + r.totalEmissions, 0),
    scope1: results.reduce((s, r) => s + (r.summary && r.summary.scope1) || 0, 0),
    scope2: results.reduce((s, r) => s + (r.summary && r.summary.scope2) || 0, 0),
    scope3: results.reduce((s, r) => s + (r.summary && r.summary.scope3) || 0, 0),
    invoiceCount: results.length,
  };
  return { results, summary, reports };
}

module.exports = {
  processSingleInvoice,
  processBatchInvoice,
};
