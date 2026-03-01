/**
 * 置信度统计与人工复核标记
 */

/**
 * 统计各置信度级别的条目数量
 * @param {Array<{ confidence?: string }>} items - 核算结果明细（EmissionResult.items 或类似）
 * @returns {{ high: number, medium: number, low: number, total: number, byConfidence: Record<string, number> }}
 */
function countByConfidence(items) {
  const list = Array.isArray(items) ? items : [];
  const byConfidence = { 高: 0, 中: 0, 低: 0 };
  for (const it of list) {
    const c = (it.confidence || '').trim();
    if (c === '高') byConfidence['高']++;
    else if (c === '中') byConfidence['中']++;
    else byConfidence['低']++;
  }
  return {
    high: byConfidence['高'],
    medium: byConfidence['中'],
    low: byConfidence['低'],
    total: list.length,
    byConfidence,
  };
}

/**
 * 标记需要人工复核的低置信度条目
 * @param {Array<{ confidence?: string, itemName?: string, reason?: string, invoiceId?: string, emissions?: number }>} items
 * @returns {{ needReview: Array<Object>, summary: { total: number, needReviewCount: number } }}
 */
function flagLowConfidence(items) {
  const list = Array.isArray(items) ? items : [];
  const needReview = list
    .filter((it) => (it.confidence || '').trim() === '低')
    .map((it) => ({
      invoiceId: it.invoiceId,
      itemName: it.itemName,
      reason: it.reason,
      emissions: it.emissions,
      confidence: it.confidence,
    }));
  return {
    needReview,
    summary: { total: list.length, needReviewCount: needReview.length },
  };
}

/**
 * 生成置信度报告（供报表输出）
 * @param {EmissionResult|{ items: Array }} emissionResult
 * @returns {{ counts: ReturnType<typeof countByConfidence>, needReview: ReturnType<typeof flagLowConfidence> }}
 */
function confidenceReport(emissionResult) {
  const items = emissionResult && emissionResult.items ? emissionResult.items : [];
  return {
    counts: countByConfidence(items),
    needReview: flagLowConfidence(items),
  };
}

module.exports = {
  countByConfidence,
  flagLowConfidence,
  confidenceReport,
};
