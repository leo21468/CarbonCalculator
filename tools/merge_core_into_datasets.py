#!/usr/bin/env python3
"""
将 data/core.csv（CPCD 核心数据库）合并进项目数据集：

1. 重写 data/grid_carbon_factors.json（全国/区域/省/参考项/发电类型/输配电等，优先 core 中最新对口年份）
2. 重写 data/transport_factors.json（公吨·公里类，core 优先；缺项可再由 data/transport.xlsx 补足）
3. 生成 data/cpcd_catalog.csv = core 去重 + data/Emission factors.csv 中「产品ID」不在 core 的补录行

常用命令：
  python tools/merge_core_into_datasets.py              # 全量：电网/货运 JSON + cpcd_catalog
  python tools/merge_core_into_datasets.py --catalog-only  # 仅重算 cpcd_catalog（不覆盖 grid/transport）

若项目约定不再更新 core.csv，日常只改 Emission factors.csv 时用 --catalog-only 即可。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "data" / "core.csv"
GRID_OUT = ROOT / "data" / "grid_carbon_factors.json"
TRANSPORT_OUT = ROOT / "data" / "transport_factors.json"
EMISSION_EXT = ROOT / "data" / "Emission factors.csv"
CATALOG_OUT = ROOT / "data" / "cpcd_catalog.csv"
TRANSPORT_XLSX = ROOT / "data" / "transport.xlsx"

REGIONS_7 = frozenset({"华北", "华东", "华中", "西北", "南方", "西南", "东北"})

_RE_KWH = re.compile(
    r"([\d.eE+-]+)\s*(t|kg|g)CO2e?\s*[/／]\s*千瓦时",
    re.IGNORECASE,
)
_RE_TONNEKM = re.compile(
    r"([\d.eE+-]+)\s*(t|kg|g)\s*CO2e?\s*[/／]\s*公吨[·.]?公里",
    re.IGNORECASE,
)


def _to_kg_per_kwh(val: float, mass: str | None) -> float:
    m = (mass or "kg").lower()
    if m == "t":
        return val * 1000.0
    if m == "g":
        return val / 1000.0
    return val


def parse_kwh(s: str) -> float | None:
    if not s or not isinstance(s, str):
        return None
    m = _RE_KWH.search(s.replace("兆瓦时", "MWh"))
    if not m:
        if "兆瓦时" in s or "MWh" in s:
            m2 = re.search(
                r"([\d.eE+-]+)\s*(t|kg|g)?\s*CO2e?\s*[/／]\s*兆瓦时",
                s,
                re.I,
            )
            if m2:
                v = float(m2.group(1))
                mu = (m2.group(2) or "t").lower()
                per_kwh = _to_kg_per_kwh(v, mu) / 1000.0
                return per_kwh
        return None
    v = float(m.group(1))
    mu = m.group(2)
    return _to_kg_per_kwh(v, mu)


def parse_tonne_km_kg(s: str) -> float | None:
    if not s:
        return None
    m = _RE_TONNEKM.search(str(s).replace("\xa0", " "))
    if not m:
        return None
    v = float(m.group(1))
    mu = m.group(2).lower()
    if mu == "t":
        return v * 1000.0
    if mu == "g":
        return v / 1000.0
    return v


def dedupe_core(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    ycol = "数据年份" if "数据年份" in df.columns else "year"
    df["_y"] = pd.to_numeric(df[ycol], errors="coerce").fillna(0)
    pid = "产品ID" if "产品ID" in df.columns else "product_id"
    return df.sort_values("_y").drop_duplicates(subset=[pid], keep="last")


def build_grid(df: pd.DataFrame) -> dict:
    name_col = "产品名称"
    fp_col = "碳足迹"
    yr_col = "数据年份"
    pid_col = "产品ID"

    national_avg = None
    national_ref_2023 = None
    national_excl = None
    national_fossil = None
    regional: dict[str, float] = {}
    provinces: dict[str, float] = {}
    generation: dict[str, float] = {}
    transmission: dict[str, float] = {}
    transmission_2023: dict[str, float] = {}

    for _, row in df.iterrows():
        name = str(row.get(name_col) or "").strip()
        fp = str(row.get(fp_col) or "")
        year = row.get(yr_col)
        try:
            y = int(float(year)) if year is not None and not pd.isna(year) else 0
        except (TypeError, ValueError):
            y = 0
        kwh = parse_kwh(fp)
        if kwh is None:
            continue

        if "2024年全国电力平均碳足迹因子" in name:
            national_avg = {
                "year": 2024,
                "kg_co2e_per_kwh": kwh,
                "source": "data/core.csv (CPCD 核心数据库)",
                "source_pdf": "data/core.csv",
                "source_table": "CPCD 核心数据库",
                "source_product_id": str(row.get(pid_col) or ""),
            }
            continue

        if "2023年全国电力平均二氧化碳排放因子" in name and "不包括" not in name:
            national_ref_2023 = {
                "kg_co2e_per_kwh": kwh,
                "note": "2023 年全国表1口径（二氧化碳排放因子），与 2024 碳足迹全国平均不同",
                "source": "data/core.csv",
                "source_product_id": str(row.get(pid_col) or ""),
            }
            continue

        if "不包括市场化交易的非化石能源电量" in name and y == 2023:
            national_excl = {
                "kg_co2e_per_kwh": kwh,
                "source": "data/core.csv",
                "source_product_id": str(row.get(pid_col) or ""),
            }
            continue

        if "全国化石能源电力二氧化碳排放因子" in name and y == 2023:
            national_fossil = {
                "kg_co2e_per_kwh": kwh,
                "source": "data/core.csv",
                "source_product_id": str(row.get(pid_col) or ""),
            }
            continue

        mreg = re.search(
            r"2023年区域电力平均二氧化碳排放因子[-－](.+?)$",
            name,
        )
        if mreg and y == 2023:
            key = mreg.group(1).strip()
            if key in REGIONS_7:
                regional[key] = kwh
            else:
                provinces[key] = kwh
            continue

        if "2024年主要发电类型电力碳足迹因子-" in name:
            sub = name.split("因子-")[-1].strip()
            generation[sub] = kwh
            continue

        if "2024年输配电碳足迹因子-" in name:
            sub = name.replace("2024年输配电碳足迹因子-", "").strip()
            transmission[sub] = kwh
            continue

        if "2023年输配电碳足迹因子" in name:
            sub = re.sub(r"^2023年输配电碳足迹因子[-－]", "", name).strip()
            if "不含" in sub or "线损" in sub:
                transmission_2023[sub] = kwh

    out: dict = {
        "_comment": "由 tools/merge_core_into_datasets.py 自 data/core.csv 生成；与 2023/2024 PDF 口径对齐项以核心库为准，并保留 PDF 可追溯字段于 supplemental_pdf。",
        "national_average": national_avg
        or {
            "year": 2024,
            "kg_co2e_per_kwh": 0.5777,
            "source": "fallback",
        },
        "regional_grids": {
            "_year": 2023,
            "_source": "data/core.csv (区域电网)",
            "_source_pdf": "data/core.csv",
            "_source_table": "2023 区域电力平均二氧化碳排放因子",
            **regional,
        },
        "provinces": {
            "_year": 2023,
            "_source": "data/core.csv（库中字段名为区域因子，对应各省 2023 电力二氧化碳排放因子）",
            "_source_pdf": "data/core.csv",
            "_source_table": "2023 区域电力平均二氧化碳排放因子-分省",
            **provinces,
        },
    }

    if national_excl:
        out["national_excluding_market_renewables_2023"] = national_excl
    if national_fossil:
        out["national_fossil_only_2023"] = national_fossil
    if national_ref_2023:
        out["national_reference_2023"] = national_ref_2023

    if generation:
        out["generation_types_2024"] = {
            "_source": "data/core.csv",
            **generation,
        }

    if transmission:
        out["transmission_2024"] = {
            "_source": "data/core.csv",
            **transmission,
        }

    if transmission_2023:
        out["transmission_2023"] = {
            "_source": "data/core.csv",
            **transmission_2023,
        }

    out["supplemental_pdf"] = {
        "note": "原始 PDF 路径 data/2023.pdf、data/2024.pdf 仍可作为审计对照；当以 core.csv 为主数据源时数值应与核心库一致。",
        "pdfs": ["data/2023.pdf", "data/2024.pdf"],
    }

    return out


def _pick_road_default(modes: list[dict]) -> dict | None:
    """默认公路因子：优先重型化石燃料「不区分」，避免误选纯电动不区分。"""
    prefer_ids = ("65119X0442024C", "65119X0272024C")  # 天然气/柴油 不区分
    for pid in prefer_ids:
        for row in modes:
            if str(row.get("product_id") or "") == pid:
                return row
    for row in modes:
        n = row.get("mode_cn") or ""
        if "天然气" in n and "不区分" in n:
            return row
        if n.strip() == "柴油货车运输-不区分质量区间":
            return row
    for row in modes:
        if (row.get("mode_cn") or "").strip() == "中型柴油货车运输":
            return row
    return modes[0] if modes else None


def build_transport_from_core(df: pd.DataFrame) -> dict:
    modes: list[dict] = []
    rail = None
    air = None
    name_col = "产品名称"
    fp_col = "碳足迹"
    yr_col = "数据年份"
    pid_col = "产品ID"
    bcol = "核算边界"

    for _, row in df.iterrows():
        fp = str(row.get(fp_col) or "")
        kg = parse_tonne_km_kg(fp)
        if kg is None:
            continue
        name = str(row.get(name_col) or "").strip()
        pid = str(row.get(pid_col) or "").strip()
        try:
            y = int(float(row.get(yr_col))) if row.get(yr_col) not in (None, "") else 2024
        except (TypeError, ValueError):
            y = 2024
        boundary = str(row.get(bcol) or "").strip()
        entry = {
            "product_id": pid,
            "mode_cn": name,
            "boundary": boundary,
            "g_co2e_per_tonne_km": kg * 1000.0,
            "kg_co2e_per_tonne_km": kg,
            "year": y,
            "source": "data/core.csv",
        }
        if name == "铁路运输" and pid.startswith("65129"):
            rail = entry
            continue
        if name == "航空运输" and "65319" in pid:
            air = entry
            continue
        modes.append(entry)

    if rail is None:
        rail = {
            "product_id": "",
            "mode_cn": "铁路运输",
            "boundary": "大门到坟墓",
            "g_co2e_per_tonne_km": 6.502,
            "kg_co2e_per_tonne_km": 0.006502,
            "year": 2024,
            "source": "fallback",
        }
    if air is None:
        air = {
            "product_id": "",
            "mode_cn": "航空运输",
            "boundary": "大门到坟墓",
            "g_co2e_per_tonne_km": 921.0,
            "kg_co2e_per_tonne_km": 0.921,
            "year": 2024,
            "source": "fallback",
        }

    return {
        "_meta": {
            "primary": "data/core.csv",
            "note": "公路细分及水运等均在 road_modes；invoice-parser 逻辑未改",
        },
        "rail": rail,
        "air": air,
        "road_default": _pick_road_default(modes),
        "road_modes": modes,
    }


def overlay_transport_xlsx(payload: dict) -> None:
    if not TRANSPORT_XLSX.exists():
        return
    df0 = pd.read_excel(TRANSPORT_XLSX, sheet_name=0, header=None)
    first = str(df0.iloc[0, 0]).strip() if df0.shape[1] else ""
    existing = {r["product_id"] for r in payload["road_modes"] if r.get("product_id")}

    def parse_tonne_km_kg_local(s: str) -> float | None:
        return parse_tonne_km_kg(s)

    if "运输方式" in first or (df0.shape[1] > 1 and "运输方式" in str(df0.iloc[0, 1])):
        return

    for _, row in df0.iterrows():
        pid = str(row.iloc[0]).strip() if len(row) > 0 else ""
        if pid == "产品ID" or pid in existing:
            continue
        name = str(row.iloc[1]).strip() if len(row) > 1 else ""
        boundary = str(row.iloc[2]).strip() if len(row) > 2 else ""
        raw_fp = row.iloc[3] if len(row) > 3 else ""
        kg = parse_tonne_km_kg_local(raw_fp)
        if kg is None or not name:
            continue
        try:
            y = int(float(row.iloc[4])) if len(row) > 4 and not pd.isna(row.iloc[4]) else 2024
        except (TypeError, ValueError):
            y = 2024
        payload["road_modes"].append(
            {
                "product_id": pid,
                "mode_cn": name,
                "boundary": boundary,
                "g_co2e_per_tonne_km": kg * 1000.0,
                "kg_co2e_per_tonne_km": kg,
                "year": y,
                "source": "data/transport.xlsx (补充，无于 core 的产品) ",
            }
        )


def build_cpcd_catalog(core_df: pd.DataFrame) -> None:
    pid = "产品ID"
    core_out = core_df.drop(columns=["_y"], errors="ignore")
    if not EMISSION_EXT.exists():
        core_out.to_csv(CATALOG_OUT, index=False, encoding="utf-8-sig")
        return
    em = pd.read_csv(EMISSION_EXT, encoding="utf-8")
    ids = set(core_out[pid].astype(str))
    em = em[em[pid].astype(str).map(lambda x: x not in ids)]
    merged = pd.concat([core_out, em], ignore_index=True)
    merged.to_csv(CATALOG_OUT, index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge data/core.csv into project datasets.")
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Only rebuild data/cpcd_catalog.csv from core + Emission factors.csv (do not overwrite grid/transport JSON).",
    )
    args = parser.parse_args()

    if not CORE.exists():
        raise SystemExit(f"Missing {CORE}")
    raw = pd.read_csv(CORE, encoding="utf-8")
    df = dedupe_core(raw)

    if args.catalog_only:
        build_cpcd_catalog(df)
        print(f"Wrote {CATALOG_OUT} (catalog-only)")
        return

    grid = build_grid(df)
    with open(GRID_OUT, "w", encoding="utf-8") as f:
        json.dump(grid, f, ensure_ascii=False, indent=2)

    trans = build_transport_from_core(df)
    overlay_transport_xlsx(trans)
    trans["road_default"] = _pick_road_default(trans["road_modes"])
    with open(TRANSPORT_OUT, "w", encoding="utf-8") as f:
        json.dump(trans, f, ensure_ascii=False, indent=2)

    build_cpcd_catalog(df)
    print(f"Wrote {GRID_OUT}")
    print(f"Wrote {TRANSPORT_OUT} (road_modes={len(trans['road_modes'])})")
    print(f"Wrote {CATALOG_OUT}")


if __name__ == "__main__":
    main()
