"""测试数据库模块（使用临时 SQLite 文件）"""
import pytest
import sys
import tempfile
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 在导入 database 前设置临时数据库路径
import backend.database as db_module

_original_path = None


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch):
    """每个测试使用独立的临时数据库"""
    global _original_path
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _original_path = db_module._DB_PATH
    monkeypatch.setattr(db_module, "_DB_PATH", path)
    yield path
    monkeypatch.setattr(db_module, "_DB_PATH", _original_path)
    try:
        os.unlink(path)
    except Exception:
        pass


def test_add_and_list_products():
    from backend.database import add_product, list_products, CustomProduct

    p = CustomProduct(
        id=None,
        product_name="测试产品",
        carbon_type="Scope 3",
        carbon_footprint="1.2kgCO2e/千克",
        co2_per_unit=1.2,
        unit="千克",
        price_per_ton=100.0,
    )
    pid = add_product(p)
    assert pid is not None
    prods = list_products()
    assert len(prods) == 1
    assert prods[0].product_name == "测试产品"


def test_find_by_name():
    from backend.database import add_product, find_by_name, CustomProduct

    p = CustomProduct(
        id=None,
        product_name="自定义办公纸",
        carbon_type="Scope 3",
        carbon_footprint="",
        co2_per_unit=0.5,
        unit="千克",
        price_per_ton=100.0,
    )
    add_product(p)
    found = find_by_name("办公纸")
    assert found is not None
    assert "办公纸" in found.product_name
