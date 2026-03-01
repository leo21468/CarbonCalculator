"""
将 reference table.xlsx 导入 SQLite，避免每次从大 xlsx 加载。
使用方式：
  python scripts/import_reference_table_to_db.py
  python scripts/import_reference_table_to_db.py --xlsx "path/to.xlsx" --db "data/reference_table.db"
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

# 与 scope_mapping 一致的列名候选
SCOPE_COL_NAMES = ("排放范围", "scope", "Scope", "碳排放范围", "范围")
TAX_CODE_COL_NAMES = ("税收分类编码", "商品和服务税收分类编码", "税号", "tax_code", "编码", "19位编码")
EXCLUDE_COL_NAMES = ("排除关键词", "排除", "exclude_keywords", "排除规则")
FACTOR_COL_NAMES = ("排放因子", "emission_factor_id", "因子", "因子ID")
NAME_COL_NAMES = ("名称", "描述", "name", "货物或应税劳务名称")


def _normalize_scope_str(val) -> str | None:
    if val is None or (hasattr(pd, 'isna') and pd.isna(val)):
        return None
    s = str(val).strip()
    s_lower = s.lower()
    if "scope 1" in s_lower or "范围1" in s or "范围一" in s:
        return "Scope 1"
    if "scope 2" in s_lower or "范围2" in s or "范围二" in s:
        return "Scope 2"
    if "scope 3" in s_lower or "范围3" in s or "范围三" in s:
        return "Scope 3"
    if s in ("Scope 1", "Scope 2", "Scope 3"):
        return s
    return None


def _parse_exclude(val) -> str:
    """返回分号分隔的排除关键词字符串，便于存入 SQLite"""
    if val is None or (hasattr(pd, 'isna') and pd.isna(val)):
        return ""
    s = str(val).strip()
    if not s:
        return ""
    for sep in (";", "；", ",", "，"):
        if sep in s:
            parts = [x.strip() for x in s.split(sep) if x.strip()]
            return ";".join(parts)
    return s


def _find_col(df, candidates: tuple) -> str | None:
    cols = [c for c in df.columns if c is not None]
    for c in cols:
        if str(c).strip() in candidates:
            return str(c)
    for cand in candidates:
        for c in cols:
            if cand in str(c):
                return str(c)
    return None


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS reference_mapping (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tax_code TEXT NOT NULL,
      scope TEXT NOT NULL,
      exclude_keywords TEXT,
      emission_factor_id TEXT DEFAULT 'default',
      name TEXT,
      source_row INTEGER,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_reference_tax_code ON reference_mapping(tax_code);
    CREATE INDEX IF NOT EXISTS idx_reference_scope ON reference_mapping(scope);
    """)


def import_xlsx_to_db(xlsx_path: Path, db_path: Path) -> int:
    if not xlsx_path.exists():
        raise FileNotFoundError(f"xlsx 不存在: {xlsx_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(xlsx_path, sheet_name=0)
    if df.empty or len(df.columns) < 2:
        print("xlsx 为空或列数不足，跳过")
        return 0

    scope_col = _find_col(df, SCOPE_COL_NAMES)
    tax_col = _find_col(df, TAX_CODE_COL_NAMES)
    exclude_col = _find_col(df, EXCLUDE_COL_NAMES)
    factor_col = _find_col(df, FACTOR_COL_NAMES)
    name_col = _find_col(df, NAME_COL_NAMES)

    if not scope_col:
        scope_col = df.columns[1] if len(df.columns) > 1 else None
    if not tax_col:
        tax_col = df.columns[0] if len(df.columns) > 0 else None
    if not scope_col or not tax_col:
        print("未找到必需的「排放范围」和「税收分类编码」列，跳过")
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        create_schema(conn)
        conn.execute("DELETE FROM reference_mapping")
        insert_sql = """
        INSERT INTO reference_mapping (tax_code, scope, exclude_keywords, emission_factor_id, name, source_row)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        count = 0
        for idx, r in df.iterrows():
            scope = _normalize_scope_str(r.get(scope_col))
            if scope is None:
                continue
            tax_val = r.get(tax_col)
            if tax_val is None or pd.isna(tax_val):
                continue
            tax_code = str(tax_val).strip()
            if not tax_code:
                continue
            exclude = _parse_exclude(r.get(exclude_col)) if exclude_col else ""
            factor_id = str(r.get(factor_col, "default")).strip() if factor_col else "default"
            if factor_id == "nan" or not factor_id:
                factor_id = "default"
            name_val = r.get(name_col) if name_col else None
            name = str(name_val).strip() if name_val is not None and not pd.isna(name_val) else None
            conn.execute(insert_sql, (tax_code, scope, exclude or None, factor_id, name, int(idx) + 2))
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="将 reference table.xlsx 导入 SQLite")
    parser.add_argument("--xlsx", default=None, help="xlsx 路径，默认项目根目录 reference table.xlsx")
    parser.add_argument("--db", default=None, help="SQLite 路径，默认 data/reference_table.db")
    args = parser.parse_args()
    xlsx_path = Path(args.xlsx) if args.xlsx else ROOT / "reference table.xlsx"
    db_path = Path(args.db) if args.db else ROOT / "data" / "reference_table.db"
    print(f"源文件: {xlsx_path}")
    print(f"目标库: {db_path}")
    n = import_xlsx_to_db(xlsx_path, db_path)
    print(f"已导入 {n} 条记录。")


if __name__ == "__main__":
    main()
