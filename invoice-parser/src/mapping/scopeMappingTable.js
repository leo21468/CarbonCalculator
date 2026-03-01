/**
 * 税收分类编码 → 碳排放范围 映射表（模拟数据）
 *
 * 【数据来源说明】
 * 本模块数据为模拟数据，基于项目内 data/tax_code_to_scope.csv 与
 * data/scope_mapping_rules.yaml 的规则整理而成。生产环境应对接国家税务
 * 总局 API 或官方《商品和服务税收分类编码表》获取权威 19 位编码与分类，
 * 并据此维护 Scope 映射。
 *
 * 【GHG Protocol 依据】
 * - Scope 1：直接排放（企业拥有或控制的排放源），如燃料燃烧（煤炭、成品油、燃气等）。
 * - Scope 2：能源间接排放（外购电、热、蒸汽、冷气等）。
 * - Scope 3：价值链其他间接排放（外购商品/服务、运输、差旅等）。
 * 参考：GHG Protocol Corporate Standard, ISO 14064-1。
 */

/** 置信度枚举 */
const CONFIDENCE = Object.freeze({ HIGH: '高', MEDIUM: '中', LOW: '低' });

/**
 * 映射规则：按税号前缀匹配，长前缀优先。
 * 结构：{ prefix: string, scope: 1|2|3, description: string, excludeKeywords: string[] }
 * excludeKeywords：货物名称若包含其中任一词，则改判为 Scope 3（例外规则，如润滑油）。
 */
const PREFIX_RULES = [
  // ---------- Scope 1：直接燃烧/工艺排放 ----------
  { prefix: '101', scope: 1, description: '煤炭采选产品', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '102', scope: 1, description: '煤炭采选产品', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '103', scope: 1, description: '煤炭采选产品', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '104', scope: 1, description: '石油和天然气开采产品', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '105', scope: 1, description: '石油和天然气开采产品', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '106', scope: 1, description: '燃气', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  // 石油加工、炼焦：默认 Scope 1，但排除润滑油/沥青/蜡/碳黑等 → Scope 3
  { prefix: '107', scope: 1, description: '石油加工、炼焦及核燃料', excludeKeywords: ['沥青', '蜡', '碳黑', '润滑油', '石蜡'], confidence: CONFIDENCE.HIGH },
  { prefix: '108', scope: 1, description: '石油加工、炼焦及核燃料', excludeKeywords: ['沥青', '蜡', '碳黑', '润滑油', '石蜡'], confidence: CONFIDENCE.HIGH },
  // 单数字前缀兜底（与 reference table / CSV 一致）
  { prefix: '1', scope: 1, description: '煤炭采选产品', excludeKeywords: [], confidence: CONFIDENCE.MEDIUM },
  { prefix: '2', scope: 1, description: '石油和天然气开采产品', excludeKeywords: [], confidence: CONFIDENCE.MEDIUM },
  { prefix: '3', scope: 1, description: '燃气', excludeKeywords: [], confidence: CONFIDENCE.MEDIUM },
  { prefix: '4', scope: 1, description: '石油加工、炼焦及核燃料', excludeKeywords: ['沥青', '蜡', '碳黑', '润滑油'], confidence: CONFIDENCE.MEDIUM },

  // ---------- Scope 2：外购电、热、冷 ----------
  { prefix: '109', scope: 2, description: '电力、热力、冷气', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '110', scope: 2, description: '电力、热力、冷气', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '5', scope: 2, description: '电力和热力、冷气', excludeKeywords: [], confidence: CONFIDENCE.MEDIUM },

  // ---------- Scope 3：农业、商品、服务等 ----------
  { prefix: '6', scope: 3, description: '农业产品', excludeKeywords: [], confidence: CONFIDENCE.MEDIUM },
  { prefix: '7', scope: 3, description: '食品、纺织品、机械设备等', excludeKeywords: [], confidence: CONFIDENCE.MEDIUM },
  { prefix: '8', scope: 3, description: '有形动产租赁服务', excludeKeywords: [], confidence: CONFIDENCE.MEDIUM },
  { prefix: '9', scope: 3, description: '销售服务、劳务、电信/物流/咨询/IT', excludeKeywords: [], confidence: CONFIDENCE.MEDIUM },
  { prefix: '300', scope: 3, description: '服务、劳务', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '301', scope: 3, description: '服务、劳务', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '302', scope: 3, description: '服务、劳务', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '303', scope: 3, description: '服务、劳务', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '304', scope: 3, description: '有形动产租赁', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
  { prefix: '305', scope: 3, description: '有形动产租赁', excludeKeywords: [], confidence: CONFIDENCE.HIGH },
];

/** 关键词 → Scope 的辅助规则（当税号匹配不明确时，按货物名称关键词推断） */
const KEYWORD_SCOPE = [
  { keywords: ['煤炭', '原煤', '洗煤', '型煤', '汽油', '柴油', '燃料油', '炼焦', '成品油', '天然气', '煤气', '液化气'], scope: 1 },
  { keywords: ['电力', '电费', '热力', '冷气', '供暖'], scope: 2 },
  { keywords: ['润滑油', '沥青', '蜡', '石蜡', '碳黑'], scope: 3 },
  { keywords: ['服务', '劳务', '运输', '物流', '快递', '咨询', 'IT', '电信', '租赁'], scope: 3 },
];

/** 默认 Scope（未匹配时归入 Scope 3，符合 GHG Protocol 价值链其他间接排放） */
const DEFAULT_SCOPE = 3;

module.exports = {
  PREFIX_RULES,
  KEYWORD_SCOPE,
  DEFAULT_SCOPE,
  CONFIDENCE,
};
