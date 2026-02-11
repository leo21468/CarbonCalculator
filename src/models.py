"""
数据模型：发票结构化数据、排放范围、碳账本等。
对应设计文档：第一步 数据采集 与 第四步 碳利润表/双账本。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Scope(Enum):
    """GHG Protocol 碳排放范围"""
    SCOPE_1 = "Scope 1"   # 直接排放（燃料）
    SCOPE_2 = "Scope 2"   # 能源间接（电、热、冷）
    SCOPE_3 = "Scope 3"   # 价值链其他


@dataclass
class SellerInfo:
    """销方信息（用于推断行业排放背景）"""
    name: str
    tax_id: Optional[str] = None
    address: Optional[str] = None


@dataclass
class InvoiceLineItem:
    """
    发票明细行：核心语义与核算基础。
    对应设计：货物或应税劳务名称、税收分类编码、金额/单价/数量。
    """
    # 核心语义来源
    name: str  # 货物或应税劳务名称
    # 国家标准锚点：19位税收分类编码（最精确）
    tax_classification_code: Optional[str] = None  # 19位
    tax_classification_name: Optional[str] = None  # 简称，如 *成品油*汽油
    # 核算量化基础
    quantity: Optional[float] = None
    unit: Optional[str] = None  # 升、度、吨等
    unit_price: Optional[float] = None
    amount: float = 0.0  # 金额（元）
    # 行级备注（供 NLP 解析）
    remark: Optional[str] = None


@dataclass
class Invoice:
    """电子发票结构化数据（接口提取后的形态）"""
    invoice_code: Optional[str] = None
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    seller: Optional[SellerInfo] = None
    buyer: Optional[SellerInfo] = None
    lines: List[InvoiceLineItem] = field(default_factory=list)
    total_amount: float = 0.0
    # 原始格式标识
    source_format: Optional[str] = None  # "OFD" | "PDF" | "XML"


# --------------- 分类与核算结果 ---------------


@dataclass
class ClassifiedLineItem:
    """已按排放范围分类的发票明细行"""
    line: InvoiceLineItem
    scope: Scope
    # 分类依据
    match_type: str  # "tax_code" | "keyword" | "semantic" | "default"
    matched_tax_code: Optional[str] = None
    emission_factor_id: Optional[str] = None  # 映射表因子ID


@dataclass
class EmissionResult:
    """单行或汇总的排放量化结果"""
    scope: Scope
    quantity: float  # 活动数据（物理量或金额）
    unit: str  # "kWh" | "t" | "CNY" 等
    emission_kg: float  # 二氧化碳当量 kg
    method: str  # "activity" | "eeio"
    factor_used: Optional[float] = None


# --------------- 碳利润表与双账本 ---------------


class CostNature(Enum):
    """成本性质：生产成本 / 期间费用"""
    MANUFACTURING = "生产成本"
    PERIOD = "期间费用"


class DebitAccount(Enum):
    """碳成本借方科目（与设计文档一致）"""
    MFG_CARBON = "制造费用 - 碳成本"
    SELLING_CARBON = "销售费用 - 碳成本"
    ADMIN_CARBON = "管理费用 - 碳成本"
    # 可扩展：研发费用 - 碳成本 等


@dataclass
class CarbonLedgerEntry:
    """
    碳会计平行记账条目。
    举例：借：原材料碳足迹 50吨（100万 × 因子0.5）
    """
    description: str
    scope: Scope
    emission_kg: float
    debit_account: DebitAccount
    amount_cny: float  # 碳成本金额 = 排放量(t) × 碳价
    ref_invoice_id: Optional[str] = None
    ref_line_id: Optional[str] = None


@dataclass
class CarbonProfitItem:
    """碳利润表单项"""
    name: str
    value: float
    note: Optional[str] = None


@dataclass
class CarbonProfitStatement:
    """
    碳利润表结构（对应设计文档第四步）。
    项目1–8 与 计算逻辑、财务含义 一致。
    """
    # 1. 营业收入
    revenue: float = 0.0
    # 2. 传统营业成本（不含碳）
    traditional_cost: float = 0.0
    # 3. 毛利
    gross_profit: float = 0.0
    # 4. 直接碳成本 (Scope 1)
    scope1_carbon_cost: float = 0.0
    # 5. 隐含碳成本 (Scope 2 & 3)
    scope2_carbon_cost: float = 0.0
    scope3_carbon_cost: float = 0.0
    # 6. 经碳调整后的毛利
    carbon_adjusted_gross: float = 0.0
    # 7. 碳资产收益/损失（卖出配额 - 买入成本）
    carbon_asset_pnl: float = 0.0
    # 8. 净碳损益
    net_carbon_pnl: float = 0.0

    def compute_derived(self) -> None:
        """根据基础数据计算派生项"""
        self.gross_profit = self.revenue - self.traditional_cost
        implied = self.scope2_carbon_cost + self.scope3_carbon_cost
        self.carbon_adjusted_gross = (
            self.gross_profit - self.scope1_carbon_cost - implied
        )
        self.net_carbon_pnl = (
            self.carbon_adjusted_gross + self.carbon_asset_pnl
        )
