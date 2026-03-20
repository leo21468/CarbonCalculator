"""
系统配置：碳价、默认排放因子、核算模式等。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CarbonPriceConfig:
    """碳价配置：显性（市场）或隐性（内部）"""
    source: str  # "market" | "internal"
    price_per_ton: float  # 元/吨CO2e
    currency: str = "CNY"
    # 若 source=market，可填交易所/抓取URL
    market_source: Optional[str] = None  # 如 "上海环境能源交易所"


@dataclass
class ScopeMappingConfig:
    """税收编码→排放范围映射配置"""
    ref_table_path: Optional[Path] = None  # reference table.xlsx 路径，默认项目根目录
    ref_db_path: Optional[Path] = None       # SQLite 路径，默认 data/reference_table.db；优先于 xlsx


@dataclass
class EmissionConfig:
    """排放核算相关配置"""
    # 默认电力排放因子 kgCO2/kWh（可替换为省级因子）
    default_electricity_factor: float = 0.5777  # 与 data/2024.pdf 表1、grid_carbon_factors.json 全国平均一致
    # 默认热力 kgCO2/GJ 或 kgCO2/MJ
    default_heat_factor: float = 0.11  # 示例，按实际替换
    # EEIO 默认路径（投入产出表因子）
    eeio_factors_path: Optional[str] = None


@dataclass
class AppConfig:
    """应用总配置"""
    scope_mapping: ScopeMappingConfig = field(default_factory=ScopeMappingConfig)
    carbon_price: CarbonPriceConfig = field(
        default_factory=lambda: CarbonPriceConfig(
            source="internal",
            price_per_ton=100.0,
        )
    )
    emission: EmissionConfig = field(default_factory=EmissionConfig)
