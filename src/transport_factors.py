"""
货运排放因子：data/transport_factors.json（与 invoice-parser 同源）。

- 铁路、航空：CPCD 2024（gCO2e/公吨·公里，JSON 内提供 kgCO2e/公吨·公里）
- 公路：由 data/transport.xlsx 经 tools/sync_transport_factors.py 汇总
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]
_JSON_PATH = _ROOT / "data" / "transport_factors.json"


def load_transport_factors() -> Dict[str, Any]:
    if not _JSON_PATH.exists():
        return {}
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_rail_kg_co2e_per_tonne_km(data: Optional[Dict[str, Any]] = None) -> float:
    d = data if data is not None else load_transport_factors()
    r = d.get("rail") or {}
    v = r.get("kg_co2e_per_tonne_km")
    return float(v) if v is not None else 0.006502


def get_air_kg_co2e_per_tonne_km(data: Optional[Dict[str, Any]] = None) -> float:
    d = data if data is not None else load_transport_factors()
    a = d.get("air") or {}
    v = a.get("kg_co2e_per_tonne_km")
    return float(v) if v is not None else 0.921


def get_road_default_kg_co2e_per_tonne_km(data: Optional[Dict[str, Any]] = None) -> Optional[float]:
    d = data if data is not None else load_transport_factors()
    rd = d.get("road_default") or {}
    v = rd.get("kg_co2e_per_tonne_km")
    return float(v) if v is not None else None


def freight_emissions_kg(
    tonne_km: float,
    mode: str,
    *,
    product_id: Optional[str] = None,
    invoice_text: str = "",
) -> Tuple[float, Dict[str, Any]]:
    """
    按吨公里计算货运 CO2e（kg）。
    mode: 'rail' | 'air' | 'road'
    返回 (kg, 使用的因子元数据)
    """
    data = load_transport_factors()
    mode = (mode or "road").lower()
    meta: Dict[str, Any] = {"mode": mode, "tonne_km": tonne_km}

    if mode == "rail":
        kg_km = get_rail_kg_co2e_per_tonne_km(data)
        meta.update({"factor": kg_km, "source": (data.get("rail") or {}).get("source")})
        return tonne_km * kg_km, meta
    if mode == "air":
        kg_km = get_air_kg_co2e_per_tonne_km(data)
        meta.update({"factor": kg_km, "source": (data.get("air") or {}).get("source")})
        return tonne_km * kg_km, meta

    modes: List[Dict[str, Any]] = list((data.get("road_modes") or []))
    chosen: Optional[Dict[str, Any]] = None
    if product_id:
        for row in modes:
            if str(row.get("product_id") or "") == product_id:
                chosen = row
                break
    if chosen is None and invoice_text:
        text = invoice_text.replace(" ", "").replace("\u00a0", "")
        best_len = 0
        for row in modes:
            name = str(row.get("mode_cn") or "").replace("\u00a0", "").replace(" ", "")
            if len(name) >= 4 and name in text and len(name) > best_len:
                best_len = len(name)
                chosen = row
    if chosen is None:
        chosen = data.get("road_default") or {}
    kg_km = chosen.get("kg_co2e_per_tonne_km") if chosen else None
    if kg_km is None:
        kg_km = get_road_default_kg_co2e_per_tonne_km(data)
    if kg_km is None:
        kg_km = 0.2478
    kg_km = float(kg_km)
    meta.update(
        {
            "factor": kg_km,
            "source": (chosen or {}).get("source"),
            "product_id": (chosen or {}).get("product_id"),
            "mode_cn": (chosen or {}).get("mode_cn"),
        }
    )
    return tonne_km * kg_km, meta
