"""
第二步：将发票明细分类至碳核算三个范围。
混合策略：一级确定性匹配（税收编码）+ 关键词/语义（宽泛类目）。
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import List, Optional

from .models import ClassifiedLineItem, Invoice, InvoiceLineItem, Scope
from .scope_mapping import TaxCodeScopeMapper
from .flight_utils import (
    detect_cabin,
    extract_iata_pair,
    get_airport_by_iata,
    looks_like_flight_ticket,
    is_domestic_route,
)
from .cpcd_flight_factor import get_cpcd_carbon_footprint


class InvoiceScopeClassifier:
    """
    规则引擎 + 关键词 + 可选语义（BERT/LLM 占位）。
    一级分类：国家税收分类编码与 GHG Protocol 预设映射表（优先 reference table.xlsx）；
    宽泛条目：关键词或语义向量判定。
    """
    def __init__(self, ref_table_path: Optional[Path] = None, ref_db_path: Optional[Path] = None):
        self.mapper = TaxCodeScopeMapper(ref_table_path=ref_table_path, ref_db_path=ref_db_path)

    def classify_invoice(self, invoice: Invoice) -> List[ClassifiedLineItem]:
        """对整张发票的每一行进行分类"""
        result = []
        for line in invoice.lines:
            result.append(
                self.classify_line(
                    line,
                    seller_name=self._seller_name(invoice),
                    invoice_raw_text=getattr(invoice, "raw_text", None),
                )
            )
        return result

    def _seller_name(self, invoice: Invoice) -> Optional[str]:
        return invoice.seller.name if invoice.seller else None

    def classify_line(
        self,
        line: InvoiceLineItem,
        seller_name: Optional[str] = None,
        invoice_raw_text: Optional[str] = None,
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

        # 0) 机票专用识别：从票面文本提取出发/到达 IATA 三字码
        #    然后后续在 EmissionCalculator 中基于 CPCD 航程因子计算碳当量。
        if looks_like_flight_ticket(name):
            pair = extract_iata_pair(name)
            if not pair and invoice_raw_text:
                # 明细抽取可能遗漏纯字母码列，此时从票据级原始文本补偿解析
                pair = extract_iata_pair(invoice_raw_text)

            if pair:
                from_code, to_code = pair
                from_airport = get_airport_by_iata(from_code)
                to_airport = get_airport_by_iata(to_code)
                # 仅当两端机场在 airport.xlsx 中能定位时，才开启机票专用分支
                if from_airport and to_airport:
                    # 国内/国际都统一打标为 CPCD（但在 EmissionCalculator 内部用固定系数计算）
                    # - 国内：0.0829 kgCO2e / 人·千米
                    # - 国际：0.18362 kgCO2e / 人·千米
                    # 把识别到的 IATA 码追加进明细名称，确保 EmissionCalculator
                    # 能通过 extract_iata_pair(classified.line.name) 命中
                    try:
                        line.name = (line.name or "").strip() + f" {from_code} {to_code}"
                    except Exception:
                        pass
                    return ClassifiedLineItem(
                        line=line,
                        scope=Scope.SCOPE_3,
                        match_type="flight_ticket",
                        matched_tax_code=tax_code,
                        emission_factor_id="cpcd_flight",
                    )

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

        def _extract_hotel_region(text: str) -> Optional[str]:
            """从酒店/住宿类明细中抽取括号里的国家/地区/城市关键字。"""
            if not text:
                return None
            # 常见形式：酒店住宿（俄罗斯联邦） / 酒店住宿(俄罗斯联邦)
            m = re.search(r"（([^）]+)）", text)
            if m:
                v = m.group(1).strip()
                return v or None
            m = re.search(r"\(([^)]+)\)", text)
            if m:
                v = m.group(1).strip()
                return v or None
            return None

        # 国内酒店常见城市（用于“国外酒店走 CPCD”的启发式判断）
        domestic_hotel_cities = {
            "北京", "上海", "广州", "深圳",
            "成都", "杭州", "南京", "武汉",
            "天津", "重庆", "西安", "长沙",
            "昆明",
        }

        def _maybe_switch_to_cpcd_hotel(text: str, current_factor_id: str) -> str:
            """
            如果当前命中的是 scope3_accommodation：
            - 抽取括号地区（如 俄罗斯联邦）
            - 若该地区不在国内酒店城市集合，且 CPCD 表能匹配到酒店住宿因子，则切到 cpcd_hotel
            """
            if current_factor_id != "scope3_accommodation":
                return current_factor_id
            region = _extract_hotel_region(text)
            if not region:
                return current_factor_id
            if region in domestic_hotel_cities:
                return current_factor_id
            # CPCD 中“酒店住宿（某地）”行 product_name 都会包含该 region
            if get_cpcd_carbon_footprint(region):
                return "cpcd_hotel"
            return current_factor_id

        # 优先级修正：当明细同时包含“服务”(scope3_service) 和“房费/住宿”(scope3_accommodation) 时，
        # 以住宿为主，避免误归类（一些 OCR/解析结果会把“住宿房费”拆成含“服务/房费”的组合）
        accom_keywords = ["住宿", "酒店", "宾馆", "旅馆", "民宿", "客房", "住房费", "房费"]
        kw_text = f"{name or ''} {tax_name or ''}"
        if factor_id_kw != "scope3_accommodation" and any(kw in kw_text for kw in accom_keywords):
            switched = _maybe_switch_to_cpcd_hotel(kw_text, "scope3_accommodation")
            return ClassifiedLineItem(
                line=line,
                scope=Scope.SCOPE_3,
                match_type="keyword_accommodation_overseas" if switched == "cpcd_hotel" else "keyword_accommodation",
                matched_tax_code=tax_code,
                emission_factor_id=switched,
            )
        if factor_id_kw != "scope3_default" or scope_kw != Scope.SCOPE_3:
            if factor_id_kw == "scope3_accommodation":
                factor_id_kw = _maybe_switch_to_cpcd_hotel(kw_text, factor_id_kw)
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
