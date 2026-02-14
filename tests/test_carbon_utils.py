"""测试碳足迹解析与价格计算"""
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.carbon_utils import parse_carbon_footprint, carbon_cost_cny


class TestParseCarbonFootprint:
    def test_tco2e_per_ton(self):
        val, unit = parse_carbon_footprint("7.4tCO2e / 公吨")
        assert val == 7400.0
        assert "公吨" in unit or unit

    def test_kgco2e_per_kg(self):
        val, unit = parse_carbon_footprint("11.746kgCO2e / 千克")
        assert abs(val - 11.746) < 0.001
        assert "千克" in unit or unit

    def test_gco2e(self):
        val, unit = parse_carbon_footprint("33.53gCO2e / 千瓦时")
        assert abs(val - 0.03353) < 0.0001

    def test_empty(self):
        val, unit = parse_carbon_footprint("")
        assert val == 0.0
        assert unit == ""

    def test_none(self):
        val, unit = parse_carbon_footprint(None)
        assert val == 0.0


class TestCarbonCostCny:
    def test_basic(self):
        cost = carbon_cost_cny(1000, 100)  # 1吨, 100元/吨
        assert cost == 100.0

    def test_fractional(self):
        cost = carbon_cost_cny(500, 200)
        assert cost == 100.0
