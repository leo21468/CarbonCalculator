"""
端到端流水线：发票 → 分类 → 排放核算 → 碳账本/碳利润表。
"""
from __future__ import annotations
from typing import List, Optional

from .models import (
    CarbonLedgerEntry,
    CarbonProfitStatement,
    EmissionResult,
    Invoice,
)
from .invoice_parser import _build_invoice_from_dict
from .classifier import InvoiceScopeClassifier
from .emission_calculator import EmissionCalculator
from .carbon_ledger import (
    build_carbon_ledger_entries,
    build_carbon_profit_statement,
    monthly_virtual_voucher,
)
from .config import AppConfig

# 非产品行关键词（汇总、元数据等；避免误伤含「单位」等的正常品名）
_NON_PRODUCT_KEYWORDS = (
    "价税合计", "合计（", "合计(", "小计", "买方信息", "购方名称", "销方名称",
    "电子发票", "发票号码", "发票代码", "开票日期", "纳税人识别号", "统一社会信用",
)


def _filter_invalid_invoice_lines(invoice: "Invoice") -> None:
    """剔除误解析为非产品行：表头、汇总、发票号/税号被当作金额等。"""
    amt_limit = 1e8  # 单行金额 > 1亿视为异常（多为发票号/税号误解析）
    valid = []
    for line in invoice.lines:
        name = (line.name or "").strip()
        amt = line.amount or 0.0
        if not name:
            continue
        if any(kw in name for kw in _NON_PRODUCT_KEYWORDS):
            continue
        if amt >= amt_limit:
            continue
        if amt <= 0:
            continue
        if len(name) <= 2 and amt > 1e6:
            continue
        valid.append(line)
    invoice.lines.clear()
    invoice.lines.extend(valid)


class CarbonAccountingPipeline:
    """
    从发票输入到碳利润表/双账本的一条龙处理。
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig()
        self.classifier = InvoiceScopeClassifier(
            ref_table_path=self.config.scope_mapping.ref_table_path,
            ref_db_path=self.config.scope_mapping.ref_db_path,
        )
        self.calculator = EmissionCalculator()

    def process_invoice(
        self,
        invoice: Invoice,
        ref_invoice_id: Optional[str] = None,
    ) -> dict:
        """
        处理单张发票：分类 → 排放计算 → 碳账本条目。
        返回：classified, emission_results, ledger_entries
        """
        _filter_invalid_invoice_lines(invoice)
        classified = self.classifier.classify_invoice(invoice)
        emission_results = self.calculator.calculate_batch(classified)
        ledger_entries = build_carbon_ledger_entries(
            emission_results,
            self.config.carbon_price,
            ref_invoice_id=ref_invoice_id,
        )
        return {
            "classified": classified,
            "emission_results": emission_results,
            "ledger_entries": ledger_entries,
            "aggregate_kg": self.calculator.aggregate_by_scope(emission_results),
        }

    def process_invoice_from_dict(
        self,
        data: dict,
        ref_invoice_id: Optional[str] = None,
    ) -> dict:
        """从 API 返回的 dict 解析发票并处理"""
        invoice = _build_invoice_from_dict(data)
        return self.process_invoice(invoice, ref_invoice_id=ref_invoice_id)

    def build_statement(
        self,
        revenue: float,
        traditional_cost: float,
        emission_results: List[EmissionResult],
        carbon_asset_pnl: float = 0.0,
    ) -> CarbonProfitStatement:
        """根据收入、传统成本、排放结果构建碳利润表"""
        return build_carbon_profit_statement(
            revenue,
            traditional_cost,
            emission_results,
            self.config.carbon_price,
            carbon_asset_pnl=carbon_asset_pnl,
        )

    def monthly_close(self, total_emission_kg: float) -> CarbonLedgerEntry:
        """月末结转：总排放量 → 虚拟凭证"""
        return monthly_virtual_voucher(
            total_emission_kg,
            self.config.carbon_price,
        )
