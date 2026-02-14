"""测试 CPCD NLP 匹配器（依赖 cpcd_full_*.csv）"""
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CSV_PATH = ROOT / "cpcd_full_20260213_164705.csv"
pytestmark = pytest.mark.skipif(
    not CSV_PATH.exists(),
    reason="CPCD CSV 文件不存在",
)


def test_matcher_load_and_match():
    from src.cpcd_matcher import CPCDNLPMatcher

    matcher = CPCDNLPMatcher(csv_path=CSV_PATH)
    matcher.load()
    matches = matcher.match("电力", top_k=3)
    assert len(matches) >= 1
    assert matches[0].similarity > 0
    assert "电力" in matches[0].product_name or len(matches[0].carbon_footprint) > 0


def test_matcher_empty_query():
    from src.cpcd_matcher import CPCDNLPMatcher

    matcher = CPCDNLPMatcher(csv_path=CSV_PATH)
    matcher.load()
    assert matcher.match("") == []
    assert matcher.match("  ") == []
