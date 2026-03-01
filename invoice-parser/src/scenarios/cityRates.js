/**
 * 差旅住宿标准数据库（模拟数据）
 *
 * 数据来源：参考财政部《中央和国家机关差旅费管理办法》及各省差旅住宿费标准
 * （具体标准以最新文件为准，此处为模拟数据，生产环境建议接入官方或企业差旅标准）
 *
 * 单位：元/间·天。other=其他人员，division=司局级，minister=省部级
 */

const cityRates = Object.freeze({
  北京: { other: 500, division: 650, minister: 800 },
  上海: { other: 500, division: 600, minister: 750 },
  广州: { other: 450, division: 550, minister: 700 },
  深圳: { other: 450, division: 550, minister: 700 },
  杭州: { other: 400, division: 500, minister: 650 },
  南京: { other: 380, division: 480, minister: 600 },
  成都: { other: 380, division: 480, minister: 600 },
  武汉: { other: 380, division: 480, minister: 600 },
  西安: { other: 350, division: 450, minister: 580 },
  重庆: { other: 380, division: 480, minister: 600 },
  天津: { other: 380, division: 480, minister: 600 },
  苏州: { other: 380, division: 480, minister: 600 },
  宁波: { other: 400, division: 500, minister: 650 },
  青岛: { other: 380, division: 480, minister: 600 },
  厦门: { other: 400, division: 500, minister: 650 },
  长沙: { other: 350, division: 450, minister: 580 },
  郑州: { other: 350, division: 450, minister: 580 },
  济南: { other: 380, division: 480, minister: 600 },
  哈尔滨: { other: 350, division: 450, minister: 580 },
  沈阳: { other: 350, division: 450, minister: 580 },
});

/**
 * 获取城市差旅标准价（其他人员档）
 * @param {string} city
 * @returns {number|null} 元/间·天，未知城市返回 null
 */
function getCityRate(city) {
  const c = (city || '').trim();
  if (!c) return null;
  const rates = cityRates[c];
  if (rates && typeof rates.other === 'number') return rates.other;
  return null;
}

module.exports = {
  cityRates,
  getCityRate,
};
