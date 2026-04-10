"""
检查 reference table 是否就绪、映射能否加载。
用法（项目根目录）:
  python scripts/verify_reference_mapping.py
  python scripts/verify_reference_mapping.py --xlsx "path/to/table.xlsx"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scope_mapping import (  # noqa: E402
    TaxCodeScopeMapper,
    _REF_DB,
    default_ref_table_path,
    _load_excel_mapping,
    _load_from_db,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 reference 映射表加载情况")
    parser.add_argument("--xlsx", default=None, help="覆盖默认 reference table.xlsx 路径")
    args = parser.parse_args()

    xlsx = Path(args.xlsx) if args.xlsx else default_ref_table_path()
    db = _REF_DB

    print("=== 文件存在性 ===")
    print(f"  默认 xlsx（根目录或 data/）: {xlsx} -> {xlsx.exists()}")
    print(f"  data/reference_table.db : {db} -> {db.exists()}")

    db_rows = _load_from_db(db)
    excel_rows = _load_excel_mapping(xlsx) if xlsx.exists() else []

    print("\n=== 直接加载行数（不含 YAML）===")
    print(f"  SQLite reference_mapping 行数: {len(db_rows)}")
    print(f"  Excel 解析行数: {len(excel_rows)}")

    m = TaxCodeScopeMapper(ref_table_path=xlsx if args.xlsx else None)
    print("\n=== TaxCodeScopeMapper 生效规则 ===")
    print(f"  前缀/税号规则数: {len(m._prefix_to_scope)}")
    print(f"  关键词规则数: {len(m._keyword_rules)}")

    print("\n=== 抽样 by_tax_code ===")
    samples = ("1090123456789012345", "1010100000000000000", "3040500000000000000")
    for code in samples:
        scope, fid, ex = m.by_tax_code(code)
        print(f"  {code[:8]}... -> {scope.value}, factor={fid}, excluded={ex}")

    if not db.exists() and not xlsx.exists():
        print("\n[提示] 未找到 xlsx 与 db，当前仅依赖 data/scope_mapping_rules.yaml 兜底。")
        print("       请将新表保存为「reference table.xlsx」（项目根目录或 data/）后执行:")
        print("         python scripts/import_reference_table_to_db.py")
        return 1

    if excel_rows and not db_rows:
        print("\n[提示] 已能解析 Excel，但尚未导入 DB；建议运行 import_reference_table_to_db.py 加速启动。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
