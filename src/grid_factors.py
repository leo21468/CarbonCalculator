"""
电网排放因子：从 data/grid_carbon_factors.json 读取（与 invoice-parser 同源）。

- 全国平均：data/2024.pdf 表1
- 区域 / 省级：data/2023.pdf 表2、表3
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parents[1]
_GRID_JSON = _ROOT / "data" / "grid_carbon_factors.json"


def load_grid_carbon_data() -> Dict[str, Any]:
    if not _GRID_JSON.exists():
        return {}
    with open(_GRID_JSON, encoding="utf-8") as f:
        return json.load(f)


def get_national_kg_co2e_per_kwh(data: Optional[Dict[str, Any]] = None) -> float:
    d = data if data is not None else load_grid_carbon_data()
    na = d.get("national_average") or {}
    v = na.get("kg_co2e_per_kwh")
    return float(v) if v is not None else 0.5777


def get_regional_kg_co2e_per_kwh(region_name: str, data: Optional[Dict[str, Any]] = None) -> Optional[float]:
    d = data if data is not None else load_grid_carbon_data()
    rg = d.get("regional_grids") or {}
    v = rg.get(region_name.strip())
    return float(v) if v is not None else None


def get_provincial_kg_co2e_per_kwh(province: str, data: Optional[Dict[str, Any]] = None) -> Optional[float]:
    d = data if data is not None else load_grid_carbon_data()
    pv = d.get("provinces") or {}
    v = pv.get(province.strip())
    return float(v) if v is not None else None
