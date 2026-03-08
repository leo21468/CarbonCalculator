"""
后端数据库：SQLite 存储用户新增的产品碳足迹数据及发票类别统计。
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _ROOT / "carbon_data.db"


@dataclass
class CustomProduct:
    """用户新增的产品碳足迹记录"""
    id: Optional[int]
    product_name: str
    carbon_type: str  # 碳种类，如 Scope1/2/3 或 电力/燃料等
    carbon_footprint: str  # 碳足迹描述，如 7.4tCO2e/公吨
    co2_per_unit: float  # 每单位 kgCO2e，便于计算价格
    unit: str
    price_per_ton: float  # 碳价 元/吨
    remark: str = ""


@dataclass
class InvoiceCategoryRecord:
    """发票类别统计记录"""
    id: Optional[int]
    invoice_number: Optional[str]
    line_name: str  # 发票明细行名称
    scope: str  # Scope 1 / Scope 2 / Scope 3
    match_type: str  # tax_code / keyword / default
    amount: float  # 金额（元）
    emission_kg: float  # 排放量 kgCO2e
    tax_code: Optional[str] = None
    created_at: Optional[str] = None


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            carbon_type TEXT NOT NULL,
            carbon_footprint TEXT,
            co2_per_unit REAL NOT NULL,
            unit TEXT NOT NULL,
            price_per_ton REAL DEFAULT 100,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoice_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT,
            line_name TEXT NOT NULL,
            scope TEXT NOT NULL,
            match_type TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            emission_kg REAL NOT NULL DEFAULT 0,
            tax_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 数据库版本表（迁移机制）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 索引：提升查询性能
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_name ON custom_products(product_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_scope ON invoice_categories(scope)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_number ON invoice_categories(invoice_number)"
    )
    _apply_migrations(conn)
    conn.commit()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """检查并自动应用数据库迁移"""
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row and row[0] is not None else 0
    # 版本1：初始化（无需额外操作，表已在 _init_db 中创建）
    if current < 1:
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES(1)")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def add_product(p: CustomProduct) -> int:
    """新增产品，返回 id"""
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO custom_products 
               (product_name, carbon_type, carbon_footprint, co2_per_unit, unit, price_per_ton, remark)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (p.product_name, p.carbon_type, p.carbon_footprint, p.co2_per_unit, p.unit, p.price_per_ton, p.remark),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_products(name_filter: Optional[str] = None) -> List[CustomProduct]:
    conn = get_connection()
    try:
        if name_filter:
            escaped = name_filter.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = conn.execute(
                "SELECT id, product_name, carbon_type, carbon_footprint, co2_per_unit, unit, price_per_ton, remark FROM custom_products WHERE product_name LIKE ? ESCAPE '\\' ORDER BY id DESC",
                (f"%{escaped}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, product_name, carbon_type, carbon_footprint, co2_per_unit, unit, price_per_ton, remark FROM custom_products ORDER BY id DESC"
            ).fetchall()
        return [
            CustomProduct(
                id=r["id"],
                product_name=r["product_name"],
                carbon_type=r["carbon_type"],
                carbon_footprint=r["carbon_footprint"] or "",
                co2_per_unit=r["co2_per_unit"],
                unit=r["unit"],
                price_per_ton=r["price_per_ton"],
                remark=r["remark"] or "",
            )
            for r in rows
        ]
    finally:
        conn.close()


def find_by_name(product_name: str) -> Optional[CustomProduct]:
    conn = get_connection()
    try:
        escaped = product_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        r = conn.execute(
            "SELECT id, product_name, carbon_type, carbon_footprint, co2_per_unit, unit, price_per_ton, remark FROM custom_products WHERE product_name LIKE ? ESCAPE '\\' LIMIT 1",
            (f"%{escaped}%",),
        ).fetchone()
        if r is None:
            return None
        return CustomProduct(
            id=r["id"],
            product_name=r["product_name"],
            carbon_type=r["carbon_type"],
            carbon_footprint=r["carbon_footprint"] or "",
            co2_per_unit=r["co2_per_unit"],
            unit=r["unit"],
            price_per_ton=r["price_per_ton"],
            remark=r["remark"] or "",
        )
    finally:
        conn.close()


def delete_product(product_id: int) -> bool:
    """删除产品，返回是否成功删除"""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM custom_products WHERE id = ?", (product_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_product(product_id: int, fields: dict) -> bool:
    """部分更新产品字段，返回是否成功更新"""
    allowed = {"product_name", "carbon_type", "carbon_footprint", "co2_per_unit", "unit", "price_per_ton", "remark"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    conn = get_connection()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [product_id]
        cur = conn.execute(f"UPDATE custom_products SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------- 发票类别统计 ----------


def add_invoice_category(record: InvoiceCategoryRecord) -> int:
    """新增发票类别记录，返回 id"""
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO invoice_categories
               (invoice_number, line_name, scope, match_type, amount, emission_kg, tax_code)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (record.invoice_number, record.line_name, record.scope,
             record.match_type, record.amount, record.emission_kg, record.tax_code),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def add_invoice_categories_batch(records: List[InvoiceCategoryRecord]) -> List[int]:
    """批量新增发票类别记录"""
    conn = get_connection()
    try:
        ids = []
        for rec in records:
            cur = conn.execute(
                """INSERT INTO invoice_categories
                   (invoice_number, line_name, scope, match_type, amount, emission_kg, tax_code)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (rec.invoice_number, rec.line_name, rec.scope,
                 rec.match_type, rec.amount, rec.emission_kg, rec.tax_code),
            )
            ids.append(cur.lastrowid)
        conn.commit()
        return ids
    finally:
        conn.close()


def list_invoice_categories() -> List[InvoiceCategoryRecord]:
    """列出所有发票类别记录"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, invoice_number, line_name, scope, match_type,
                      amount, emission_kg, tax_code, created_at
               FROM invoice_categories ORDER BY id DESC"""
        ).fetchall()
        return [
            InvoiceCategoryRecord(
                id=r["id"],
                invoice_number=r["invoice_number"],
                line_name=r["line_name"],
                scope=r["scope"],
                match_type=r["match_type"],
                amount=r["amount"],
                emission_kg=r["emission_kg"],
                tax_code=r["tax_code"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


def get_invoice_category_stats() -> Dict[str, dict]:
    """按 Scope 汇总发票类别统计：总金额、总排放量、条目数"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT scope,
                      COUNT(*) as count,
                      COALESCE(SUM(amount), 0) as total_amount,
                      COALESCE(SUM(emission_kg), 0) as total_emission_kg
               FROM invoice_categories
               GROUP BY scope
               ORDER BY scope"""
        ).fetchall()
        return {
            r["scope"]: {
                "count": r["count"],
                "total_amount": round(r["total_amount"], 2),
                "total_emission_kg": round(r["total_emission_kg"], 4),
            }
            for r in rows
        }
    finally:
        conn.close()


def clear_invoice_categories() -> int:
    """清空所有发票类别记录，返回删除的行数。"""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM invoice_categories")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
