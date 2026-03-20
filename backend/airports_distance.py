from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from fastapi import HTTPException
from pypinyin import Style, pinyin

_ROOT = Path(__file__).resolve().parents[1]
_AIRPORT_XLSX = _ROOT / "data" / "airport.xlsx"
_AIRPORT_ZH_ALIAS_CSV = _ROOT / "data" / "airport_zh_alias.csv"

_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class AirportRecord:
    iata_code: str
    ident: str
    name: str
    latitude_deg: float
    longitude_deg: float
    municipality: str
    key: str
    muni_key: str


_lock = threading.Lock()
_loaded = False
_airports: List[AirportRecord] = []
_iata_map: Dict[str, AirportRecord] = {}
_ident_map: Dict[str, AirportRecord] = {}
_zh_alias_map: Dict[str, str] = {}


def _normalize_key(s: Optional[str]) -> str:
    s = str(s or "").strip().lower()
    # 只保留 a-z / 0-9，便于在“中文->拼音(字母)”与英文机场名之间做匹配
    return re.sub(r"[^a-z0-9]+", "", s)


def _normalize_zh_alias_key(s: Optional[str]) -> str:
    """
    中文别名 key：去空白与常见分隔符，保留中英文数字。
    （不做拼音化，避免“底特律”这类音译词失真）
    """
    t = str(s or "").strip().lower()
    t = re.sub(r"[\s·•．。()（）\-\_]+", "", t)
    return t


def _load_zh_alias_map() -> Dict[str, str]:
    """
    从 data/airport_zh_alias.csv 加载中文别名映射：
      - zh: 中文机场名（可多个写多行）
      - iata_code: IATA 三字码（优先）
      - ident: ICAO/ident（兜底）
    返回：alias_key -> code（IATA/IDENT）
    """
    if not _AIRPORT_ZH_ALIAS_CSV.exists():
        return {}
    try:
        df = pd.read_csv(_AIRPORT_ZH_ALIAS_CSV)
    except Exception:
        return {}

    out: Dict[str, str] = {}
    if "zh" not in df.columns:
        return out

    for _, r in df.iterrows():
        zh = r.get("zh", None)
        if zh is None:
            continue
        k = _normalize_zh_alias_key(zh)
        if not k:
            continue
        iata = str(r.get("iata_code", "")).strip().upper() if pd.notna(r.get("iata_code", None)) else ""
        ident = str(r.get("ident", "")).strip().upper() if pd.notna(r.get("ident", None)) else ""
        code = iata or ident
        if code:
            out[k] = code
    return out


def _load_airports_once() -> None:
    global _loaded, _airports, _iata_map, _ident_map, _zh_alias_map
    if _loaded:
        return
    with _lock:
        if _loaded:
            return

        if not _AIRPORT_XLSX.exists():
            raise HTTPException(status_code=503, detail=f"airport.xlsx 未找到：{_AIRPORT_XLSX}")

        df = pd.read_excel(_AIRPORT_XLSX)
        required = {"name", "latitude_deg", "longitude_deg", "iata_code", "ident", "municipality"}
        missing = required - set(df.columns)
        if missing:
            raise HTTPException(status_code=500, detail=f"airport.xlsx 缺少列：{sorted(missing)}")

        df = df.dropna(subset=["latitude_deg", "longitude_deg", "name"])
        # 过滤异常数据（经纬度范围）
        df = df[
            (df["latitude_deg"].astype(float) >= -90)
            & (df["latitude_deg"].astype(float) <= 90)
            & (df["longitude_deg"].astype(float) >= -180)
            & (df["longitude_deg"].astype(float) <= 180)
        ]

        airports: List[AirportRecord] = []
        iata_map: Dict[str, AirportRecord] = {}
        ident_map: Dict[str, AirportRecord] = {}

        for _, r in df.iterrows():
            name = str(r.get("name", "")).strip()
            muni = str(r.get("municipality", "")).strip()
            iata = str(r.get("iata_code", "")).strip() if pd.notna(r.get("iata_code", None)) else ""
            ident = str(r.get("ident", "")).strip() if pd.notna(r.get("ident", None)) else ""
            if not name:
                continue

            lat = float(r["latitude_deg"])
            lon = float(r["longitude_deg"])
            key = _normalize_key(name)
            muni_key = _normalize_key(muni)

            rec = AirportRecord(
                iata_code=iata.upper(),
                ident=ident.upper(),
                name=name,
                latitude_deg=lat,
                longitude_deg=lon,
                municipality=muni,
                key=key,
                muni_key=muni_key,
            )
            airports.append(rec)

            if rec.iata_code and rec.iata_code != "NAN":
                iata_map[rec.iata_code] = rec
            if rec.ident:
                ident_map[rec.ident] = rec

        _airports = airports
        _iata_map = iata_map
        _ident_map = ident_map
        _zh_alias_map = _load_zh_alias_map()
        _loaded = True


def _looks_like_iata(s: str) -> bool:
    s = s.strip()
    return bool(re.fullmatch(r"[A-Za-z]{3}", s))


def _cn_to_pinyin_key(raw: str) -> str:
    """
    将中文机场输入转为可与英文机场名做匹配的“拼音字母key”。
    重点做了常见中文后缀/词汇到英文含义的替换：
      - 首都(shoudu) -> capital
      - 国际(guoji) -> international
      - 机场(jichang) -> airport
    """

    # pypinyin 对纯字母/数字也会返回自身；我们后续用 normalize_key 做统一
    tokens = pinyin(raw, style=Style.NORMAL, heteronym=False, errors="ignore")
    syllables = [t[0] for t in tokens if t and t[0]]

    joined = "".join(syllables).lower()
    # 词汇替换：让“首都机场”能更好地匹配 “Capital ... Airport”
    joined = joined.replace("shoudu", "capital")
    joined = joined.replace("guoji", "international")
    joined = joined.replace("jichang", "airport")
    return _normalize_key(joined)


def _resolve_by_similarity(input_key: str, candidates: List[AirportRecord]) -> Tuple[AirportRecord, float]:
    best: Optional[Tuple[AirportRecord, float]] = None
    for a in candidates:
        if not a.key:
            continue
        score = SequenceMatcher(None, input_key, a.key).ratio()
        if best is None or score > best[1]:
            best = (a, score)
    if best is None:
        raise HTTPException(status_code=400, detail="无法解析机场：候选集合为空")
    return best


def resolve_airport(raw_input: str) -> Tuple[AirportRecord, float, List[dict]]:
    """
    解析用户输入为某个 airport.xlsx 里的机场记录。
    返回：
      - record
      - score
      - top_candidates（用于错误提示/调试）
    """
    _load_airports_once()

    raw = (raw_input or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="机场输入不能为空")

    # 1) IATA/Ident 直接匹配
    raw_upper = raw.upper()
    if _looks_like_iata(raw_upper) and raw_upper in _iata_map:
        return _iata_map[raw_upper], 1.0, []
    if raw_upper in _ident_map:
        return _ident_map[raw_upper], 1.0, []

    # 1.5) 中文别名表（优先级高于拼音相似度）
    alias_key = _normalize_zh_alias_key(raw)
    code = _zh_alias_map.get(alias_key)
    if code:
        if _looks_like_iata(code) and code in _iata_map:
            return _iata_map[code], 1.0, []
        if code in _ident_map:
            return _ident_map[code], 1.0, []

    # 2) 普通英文匹配（用户可能直接输入英文机场名的一部分）
    direct_key = _normalize_key(raw)
    if direct_key:
        # 简单先做 muni 过滤，减少相似度计算量
        muni_guess = direct_key[:6]
        candidates = (
            [a for a in _airports if a.muni_key and muni_guess and muni_guess in a.muni_key]
            if muni_guess
            else _airports
        )
        record, score = _resolve_by_similarity(direct_key, candidates)
        if score >= 0.55:
            return record, score, []

    # 3) 中文 -> 拼音key 后做相似度匹配
    input_key = _cn_to_pinyin_key(raw)
    if not input_key:
        raise HTTPException(status_code=400, detail="无法解析机场输入（可能输入内容过短或不支持）")

    # muni guess：取拼音key 的前若干字符，粗略用于过滤
    muni_guess1 = input_key[:6]
    muni_guess2 = input_key[:4]
    candidates2 = [
        a for a in _airports if (a.muni_key and (muni_guess1 in a.muni_key or muni_guess2 in a.muni_key))
    ]
    candidates = candidates2 if candidates2 else _airports

    # 计算相似度并保留 topN 供提示
    scored: List[Tuple[AirportRecord, float]] = []
    for a in candidates:
        if not a.key:
            continue
        score = SequenceMatcher(None, input_key, a.key).ratio()
        scored.append((a, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:5]

    best_rec, best_score = top[0]
    if best_score < 0.42:
        top_suggestions = [
            {"name": x.name, "iata_code": x.iata_code, "score": round(s, 3)}
            for x, s in top[:3]
        ]
        raise HTTPException(
            status_code=404,
            detail={
                "message": "未在机场库中找到匹配的机场，请检查输入（也可使用 IATA 三字码，如 PEK/PVG）",
                "input": raw_input,
                "suggestions": top_suggestions,
            },
        )

    top_candidates = [
        {"name": x.name, "iata_code": x.iata_code, "score": round(s, 3)}
        for x, s in top[:3]
    ]
    return best_rec, best_score, top_candidates


def great_circle_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    使用大圆距离（Haversine）计算两点球面距离（单位：km）。
    """
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return _EARTH_RADIUS_KM * c

