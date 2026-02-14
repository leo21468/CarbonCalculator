"""
后端数据库：SQLite 存储用户新增的产品碳足迹数据。
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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
    conn.commit()


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


def list_products() -> List[CustomProduct]:
    conn = get_connection()
    try:
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
        r = conn.execute(
            "SELECT id, product_name, carbon_type, carbon_footprint, co2_per_unit, unit, price_per_ton, remark FROM custom_products WHERE product_name LIKE ? LIMIT 1",
            (f"%{product_name}%",),
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
