"""
第二步（一）：税收分类编码 → 排放范围 映射表加载与查询。
在碳核算模型中建立「19位税号 → 排放因子」的映射。
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import Scope

# 项目根目录
_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"


def _load_csv_mapping() -> List[Tuple[str, Scope, str, List[str], str]]:
    """加载 data/tax_code_to_scope.csv：前缀, scope, 描述, 排除关键词, 因子ID"""
    rows = []
    p = _DATA / "tax_code_to_scope.csv"
    if not p.exists():
        return rows
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        return rows
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = [x.strip() for x in line.split(",")]
        if len(parts) < 3:
            continue
        prefix, scope_str, desc = parts[0], parts[1], parts[2]
        exclude = (parts[3].split(";") if len(parts) > 3 and parts[3] else [])
        factor_id = parts[4] if len(parts) > 4 else "default"
        try:
            scope = Scope(scope_str)
        except ValueError:
            continue
        rows.append((prefix, scope, desc, exclude, factor_id))
    return rows


def _load_yaml_mapping() -> List[dict]:
    """加载 data/scope_mapping_rules.yaml（若存在）"""
    p = _DATA / "scope_mapping_rules.yaml"
    if not p.exists():
        return []
    try:
        import yaml
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("rules", [])
    except Exception:
        return []


class TaxCodeScopeMapper:
    """
    19位税号 / 前缀 / 关键词 → Scope + 排放因子ID。
    优先精确匹配19位，再前缀，再关键词；应用排除规则。
    """
    def __init__(self):
        self._prefix_to_scope: List[Tuple[str, Scope, List[str], str]] = []
        self._keyword_rules: List[Tuple[List[str], Scope, List[str], str]] = []
        self._default_scope = Scope.SCOPE_3
        self._build()

    def _build(self) -> None:
        # 先加载 YAML（更细粒度）
        yaml_rules = _load_yaml_mapping()
        for r in yaml_rules:
            scope_name = r.get("scope", "Scope 3")
            try:
                scope = Scope(scope_name)
            except ValueError:
                scope = Scope.SCOPE_3
            factor_id = r.get("emission_factor_id", "default")
            exclude = r.get("exclude_keywords") or []
            for prefix in r.get("tax_code_prefixes") or []:
                self._prefix_to_scope.append((str(prefix).strip(), scope, exclude, factor_id))
            kws = r.get("keywords") or []
            if kws:
                self._keyword_rules.append((kws, scope, exclude, factor_id))

        # 再加载 CSV 补充
        for prefix, scope, _desc, exclude, factor_id in _load_csv_mapping():
            self._prefix_to_scope.append((prefix, scope, exclude, factor_id))

    def by_tax_code(self, tax_code: Optional[str]) -> Tuple[Scope, str, bool]:
        """
        按19位或前缀匹配。
        返回 (scope, emission_factor_id, was_excluded)。
        若命中排除关键词则 was_excluded=True，应归入 Scope 3。
        """
        if not tax_code or not str(tax_code).strip():
            return self._default_scope, "scope3_default", False
        code = str(tax_code).strip()
        # 从长到短匹配前缀
        sorted_prefixes = sorted(
            [(p, s, ex, fid) for p, s, ex, fid in self._prefix_to_scope],
            key=lambda x: -len(x[0])
        )
        for prefix, scope, exclude, factor_id in sorted_prefixes:
            if code.startswith(prefix) or code == prefix:
                # 检查排除关键词（在名称中判断，此处仅返回；名称在 classifier 中判断）
                return scope, factor_id, False
        return self._default_scope, "scope3_default", False

    def by_keywords(self, name: Optional[str], tax_classification_name: Optional[str]) -> Tuple[Scope, str, bool]:
        """
        按关键词匹配（如 *运输服务* *成品油* *煤炭*）。
        name: 货物或应税劳务名称；tax_classification_name: 税收分类简称。
        """
        text = " ".join(filter(None, [name or "", tax_classification_name or ""]))
        if not text:
            return self._default_scope, "scope3_default", False
        for kws, scope, exclude, factor_id in self._keyword_rules:
            for kw in kws:
                if kw in text:
                    for ex in exclude:
                        if ex in text:
                            return Scope.SCOPE_3, "scope3_default", True
                    return scope, factor_id, False
        return self._default_scope, "scope3_default", False
