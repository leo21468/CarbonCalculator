"""
碳价获取：显性价格（市场）可从上海环境能源交易所每日收盘价抓取；
隐性价格由用户在系统中设定（如 100–300 元/吨）。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

# 上海环境能源交易所 CEA 行情页（示例，实际以官网为准）
# 每日收盘后抓取，最权威免费
SHANGHAI_EEX_QUOTE_URL = "https://www.cneeex.com/cneeex/index/index.html"


@dataclass
class CarbonPriceQuote:
    """单日碳价行情"""
    price_per_ton: float  # 元/吨
    date: Optional[str] = None
    source: str = "internal"
    currency: str = "CNY"


def fetch_market_price_cea() -> Optional[CarbonPriceQuote]:
    """
    从上海环境能源交易所抓取当日/最近 CEA 碳配额收盘价。
    需根据实际页面结构解析（爬虫）。此处为占位，返回 None 表示未实现或失败。
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.get(SHANGHAI_EEX_QUOTE_URL, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # 实际需定位收盘价元素，例如：
        # price_el = soup.select_one(".close-price")  # 示例
        # if price_el: return CarbonPriceQuote(price_per_ton=float(price_el.text), source="market")
        return None
    except (ImportError, ConnectionError, ValueError) as e:
        # Handle specific exceptions: ImportError for missing libraries,
        # ConnectionError for network issues, ValueError for parsing errors
        return None
    except Exception:
        # Catch-all for any other unexpected errors
        return None


def get_carbon_price(
    source: str = "internal",
    internal_price: float = 100.0,
) -> CarbonPriceQuote:
    """
    获取碳价。source="market" 时尝试抓取交易所价格；
    source="internal" 时使用 internal_price（元/吨）。
    """
    if source == "market":
        quote = fetch_market_price_cea()
        if quote:
            return quote
    return CarbonPriceQuote(
        price_per_ton=internal_price,
        source="internal",
    )
