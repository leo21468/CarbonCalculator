"""联网因子搜索服务：本地优先，外部候选需人工采纳后才参与核算。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable, Optional

from backend.carbon_utils import carbon_cost_cny, parse_carbon_footprint
from backend.database import (
    CustomProduct,
    ExternalFactorCandidate,
    add_product,
    find_by_name,
    get_external_factor_candidate,
    list_external_factor_candidates,
    save_external_factor_candidate,
)

_LOCAL_SIMILARITY_THRESHOLD = float(os.environ.get("FACTOR_SEARCH_MIN_LOCAL_SIMILARITY", "0.30"))
_VALID_UNITS = {"kg", "t", "吨", "千克", "kWh", "千瓦时", "件", "台", "个", "公吨", "CNY", "元"}


def external_search_enabled() -> bool:
    return (os.environ.get("ENABLE_EXTERNAL_FACTOR_SEARCH") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _timeout_seconds() -> float:
    raw = os.environ.get("EXTERNAL_SEARCH_TIMEOUT_SECONDS", "8")
    try:
        return max(1.0, min(float(raw), 30.0))
    except ValueError:
        return 8.0


def _custom_to_dict(p: CustomProduct) -> dict[str, Any]:
    cost = carbon_cost_cny(p.co2_per_unit, p.price_per_ton)
    return {
        "source": "custom",
        "id": p.id,
        "product_name": p.product_name,
        "carbon_type": p.carbon_type,
        "carbon_footprint": p.carbon_footprint,
        "co2_per_unit_kg": p.co2_per_unit,
        "unit": p.unit,
        "unit_weight_kg": p.unit_weight_kg,
        "carbon_cost_cny": round(cost, 2),
        "price_per_ton": p.price_per_ton,
    }


def _candidate_to_dict(c: ExternalFactorCandidate, cached: bool = True) -> dict[str, Any]:
    return {
        "id": c.id,
        "query_text": c.query_text,
        "product_name": c.product_name,
        "factor_value": c.factor_value,
        "unit": c.unit,
        "region": c.region,
        "year": c.year,
        "source_name": c.source_name,
        "source_url": c.source_url,
        "confidence": round(float(c.confidence or 0.0), 3),
        "cached": cached,
        "adoptable": c.id is not None and c.factor_value > 0 and bool(c.product_name and c.unit),
        "created_at": c.created_at,
        "last_checked_at": c.last_checked_at,
    }


def _dedupe_candidates(candidates: Iterable[ExternalFactorCandidate]) -> list[ExternalFactorCandidate]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[ExternalFactorCandidate] = []
    for c in candidates:
        key = (
            (c.product_name or "").strip(),
            (c.unit or "").strip(),
            (c.source_name or "").strip(),
            (c.source_url or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _valid_candidate(c: ExternalFactorCandidate) -> bool:
    if not c.product_name or not c.unit:
        return False
    if c.factor_value <= 0:
        return False
    if c.unit not in _VALID_UNITS and len(c.unit) > 16:
        return False
    return True


def _get_cpcd_matches(product_name: str, top_k: int = 3) -> list[dict[str, Any]]:
    from src.cpcd_matcher import CPCDNLPMatcher

    matcher = CPCDNLPMatcher()
    matcher.load()
    matches = matcher.match(product_name, top_k=top_k, min_similarity=0.01)
    out: list[dict[str, Any]] = []
    for m in matches:
        co2_kg, unit = parse_carbon_footprint(m.carbon_footprint)
        out.append(
            {
                "source": "cpcd",
                "product_id": m.product_id,
                "product_name": m.product_name,
                "carbon_type": m.accounting_boundary or m.data_type or "-",
                "carbon_footprint": m.carbon_footprint,
                "co2_per_unit_kg": round(co2_kg, 4) if co2_kg > 0 else None,
                "unit": unit or "-",
                "similarity": round(m.similarity, 3),
                "company_name": m.company_name,
                "year": m.data_year,
            }
        )
    return out


def _search_climatiq(query: str, region: Optional[str], year: Optional[str]) -> list[ExternalFactorCandidate]:
    api_key = (os.environ.get("CLIMATIQ_API_KEY") or "").strip()
    if not api_key:
        return []
    try:
        import requests
    except ImportError:
        return []

    params: dict[str, Any] = {"query": query}
    if region:
        params["region"] = region
    if year:
        params["year"] = year
    resp = requests.get(
        "https://api.climatiq.io/data/v1/search",
        params=params,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_timeout_seconds(),
    )
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("results") if isinstance(payload, dict) else []
    candidates: list[ExternalFactorCandidate] = []
    for item in results[:8]:
        value = item.get("factor") or item.get("co2e_factor") or item.get("factor_value")
        try:
            factor_value = float(value)
        except (TypeError, ValueError):
            continue
        unit = str(item.get("unit") or item.get("unit_type") or item.get("activity_unit") or "").strip()
        if not unit:
            continue
        candidates.append(
            ExternalFactorCandidate(
                id=None,
                query_text=query,
                product_name=str(item.get("name") or item.get("activity_id") or query).strip(),
                factor_value=factor_value,
                unit=unit,
                region=str(item.get("region") or region or "").strip(),
                year=str(item.get("year") or year or "").strip(),
                source_name=str(item.get("source") or "Climatiq").strip(),
                source_url=str(item.get("source_link") or item.get("source_url") or "https://www.climatiq.io/").strip(),
                confidence=0.72,
                raw_payload_json=json.dumps(item, ensure_ascii=False),
            )
        )
    return candidates


def _search_public_reference_pages(query: str, region: Optional[str], year: Optional[str]) -> list[ExternalFactorCandidate]:
    """
    公开网页轻量抓取。v1 只把能从页面文本明确解析出数值的内容保存为候选。
    """
    if not any(kw in query for kw in ("电", "电力", "用电", "电网", "千瓦时", "kWh")):
        return []
    try:
        import requests
    except ImportError:
        return []

    sources = [
        (
            "生态环境部电力因子公告",
            "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/t20251231_1139517.html",
        ),
        (
            "国家温室气体排放因子库",
            "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/202603/t20260301_1145117.shtml",
        ),
    ]
    candidates: list[ExternalFactorCandidate] = []
    for source_name, url in sources:
        resp = requests.get(url, timeout=_timeout_seconds())
        resp.raise_for_status()
        text = resp.text
        # 仅接受页面中出现的 kgCO2/kWh 或 kgCO2e/kWh 形式，避免凭空猜测。
        matches = re.findall(
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:kg\s*CO2e?|kgCO2e?|千克二氧化碳)\s*[/／每]\s*(kWh|千瓦时)",
            text,
            flags=re.IGNORECASE,
        )
        for value, unit in matches[:2]:
            candidates.append(
                ExternalFactorCandidate(
                    id=None,
                    query_text=query,
                    product_name="电力碳排放因子",
                    factor_value=float(value),
                    unit="kWh" if unit.lower() == "kwh" else unit,
                    region=region or "中国",
                    year=str(year or ""),
                    source_name=source_name,
                    source_url=url,
                    confidence=0.58,
                    raw_payload_json=json.dumps({"url": url, "matched_value": value, "matched_unit": unit}, ensure_ascii=False),
                )
            )
    return candidates


def _search_cpcd_ipe_pages(query: str, region: Optional[str], year: Optional[str]) -> list[ExternalFactorCandidate]:
    """
    CPCD/IPE 暂无稳定开放搜索 API。v1 保留适配器位置，避免把不可结构化网页结果写入候选。
    """
    return []


def _external_candidates(query: str, region: Optional[str], year: Optional[str]) -> tuple[list[ExternalFactorCandidate], list[str]]:
    errors: list[str] = []
    candidates: list[ExternalFactorCandidate] = []
    for name, fn in (
        ("Climatiq", _search_climatiq),
        ("生态环境部公开页面", _search_public_reference_pages),
        ("CPCD/IPE", _search_cpcd_ipe_pages),
    ):
        try:
            candidates.extend(fn(query, region, year))
        except Exception as exc:
            errors.append(f"{name} 查询失败：{exc}")
    return [c for c in _dedupe_candidates(candidates) if _valid_candidate(c)], errors


def search_factors(
    product_name: str,
    region: Optional[str] = None,
    year: Optional[str] = None,
    include_external: bool = True,
) -> dict[str, Any]:
    query = (product_name or "").strip()
    if not query:
        raise ValueError("产品名称不能为空")

    custom = find_by_name(query)
    local_matches: list[dict[str, Any]] = []
    if custom:
        local_result = _custom_to_dict(custom)
        should_search_external = False
    else:
        local_matches = _get_cpcd_matches(query)
        local_result = local_matches[0] if local_matches else {
            "source": "none",
            "product_name": query,
            "carbon_type": "-",
            "carbon_footprint": "-",
            "co2_per_unit_kg": None,
            "unit": "-",
        }
        best_similarity = float(local_result.get("similarity") or 0.0)
        should_search_external = best_similarity < _LOCAL_SIMILARITY_THRESHOLD

    cached = list_external_factor_candidates(query_text=query, region=region, year=year, limit=10)
    external_errors: list[str] = []
    external_attempted = False
    if include_external and should_search_external and external_search_enabled():
        external_attempted = True
        external, external_errors = _external_candidates(query, region, year)
        for c in external:
            c.id = save_external_factor_candidate(c)
        cached = list_external_factor_candidates(query_text=query, region=region, year=year, limit=10)

    return {
        "local_result": local_result,
        "local_matches": local_matches,
        "external_candidates": [_candidate_to_dict(c, cached=True) for c in cached],
        "external_enabled": external_search_enabled(),
        "external_attempted": external_attempted,
        "external_errors": external_errors,
    }


def adopt_candidate(
    candidate_id: int,
    carbon_type: str,
    price_per_ton: float = 100.0,
    remark: str = "",
) -> int:
    c = get_external_factor_candidate(candidate_id)
    if not c:
        raise LookupError("候选因子不存在")
    if not _valid_candidate(c):
        raise ValueError("候选因子字段不完整，无法采纳")
    ctype = (carbon_type or "").strip()
    if not ctype:
        raise ValueError("碳种类不能为空")
    try:
        price = float(price_per_ton)
    except (TypeError, ValueError):
        raise ValueError("碳价需为数字")
    if price < 0:
        raise ValueError("碳价不能为负数")

    adopted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_bits = [
        f"来源={c.source_name or '-'}",
        f"年份={c.year or '-'}",
        f"地区={c.region or '-'}",
        f"链接={c.source_url or '-'}",
        f"采纳时间={adopted_at}",
    ]
    if remark.strip():
        source_bits.append(f"备注={remark.strip()}")
    product = CustomProduct(
        id=None,
        product_name=c.product_name.strip(),
        carbon_type=ctype,
        carbon_footprint=f"{c.factor_value:g}kgCO2e/{c.unit}",
        co2_per_unit=float(c.factor_value),
        unit=c.unit.strip(),
        price_per_ton=price,
        remark="联网候选采纳；" + "；".join(source_bits),
        unit_weight_kg=None,
    )
    return add_product(product)


def candidate_payload_for_tests(c: ExternalFactorCandidate) -> dict[str, Any]:
    """测试辅助：保持候选序列化口径与 API 一致。"""
    return _candidate_to_dict(c, cached=True) | {"raw": asdict(c)}
