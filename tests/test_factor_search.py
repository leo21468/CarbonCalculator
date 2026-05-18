from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import database
from backend.database import CustomProduct, ExternalFactorCandidate, add_product, save_external_factor_candidate
from backend.factor_search import search_factors
from backend.app import app


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "_DB_PATH", tmp_path / "carbon_test.db")
    monkeypatch.delenv("ENABLE_EXTERNAL_FACTOR_SEARCH", raising=False)
    monkeypatch.delenv("CLIMATIQ_API_KEY", raising=False)
    return database._DB_PATH


def test_local_custom_product_prevents_external_search(temp_db, monkeypatch):
    add_product(
        CustomProduct(
            id=None,
            product_name="自定义办公纸",
            carbon_type="Scope 3",
            carbon_footprint="1.2kgCO2e/包",
            co2_per_unit=1.2,
            unit="包",
            price_per_ton=100,
        )
    )
    monkeypatch.setenv("ENABLE_EXTERNAL_FACTOR_SEARCH", "true")
    monkeypatch.setattr("backend.factor_search._external_candidates", lambda *args, **kwargs: pytest.fail("should not call external"))

    data = search_factors("自定义办公纸", include_external=True)

    assert data["local_result"]["source"] == "custom"
    assert data["external_attempted"] is False
    assert data["external_candidates"] == []


def test_factor_search_api_external_disabled_returns_local_only(temp_db, monkeypatch):
    monkeypatch.setattr("backend.factor_search._get_cpcd_matches", lambda *args, **kwargs: [])
    client = TestClient(app)

    resp = client.post("/api/factors/search", json={"product_name": "不存在的产品", "include_external": True})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["local_result"]["source"] == "none"
    assert data["external_enabled"] is False
    assert data["external_attempted"] is False


def test_adopt_candidate_creates_custom_product(temp_db):
    cid = save_external_factor_candidate(
        ExternalFactorCandidate(
            id=None,
            query_text="低碳玻璃",
            product_name="低碳玻璃",
            factor_value=2.5,
            unit="kg",
            region="中国",
            year="2024",
            source_name="测试来源",
            source_url="https://example.com/factor",
            confidence=0.8,
            raw_payload_json="{}",
        )
    )
    client = TestClient(app)

    resp = client.post("/api/factors/adopt", json={"id": cid, "carbon_type": "Scope 3", "price_per_ton": 120})

    assert resp.status_code == 200
    product_id = resp.json()["data"]["id"]
    products = database.list_products("低碳玻璃")
    assert products[0].id == product_id
    assert products[0].co2_per_unit == 2.5
    assert "测试来源" in products[0].remark


def test_adopt_missing_candidate_returns_404(temp_db):
    client = TestClient(app)

    resp = client.post("/api/factors/adopt", json={"id": 9999, "carbon_type": "Scope 3"})

    assert resp.status_code == 404
