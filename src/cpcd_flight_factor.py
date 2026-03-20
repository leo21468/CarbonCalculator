"""
机票/酒店等 CPCD 因子查询。

数据源：优先 data/cpcd_catalog.csv（core + 扩展库合并），否则 data/Emission factors.csv。
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_CATALOG = _DATA / "cpcd_catalog.csv"
_CPCD_CSV = _CATALOG if _CATALOG.exists() else _DATA / "Emission factors.csv"

_lock = threading.Lock()
_loaded = False
_df = None


_RE_CARBON_FOOTPRINT = re.compile(
    r"([\d.eE+-]+)\s*(t|kg|g)\s*CO2e?\s*[/／]\s*([^\s,;]+)",
    re.IGNORECASE,
)


def _load_cpcd_once() -> None:
    global _loaded, _df
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        if not _CPCD_CSV.exists():
            _df = None
            _loaded = True
            return
        _df = pd.read_csv(_CPCD_CSV, encoding="utf-8")
        # 标准化列名（与 cpcd_matcher.py 相同的映射思路）
        col_map = {
            "产品ID": "product_id",
            "产品名称": "product_name",
            "核算边界": "accounting_boundary",
            "碳足迹": "carbon_footprint",
            "企业名称": "company_name",
            "数据年份": "data_year",
            "数据类型": "data_type",
            "是否低碳": "is_low_carbon",
        }
        _df.columns = [col_map.get(str(c).strip(), str(c).strip()) for c in _df.columns]
        _loaded = True


def select_flight_product(is_domestic: bool, cabin: Optional[str]) -> str:
    """
    根据路由与舱位选择 CPCD 的“产品名称关键字”。
    """
    # 口径：国际统一使用“国际飞机航程”一行；
    # 国内不走该 CPCD 分支（由 emission_factors.csv 的“航空差旅”因子统一核算）。
    if is_domestic:
        return "国内飞机航程"
    return "国际飞机航程"


def get_cpcd_carbon_footprint(product_name_keyword: str) -> Optional[str]:
    """
    在 CPCD（Emission factors.csv）中查找最匹配的碳当量因子 carbon_footprint 字段。
    选择策略：product_name 包含关键字；同关键字优先 data_year 最大。
    """
    _load_cpcd_once()
    if _df is None or _df.empty:
        return None
    if "product_name" not in _df.columns or "carbon_footprint" not in _df.columns:
        return None
    mask = _df["product_name"].fillna("").astype(str).str.contains(product_name_keyword, na=False)
    sub = _df[mask]
    if sub.empty:
        return None
    if "data_year" in sub.columns:
        # 取最大年份（无法解析则当作 0）
        years = pd.to_numeric(sub["data_year"], errors="coerce").fillna(0)
        sub = sub.assign(_year=years).sort_values(by="_year", ascending=False)
    row = sub.iloc[0]
    return str(row.get("carbon_footprint", "") or "")


def parse_carbon_footprint_to_factor_kg(carbon_footprint: str) -> Tuple[float, str]:
    """
    解析如：
      - '0.18362kgCO2e / 人·千米'
      - '4.49363kgCO2e / 千米'
      - '0.40781kgCO2e / 人·千米'
    返回：(factor_kg_per_unit, unit_name)
    """
    if not carbon_footprint:
        return 0.0, ""
    t = str(carbon_footprint).strip()
    m = _RE_CARBON_FOOTPRINT.search(t)
    if not m:
        return 0.0, ""
    val = float(m.group(1))
    prefix = m.group(2).lower()
    unit_name = m.group(3).strip()
    if prefix == "t":
        val *= 1000.0
    elif prefix == "g":
        val /= 1000.0
    return val, unit_name

