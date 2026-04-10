"""测试 FastAPI 后端 API（已移除 PDF 发票测试）"""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def client():
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


def test_match_product(client):
    r = client.post("/api/match", json={"product_name": "电力"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True


def test_invoice_process_json(client):
    body = {
        "invoice_number": "INV_JSON_001",
        "seller": {"name": "测试公司"},
        "lines": [{"name": "电费", "amount": 200.0, "quantity": 100, "unit": "度"}],
    }
    r = client.post("/api/invoice/process", json=body)
    assert r.status_code == 200
    data = r.json().get("data", {})
    assert data.get("invoice_number") == "INV_JSON_001"
    assert isinstance(data.get("lines"), list)


def test_commute_distance_iata(client):
    r = client.post(
        "/api/airports/commute-distance",
        json={"from_airport": "PEK", "to_airport": "PVG"},
    )
    assert r.status_code == 200
    data = r.json().get("data", {})
    assert data.get("distance_km") is not None
    assert data.get("distance_km") > 0

