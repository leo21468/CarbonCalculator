"""
基于 NLP 的 CPCD 类别匹配：将 agent 输入文字与 cpcd_full_*.csv 中的产品名称进行语义匹配。
使用 jieba 分词 + TF-IDF + 余弦相似度。
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CPCD_PATH = _ROOT / "cpcd_full_20260213_164705.csv"


@dataclass
class CPCDMatch:
    """匹配结果：对应 CSV 中的一行"""
    product_id: str
    product_name: str
    accounting_boundary: str
    carbon_footprint: str
    company_name: str
    data_year: str
    data_type: str
    is_low_carbon: str
    similarity: float
    row_index: int


def _tokenize_cn(text: str) -> List[str]:
    """中文分词（jieba）"""
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        return list(text)  # 无 jieba 时退化为字符级


class CPCDNLPMatcher:
    """
    将用户输入文本与 CPCD CSV 中的产品名称进行 NLP 匹配。
    使用 TF-IDF + 余弦相似度。
    """
    def __init__(self, csv_path: Optional[Path] = None):
        self.path = Path(csv_path) if csv_path else _DEFAULT_CPCD_PATH
        self._df = None
        self._vectorizer = None
        self._tfidf_matrix = None
        self._product_texts: List[str] = []
        self._loaded = False

    def load(self) -> None:
        """加载 CSV 并构建 TF-IDF 索引"""
        import pandas as pd
        from sklearn.feature_extraction.text import TfidfVectorizer

        if not self.path.exists():
            raise FileNotFoundError(f"CPCD 文件不存在: {self.path}")

        self._df = pd.read_csv(self.path, encoding="utf-8")
        # 标准化列名（CSV 原列为中文）
        col_map = {
            "产品ID": "product_id",
            "产品名称": "product_name",
            "核算边界": "accounting_boundary",
            "碳足迹": "carbon_footprint",
            "企业名称": "company_name",
            "数据年份": "data_year",
            "数据类型": "data_type",
            "是否低碳": "is_low_carbon",
        }
        self._df.columns = [col_map.get(str(c).strip(), str(c).strip()) for c in self._df.columns]
        name_col = "product_name" if "product_name" in self._df.columns else "产品名称"
        self._product_texts = self._df[name_col].fillna("").astype(str).tolist()
        # 用 jieba 分词后的空格连接作为 TF-IDF 输入
        corpus = [" ".join(_tokenize_cn(t)) for t in self._product_texts]
        self._vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b", min_df=1)
        self._tfidf_matrix = self._vectorizer.fit_transform(corpus)
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def match(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> List[CPCDMatch]:
        """
        将输入文本与 CSV 中的产品名称进行匹配，返回最相似的 top_k 条记录。
        query: agent 输入的文本
        top_k: 返回的最大匹配数
        min_similarity: 最低相似度阈值 (0-1)
        """
        self._ensure_loaded()
        from sklearn.metrics.pairwise import cosine_similarity

        if not query or not str(query).strip():
            return []
        q_tokens = " ".join(_tokenize_cn(str(query).strip()))
        q_vec = self._vectorizer.transform([q_tokens])
        sims = cosine_similarity(q_vec, self._tfidf_matrix)[0]
        indices = sims.argsort()[::-1]

        results = []
        for i in indices[: top_k * 2]:
            s = float(sims[i])
            if s < min_similarity:
                break
            row = self._df.iloc[i]
            pid = row.get("product_id", row.get("产品ID", ""))
            pname = row.get("product_name", row.get("产品名称", ""))
            results.append(
                CPCDMatch(
                    product_id=str(pid),
                    product_name=str(pname),
                    accounting_boundary=str(row.get("accounting_boundary", row.get("核算边界", ""))),
                    carbon_footprint=str(row.get("carbon_footprint", row.get("碳足迹", ""))),
                    company_name=str(row.get("company_name", row.get("企业名称", ""))),
                    data_year=str(row.get("data_year", row.get("数据年份", ""))),
                    data_type=str(row.get("data_type", row.get("数据类型", ""))),
                    is_low_carbon=str(row.get("is_low_carbon", row.get("是否低碳", ""))),
                    similarity=s,
                    row_index=int(i),
                )
            )
            if len(results) >= top_k:
                break
        return results


if __name__ == "__main__":
    import sys
    m = CPCDNLPMatcher()
    q = sys.argv[1] if len(sys.argv) > 1 else "电力"
    for r in m.match(q, top_k=5):
        print(f"{r.similarity:.3f}\t{r.product_name}\t{r.carbon_footprint}")
