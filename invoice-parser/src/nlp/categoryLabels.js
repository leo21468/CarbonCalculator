/**
 * 发票明细 BERT/混合分类 的类别标签（10 类）
 * 与 trainingData.json、hybridClassifier 一致
 */
const CATEGORY_LABELS = Object.freeze({
  0: '电子产品',
  1: '办公家具',
  2: '文具纸张',
  3: '运输服务',
  4: '维修服务',
  5: '燃料能源',
  6: '建筑材料',
  7: '机械设备',
  8: '食品饮料',
  9: '其他',
});

const CATEGORY_NAMES = Object.freeze(Object.values(CATEGORY_LABELS));
const NUM_CATEGORIES = CATEGORY_NAMES.length;

function getCategoryName(id) {
  return CATEGORY_LABELS[id] ?? '其他';
}

module.exports = { CATEGORY_LABELS, CATEGORY_NAMES, NUM_CATEGORIES, getCategoryName };
