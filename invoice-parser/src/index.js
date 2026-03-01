/**
 * 碳核算系统主入口
 *
 * 完整流程：解析发票 → 分类范围 → 语义增强 → 匹配因子 → 计算排放 → 场景专项处理
 */

const { parseInvoice } = require('./parser');
const { classifyByTaxCode } = require('./mapping/classifyByTaxCode');
const { processGoodsName } = require('./nlp');
const { matchFactor } = require('./matching/factorMatcher');
const { getRegionFromContext } = require('./matching/regionMapper');
const { calculateBatch, calculate } = require('./calculation');
const { EmissionResult } = require('./models/EmissionResult');
const {
  processElectricity,
  processWater,
  processTransport,
  processLogistics,
  processWaste,
  extractCity,
  calculateHotelEmission,
} = require('./scenarios');

/**
 * 步骤1：解析发票
 */
async function step1ParseInvoice(filePath, fileType) {
  return parseInvoice(filePath, fileType);
}

/**
 * 步骤2：分类范围（按税号+货物名称）
 */
function step2ClassifyScope(invoice) {
  const items = Array.isArray(invoice?.items) ? invoice.items : [];
  return items.map((it) => ({
    item: it,
    classification: classifyByTaxCode(it.taxCode || it.tax_classification_code, it.name || it.goodsName),
  }));
}

/**
 * 步骤3：语义增强（NLP 处理模糊类目，可选异步）
 */
async function step3SemanticEnhance(classifiedItems) {
  const out = [];
  for (const { item, classification } of classifiedItems) {
    const name = item.name || item.goodsName || '';
    const enhanced = { ...item, _scopeFromTax: classification.scope, _scopeReason: classification.reason };
    try {
      const nlpResult = processGoodsName(name);
      if (nlpResult && nlpResult.summary) enhanced._nlpSummary = nlpResult.summary;
    } catch (e) {
      // NLP 可选，失败不阻塞
    }
    out.push({ item: enhanced, classification });
  }
  return out;
}

/**
 * 步骤4：匹配因子
 */
function step4MatchFactors(classifiedItems, context) {
  return classifiedItems.map(({ item, classification }) => {
    const matched = matchFactor(item, context);
    return { item, classification, matched };
  });
}

/**
 * 步骤5：计算排放（通用）
 */
function step5Calculate(matchedItems) {
  const calc = require('./calculation/calculationService').calculate;
  return matchedItems.map(({ item, classification, matched }) => {
    const c = calc(item, matched);
    return {
      item,
      classification,
      matched,
      emissions: c.value,
      method: c.method,
      confidence: c.confidence,
      factorUsed: c.factorUsed,
      reason: c.reason,
      scope: c.scope,
      itemName: c.itemName,
    };
  });
}

/**
 * 步骤6：场景专项处理（水电、住宿、交通、物流、废弃物）
 * 若整张发票被识别为某一场景且处理成功，返回该场景的一条结果；否则返回 null
 */
function step6ScenarioHandling(invoice, context) {
  const inv = invoice && typeof invoice.toObject === 'function' ? invoice.toObject() : invoice;
  const region = context?.region || getRegionFromContext(inv);

  let r = processElectricity(inv, region);
  if (r.success) return { type: 'electricity', result: r };
  r = processWater(inv);
  if (r.success) return { type: 'water', result: r };
  const isHotelLike = /酒店|宾馆|旅馆|住宿/.test(inv.sellerName || '') || (Array.isArray(inv.items) && inv.items.some((it) => /酒店|宾馆|住宿/.test(it.name || it.goodsName || '')));
  if (isHotelLike && (inv.totalAmount > 0 || (inv.items && inv.items[0] && inv.items[0].amount))) {
    const amount = inv.totalAmount || (inv.items[0] && inv.items[0].amount) || 0;
    const hotelRes = calculateHotelEmission(amount, extractCity(inv), null, inv);
    if (!hotelRes.error && hotelRes.emissionsKg > 0) return { type: 'hotel', result: { success: true, emissionsKg: hotelRes.emissionsKg, nights: hotelRes.nights, scope: 3 } };
  }
  r = processTransport(inv);
  if (r.success) return { type: 'transport', result: r };
  r = processLogistics(inv);
  if (r.success) return { type: 'logistics', result: r };
  r = processWaste(inv);
  if (r.success) return { type: 'waste', result: r };
  return null;
}

module.exports = {
  step1ParseInvoice,
  step2ClassifyScope,
  step3SemanticEnhance,
  step4MatchFactors,
  step5Calculate,
  step6ScenarioHandling,
  parseInvoice,
  classifyByTaxCode,
  processGoodsName,
  matchFactor,
  getRegionFromContext,
  calculateBatch,
  EmissionResult,
  processElectricity,
  processWater,
  processTransport,
  processLogistics,
  processWaste,
  calculateHotelEmission,
};

// 编排器与 API 按需引用
module.exports.processSingleInvoice = function (input, options) {
  return require('./orchestrator/processInvoice').processSingleInvoice(input, options);
};
module.exports.processBatchInvoice = function (inputs, options) {
  return require('./orchestrator/processInvoice').processBatchInvoice(inputs, options);
};
module.exports.confidenceReport = function (emissionResult) {
  return require('./orchestrator/confidenceReporter').confidenceReport(emissionResult);
};
