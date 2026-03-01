/**
 * 酒店住宿排放因子（kgCO2e/间夜）
 *
 * 数据来源：参考 CHSB（中国酒店可持续基准/相关研究）等数据库的酒店住宿碳足迹
 * （此处为模拟数据，生产环境建议使用 CHSB 或企业认可的排放因子库）
 *
 * 单位：kgCO2e/间夜
 */

const hotelFactors = Object.freeze({
  北京: 68.5,
  上海: 65.2,
  广州: 58.7,
  深圳: 55.3,
  杭州: 48.9,
  南京: 45.6,
  成都: 46.2,
  武汉: 44.8,
  西安: 42.5,
  重庆: 45.0,
  天津: 52.0,
  苏州: 47.0,
  宁波: 46.5,
  青岛: 48.0,
  厦门: 50.2,
  长沙: 43.0,
  郑州: 42.0,
  济南: 46.0,
  哈尔滨: 48.5,
  沈阳: 47.5,
});

/** 未知城市时的默认因子（取平均值约 50） */
const DEFAULT_FACTOR = 50;

/**
 * 获取城市酒店排放因子
 * @param {string} city
 * @returns {number} kgCO2e/间夜
 */
function getHotelFactor(city) {
  const c = (city || '').trim();
  if (!c) return DEFAULT_FACTOR;
  const v = hotelFactors[c];
  return typeof v === 'number' ? v : DEFAULT_FACTOR;
}

module.exports = {
  hotelFactors,
  DEFAULT_FACTOR,
  getHotelFactor,
};
