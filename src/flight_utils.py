from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_AIRPORT_XLSX = _ROOT / "data" / "airport.xlsx"

_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class AirportCoord:
    latitude_deg: float
    longitude_deg: float
    iso_country: Optional[str]


_lock = threading.Lock()
_loaded = False
_iata_to_airport: Dict[str, AirportCoord] = {}


def _load_airport_index_once() -> None:
    global _loaded, _iata_to_airport
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        if not _AIRPORT_XLSX.exists():
            # 只有在 invoice 计算时才需要；这里直接降级为未找到索引
            _iata_to_airport = {}
            _loaded = True
            return

        df = pd.read_excel(_AIRPORT_XLSX)
        if df.empty:
            _iata_to_airport = {}
            _loaded = True
            return

        for _, r in df.iterrows():
            code = str(r.get("iata_code", "")).strip().upper() if pd.notna(r.get("iata_code", None)) else ""
            if not code or code == "NAN":
                continue
            lat = r.get("latitude_deg", None)
            lon = r.get("longitude_deg", None)
            if pd.isna(lat) or pd.isna(lon):
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                continue
            iso_country = None
            iso_val = r.get("iso_country", None)
            if iso_val is not None and not (hasattr(pd, "isna") and pd.isna(iso_val)):
                iso_country = str(iso_val).strip().upper() if str(iso_val).strip() else None
            _iata_to_airport[code] = AirportCoord(
                latitude_deg=lat_f,
                longitude_deg=lon_f,
                iso_country=iso_country,
            )

        _loaded = True


def get_airport_by_iata(iata_code: str) -> Optional[AirportCoord]:
    _load_airport_index_once()
    if not iata_code:
        return None
    return _iata_to_airport.get(iata_code.strip().upper())


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


_PAIR_RE = re.compile(r"([A-Za-z]{3})\s*[-–—/→>]+\s*([A-Za-z]{3})")
_CODE_RE = re.compile(r"\b([A-Za-z]{3})\b")
_PAIR_FROM_TO_CN_RE = re.compile(
    r"(出发|起飞)\D{0,60}\b([A-Z]{3})\b.*?(到达|降落)\D{0,60}\b([A-Z]{3})\b",
    re.IGNORECASE | re.DOTALL,
)
_PAIR_FROM_TO_EN_RE = re.compile(
    r"\bFROM\b\D{0,50}\b([A-Z]{3})\b.*?\bTO\b\D{0,50}\b([A-Z]{3})\b",
    re.IGNORECASE | re.DOTALL,
)


def extract_iata_pair(text: str) -> Optional[Tuple[str, str]]:
    """
    从票面文本提取 (出发, 到达) 的 IATA 三字码。
    优先识别形如 PEK-SHA / PEK→SHA / PEK/SHA 的形式。
    """
    if not text:
        return None
    t = str(text)
    t_upper = t.upper()

    # 1) 优先从“出发...到达...”结构直接抽取
    m = _PAIR_FROM_TO_CN_RE.search(t_upper)
    if m:
        return m.group(2).upper(), m.group(4).upper()

    m = _PAIR_FROM_TO_EN_RE.search(t_upper)
    if m:
        return m.group(1).upper(), m.group(2).upper()

    # 2) 常见的 “PEK-SHA / PEK→SHA / PEK/SHA” 形式
    m = _PAIR_RE.search(t_upper)
    if m:
        a, b = m.group(1).upper(), m.group(2).upper()
        if a != b:
            return a, b

    # 3) 退化：抽取所有三字码，取前两个不同的
    codes = [c.upper() for c in _CODE_RE.findall(t_upper)]
    seen: List[str] = []
    for c in codes:
        if c not in seen:
            seen.append(c)
        if len(seen) >= 2:
            break
    if len(seen) >= 2:
        return seen[0], seen[1]
    return None


def detect_cabin(text: str) -> Optional[str]:
    """
    返回舱位类型：
      - 'first' | 'business' | 'economy' | 'premium_economy' | None
    """
    if not text:
        return None
    t = str(text)
    # 中文优先（票面常见）
    if "头等舱" in t or "first" in t.lower():
        return "first"
    if "商务舱" in t or "business" in t.lower():
        return "business"
    if "高端经济舱" in t or "premium" in t.lower():
        return "premium_economy"
    if "经济舱" in t or "economy" in t.lower():
        return "economy"
    return None


def looks_like_flight_ticket(text: str) -> bool:
    if not text:
        return False
    t = str(text)
    t_low = t.lower()
    # 常见关键字：机票/航班/出发/到达/登机/起飞/降落
    cn_kws = ("机票", "航班", "登机", "起飞", "到达", "出发", "航空", "飞机", "客运")
    en_kws = ("ticket", "flight", "air")
    return any(kw in t for kw in cn_kws) or any(kw in t_low for kw in en_kws)


def is_domestic_route(from_airport: AirportCoord, to_airport: AirportCoord) -> Optional[bool]:
    if from_airport.iso_country and to_airport.iso_country:
        return from_airport.iso_country == to_airport.iso_country
    return None

