"""机票图片独立核算：图片抽取、航段校验、飞行排放与碳价换算。"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import tempfile
from datetime import date as _date
from pathlib import Path
from typing import Any, Optional

from backend.airports_distance import AirportRecord, great_circle_distance_km, resolve_airport
from backend.carbon_utils import carbon_cost_cny
from src.emission_factors import EmissionFactorStore
from src.flight_utils import get_airport_by_iata
from src.invoice_parser import parse_amount_cny


VISION_PROMPT = """# 任务
请分析用户提供的图片。
# 提取字段与标准化规则
请从图片中寻找以下字段，并应用标准化规则。如果某个字段在图片上完全找不到，请用 null 作为其值。
1. passenger_name: 提取乘机人姓名。如果有多个名字，只取第一个。
2. segments: 列表。一张机票可能有多个航段。每个航段包含 departure、arrival、flight_number、date、class。
   departure/arrival 标准化为 IATA 三字码；date 标准化为 YYYY-MM-DD；class 映射为 经济舱/商务舱/头等舱。
3. total_amount: 提取机票总价（含税），只保留数字。
4. is_domestic: 判断是否为国内航班，输出 true 或 false。
只返回 JSON，不要解释。"""

DOMESTIC_PASSENGER_FACTOR_KG_PER_KM = 0.0829
INTERNATIONAL_PASSENGER_FACTOR_KG_PER_KM = 0.18362
FLIGHT_FACTOR_SOURCE = "本地航空客运因子：国内 0.0829、国际 0.18362 kgCO2e/人·千米"
DEFAULT_CARBON_PRICE = float(os.environ.get("FLIGHT_TICKET_DEFAULT_CARBON_PRICE_PER_TON", "100"))

_ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_REFUND_KEYWORDS = ("退票", "退款", "退改", "改签", "退票费", "改签费", "保险", "服务费")
_IATA_RE = re.compile(r"\b([A-Z]{3})\b")
_FLIGHT_NO_RE = re.compile(r"\b([A-Z]{2}\d{3,5})\b")
_DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
_AMOUNT_RE = re.compile(r"(?:￥|¥|CNY|RMB)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*(?:元)?", re.IGNORECASE)
_COMMON_AIRPORT_ALIASES = {
    "北京首都": "PEK",
    "首都机场": "PEK",
    "北京大兴": "PKX",
    "大兴机场": "PKX",
    "上海虹桥": "SHA",
    "虹桥机场": "SHA",
    "上海浦东": "PVG",
    "浦东机场": "PVG",
    "广州白云": "CAN",
    "白云机场": "CAN",
    "深圳宝安": "SZX",
    "宝安机场": "SZX",
    "成都天府": "TFU",
    "成都双流": "CTU",
}


class FlightTicketError(ValueError):
    """机票接口可展示给用户的业务错误。"""


def is_supported_image(filename: str, content_type: Optional[str] = None) -> bool:
    ext = Path(filename or "").suffix.lower()
    if ext in _ALLOWED_IMAGE_EXT:
        return True
    return bool(content_type and content_type.lower().startswith("image/"))


def analyze_flight_ticket_image(
    content: bytes,
    filename: str = "ticket.png",
    content_type: Optional[str] = None,
    carbon_price_per_ton: Optional[float] = None,
    carbon_price_date: Optional[str] = None,
) -> dict[str, Any]:
    if not content:
        raise FlightTicketError("文件内容为空")
    if not is_supported_image(filename, content_type):
        raise FlightTicketError("仅支持图片格式：JPG、PNG、WEBP、BMP")

    extraction = extract_ticket_fields(content, filename=filename, content_type=content_type)
    extracted = extraction["fields"]
    extraction_warnings = extraction["warnings"]
    raw_text = extraction.get("raw_text") or ""

    return build_flight_ticket_result(
        extracted,
        raw_text=raw_text,
        extraction_warnings=extraction_warnings,
        carbon_price_per_ton=carbon_price_per_ton,
        carbon_price_date=carbon_price_date,
    )


def extract_ticket_fields(content: bytes, filename: str, content_type: Optional[str]) -> dict[str, Any]:
    warnings: list[str] = []
    fields = _extract_with_vision_model(content, filename, content_type, warnings)
    raw_text = ""
    if fields is None:
        raw_text = _ocr_image_to_text(content, filename, warnings)
        fields = _extract_with_rules(raw_text)
    fields = normalize_extracted_fields(fields or {})
    return {"fields": fields, "warnings": warnings, "raw_text": raw_text}


def _extract_with_vision_model(
    content: bytes,
    filename: str,
    content_type: Optional[str],
    warnings: list[str],
) -> Optional[dict[str, Any]]:
    provider = (os.environ.get("VISION_MODEL_PROVIDER") or "sjtu").strip().lower()
    api_key = (
        os.environ.get("VISION_MODEL_API_KEY")
        or os.environ.get("SJTU_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    if not api_key:
        warnings.append("视觉模型未配置，已尝试本地 OCR/规则兜底")
        return None

    mime = content_type or mimetypes.guess_type(filename)[0] or "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
    model = (os.environ.get("VISION_MODEL_NAME") or ("qwen" if provider == "sjtu" else "gpt-4o-mini")).strip()
    if provider in {"sjtu", "qwen", "openai_compatible", "openai-compatible"}:
        return _extract_with_openai_compatible_http(
            api_key=api_key,
            model=model,
            data_url=data_url,
            warnings=warnings,
        )

    try:
        from openai import OpenAI
    except ImportError:
        warnings.append("openai SDK 未安装，已尝试本地 OCR/规则兜底")
        return None

    try:
        base_url = (os.environ.get("VISION_MODEL_BASE_URL") or "").strip() or None
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        text = resp.choices[0].message.content or "{}"
        return json.loads(text)
    except Exception as exc:
        warnings.append(f"视觉模型抽取失败，已尝试本地 OCR/规则兜底：{exc}")
        return None


def _extract_with_openai_compatible_http(
    api_key: str,
    model: str,
    data_url: str,
    warnings: list[str],
) -> Optional[dict[str, Any]]:
    try:
        import requests
    except ImportError:
        warnings.append("requests 未安装，交大 Qwen 视觉模型不可用，已尝试本地 OCR/规则兜底")
        return None

    base_url = (os.environ.get("VISION_MODEL_BASE_URL") or "https://models.sjtu.edu.cn/api/v1").strip().rstrip("/")
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": VISION_PROMPT},
                        ],
                    }
                ],
                "stream": False,
                "max_tokens": 1024,
                "temperature": 0,
            },
            timeout=float(os.environ.get("VISION_MODEL_TIMEOUT_SECONDS", "60")),
        )
        resp.raise_for_status()
        payload = resp.json()
        text = payload["choices"][0]["message"]["content"] or "{}"
        return _parse_json_object(text)
    except Exception as exc:
        warnings.append(f"交大 Qwen 视觉模型抽取失败，已尝试本地 OCR/规则兜底：{exc}")
        return None


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def _ocr_image_to_text(content: bytes, filename: str, warnings: list[str]) -> str:
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        warnings.append("PaddleOCR 未安装，本地 OCR 兜底不可用")
        return ""
    suffix = Path(filename or "ticket.png").suffix or ".png"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        ocr = PaddleOCR(use_textline_orientation=True, lang="ch")
        result = ocr.predict(tmp_path) if hasattr(ocr, "predict") else ocr.ocr(tmp_path)
        texts = _flatten_ocr_text(result)
        return "\n".join(t for t in texts if t)
    except Exception as exc:
        warnings.append(f"本地 OCR 失败：{exc}")
        return ""
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _flatten_ocr_text(result: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(result, list):
        for item in result:
            texts.extend(_flatten_ocr_text(item))
    elif isinstance(result, dict):
        if "rec_texts" in result and isinstance(result["rec_texts"], list):
            texts.extend(str(x) for x in result["rec_texts"])
        else:
            for v in result.values():
                texts.extend(_flatten_ocr_text(v))
    elif isinstance(result, tuple) and len(result) >= 2:
        val = result[1]
        if isinstance(val, (tuple, list)) and val:
            texts.append(str(val[0]))
    return texts


def _extract_with_rules(text: str) -> dict[str, Any]:
    if not text:
        return {"passenger_name": None, "segments": [], "total_amount": None, "is_domestic": None}
    t = text.upper()
    codes = [c for c in _IATA_RE.findall(t) if c not in {"CNY", "RMB"}]
    segments = []
    if len(codes) >= 2:
        flight_numbers = _FLIGHT_NO_RE.findall(t)
        dates = _DATE_RE.findall(text)
        date_val = _format_date_tuple(dates[0]) if dates else None
        cabin = _detect_cabin(text)
        for i in range(0, len(codes) - 1, 2):
            segments.append(
                {
                    "departure": codes[i],
                    "arrival": codes[i + 1],
                    "flight_number": flight_numbers[0] if flight_numbers else None,
                    "date": date_val,
                    "class": cabin,
                }
            )
            break
    return {
        "passenger_name": _extract_passenger_name(text),
        "segments": segments,
        "total_amount": _extract_amount(text),
        "is_domestic": None,
    }


def _format_date_tuple(parts: tuple[str, str, str]) -> str:
    return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def _detect_cabin(text: str) -> Optional[str]:
    low = text.lower()
    if "头等" in text or "first" in low:
        return "头等舱"
    if "商务" in text or "business" in low:
        return "商务舱"
    if "经济" in text or "economy" in low or "eco" in low:
        return "经济舱"
    return None


def _extract_passenger_name(text: str) -> Optional[str]:
    m = re.search(r"(?:乘机人|旅客|姓名|PASSENGER)\s*[:：]?\s*([A-Za-z\u4e00-\u9fff·\s]{2,30})", text, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().split()[0]


def _extract_amount(text: str) -> Optional[float]:
    matches = _AMOUNT_RE.findall(text)
    vals = []
    for raw in matches:
        val = parse_amount_cny(raw)
        if val is not None and val > 0:
            vals.append(val)
    return max(vals) if vals else None


def normalize_extracted_fields(fields: dict[str, Any]) -> dict[str, Any]:
    segments = fields.get("segments") or []
    if not isinstance(segments, list):
        segments = []
    norm_segments: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        norm_segments.append(
            {
                "departure": _none_or_str(seg.get("departure")),
                "arrival": _none_or_str(seg.get("arrival")),
                "flight_number": _none_or_str(seg.get("flight_number")),
                "date": _normalize_date(seg.get("date")),
                "class": _normalize_cabin(seg.get("class")),
            }
        )
    amount = fields.get("total_amount")
    if amount is not None:
        amount = parse_amount_cny(str(amount))
    return {
        "passenger_name": _none_or_str(fields.get("passenger_name")),
        "segments": norm_segments,
        "total_amount": amount,
        "is_domestic": fields.get("is_domestic") if isinstance(fields.get("is_domestic"), bool) else None,
    }


def _none_or_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _normalize_date(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    m = _DATE_RE.search(s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    return s or None


def _normalize_cabin(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    low = s.lower()
    if "头等" in s or "first" in low:
        return "头等舱"
    if "商务" in s or "business" in low:
        return "商务舱"
    if "经济" in s or "economy" in low or "eco" in low:
        return "经济舱"
    return s


def build_flight_ticket_result(
    extracted: dict[str, Any],
    raw_text: str = "",
    extraction_warnings: Optional[list[str]] = None,
    carbon_price_per_ton: Optional[float] = None,
    carbon_price_date: Optional[str] = None,
) -> dict[str, Any]:
    warnings = list(extraction_warnings or [])
    assumptions: list[str] = []
    raw_for_quality = json.dumps(extracted, ensure_ascii=False) + "\n" + (raw_text or "")

    if any(kw in raw_for_quality for kw in _REFUND_KEYWORDS):
        warnings.append("票面疑似退票/改签/保险/服务费，不按飞行排放计算")
        price = resolve_carbon_price(carbon_price_per_ton, carbon_price_date)
        return _build_no_emission_result(extracted, price, warnings, assumptions, "manual_review")

    calculated_segments, segment_warnings, segment_assumptions = calculate_segments(extracted.get("segments") or [])
    warnings.extend(segment_warnings)
    assumptions.extend(segment_assumptions)

    amount = extracted.get("total_amount")
    if calculated_segments:
        method = "activity_distance" if not segment_assumptions else "estimated_activity_distance"
        total_kg = round(sum(float(s["emission_kg"]) for s in calculated_segments), 4)
        factor_source = FLIGHT_FACTOR_SOURCE
    elif amount and amount > 0:
        method = "eeio_amount"
        eeio_factor = _air_eeio_factor()
        total_kg = round(float(amount) * eeio_factor, 4)
        factor_source = f"本地 EEIO 航空差旅因子：{eeio_factor} kgCO2e/元"
        assumptions.append("未能可靠解析航段，按机票金额使用航空差旅 EEIO 因子估算")
    else:
        price = resolve_carbon_price(carbon_price_per_ton, carbon_price_date)
        warnings.append("未能解析有效航段且缺少金额，无法计算排放")
        return _build_no_emission_result(extracted, price, warnings, assumptions, "manual_review")

    quality = assess_quality(extracted, calculated_segments, method, warnings)
    ticket_date = _first_segment_date(extracted) or carbon_price_date
    price = resolve_carbon_price(carbon_price_per_ton, ticket_date)
    carbon_cost = carbon_cost_cny(total_kg, price["price_per_ton"])
    fields_summary = _fields_summary(extracted, calculated_segments)
    explanation = _format_explanation(
        fields_summary=fields_summary,
        method=method,
        total_kg=total_kg,
        assumptions=assumptions,
        confidence=quality,
        factor_source=factor_source,
        price=price,
        segments=calculated_segments,
    )
    return {
        "ticket_type": "机票",
        "extracted_fields": extracted,
        "segments": calculated_segments,
        "calculation_method": method,
        "total_emissions_kg": total_kg,
        "carbon_price_per_ton": round(price["price_per_ton"], 4),
        "carbon_price_date": price.get("date"),
        "carbon_price_source": price.get("source"),
        "carbon_cost_cny": round(carbon_cost, 4),
        "confidence": quality,
        "assumptions": assumptions,
        "warnings": warnings,
        "explanation": explanation,
    }


def calculate_segments(segments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    assumptions: list[str] = []
    seen: set[tuple[str, str, Optional[str], Optional[str]]] = set()
    for idx, seg in enumerate(segments):
        dep_raw = seg.get("departure")
        arr_raw = seg.get("arrival")
        if not dep_raw or not arr_raw:
            warnings.append(f"第 {idx + 1} 段缺少起点或终点")
            continue
        try:
            dep_rec, dep_score, _ = _resolve_ticket_airport(dep_raw)
            arr_rec, arr_score, _ = _resolve_ticket_airport(arr_raw)
        except Exception as exc:
            warnings.append(f"第 {idx + 1} 段机场解析失败：{exc}")
            continue
        if dep_rec.iata_code == arr_rec.iata_code:
            warnings.append(f"第 {idx + 1} 段起终点相同，已跳过")
            continue
        key = (dep_rec.iata_code, arr_rec.iata_code, seg.get("date"), seg.get("flight_number"))
        if key in seen:
            warnings.append(f"第 {idx + 1} 段疑似重复航段，已跳过")
            continue
        seen.add(key)
        distance_km = great_circle_distance_km(
            dep_rec.latitude_deg,
            dep_rec.longitude_deg,
            arr_rec.latitude_deg,
            arr_rec.longitude_deg,
        )
        is_domestic = _is_domestic(dep_rec.iata_code, arr_rec.iata_code)
        factor = DOMESTIC_PASSENGER_FACTOR_KG_PER_KM if is_domestic else INTERNATIONAL_PASSENGER_FACTOR_KG_PER_KM
        if not _looks_like_iata(dep_raw) or not _looks_like_iata(arr_raw) or dep_score < 1.0 or arr_score < 1.0:
            assumptions.append(f"第 {idx + 1} 段使用机场库默认匹配：{dep_raw}->{dep_rec.iata_code}, {arr_raw}->{arr_rec.iata_code}")
        out.append(
            {
                "departure": dep_rec.iata_code,
                "arrival": arr_rec.iata_code,
                "departure_name": dep_rec.name,
                "arrival_name": arr_rec.name,
                "flight_number": seg.get("flight_number"),
                "date": seg.get("date"),
                "class": seg.get("class"),
                "is_domestic": bool(is_domestic),
                "distance_km": round(distance_km, 4),
                "factor_kg_per_passenger_km": factor,
                "emission_kg": round(distance_km * factor, 4),
            }
        )
    return out, warnings, assumptions


def _resolve_ticket_airport(raw: Any) -> tuple[AirportRecord, float, list[dict]]:
    s = str(raw or "").strip()
    alias = _COMMON_AIRPORT_ALIASES.get(s)
    if not alias:
        compact = re.sub(r"[\s·•．。()（）\-_]+", "", s)
        alias = _COMMON_AIRPORT_ALIASES.get(compact)
    return resolve_airport(alias or s)


def _looks_like_iata(v: Any) -> bool:
    return bool(v and re.fullmatch(r"[A-Za-z]{3}", str(v).strip()))


def _is_domestic(dep_iata: str, arr_iata: str) -> bool:
    dep = get_airport_by_iata(dep_iata)
    arr = get_airport_by_iata(arr_iata)
    if dep and arr and dep.iso_country and arr.iso_country:
        return dep.iso_country == arr.iso_country
    return False


def _air_eeio_factor() -> float:
    factor = EmissionFactorStore().get("scope3_transport_air")
    return float((factor or {}).get("kg_co2e_per_unit") or 0.1497)


def assess_quality(
    extracted: dict[str, Any],
    calculated_segments: list[dict[str, Any]],
    method: str,
    warnings: list[str],
) -> str:
    if method == "manual_review" or any("退票" in w or "改签" in w or "无法计算" in w for w in warnings):
        return "需人工复核"
    if any(s["distance_km"] < 50 or s["distance_km"] > 20000 for s in calculated_segments):
        warnings.append("存在异常航段距离")
        return "需人工复核"
    extracted_domestic = extracted.get("is_domestic")
    if calculated_segments and isinstance(extracted_domestic, bool):
        actual_domestic = all(bool(s["is_domestic"]) for s in calculated_segments)
        if actual_domestic != extracted_domestic:
            warnings.append("票面国内/国际判断与机场库结果不一致")
            return "中置信"
    if method == "activity_distance" and not warnings:
        return "高置信"
    if method in {"activity_distance", "estimated_activity_distance", "eeio_amount"}:
        return "中置信"
    return "需人工复核"


def resolve_carbon_price(manual_price: Optional[float], price_date: Optional[str]) -> dict[str, Any]:
    if os.environ.get("FLIGHT_TICKET_ENABLE_MARKET_PRICE", "true").strip().lower() in {"1", "true", "yes", "on"}:
        market = _fetch_market_price(price_date)
        if market:
            return market
    if manual_price is not None:
        return {
            "price_per_ton": float(manual_price),
            "date": price_date,
            "source": "manual_fallback",
        }
    return {
        "price_per_ton": DEFAULT_CARBON_PRICE,
        "date": price_date,
        "source": "internal_default",
    }


def _fetch_market_price(price_date: Optional[str]) -> Optional[dict[str, Any]]:
    try:
        import requests
    except ImportError:
        return None
    urls = [
        "https://www.cneeex.com/cneeex/index/index.html",
        "https://www.cneeex.com/",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
        except Exception:
            continue
        text = resp.text
        price = _parse_market_price_from_text(text)
        if price:
            return {
                "price_per_ton": price,
                "date": price_date or _date.today().isoformat(),
                "source": f"market:{url}",
            }
    return None


def _parse_market_price_from_text(text: str) -> Optional[float]:
    patterns = [
        r"(?:综合价格|收盘价|成交均价|CEA)[^0-9]{0,30}([0-9]{1,4}(?:\.[0-9]{1,2})?)\s*元",
        r"([0-9]{1,4}(?:\.[0-9]{1,2})?)\s*元\s*/?\s*吨",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            val = float(m.group(1))
            if 1 <= val <= 500:
                return val
    return None


def _first_segment_date(extracted: dict[str, Any]) -> Optional[str]:
    for seg in extracted.get("segments") or []:
        if seg.get("date"):
            return seg["date"]
    return None


def _fields_summary(extracted: dict[str, Any], segments: list[dict[str, Any]]) -> str:
    if segments:
        return "；".join(f"{s['departure']} → {s['arrival']}" for s in segments)
    raw_segments = extracted.get("segments") or []
    if raw_segments:
        return "；".join(f"{s.get('departure') or '?'} → {s.get('arrival') or '?'}" for s in raw_segments)
    return "未识别到有效航段"


def _format_explanation(
    fields_summary: str,
    method: str,
    total_kg: Optional[float],
    assumptions: list[str],
    confidence: str,
    factor_source: str,
    price: dict[str, Any],
    segments: list[dict[str, Any]],
) -> str:
    method_label = {
        "activity_distance": "活动数据法",
        "estimated_activity_distance": "估算版活动数据法",
        "eeio_amount": "EEIO 金额估算法",
        "manual_review": "人工复核",
    }.get(method, method)
    assumptions_text = "；".join(assumptions) if assumptions else "默认每个航段 1 名乘客；舱位不额外加权"
    detail = "；".join(
        f"{s['departure']}→{s['arrival']} {s['distance_km']:.2f} km × {s['factor_kg_per_passenger_km']} kgCO2e/人·千米 = {s['emission_kg']:.4f} kgCO2e"
        for s in segments
    )
    if not detail:
        detail = factor_source
    result_text = f"{total_kg} kgCO2e" if total_kg is not None else "无法计算"
    return (
        f"识别结果：机票\n"
        f"抽取字段：{fields_summary}\n"
        f"计算路径：{method_label}\n"
        f"结果：{result_text}\n"
        f"假设：{assumptions_text}\n"
        f"置信度：{confidence}\n"
        f"进一步的计算过程与解释：{detail}。碳价采用 {price.get('source')}，"
        f"{price.get('price_per_ton')} 元/吨CO2e。"
    )


def _build_no_emission_result(
    extracted: dict[str, Any],
    price: dict[str, Any],
    warnings: list[str],
    assumptions: list[str],
    method: str,
) -> dict[str, Any]:
    explanation = _format_explanation(
        fields_summary=_fields_summary(extracted, []),
        method=method,
        total_kg=None,
        assumptions=assumptions,
        confidence="需人工复核",
        factor_source="未执行排放计算",
        price=price,
        segments=[],
    )
    return {
        "ticket_type": "机票",
        "extracted_fields": extracted,
        "segments": [],
        "calculation_method": method,
        "total_emissions_kg": None,
        "carbon_price_per_ton": round(price["price_per_ton"], 4),
        "carbon_price_date": price.get("date"),
        "carbon_price_source": price.get("source"),
        "carbon_cost_cny": None,
        "confidence": "需人工复核",
        "assumptions": assumptions,
        "warnings": warnings,
        "explanation": explanation,
    }
