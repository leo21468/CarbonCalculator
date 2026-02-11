"""
第四步（五）：报表分析与洞察。
- 产品线「伪利润」识别：财务毛利高但碳调整后为负；
- 供应链议价依据：Scope 3 隐含碳成本过高的供应商。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from .models import CarbonProfitStatement, EmissionResult, Scope


@dataclass
class ProductLineCarbonInsight:
    """产品线碳视角：表面毛利 vs 碳调整后毛利"""
    product_line_id: str
    product_name: str
    gross_profit_pct: float  # 传统毛利率 %
    carbon_adjusted_gross_pct: float  # 碳调整后毛利率 %
    carbon_cost_total: float
    is_pseudo_profit: bool  # 碳调整后毛利为负则为 True


@dataclass
class SupplierCarbonInsight:
    """供应商隐含碳成本：用于供应链议价"""
    supplier_id: str
    supplier_name: str
    scope3_emission_kg: float
    scope3_carbon_cost_cny: float
    total_purchase_cny: float
    carbon_intensity: float  # 元采购额对应碳成本或排放强度


def identify_pseudo_profit(
    gross_profit_pct: float,
    carbon_adjusted_gross_pct: float,
) -> bool:
    """
    识别「伪利润」：财务毛利为正但碳调整后毛利为负，
    说明产品表面赚钱，实际在透支环境成本。
    """
    return gross_profit_pct > 0 and carbon_adjusted_gross_pct < 0


def product_line_insights(
    product_lines: List[dict],
) -> List[ProductLineCarbonInsight]:
    """
    输入：各产品线的 revenue, traditional_cost, emission_results（或碳成本汇总）。
    输出：是否伪利润、碳调整后毛利率等。
    """
    insights = []
    for pl in product_lines:
        revenue = pl.get("revenue", 0) or 0
        cost = pl.get("traditional_cost", 0) or 0
        carbon_cost = pl.get("carbon_cost", 0) or 0
        if revenue <= 0:
            continue
        gross_pct = (revenue - cost) / revenue * 100
        carbon_adj_pct = (revenue - cost - carbon_cost) / revenue * 100
        is_pseudo = identify_pseudo_profit(gross_pct, carbon_adj_pct)
        insights.append(
            ProductLineCarbonInsight(
                product_line_id=pl.get("product_line_id", ""),
                product_name=pl.get("product_name", ""),
                gross_profit_pct=gross_pct,
                carbon_adjusted_gross_pct=carbon_adj_pct,
                carbon_cost_total=carbon_cost,
                is_pseudo_profit=is_pseudo,
            )
        )
    return insights


def supplier_scope3_insights(
    supplier_emissions: List[dict],
    carbon_price_per_ton: float,
) -> List[SupplierCarbonInsight]:
    """
    按供应商汇总 Scope 3 排放与碳成本，得到隐含碳成本与采购额占比，
    用于「某供应商带来的隐含碳成本过高，要求降价或减排」。
    """
    results = []
    for s in supplier_emissions:
        sid = s.get("supplier_id", "")
        name = s.get("supplier_name", "")
        scope3_kg = s.get("scope3_emission_kg", 0) or 0
        purchase = s.get("total_purchase_cny", 0) or 0
        cost_cny = (scope3_kg / 1000.0) * carbon_price_per_ton
        intensity = (scope3_kg / purchase) if purchase > 0 else 0
        results.append(
            SupplierCarbonInsight(
                supplier_id=sid,
                supplier_name=name,
                scope3_emission_kg=scope3_kg,
                scope3_carbon_cost_cny=cost_cny,
                total_purchase_cny=purchase,
                carbon_intensity=intensity,
            )
        )
    return results
