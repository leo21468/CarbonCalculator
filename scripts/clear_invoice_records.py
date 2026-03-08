"""
清空后端发票类别记录（carbon_data.db 中的 invoice_categories 表）。
用法（在项目根目录）：
  python scripts/clear_invoice_records.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import clear_invoice_categories

if __name__ == "__main__":
    n = clear_invoice_categories()
    print(f"已清空 {n} 条发票类别记录。")
