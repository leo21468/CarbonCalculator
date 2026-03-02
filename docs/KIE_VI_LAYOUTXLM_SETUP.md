# VI-LayoutXLM 关键信息抽取（KIE）配置指南

本系统支持使用百度 PaddleOCR 的 **VI-LayoutXLM** 模型进行发票关键信息抽取，作为图片型 PDF 解析的兜底方案。

## 前置条件

1. **克隆 PaddleOCR 完整仓库**（KIE 暂不支持 whl 包直接调用）：

```bash
git clone https://gitee.com/PaddlePaddle/PaddleOCR.git
cd PaddleOCR
pip install -r requirements.txt
pip install -r ppstructure/kie/requirements.txt
```

2. **下载 SER 模型**：

```bash
cd ppstructure
mkdir -p inference && cd inference
# XFUND 通用模型（含 question/answer/other 类别）
wget https://paddleocr.bj.bcebos.com/ppstructure/models/vi_layoutxlm/ser_vi_layoutxlm_xfund_infer.tar
tar -xf ser_vi_layoutxlm_xfund_infer.tar
cd ../..
```

3. **可选：发票专用模型**（需自行训练，参考 [增值税发票 KIE 文档](https://paddlepaddle.github.io/PaddleOCR/v2.10.0/applications/发票关键信息抽取.html)）

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `USE_KIE=1` | 启用 KIE 兜底 | `export USE_KIE=1` |
| `PADDLEOCR_ROOT` | PaddleOCR 仓库根目录 | `export PADDLEOCR_ROOT=/path/to/PaddleOCR` |
| `KIE_SER_MODEL` | SER 模型路径（可选） | `export KIE_SER_MODEL=ppstructure/inference/ser_vi_layoutxlm_xfund_infer` |

## 启用方式

```bash
export USE_KIE=1
export PADDLEOCR_ROOT=/path/to/PaddleOCR
# 启动服务或运行解析
python run_server.py
```

## 调用时机

KIE 仅在以下情况作为**最后兜底**被调用：

1. PDF 为图片型（文本 < 20 字）
2. 已尝试：表格提取 → OCR 结构化 → 正则文本提取 → PP-Structure
3. 以上均未提取到任何明细行

## 输出格式

VI-LayoutXLM SER 模型输出 `question` / `answer` / `other` 类别，系统按顺序配对 question-answer 转为 `InvoiceLineItem`，或从含 `*XXX*` 格式的 answer 中解析商品名与金额。
