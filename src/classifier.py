"""
第二步：将发票明细分类至碳核算三个范围。
混合策略：一级确定性匹配（税收编码）+ 关键词/语义（宽泛类目）。
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional

from .models import ClassifiedLineItem, Invoice, InvoiceLineItem, Scope
from .scope_mapping import TaxCodeScopeMapper


class InvoiceScopeClassifier:
    """
    规则引擎 + 关键词 + 可选语义（BERT/LLM 占位）。
    一级分类：国家税收分类编码与 GHG Protocol 预设映射表（优先 reference table.xlsx）；
    宽泛条目：关键词或语义向量判定。
    """
    def __init__(self, ref_table_path: Optional[Path] = None):
        self.mapper = TaxCodeScopeMapper(ref_table_path=ref_table_path)

    def classify_invoice(self, invoice: Invoice) -> List[ClassifiedLineItem]:
        """对整张发票的每一行进行分类"""
        result = []
        for line in invoice.lines:
            result.append(self.classify_line(line, seller_name=self._seller_name(invoice)))
        return result

    def _seller_name(self, invoice: Invoice) -> Optional[str]:
        return invoice.seller.name if invoice.seller else None

    def classify_line(
        self,
        line: InvoiceLineItem,
        seller_name: Optional[str] = None,
    ) -> ClassifiedLineItem:
        """
        单行分类逻辑：
        1) 若有19位税号，优先用映射表；
        2) 应用排除规则（沥青、蜡、碳黑、润滑油 → Scope 3）；
        3) 无税号或宽泛时用关键词（*成品油*、*煤炭*、*运输服务*等）；
        4) 可选：语义模型（占位）；
        5) 兜底 Scope 3。
        """
        scope = Scope.SCOPE_3
        match_type = "default"
        factor_id = "scope3_default"
        tax_code = line.tax_classification_code
        name = line.name or ""
        tax_name = line.tax_classification_name or ""

        # 1) 税收分类编码精确/前缀匹配
        if tax_code:
            scope, factor_id, was_excluded = self.mapper.by_tax_code(tax_code)
            if not was_excluded:
                # 排除规则：在名称/税收简称中若含排除词，改 Scope 3
                if self._has_exclusion(name, tax_name, scope):
                    scope = Scope.SCOPE_3
                    factor_id = "scope3_default"
                    match_type = "tax_code_excluded"
                else:
                    match_type = "tax_code"
                    return ClassifiedLineItem(
                        line=line,
                        scope=scope,
                        match_type=match_type,
                        matched_tax_code=tax_code,
                        emission_factor_id=factor_id,
                    )

        # 2) 关键词匹配（*运输服务*、*煤炭*、*成品油*等）
        scope_kw, factor_id_kw, excluded = self.mapper.by_keywords(name, tax_name)
        if factor_id_kw != "scope3_default" or scope_kw != Scope.SCOPE_3:
            match_type = "keyword"
            return ClassifiedLineItem(
                line=line,
                scope=scope_kw,
                match_type=match_type,
                matched_tax_code=tax_code,
                emission_factor_id=factor_id_kw,
            )

        # 3) 销方语义辅助：例如 顺丰/EMS → 运输 → Scope 3
        if seller_name and self._is_logistics_seller(seller_name):
            match_type = "seller_keyword"
            return ClassifiedLineItem(
                line=line,
                scope=Scope.SCOPE_3,
                match_type=match_type,
                matched_tax_code=tax_code,
                emission_factor_id="scope3_service",
            )

        # 4) 可选：BERT/LLM 语义（占位）
        # semantic_scope, semantic_factor = self._semantic_classify(name, line.remark)
        # if semantic_scope is not None: ...

        # 5) 兜底
        return ClassifiedLineItem(
            line=line,
            scope=Scope.SCOPE_3,
            match_type="default",
            matched_tax_code=tax_code,
            emission_factor_id="scope3_default",
        )

    def _has_exclusion(self, name: str, tax_name: str, scope: Scope) -> bool:
        """Scope 1 石油加工类排除：沥青、蜡、碳黑、润滑油 → 归 Scope 3"""
        if scope != Scope.SCOPE_1:
            return False
        text = (name + " " + tax_name).lower()
        for word in ["沥青", "蜡", "碳黑", "润滑油", "石蜡"]:
            if word in text:
                return True
        return False

    def _is_logistics_seller(self, seller_name: str) -> bool:
        return any(
            x in (seller_name or "")
            for x in ["顺丰", "EMS", "中通", "圆通", "韵达", "德邦", "京东物流"]
        )
