"""
排放因子表：19位税号/因子ID → 物理因子或 EEIO 因子。
"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, Optional

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"


def load_emission_factors() -> Dict[str, dict]:
    """
    加载 data/emission_factors.csv。
    返回 factor_id -> { scope, unit, kg_co2e_per_unit, description }
    """
    result = {}
    p = _DATA / "emission_factors.csv"
    if not p.exists():
        return result
    with open(p, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows or len(rows) < 2:
        return result
    for parts in rows[1:]:
        if not parts or len(parts) < 4:
            continue
        fid = parts[0].strip()
        try:
            kg_co2e = float(parts[3].strip())
        except (ValueError, TypeError):
            # Skip invalid rows with non-numeric emission factors
            continue
        result[fid] = {
            "scope": parts[1].strip(),
            "unit": parts[2].strip(),
            "kg_co2e_per_unit": kg_co2e,
            "description": parts[4].strip() if len(parts) > 4 else "",
        }
    return result


class EmissionFactorStore:
    def __init__(self):
        self._factors = load_emission_factors()

    def get(self, factor_id: str) -> Optional[dict]:
        return self._factors.get(factor_id)

    def get_kg_per_unit(self, factor_id: str) -> Optional[float]:
        d = self._factors.get(factor_id)
        return d.get("kg_co2e_per_unit") if d else None

    def get_unit(self, factor_id: str) -> Optional[str]:
        d = self._factors.get(factor_id)
        return d.get("unit") if d else None
