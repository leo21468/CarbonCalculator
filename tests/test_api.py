"""测试 FastAPI 后端 API"""
import pytest
import sys
import tempfile
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """使用 TestClient 测试 API"""
    import backend.database as db_module
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    original = db_module._DB_PATH
    db_module._DB_PATH = path
    try:
        from backend.app import app
        with TestClient(app) as c:
            yield c
    finally:
        db_module._DB_PATH = original
        try:
            os.unlink(path)
        except Exception:
            pass


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    text = r.content.decode("utf-8", errors="ignore")
    assert "碳足迹" in text or "Agent" in text or "agent" in text.lower()


def test_match_empty(client):
    r = client.post("/api/match", json={"product_name": ""})
    assert r.status_code == 422 or r.status_code == 400


def test_match_product(client):
    r = client.post("/api/match", json={"product_name": "电力"})
    assert r.status_code == 200
    data = r.json()
    assert "product_name" in data
    assert "carbon_type" in data
    assert "source" in data


def test_add_and_match_custom(client):
    """新增自定义产品后，查询应优先返回自定义数据"""
    r1 = client.post(
        "/api/products",
        json={
            "product_name": "测试办公纸",
            "carbon_type": "Scope 3",
            "carbon_footprint": "0.5kgCO2e/千克",
            "co2_per_unit": 0.5,
            "unit": "千克",
            "price_per_ton": 100,
        },
    )
    assert r1.status_code == 200
    r2 = client.post("/api/match", json={"product_name": "办公纸"})
    assert r2.status_code == 200
    data = r2.json()
    assert data.get("source") == "custom"
    assert "办公纸" in data.get("product_name", "")
