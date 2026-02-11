"""
演示：从发票结构化数据 → 分类 → 排放核算 → 碳账本与碳利润表。
"""
import sys
from pathlib import Path

# 将项目根目录加入 path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import CarbonAccountingPipeline
from src.config import AppConfig, CarbonPriceConfig


def main():
    # 示例：一张包含电费与办公用品的发票（API 返回的 dict）
    invoice_data = {
        "invoice_code": "011001900104",
        "invoice_number": "12345678",
        "date": "2025-02-01",
        "total_amount": 15000.0,
        "seller": {"name": "国网上海市电力公司", "tax_id": "91310000MA1FL2XX"},
        "buyer": {"name": "示例企业", "tax_id": "91310000MA1FL2YY"},
        "lines": [
            {
                "name": "电力*电费*",
                "tax_classification_code": "1090100000000000000",
                "tax_classification_name": "*电力*电费",
                "quantity": 5000,
                "unit": "度",
                "unit_price": 0.8,
                "amount": 4000.0,
            },
            {
                "name": "办公用品*文具*",
                "tax_classification_code": "3010100000000000000",
                "amount": 11000.0,
            },
        ],
    }

    config = AppConfig(
        carbon_price=CarbonPriceConfig(source="internal", price_per_ton=100.0),
    )
    pipeline = CarbonAccountingPipeline(config=config)

    # 处理发票
    out = pipeline.process_invoice_from_dict(invoice_data, ref_invoice_id="INV-001")
    print("=== 分类结果 ===")
    for c in out["classified"]:
        print(f"  {c.line.name} -> {c.scope.value} ({c.match_type})")
    print("\n=== 排放结果 (kg CO2e) ===")
    for r in out["emission_results"]:
        print(f"  {r.scope.value}: {r.emission_kg:.2f} kg ({r.method})")
    print("\n=== 按范围汇总 (kg) ===")
    for scope, kg in out["aggregate_kg"].items():
        print(f"  {scope.value}: {kg:.2f}")
    print("\n=== 碳账本条目 ===")
    for e in out["ledger_entries"]:
        print(f"  借 {e.debit_account.value}  {e.amount_cny:.2f} 元")

    # 碳利润表（示例财务数据）
    revenue = 1_000_000.0
    traditional_cost = 600_000.0
    all_emissions = out["emission_results"]
    st = pipeline.build_statement(revenue, traditional_cost, all_emissions)
    print("\n=== 碳利润表 ===")
    print(f"  营业收入: {st.revenue:,.2f}")
    print(f"  传统营业成本: {st.traditional_cost:,.2f}")
    print(f"  毛利: {st.gross_profit:,.2f}")
    print(f"  直接碳成本 (Scope 1): {st.scope1_carbon_cost:,.2f}")
    print(f"  隐含碳成本 (Scope 2): {st.scope2_carbon_cost:,.2f}")
    print(f"  隐含碳成本 (Scope 3): {st.scope3_carbon_cost:,.2f}")
    print(f"  经碳调整后的毛利: {st.carbon_adjusted_gross:,.2f}")
    print(f"  净碳损益: {st.net_carbon_pnl:,.2f}")


if __name__ == "__main__":
    main()
