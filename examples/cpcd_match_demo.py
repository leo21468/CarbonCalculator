"""
演示：使用 NLP 将 agent 输入文字与 CPCD CSV 中的产品类别进行匹配。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cpcd_matcher import CPCDNLPMatcher, CPCDMatch


def main():
    csv_path = ROOT / "cpcd_full_20260213_164705.csv"
    matcher = CPCDNLPMatcher(csv_path=csv_path)
    matcher.load()

    queries = [
        "电力",
        "汽油",
        "办公用品",
        "鸡蛋",
        "光伏组件",
        "煤炭",
        "运输服务",
        "黄豆",
    ]
    for q in queries:
        print(f"\n=== 输入: 「{q}」===")
        matches = matcher.match(q, top_k=3)
        for m in matches:
            print(f"  相似度 {m.similarity:.3f} | {m.product_name} | {m.carbon_footprint}")


if __name__ == "__main__":
    main()
