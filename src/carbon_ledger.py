"""
第四步：碳利润表与双账本。
（一）碳价；（二）成本归集与分配；（三）碳利润表结构；（四）双账本平行记账。
"""
from __future__ import annotations
from typing import List, Optional

from .config import AppConfig, CarbonPriceConfig
from .models import (
    CarbonLedgerEntry,
    CarbonProfitStatement,
    DebitAccount,
    EmissionResult,
    Scope,
)


def emission_kg_to_tons(kg: float) -> float:
    return kg / 1000.0


def carbon_cost_cny(emission_kg: float, price_per_ton: float) -> float:
    """碳成本 = 排放量(吨) × 碳价(元/吨)"""
    return emission_kg_to_tons(emission_kg) * price_per_ton


def scope_to_debit_account(scope: Scope, cost_nature: str = "auto") -> DebitAccount:
    """
    将排放范围映射到碳成本借方科目。
    成本性质：生产成本 → 制造费用；期间费用 → 销售/管理费用。
    cost_nature: "manufacturing" | "selling" | "admin" | "auto"
    """
    if cost_nature == "manufacturing":
        return DebitAccount.MFG_CARBON
    if cost_nature == "selling":
        return DebitAccount.SELLING_CARBON
    if cost_nature == "admin":
        return DebitAccount.ADMIN_CARBON
    # auto：Scope 1/2 多为生产，Scope 3 可按场景再分，这里简化为制造/管理
    if scope == Scope.SCOPE_1 or scope == Scope.SCOPE_2:
        return DebitAccount.MFG_CARBON
    return DebitAccount.ADMIN_CARBON


def build_carbon_ledger_entries(
    emission_results: List[EmissionResult],
    carbon_price: CarbonPriceConfig,
    cost_nature: str = "auto",
    ref_invoice_id: Optional[str] = None,
) -> List[CarbonLedgerEntry]:
    """
    根据排放结果生成碳会计平行记账条目。
    借：xx科目 - 碳成本；金额 = 排放量(吨) × 碳价。
    """
    entries = []
    for r in emission_results:
        amount_cny = carbon_cost_cny(r.emission_kg, carbon_price.price_per_ton)
        debit = scope_to_debit_account(r.scope, cost_nature)
        entries.append(
            CarbonLedgerEntry(
                description=f"碳成本 {r.scope.value}",
                scope=r.scope,
                emission_kg=r.emission_kg,
                debit_account=debit,
                amount_cny=amount_cny,
                ref_invoice_id=ref_invoice_id,
            )
        )
    return entries


def build_carbon_profit_statement(
    revenue: float,
    traditional_cost: float,
    emission_results: List[EmissionResult],
    carbon_price: CarbonPriceConfig,
    carbon_asset_pnl: float = 0.0,
) -> CarbonProfitStatement:
    """
    构建碳利润表。
    1. 营业收入；2. 传统营业成本；3. 毛利；
    4. 直接碳成本(Scope 1)；5. 隐含碳成本(Scope 2&3)；
    6. 经碳调整后的毛利；7. 碳资产收益/损失；8. 净碳损益。
    """
    st = CarbonProfitStatement(
        revenue=revenue,
        traditional_cost=traditional_cost,
        carbon_asset_pnl=carbon_asset_pnl,
    )
    scope1_kg = sum(r.emission_kg for r in emission_results if r.scope == Scope.SCOPE_1)
    scope2_kg = sum(r.emission_kg for r in emission_results if r.scope == Scope.SCOPE_2)
    scope3_kg = sum(r.emission_kg for r in emission_results if r.scope == Scope.SCOPE_3)
    st.scope1_carbon_cost = carbon_cost_cny(scope1_kg, carbon_price.price_per_ton)
    st.scope2_carbon_cost = carbon_cost_cny(scope2_kg, carbon_price.price_per_ton)
    st.scope3_carbon_cost = carbon_cost_cny(scope3_kg, carbon_price.price_per_ton)
    st.compute_derived()
    return st


def monthly_virtual_voucher(
    total_emission_kg: float,
    carbon_price: CarbonPriceConfig,
    debit_account: DebitAccount = DebitAccount.ADMIN_CARBON,
) -> CarbonLedgerEntry:
    """
    期末结转：月底抓取当月 Scope 1+2+3 总量 × 碳价，生成虚拟凭证，扣减当月利润。
    """
    amount = carbon_cost_cny(total_emission_kg, carbon_price.price_per_ton)
    return CarbonLedgerEntry(
        description="当月碳成本结转（碳调整后净利润）",
        scope=Scope.SCOPE_3,
        emission_kg=total_emission_kg,
        debit_account=debit_account,
        amount_cny=amount,
    )
