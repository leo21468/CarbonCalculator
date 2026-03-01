/**
 * 根据销方/购方地址映射到区域电网（华北/华东/华南等）
 * 用于选择区域电力因子。省级简称或全称 → 区域。
 */

/** 省份/直辖市 → 区域电网 */
const PROVINCE_TO_GRID = Object.freeze({
  北京: '华北',
  天津: '华北',
  河北: '华北',
  山西: '华北',
  内蒙古: '华北',
  辽宁: '东北',
  吉林: '东北',
  黑龙江: '东北',
  上海: '华东',
  江苏: '华东',
  浙江: '华东',
  安徽: '华东',
  福建: '华东',
  江西: '华东',
  山东: '华东',
  河南: '华中',
  湖北: '华中',
  湖南: '华中',
  广东: '南方',
  广西: '南方',
  海南: '南方',
  重庆: '华中',
  四川: '西南',
  贵州: '南方',
  云南: '南方',
  西藏: '西南',
  陕西: '西北',
  甘肃: '西北',
  青海: '西北',
  宁夏: '西北',
  新疆: '西北',
});

/**
 * 从地址字符串中解析省份并映射到区域电网
 * @param {string} address - 销方或购方地址，如 "北京市朝阳区xxx"、"江苏省南京市"
 * @returns {string} 区域：华北/华东/华中/东北/南方/西北/西南，无法识别时返回 "全国"
 */
function mapAddressToRegion(address) {
  const s = (address || '').trim();
  if (!s) return '全国';
  for (const [province, region] of Object.entries(PROVINCE_TO_GRID)) {
    if (s.includes(province)) return region;
  }
  if (/华北|京津冀/.test(s)) return '华北';
  if (/华东|江浙沪/.test(s)) return '华东';
  if (/华南|珠三角|粤港澳/.test(s)) return '南方';
  if (/华中/.test(s)) return '华中';
  if (/东北/.test(s)) return '东北';
  if (/西北/.test(s)) return '西北';
  if (/西南/.test(s)) return '西南';
  return '全国';
}

/**
 * 从上下文（发票或销方/购方）解析区域，优先销方
 * @param {Object} [context] - { sellerAddress, buyerAddress, region }
 * @returns {string}
 */
function getRegionFromContext(context) {
  if (!context) return '全国';
  if (context.region && typeof context.region === 'string') return context.region.trim() || '全国';
  if (context.sellerAddress) return mapAddressToRegion(context.sellerAddress);
  if (context.buyerAddress) return mapAddressToRegion(context.buyerAddress);
  return '全国';
}

module.exports = {
  mapAddressToRegion,
  getRegionFromContext,
  PROVINCE_TO_GRID,
};
