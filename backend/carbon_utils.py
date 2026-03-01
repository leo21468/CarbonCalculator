"""
碳足迹解析与价格计算：从 CPCD 碳足迹字符串解析数值，计算碳成本。
"""
import re
from typing import Tuple


def parse_carbon_footprint(text: str) -> Tuple[float, str]:
    """
    解析碳足迹字符串，支持多种格式：
      - "7.4tCO2e / 公吨"、"0.5839kgCO2e/kWh"（标准格式）
      - "1.2 kg CO2e/件"（单位前有空格）
      - "3.5CO2e/t"（无 kg/g/t 前缀，直接 CO2e）
      - "33.53gCO2e/千瓦时"（克级）
    返回 (每单位 kgCO2e, 单位名)。
    """
    if not text or not str(text).strip():
        return 0.0, ""
    t = str(text).strip()

    # 优先匹配带显式质量单位的格式（tCO2e / kgCO2e / gCO2e），单位间允许空格
    m = re.search(
        r"([\d.eE+-]+)\s*(t|kg|g)\s*CO2e?\s*[/／]\s*([^\s,;]+)",
        t, re.IGNORECASE
    )
    if not m:
        # 兜底：匹配无斜线的 tCO2e/kgCO2e/gCO2e（不含分母单位）
        m = re.search(r"([\d.eE+-]+)\s*(t|kg|g)\s*CO2e?", t, re.IGNORECASE)
    if not m:
        # 匹配 CO2e/t 或 CO2e/件 等（无质量前缀，默认 kg）
        m2 = re.search(r"([\d.eE+-]+)\s*CO2e?\s*[/／]\s*([^\s,;]+)", t, re.IGNORECASE)
        if m2:
            try:
                val = float(m2.group(1))
            except ValueError:
                return 0.0, ""
            unit_name = m2.group(2).strip()
            # 无前缀默认视为 kg
            return val, unit_name or "单位"
        return 0.0, ""

    try:
        val = float(m.group(1))
    except ValueError:
        return 0.0, ""
    unit_prefix = m.group(2).lower()
    unit_name = m.group(3).strip() if len(m.groups()) >= 3 and m.group(3) else ""
    if unit_prefix == "t":
        val *= 1000
    elif unit_prefix == "g":
        val /= 1000
    # kg 不变
    return val, unit_name or "单位"


def carbon_cost_cny(co2_kg: float, price_per_ton: float) -> float:
    """碳成本 = 排放量(吨) × 碳价(元/吨)"""
    return (co2_kg / 1000) * price_per_ton
