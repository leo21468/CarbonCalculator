"""Inspect reference table.xlsx structure"""
import pandas as pd
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from src.scope_mapping import default_ref_table_path

path = default_ref_table_path()
print("Looking for:", path)
print("Exists:", path.exists())
if not path.exists():
    sys.exit(1)

xl = pd.ExcelFile(path)
print("Sheets:", xl.sheet_names)
for n in xl.sheet_names:
    df = pd.read_excel(path, sheet_name=n)
    print(f"\n--- Sheet: {n} ---")
    print("Columns:", list(df.columns))
    print("Shape:", df.shape)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 500)
    print(df.head(50).to_string())
