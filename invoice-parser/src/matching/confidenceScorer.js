/**
 * 根据数据完整性与匹配类型计算置信度（高/中/低）
 *
 * - 高：有物理量 + 明确物料 + 匹配到物理因子
 * - 中：有金额 + 明确行业/税收编码 + 匹配到 EEIO 因子
 * - 低：仅有金额 + 模糊匹配 或 使用默认因子
 */

const CONFIDENCE = Object.freeze({ HIGH: '高', MEDIUM: '中', LOW: '低' });

/**
 * 计算匹配结果的置信度
 * @param {Object} opts
 * @param {boolean} [opts.hasPhysical] - 是否有物理量（数量+单位）
 * @param {boolean} [opts.hasMaterial] - 是否明确物料（名称可映射到具体物料/行业）
 * @param {boolean} [opts.hasTaxCode] - 是否有税收编码
 * @param {string} [opts.matchType] - 物理因子 | EEIO因子 | 默认因子
 * @param {boolean} [opts.isFuzzy] - 是否模糊匹配（仅关键词/无编码）
 * @returns {'高'|'中'|'低'}
 */
function scoreConfidence(opts = {}) {
  const { hasPhysical, hasMaterial, hasTaxCode, matchType, isFuzzy } = opts;
  const isPhysical = matchType === '物理因子';
  const isEEIO = matchType === 'EEIO因子';
  const isDefault = matchType === '默认因子';

  if (hasPhysical && hasMaterial && isPhysical) return CONFIDENCE.HIGH;
  if (hasPhysical && hasMaterial) return isPhysical ? CONFIDENCE.HIGH : CONFIDENCE.MEDIUM;
  if ((hasTaxCode || hasMaterial) && isEEIO && !isFuzzy) return CONFIDENCE.MEDIUM;
  if (hasTaxCode && isEEIO) return CONFIDENCE.MEDIUM;
  if (isEEIO && hasMaterial) return isFuzzy ? CONFIDENCE.LOW : CONFIDENCE.MEDIUM;
  if (isDefault || isFuzzy) return CONFIDENCE.LOW;
  return CONFIDENCE.LOW;
}

module.exports = {
  scoreConfidence,
  CONFIDENCE,
};
