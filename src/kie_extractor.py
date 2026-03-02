"""
VI-LayoutXLM 关键信息抽取（KIE）可选模块。

用于从发票图像中抽取结构化 key-value 对（如 项目名称、金额），
需配合 PaddleOCR 完整仓库使用，非 whl 包内置功能。

使用前需完成：
  1. git clone https://gitee.com/PaddlePaddle/PaddleOCR.git
  2. pip install -r PaddleOCR/requirements.txt
  3. pip install -r PaddleOCR/ppstructure/kie/requirements.txt
  4. 下载 SER 模型：ser_vi_layoutxlm_xfund_infer（或发票微调模型）

环境变量：
  PADDLEOCR_ROOT: PaddleOCR 仓库根目录
  KIE_SER_MODEL: SER 模型目录（默认 inference/ser_vi_layoutxlm_xfund_infer）
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from .models import InvoiceLineItem


def _get_paddleocr_root() -> Optional[Path]:
    root = os.environ.get("PADDLEOCR_ROOT", "").strip()
    if root:
        p = Path(root)
        pred = p / "ppstructure" / "predict_system.py"
        if p.is_dir() and pred.exists():
            return p
    return None


def _get_ser_model_dir(paddle_root: Path) -> Optional[Path]:
    custom = os.environ.get("KIE_SER_MODEL", "").strip()
    if custom:
        p = Path(custom)
        if p.is_absolute() and p.is_dir():
            return p
        if not p.is_absolute():
            full = paddle_root / p
            if full.is_dir():
                return full
    infer_dir = paddle_root / "ppstructure" / "inference"
    candidates = [
        infer_dir / "ser_vi_layoutxlm_xfund_infer",
        infer_dir / "ser_vi_layoutxlm_fapiao_udml" / "best_accuracy",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def extract_lines_via_kie(
    image_path: str,
    paddle_root: Path,
    ser_model_dir: Path,
) -> List[dict]:
    """调用 PaddleOCR predict_system --mode=kie (VI-LayoutXLM) 抽取 key-value 对。

    Returns:
        list of {"transcription": str, "label": str} 等 KIE 输出结构
    """
    pred_script = paddle_root / "ppstructure" / "predict_system.py"
    if not pred_script.exists():
        return []

    class_file = paddle_root / "ppocr" / "utils" / "dict" / "kie_dict" / "xfund_class_list.txt"
    if not class_file.exists():
        class_file = paddle_root / "train_data" / "XFUND" / "class_list_xfun.txt"
    ser_dict = str(class_file) if class_file.exists() else ""

    out_dir = Path(tempfile.gettempdir()) / "carbon_calc_kie"
    out_dir.mkdir(parents=True, exist_ok=True)
    img_name = Path(image_path).stem

    cmd = [
        "python",
        str(pred_script),
        f"--image_dir={image_path}",
        "--mode=kie",
        f"--ser_model_dir={ser_model_dir}",
        "--kie_algorithm=LayoutXLM",
        "--ocr_order_method=tb-yx",
        f"--output={out_dir}",
    ]
    if ser_dict:
        cmd.append(f"--ser_dict_path={ser_dict}")

    try:
        subprocess.run(
            cmd,
            cwd=str(paddle_root),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    res_file = out_dir / "kie" / img_name / "res_0_kie.txt"
    if not res_file.exists():
        return []

    return _parse_kie_results(res_file)


def _parse_kie_results(path: Path) -> List[dict]:
    """解析 predict_system --mode=kie 输出：path\t{"ocr_info": [...]}"""
    items = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    for line in content.splitlines():
        line = line.strip()
        if "\t" in line:
            _, json_part = line.split("\t", 1)
            try:
                obj = json.loads(json_part)
                info = obj.get("ocr_info", obj)
                if isinstance(info, list):
                    for e in info:
                        if isinstance(e, dict) and e.get("transcription"):
                            items.append(e)
            except json.JSONDecodeError:
                pass
    return items


def kie_results_to_line_items(kv_list: List[dict]) -> List[InvoiceLineItem]:
    """将 KIE SER 输出转为 InvoiceLineItem。

    KIE 输出格式：{"transcription": "文本", "label": "question"|"answer"|"other"}。
    按顺序配对 question-answer；或取含 *XXX* 的 answer 作为商品名，相邻数字为金额。
    """
    lines: List[InvoiceLineItem] = []
    seq = [(kv.get("transcription", "").strip(), (kv.get("label") or "").lower()) for kv in kv_list]
    seq = [(t, l) for t, l in seq if t]

    pairs = []
    i = 0
    while i < len(seq):
        text, label = seq[i]
        if label == "question" and i + 1 < len(seq):
            nxt_t, nxt_l = seq[i + 1]
            if nxt_l == "answer":
                amt = _parse_amount(nxt_t)
                if amt is not None and 0 < amt < 1e8:
                    if not any(kw in text for kw in ("合计", "价税合计", "小计")):
                        pairs.append((text, amt))
                i += 2
                continue
        i += 1

    for name, amt in pairs:
        lines.append(InvoiceLineItem(name=name, amount=amt))

    if not lines:
        for text, label in seq:
            if label == "answer" and "*" in text and any("\u4e00" <= c <= "\u9fff" for c in text):
                if any(kw in text for kw in ("合计", "价税合计", "小计")):
                    continue
                nums = re.findall(r"\d+(?:\.\d+)?", text)
                amt = _parse_amount(nums[-1]) if nums else None
                if amt and 0 < amt < 1e8:
                    lines.append(InvoiceLineItem(name=text, amount=amt))

    return lines


def _parse_amount(s: str) -> Optional[float]:
    s = re.sub(r"[¥￥,，\s]", "", str(s))
    s = re.sub(r"[^\d.\-]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def try_kie_extract(image_path: str) -> List[InvoiceLineItem]:
    """当 PaddleOCR 与 SER 模型就绪时，尝试 KIE 抽取。

    环境变量：
      USE_KIE=1 启用
      PADDLEOCR_ROOT 仓库路径
      KIE_SER_MODEL 模型路径（可选）
    """
    if os.environ.get("USE_KIE", "0").strip() not in ("1", "true", "True", "yes"):
        return []

    root = _get_paddleocr_root()
    if not root:
        return []

    ser_dir = _get_ser_model_dir(root)
    if not ser_dir:
        return []

    kv_list = extract_lines_via_kie(image_path, root, ser_dir)
    return kie_results_to_line_items(kv_list)
