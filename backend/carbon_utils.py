"""
碳足迹解析与价格计算：从 CPCD 碳足迹字符串解析数值，计算碳成本。
"""
import re
from typing import Optional, Tuple


def parse_carbon_footprint(text: str) -> Tuple[float, str]:
    """
    解析碳足迹字符串，如 "7.4tCO2e / 公吨"、"0.5839kgCO2e/kWh"。
    返回 (每单位 kgCO2e, 单位名)。
    """
    if not text or not str(text).strip():
        return 0.0, ""
    t = str(text).strip()
    # 匹配数字（含小数、科学计数法）和单位
    m = re.search(r"([\d.eE+-]+)\s*(tCO2e|kgCO2e|gCO2e)\s*[/／]\s*([^\s]+)", t)
    if not m:
        m = re.search(r"([\d.eE+-]+)\s*(tCO2e|kgCO2e|gCO2e)\s*[/／]?\s*([^\s]*)", t)
    if not m:
        m = re.search(r"([\d.eE+-]+)\s*(tCO2e|kgCO2e|gCO2e)", t)
    if not m:
        return 0.0, ""
    try:
        val = float(m.group(1))
    except ValueError:
        return 0.0, ""
    unit_raw = m.group(2).lower() if m.group(2) else "kg"
    unit_name = m.group(3).strip() if len(m.groups()) > 3 and m.group(3) else ""
    if unit_raw.startswith("t"):
        val *= 1000
    elif unit_raw.startswith("g") and not unit_raw.startswith("kg"):
        val /= 1000
    return val, unit_name or "单位"


def carbon_cost_cny(co2_kg: float, price_per_ton: float) -> float:
    """碳成本 = 排放量(吨) × 碳价(元/吨)"""
    return (co2_kg / 1000) * price_per_ton
