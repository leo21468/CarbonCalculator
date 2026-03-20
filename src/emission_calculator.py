"""
第三步：排放量化核算模型。
1. 活动数据法（高精度）：发票含数量（升、度、吨）时，E = 活动数据 × 排放因子。
2. 基于支出的经济投入产出（EEIO）：仅含金额时，用金额 × 排放强度（kg/元）。
"""
from __future__ import annotations
import re
from typing import List, Optional

from .models import ClassifiedLineItem, EmissionResult, Scope
from .emission_factors import EmissionFactorStore
from .flight_utils import extract_iata_pair, get_airport_by_iata, haversine_distance_km
from .cpcd_flight_factor import get_cpcd_carbon_footprint, parse_carbon_footprint_to_factor_kg


# 单位标准化：发票常用单位 → 因子表单位
UNIT_NORMALIZE = {
    "度": "kWh",
    "千瓦时": "kWh",
    "kwh": "kWh",
    "吨": "t",
    "升": "L",
    "l": "L",
    "立方米": "m3",
    "m³": "m3",
    "元": "CNY",
    "cny": "CNY",
    # 用水单位
    "吨(水)": "m3",
    "t(水)": "m3",
}

# 各城市酒店差旅日均费用参考（元/间夜，来源：财政部差旅费管理办法"其他人员"标准）
# 用于住宿发票无入住天数时反推间夜数
_HOTEL_CITY_PRICE: dict = {
    "北京": 500, "上海": 500, "广州": 400, "深圳": 400,
    "成都": 350, "杭州": 350, "南京": 350, "武汉": 350,
    "天津": 350, "重庆": 300, "西安": 300, "长沙": 300,
    "默认": 300,
}

# 住宿碳排放因子（kgCO2e/晚）
# 数据口径：国内住宿差旅-基于消费数量核算（66.52 kgCO2e / 晚）
_HOTEL_KG_PER_NIGHT = 66.52

# 住宿基于支出金额的排放因子（kgCO2e/元）
# 数据口径：国内住宿差旅-基于支出金额核算（2.036 tCO2e / 万元人民币）
# 2.036 tCO2e/万元 = 2036 kgCO2e/万元 = 0.2036 kgCO2e/元
_HOTEL_KG_PER_CNY = 0.2036


class EmissionCalculator:
    """
    根据数据完整度自动切换核算模式：
    - 有 quantity + unit → 活动数据法
    - 仅 amount（元）→ EEIO
    """
    def __init__(self):
        self.factors = EmissionFactorStore()

    def calculate_line(self, classified: ClassifiedLineItem) -> Optional[EmissionResult]:
        """单行排放计算"""
        line = classified.line
        factor_id = classified.emission_factor_id or "scope3_default"

        # 机票专用分支：识别出发/到达 IATA 三位码 → 大圆距离 → CPCD 机票航程碳当量
        if factor_id == "cpcd_flight":
            return self._calculate_flight_ticket_cpcd(classified)

        # 酒店专用分支：国外酒店走 CPCD 的“酒店住宿”因子
        if factor_id == "cpcd_hotel":
            return self._calculate_hotel_accommodation_cpcd(classified, line)

        factor = self.factors.get(factor_id)
        if not factor:
            factor = self.factors.get("scope3_default") or {
                "unit": "CNY",
                "kg_co2e_per_unit": 0.00015,
            }

        unit = factor.get("unit", "CNY")
        kg_per_unit = factor.get("kg_co2e_per_unit", 0.0)

        # 住宿发票特殊处理：有入住天数用间夜法，否则按城市均价反推
        if factor_id == "scope3_accommodation":
            return self._calculate_accommodation(classified, line)

        # 活动数据法：有数量且单位可映射
        if line.quantity is not None and line.quantity > 0 and line.unit:
            unit_str = str(line.unit).strip() if line.unit else ""
            normalized_unit = UNIT_NORMALIZE.get(unit_str, unit_str)
            if normalized_unit == unit:
                emission_kg = line.quantity * kg_per_unit
                return EmissionResult(
                    scope=classified.scope,
                    quantity=line.quantity,
                    unit=line.unit,
                    emission_kg=emission_kg,
                    method="activity",
                    factor_used=kg_per_unit,
                )
            # 若单位不一致可在此做换算（如 kWh 与 MWh）

        # EEIO：仅金额（万元或元；因子表按元则 amount 直接乘）
        amount_cny = line.amount
        if amount_cny <= 0:
            return None
        if unit == "CNY":
            emission_kg = amount_cny * kg_per_unit
            return EmissionResult(
                scope=classified.scope,
                quantity=amount_cny,
                unit="CNY",
                emission_kg=emission_kg,
                method="eeio",
                factor_used=kg_per_unit,
            )

        # 仍有金额但因子是物理单位：用 EEIO 兜底因子
        fallback = self.factors.get("scope3_default")
        if fallback:
            k = fallback.get("kg_co2e_per_unit", 0.00015)
            return EmissionResult(
                scope=classified.scope,
                quantity=amount_cny,
                unit="CNY",
                emission_kg=amount_cny * k,
                method="eeio",
                factor_used=k,
            )
        return None

    def _calculate_flight_ticket_cpcd(self, classified: ClassifiedLineItem) -> Optional[EmissionResult]:
        name = classified.line.name or ""
        pair = extract_iata_pair(name)
        if not pair:
            return None
        from_code, to_code = pair

        from_airport = get_airport_by_iata(from_code)
        to_airport = get_airport_by_iata(to_code)
        if not from_airport or not to_airport:
            return None

        distance_km = haversine_distance_km(
            from_airport.latitude_deg,
            from_airport.longitude_deg,
            to_airport.latitude_deg,
            to_airport.longitude_deg,
        )
        if distance_km <= 0:
            return None

        # 国内/国际判定：优先使用 airport.xlsx 的 iso_country
        is_domestic = False
        if from_airport.iso_country and to_airport.iso_country:
            is_domestic = (from_airport.iso_country == to_airport.iso_country)

        # 口径：按你的要求使用固定系数（不依赖 CPCD 文件是否能匹配）
        # 国内：0.0829 kgCO2e / 人·千米
        # 国际：0.18362 kgCO2e / 人·千米
        factor_val_kg = 0.0829 if is_domestic else 0.18362
        unit_name = "人·千米"

        # 活动数据：优先用 quantity 作为“乘客/机票数量”，缺失则默认为 1
        passengers = classified.line.quantity if classified.line.quantity and classified.line.quantity > 0 else 1.0

        emission_kg = factor_val_kg * distance_km * passengers
        activity = passengers * distance_km
        unit_out = "人·千米"

        return EmissionResult(
            scope=classified.scope,
            quantity=float(activity),
            unit=unit_out,
            emission_kg=float(emission_kg),
            method="flight_cpcd",
            factor_used=float(factor_val_kg),
        )

    def _calculate_accommodation(
        self, classified: ClassifiedLineItem, line: "InvoiceLineItem"
    ) -> Optional[EmissionResult]:
        """
        住宿发票排放计算（国内）。
        优先：有金额 →「基于支出金额」2.036 tCO2e/万元 → 0.2036 kgCO2e/元。
        兜底：无金额 → 间夜 quantity × 66.52 kgCO2e/晚（基于消费数量）。
        """
        if line.amount and line.amount > 0:
            amount_cny = float(line.amount)
            emission_kg = amount_cny * _HOTEL_KG_PER_CNY
            return EmissionResult(
                scope=classified.scope,
                quantity=amount_cny,
                unit="CNY",
                emission_kg=float(emission_kg),
                method="eeio",
                factor_used=_HOTEL_KG_PER_CNY,
            )

        if line.quantity is not None and line.quantity > 0:
            nights = float(line.quantity)
            emission_kg = nights * _HOTEL_KG_PER_NIGHT
            return EmissionResult(
                scope=classified.scope,
                quantity=nights,
                unit="晚",
                emission_kg=float(emission_kg),
                method="activity",
                factor_used=_HOTEL_KG_PER_NIGHT,
            )

        return None

    def _calculate_hotel_accommodation_cpcd(
        self,
        classified: ClassifiedLineItem,
        line: "InvoiceLineItem",
    ) -> Optional[EmissionResult]:
        """
        CPCD 外国酒店住宿核算：
        - 明细名中抽取括号地区/国家（如“酒店住宿（俄罗斯联邦）”）
        - 从 CPCD 表里查“酒店住宿”对应因子（kgCO2e / 房·晚）
        - quantity 优先按入住晚数 nights；缺失则用 amount 做极简估算
        """
        text = f"{line.name or ''} {line.remark or ''} {line.tax_classification_name or ''}"
        regions = re.findall(r"（([^）]+)）", text) + re.findall(r"\(([^)]+)\)", text)
        region = regions[0].strip() if regions else ""

        footprint = None
        if region:
            # CPCD 的 product_name 中一般都会包含 region 字段
            footprint = get_cpcd_carbon_footprint(region)
        if not footprint:
            footprint = get_cpcd_carbon_footprint("酒店住宿")
        if not footprint:
            return None

        factor_val_kg, unit_name = parse_carbon_footprint_to_factor_kg(footprint)
        if factor_val_kg <= 0:
            return None

        if line.quantity is not None and line.quantity > 0:
            nights = float(line.quantity)
        elif line.amount and line.amount > 0:
            # 兜底：按 300 元/晚估算
            nights = max(1.0, float(line.amount) / 300.0)
        else:
            nights = 1.0

        emission_kg = factor_val_kg * nights
        unit_out = unit_name or "房·晚"

        return EmissionResult(
            scope=classified.scope,
            quantity=nights,
            unit=unit_out,
            emission_kg=float(emission_kg),
            method="hotel_cpcd",
            factor_used=float(factor_val_kg),
        )

    def calculate_batch(self, classified_lines: List[ClassifiedLineItem]) -> List[EmissionResult]:
        """批量计算，过滤掉 None"""
        results = []
        for cl in classified_lines:
            r = self.calculate_line(cl)
            if r is not None:
                results.append(r)
        return results

    def aggregate_by_scope(self, results: List[EmissionResult]) -> dict:
        """按 Scope 汇总排放量（kg）"""
        agg = {Scope.SCOPE_1: 0.0, Scope.SCOPE_2: 0.0, Scope.SCOPE_3: 0.0}
        for r in results:
            agg[r.scope] = agg.get(r.scope, 0.0) + r.emission_kg
        return agg
