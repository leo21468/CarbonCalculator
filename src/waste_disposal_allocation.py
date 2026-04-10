"""
废弃物模块：按「活动数据 × 处置路径比例 × CPCD 因子」核算。
活动数据 = 发票数量 × 销售产品单台重量（kg）→ 吨；再按各类废弃物比例分配至焚烧/填埋/综合利用等路径。
CPCD 因子自 data/Emission factors.csv（或 cpcd_catalog.csv）按产品ID读取。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_CPCD_CSV = _DATA / "cpcd_catalog.csv" if (_DATA / "cpcd_catalog.csv").exists() else _DATA / "Emission factors.csv"

# 因子 ID（与 reference table / emission_factors.csv 中 waste_cat* 一致）
WASTE_CAT1_MSW = "waste_cat1_msw"  # ① 生活垃圾分类
WASTE_CAT2_INDUSTRIAL = "waste_cat2_industrial"  # ② 一般工业固废
WASTE_CAT3_WEEE = "waste_cat3_weee"  # ③ 电子废弃物
WASTE_CAT4_HW = "waste_cat4_hw"  # ④ 危险废弃物
WASTE_CAT5_AGRI = "waste_cat5_agri"  # ⑤ 农业固体废弃物

WASTE_ALLOCATION_FACTOR_IDS = frozenset(
    {
        WASTE_CAT1_MSW,
        WASTE_CAT2_INDUSTRIAL,
        WASTE_CAT3_WEEE,
        WASTE_CAT4_HW,
        WASTE_CAT5_AGRI,
    }
)

# 各路径选用的 CPCD 产品ID（来自 Emission factors.csv 等；可随数据表更新替换）
# ① 72% 焚烧 20% 填埋 8% 其他/堆肥
_C1 = [
    (0.72, "94333X0022023A"),  # 机械炉排炉垃圾焚烧
    (0.20, "94332X0032013A"),  # 生活垃圾填埋
    (0.08, "94339X0132017A"),  # 厨余堆肥+其余焚烧（代表堆肥/其他）
]
# ② 4% 焚烧 15% 填埋 81% 综合利用及其他
_C2 = [
    (0.04, "94333X0022023A"),
    (0.15, "94332X0032013A"),
    (0.81, "94313X0032016A"),  # 废塑料机械回收（综合利用代理）
]
# ③ 10% 焚烧 5% 填埋 85% 拆解回收
_C3 = [
    (0.10, "94333X0022023A"),
    (0.05, "94332X0032013A"),
    (0.85, "94313X0032016A"),  # 拆解回收代理
]
# ④ 35% 焚烧 15% 填埋 50% 综合利用
_C4 = [
    (0.35, "94311X0102022A"),  # 危险废物焚烧协同
    (0.15, "94332X0052013A"),  # 填埋无气回收
    (0.50, "94311X0022022A"),  # 污泥干化焚烧+建材利用（综合利用代理）
]
# ⑤ 10% 焚烧 2% 填埋 88% 综合利用
_C5 = [
    (0.10, "94333X0022023A"),
    (0.02, "94332X0032013A"),
    (0.88, "94313X0032016A"),
]

WASTE_ROUTE_PROFILES: Dict[str, List[Tuple[float, str]]] = {
    WASTE_CAT1_MSW: _C1,
    WASTE_CAT2_INDUSTRIAL: _C2,
    WASTE_CAT3_WEEE: _C3,
    WASTE_CAT4_HW: _C4,
    WASTE_CAT5_AGRI: _C5,
}

_cpcd_kg_per_tonne_cache: Dict[str, float] = {}


def _carbon_footprint_to_kg_per_tonne_waste(text: str) -> float:
    """将 CPCD 碳足迹字符串转为「千克 CO2e / 吨废弃物」。"""
    from backend.carbon_utils import parse_carbon_footprint

    if not text or not str(text).strip():
        return 0.0
    val, denom = parse_carbon_footprint(str(text).strip())
    if val <= 0:
        return 0.0
    d = (denom or "").strip().lower()
    if "公吨" in denom or (d == "吨" or denom == "t"):
        return float(val)
    if "千克" in denom or d in ("kg", "公斤"):
        return float(val) * 1000.0
    # 件、条、部等无法按吨归一化
    return 0.0


def _load_cpcd_row_by_id(product_id: str) -> Optional[str]:
    """返回匹配行的碳足迹字符串。"""
    if not _CPCD_CSV.exists():
        return None
    with open(_CPCD_CSV, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) < 2:
        return None
    for parts in rows[1:]:
        if not parts or len(parts) < 4:
            continue
        if parts[0].strip() == product_id.strip():
            return parts[3].strip()
    return None


def get_cpcd_kg_co2e_per_tonne(product_id: str) -> float:
    """CPCD 产品ID → 千克 CO2e/吨废弃物（缓存）。"""
    if product_id in _cpcd_kg_per_tonne_cache:
        return _cpcd_kg_per_tonne_cache[product_id]
    cf = _load_cpcd_row_by_id(product_id)
    k = _carbon_footprint_to_kg_per_tonne_waste(cf or "") if cf else 0.0
    _cpcd_kg_per_tonne_cache[product_id] = k
    return k


def compute_waste_emission_kg(mass_tonnes: float, profile_id: str) -> float:
    """
    废弃物质量（吨）× 各路径比例 × 各路径 kgCO2e/吨 → 总 kgCO2e。
    """
    if mass_tonnes <= 0:
        return 0.0
    routes = WASTE_ROUTE_PROFILES.get(profile_id)
    if not routes:
        return 0.0
    total = 0.0
    for ratio, cpcd_id in routes:
        intensity = get_cpcd_kg_co2e_per_tonne(cpcd_id)
        total += mass_tonnes * ratio * intensity
    return total


def is_waste_allocation_factor(factor_id: Optional[str]) -> bool:
    return bool(factor_id) and factor_id in WASTE_ALLOCATION_FACTOR_IDS
