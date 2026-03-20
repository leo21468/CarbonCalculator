#!/usr/bin/env python3
"""
[旧流程] 合并铁路/航空固定值与 data/transport.xlsx → transport_factors.json。

**推荐**：运行 `tools/merge_core_into_datasets.py`（从 core 快照生成 transport，并可将 xlsx 独有行补入；**core 冻结后**请直接改 `transport_factors.json` 或仅用本脚本维护 xlsx）。

本脚本仍可用于仅维护 xlsx、无 core 时的简单场景。

transport.xlsx 支持两种格式：
1) CPCD 导出：无表头，列 = 产品ID, 产品名称, 核算边界, 碳足迹, 数据年份
   碳足迹示例：「0.1826kgCO2e / 公吨·公里」
2) 简化表：有表头，列含 运输方式, 核算边界, gCO2e_per_tonne_km, 年份, 备注
运行：python tools/sync_transport_factors.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "data" / "transport.xlsx"
OUT = ROOT / "data" / "transport_factors.json"

# 用户提供的 CPCD：gCO2e / 公吨·公里
CPCD_RAIL_G = 6.502
CPCD_AIR_G = 921.0


def parse_tonne_km_kg(s: str) -> float | None:
    """解析为 kgCO2e / 公吨·公里"""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    t = str(s).strip().replace("\xa0", " ")
    # 0.1826kgCO2e / 公吨·公里 或 921gCO2e / 公吨·公里
    m = re.search(
        r"([\d.]+)\s*(kg|g)\s*CO2e?\s*/\s*公吨[·.]?公里",
        t,
        re.IGNORECASE,
    )
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2).lower() == "g":
        val /= 1000.0
    return val


def _pick_default_road(modes: list[dict]) -> dict | None:
    if not modes:
        return None
    for row in modes:
        name = row.get("mode_cn") or ""
        if "不区分" in name:
            return row
    for row in modes:
        n = (row.get("mode_cn") or "").strip().replace("\xa0", " ")
        if (
            row.get("year") == 2024
            and "摇篮到坟墓" in str(row.get("boundary", ""))
            and n == "中型柴油货车运输"
        ):
            return row
    for row in modes:
        if row.get("year") == 2024 and "摇篮到坟墓" in str(row.get("boundary", "")):
            return row
    return modes[0]


def load_cpcd_style(df: pd.DataFrame) -> list[dict]:
    modes = []
    for _, row in df.iterrows():
        pid = str(row.iloc[0]).strip() if len(row) > 0 else ""
        name = str(row.iloc[1]).strip() if len(row) > 1 else ""
        if pid == "产品ID" or "碳足迹" in pid:
            continue  # 表头行
        boundary = str(row.iloc[2]).strip() if len(row) > 2 else ""
        raw_fp = row.iloc[3] if len(row) > 3 else ""
        year = row.iloc[4] if len(row) > 4 else None
        try:
            y = int(float(year)) if year is not None and not pd.isna(year) else 2024
        except (TypeError, ValueError):
            y = 2024
        kg = parse_tonne_km_kg(raw_fp)
        if kg is None:
            continue
        if not name or name == "nan":
            continue
        modes.append(
            {
                "product_id": pid,
                "mode_cn": name.replace("\xa0", " ").strip(),
                "boundary": boundary.replace("\xa0", " ").strip(),
                "g_co2e_per_tonne_km": kg * 1000.0,
                "kg_co2e_per_tonne_km": kg,
                "year": y,
                "source": "data/transport.xlsx (CPCD)",
            }
        )
    return modes


def load_simple_style(df: pd.DataFrame) -> list[dict]:
    cols = [str(c).strip() for c in df.columns]
    modes = []

    def col(*names: str) -> int | None:
        for i, c in enumerate(cols):
            if any(n in c for n in names):
                return i
        return None

    i_mode = col("运输方式", "方式")
    i_boundary = col("核算边界", "边界")
    i_g = col("gCO2e", "每吨公里")
    i_year = col("年份", "年")
    i_note = col("备注", "来源")
    i_id = col("产品ID", "ID")
    if i_mode is None or i_g is None:
        return []
    for _, row in df.iterrows():
        mode = row.iloc[i_mode]
        if pd.isna(mode):
            continue
        g = row.iloc[i_g]
        if pd.isna(g):
            continue
        try:
            g_val = float(g)
        except (TypeError, ValueError):
            continue
        pid = ""
        if i_id is not None and not pd.isna(row.iloc[i_id]):
            pid = str(row.iloc[i_id]).strip()
        boundary = (
            str(row.iloc[i_boundary]).strip()
            if i_boundary is not None and not pd.isna(row.iloc[i_boundary])
            else "大门到坟墓"
        )
        y = 2024
        if i_year is not None and not pd.isna(row.iloc[i_year]):
            try:
                y = int(float(row.iloc[i_year]))
            except (TypeError, ValueError):
                pass
        note = ""
        if i_note is not None and not pd.isna(row.iloc[i_note]):
            note = str(row.iloc[i_note]).strip()
        modes.append(
            {
                "product_id": pid,
                "mode_cn": str(mode).strip(),
                "boundary": boundary,
                "g_co2e_per_tonne_km": g_val,
                "kg_co2e_per_tonne_km": g_val / 1000.0,
                "year": y,
                "source": note or "data/transport.xlsx",
            }
        )
    return modes


def main() -> None:
    road_modes: list[dict] = []
    if XLSX.exists():
        df0 = pd.read_excel(XLSX, sheet_name=0, header=None)
        # 有表头：第一行含「运输方式」等
        first = str(df0.iloc[0, 0]).strip() if df0.shape[1] > 0 else ""
        if "运输方式" in first or (df0.shape[1] > 1 and "运输方式" in str(df0.iloc[0, 1])):
            df = pd.read_excel(XLSX, sheet_name=0)
            road_modes = load_simple_style(df)
        else:
            road_modes = load_cpcd_style(df0)

    default_road = _pick_default_road(road_modes)

    payload = {
        "_meta": {
            "sync": "tools/sync_transport_factors.py",
            "rail_air_note": "铁路、航空为 CPCD 2024，单位 gCO2e/公吨·公里，已换算为 kgCO2e/公吨·公里",
            "road_note": "公路见 data/transport.xlsx，碳足迹列已为 kgCO2e/公吨·公里 时直接采用",
        },
        "rail": {
            "product_id": "",
            "mode_cn": "铁路运输",
            "boundary": "大门到坟墓",
            "g_co2e_per_tonne_km": CPCD_RAIL_G,
            "kg_co2e_per_tonne_km": CPCD_RAIL_G / 1000.0,
            "year": 2024,
            "source": "CPCD 铁路运输",
        },
        "air": {
            "product_id": "",
            "mode_cn": "航空运输",
            "boundary": "大门到坟墓",
            "g_co2e_per_tonne_km": CPCD_AIR_G,
            "kg_co2e_per_tonne_km": CPCD_AIR_G / 1000.0,
            "year": 2024,
            "source": "CPCD 航空运输",
        },
        "road_default": default_road,
        "road_modes": road_modes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT} (road rows: {len(road_modes)})")


if __name__ == "__main__":
    main()
