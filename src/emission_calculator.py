"""
第三步：排放量化核算模型。
1. 活动数据法（高精度）：发票含数量（升、度、吨）时，E = 活动数据 × 排放因子。
2. 基于支出的经济投入产出（EEIO）：仅含金额时，用金额 × 排放强度（kg/元）。
"""
from __future__ import annotations
from typing import List, Optional

from .models import ClassifiedLineItem, EmissionResult, Scope
from .emission_factors import EmissionFactorStore


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
}


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
        factor = self.factors.get(factor_id)
        if not factor:
            factor = self.factors.get("scope3_default") or {
                "unit": "CNY",
                "kg_co2e_per_unit": 0.00015,
            }

        unit = factor.get("unit", "CNY")
        kg_per_unit = factor.get("kg_co2e_per_unit", 0.0)

        # 活动数据法：有数量且单位可映射
        if line.quantity is not None and line.quantity > 0 and line.unit:
            normalized_unit = UNIT_NORMALIZE.get(line.unit.strip(), line.unit.strip())
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
