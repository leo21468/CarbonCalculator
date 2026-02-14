"""
第二步（一）：税收分类编码 → 排放范围 映射表加载与查询。
优先使用项目根目录的 reference table.xlsx；若无则回退到 data/ 下 CSV、YAML。
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple

from .models import Scope

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_REF_TABLE = _ROOT / "reference table.xlsx"

# 可能的 Excel 列名映射（兼容中英文）
_SCOPE_COL_NAMES = ("排放范围", "scope", "Scope", "碳排放范围", "范围")
_TAX_CODE_COL_NAMES = ("税收分类编码", "商品和服务税收分类编码", "税号", "tax_code", "编码", "19位编码")
_EXCLUDE_COL_NAMES = ("排除关键词", "排除", "exclude_keywords", "排除规则")
_FACTOR_COL_NAMES = ("排放因子", "emission_factor_id", "因子", "因子ID")
_NAME_COL_NAMES = ("名称", "描述", "name", "货物或应税劳务名称")


def _normalize_scope(val) -> Optional[Scope]:
    """将单元格值转为 Scope 枚举"""
    import pandas as pd
    import math
    
    # Use proper NaN checking instead of string comparison
    if val is None:
        return None
    if isinstance(val, float):
        if pd.isna(val) or math.isnan(val):
            return None
    s = str(val).strip()
    for scope in Scope:
        if scope.value in s or s in scope.value or s == str(scope.value):
            return scope
    s_lower = s.lower()
    if "scope 1" in s_lower or "范围1" in s or "范围一" in s:
        return Scope.SCOPE_1
    if "scope 2" in s_lower or "范围2" in s or "范围二" in s:
        return Scope.SCOPE_2
    if "scope 3" in s_lower or "范围3" in s or "范围三" in s:
        return Scope.SCOPE_3
    return None


def _parse_exclude(val) -> List[str]:
    """解析排除关键词列：分号/逗号分隔"""
    import pandas as pd
    import math
    
    # Use proper NaN checking
    if val is None:
        return []
    if isinstance(val, float):
        if pd.isna(val) or math.isnan(val):
            return []
    s = str(val).strip()
    if not s:
        return []
    for sep in (";", "；", ",", "，"):
        if sep in s:
            return [x.strip() for x in s.split(sep) if x.strip()]
    return [s] if s else []


def _find_col(df, candidates: tuple) -> Optional[str]:
    """在 DataFrame 列名中查找匹配列"""
    cols = [c for c in df.columns if c is not None]
    for c in cols:
        if str(c).strip() in candidates:
            return str(c)
    for cand in candidates:
        for c in cols:
            if cand in str(c):
                return str(c)
    return None


def _load_excel_mapping(path: Optional[Path] = None) -> List[Tuple[str, Scope, List[str], str]]:
    """
    从 reference table.xlsx 加载映射规则。
    返回 [(tax_code_prefix, scope, exclude_keywords, emission_factor_id), ...]
    """
    p = path or _REF_TABLE
    if not p.exists():
        return []
    try:
        import pandas as pd
        df = pd.read_excel(p, sheet_name=0)
        if df.empty or len(df.columns) < 2:
            return []
    except Exception:
        return []

    scope_col = _find_col(df, _SCOPE_COL_NAMES)
    tax_col = _find_col(df, _TAX_CODE_COL_NAMES)
    exclude_col = _find_col(df, _EXCLUDE_COL_NAMES)
    factor_col = _find_col(df, _FACTOR_COL_NAMES)

    if not scope_col:
        scope_col = df.columns[1] if len(df.columns) > 1 else None
    if not tax_col:
        tax_col = df.columns[0] if len(df.columns) > 0 else None
    
    # Cannot proceed without required columns
    if not scope_col or not tax_col:
        return []

    rows = []
    for _, r in df.iterrows():
        scope = _normalize_scope(r.get(scope_col))
        if scope is None:
            continue
        tax_val = r.get(tax_col)
        import pandas as pd
        import math
        if tax_val is None:
            continue
        if isinstance(tax_val, float) and (pd.isna(tax_val) or math.isnan(tax_val)):
            continue
        tax_code = str(tax_val).strip()
        if not tax_code:
            continue
        exclude = _parse_exclude(r.get(exclude_col)) if exclude_col else []
        factor_id = str(r.get(factor_col, "default")).strip() if factor_col else "default"
        if factor_id == "nan" or not factor_id:
            factor_id = "default"
        rows.append((tax_code, scope, exclude, factor_id))
    return rows


def _load_csv_mapping() -> List[Tuple[str, Scope, str, List[str], str]]:
    """加载 data/tax_code_to_scope.csv：前缀, scope, 描述, 排除关键词, 因子ID"""
    rows = []
    p = _DATA / "tax_code_to_scope.csv"
    if not p.exists():
        return rows
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()
    # Check if file has enough lines (header + at least one data row)
    if not lines or len(lines) < 2:
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
    优先从 reference table.xlsx 构建规则；若无则用 YAML/CSV。
    """
    def __init__(self, ref_table_path: Optional[Path] = None):
        self._ref_table = Path(ref_table_path) if ref_table_path else _REF_TABLE
        self._prefix_to_scope: List[Tuple[str, Scope, List[str], str]] = []
        self._keyword_rules: List[Tuple[List[str], Scope, List[str], str]] = []
        self._default_scope = Scope.SCOPE_3
        self._build()

    def _build(self) -> None:
        # 1) 优先从 reference table.xlsx 加载
        excel_rows = _load_excel_mapping(self._ref_table) if self._ref_table.exists() else []
        if excel_rows:
            self._prefix_to_scope = excel_rows
        else:
            # 2) 回退到 YAML
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

            # 3) 再用 CSV 补充
            for prefix, scope, _desc, exclude, factor_id in _load_csv_mapping():
                self._prefix_to_scope.append((prefix, scope, exclude, factor_id))

        # Excel 加载时暂不填充 keyword_rules，仅用前缀；若需关键词可后续从 YAML 补充
        if not self._keyword_rules:
            yaml_rules = _load_yaml_mapping()
            for r in yaml_rules:
                scope_name = r.get("scope", "Scope 3")
                try:
                    scope = Scope(scope_name)
                except ValueError:
                    scope = Scope.SCOPE_3
                factor_id = r.get("emission_factor_id", "default")
                exclude = r.get("exclude_keywords") or []
                kws = r.get("keywords") or []
                if kws:
                    self._keyword_rules.append((kws, scope, exclude, factor_id))

    def by_tax_code(self, tax_code: Optional[str]) -> Tuple[Scope, str, bool]:
        """
        按19位或前缀匹配。
        返回 (scope, emission_factor_id, was_excluded)。
        """
        if not tax_code or not str(tax_code).strip():
            return self._default_scope, "scope3_default", False
        code = str(tax_code).strip()
        sorted_prefixes = sorted(
            [(p, s, ex, fid) for p, s, ex, fid in self._prefix_to_scope],
            key=lambda x: -len(str(x[0]))
        )
        for prefix, scope, exclude, factor_id in sorted_prefixes:
            p = str(prefix)
            if code.startswith(p) or code == p:
                return scope, factor_id, False
        return self._default_scope, "scope3_default", False

    def by_keywords(self, name: Optional[str], tax_classification_name: Optional[str]) -> Tuple[Scope, str, bool]:
        """按关键词匹配（如 *运输服务* *成品油* *煤炭*）。"""
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
