from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app
from backend.flight_ticket_service import _extract_with_vision_model, build_flight_ticket_result


def test_flight_ticket_activity_iata(monkeypatch):
    monkeypatch.setenv("FLIGHT_TICKET_ENABLE_MARKET_PRICE", "false")
    extracted = {
        "passenger_name": "张三",
        "segments": [
            {"departure": "PEK", "arrival": "SHA", "flight_number": "CA1234", "date": "2026-05-01", "class": "经济舱"}
        ],
        "total_amount": 1200.0,
        "is_domestic": True,
    }

    data = build_flight_ticket_result(extracted, carbon_price_per_ton=100, carbon_price_date="2026-05-01")

    assert data["ticket_type"] == "机票"
    assert data["calculation_method"] == "activity_distance"
    assert data["segments"][0]["departure"] == "PEK"
    assert data["segments"][0]["arrival"] == "SHA"
    assert data["total_emissions_kg"] > 0
    assert data["carbon_cost_cny"] > 0
    assert "识别结果：机票" in data["explanation"]


def test_flight_ticket_chinese_airports_marked_estimated(monkeypatch):
    monkeypatch.setenv("FLIGHT_TICKET_ENABLE_MARKET_PRICE", "false")
    extracted = {
        "passenger_name": "张三",
        "segments": [
            {"departure": "北京首都", "arrival": "上海虹桥", "flight_number": "CA1234", "date": "2026-05-01", "class": "经济舱"}
        ],
        "total_amount": 1200.0,
        "is_domestic": True,
    }

    data = build_flight_ticket_result(extracted, carbon_price_per_ton=100)

    assert data["segments"][0]["departure"] == "PEK"
    assert data["segments"][0]["arrival"] == "SHA"
    assert data["calculation_method"] == "estimated_activity_distance"
    assert data["assumptions"]


def test_flight_ticket_multi_segment_sums(monkeypatch):
    monkeypatch.setenv("FLIGHT_TICKET_ENABLE_MARKET_PRICE", "false")
    extracted = {
        "passenger_name": "张三",
        "segments": [
            {"departure": "PEK", "arrival": "SHA", "date": "2026-05-01", "class": "经济舱"},
            {"departure": "SHA", "arrival": "CAN", "date": "2026-05-02", "class": "经济舱"},
        ],
        "total_amount": 1800.0,
        "is_domestic": True,
    }

    data = build_flight_ticket_result(extracted, carbon_price_per_ton=100)

    assert len(data["segments"]) == 2
    assert data["total_emissions_kg"] == round(sum(s["emission_kg"] for s in data["segments"]), 4)


def test_flight_ticket_refund_requires_manual_review(monkeypatch):
    monkeypatch.setenv("FLIGHT_TICKET_ENABLE_MARKET_PRICE", "false")
    extracted = {
        "passenger_name": "张三",
        "segments": [{"departure": "PEK", "arrival": "SHA"}],
        "total_amount": 200.0,
        "is_domestic": True,
    }

    data = build_flight_ticket_result(extracted, raw_text="退票费 200 元", carbon_price_per_ton=100)

    assert data["calculation_method"] == "manual_review"
    assert data["total_emissions_kg"] is None
    assert data["confidence"] == "需人工复核"


def test_flight_ticket_eeio_when_no_valid_segment(monkeypatch):
    monkeypatch.setenv("FLIGHT_TICKET_ENABLE_MARKET_PRICE", "false")
    extracted = {
        "passenger_name": "张三",
        "segments": [{"departure": None, "arrival": None}],
        "total_amount": 1000.0,
        "is_domestic": None,
    }

    data = build_flight_ticket_result(extracted, carbon_price_per_ton=100)

    assert data["calculation_method"] == "eeio_amount"
    assert data["total_emissions_kg"] == 149.7
    assert data["confidence"] == "中置信"


def test_flight_ticket_api_upload(monkeypatch):
    def fake_analyze(**kwargs):
        return {
            "ticket_type": "机票",
            "extracted_fields": {"passenger_name": "张三", "segments": [], "total_amount": None, "is_domestic": None},
            "segments": [],
            "calculation_method": "manual_review",
            "total_emissions_kg": None,
            "carbon_price_per_ton": 100,
            "carbon_cost_cny": None,
            "confidence": "需人工复核",
            "assumptions": [],
            "warnings": ["测试"],
            "explanation": "识别结果：机票",
        }

    monkeypatch.setattr("backend.routers.flight_ticket.analyze_flight_ticket_image", fake_analyze)
    client = TestClient(app)

    resp = client.post(
        "/api/flight-ticket/analyze",
        files={"file": ("ticket.png", b"fake-image", "image/png")},
        data={"carbon_price_per_ton": "100"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["ticket_type"] == "机票"


def test_sjtu_qwen_vision_extractor_uses_openai_compatible_endpoint(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"passenger_name":"张三","segments":[{"departure":"PEK","arrival":"SHA","flight_number":"CA1234","date":"2026-05-01","class":"经济舱"}],"total_amount":1200,"is_domestic":true}'
                        }
                    }
                ]
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("VISION_MODEL_PROVIDER", "sjtu")
    monkeypatch.setenv("VISION_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("VISION_MODEL_BASE_URL", "https://models.sjtu.edu.cn/api/v1")
    monkeypatch.setenv("VISION_MODEL_NAME", "qwen")
    monkeypatch.setattr("requests.post", fake_post)

    warnings = []
    fields = _extract_with_vision_model(b"image-bytes", "ticket.png", "image/png", warnings)

    assert fields["passenger_name"] == "张三"
    assert captured["url"] == "https://models.sjtu.edu.cn/api/v1/chat/completions"
    assert captured["json"]["model"] == "qwen"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert warnings == []
