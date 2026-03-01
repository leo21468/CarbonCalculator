"""测试 FastAPI 后端 API"""
import pytest
import sys
import tempfile
import os
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient


def _create_test_invoice_pdf() -> bytes:
    """创建一个带表格的测试发票 PDF，返回 bytes"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    cn = ParagraphStyle('CN', parent=getSampleStyleSheet()['Normal'], fontName='STSong-Light', fontSize=10)
    cn_title = ParagraphStyle('CNTitle', parent=getSampleStyleSheet()['Title'], fontName='STSong-Light', fontSize=16)
    elements.append(Paragraph("增值税电子普通发票", cn_title))
    elements.append(Paragraph("发票号码：99998888", cn))
    elements.append(Paragraph("开票日期：2025年06月15日", cn))
    elements.append(Paragraph("购买方：名称：测试公司", cn))
    elements.append(Spacer(1, 10))
    data = [
        ["货物或应税劳务名称", "数量", "单位", "单价", "金额"],
        ["*电力*电费", "1000", "度", "0.80", "800.00"],
        ["办公用品", "", "", "", "500.00"],
    ]
    t = Table(data, colWidths=[200, 60, 60, 60, 80])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'STSong-Light'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("销售方：名称：国网上海", cn))
    doc.build(elements)
    return buf.getvalue()


@pytest.fixture
def client():
    """使用 TestClient 测试 API"""
    import backend.database as db_module
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    original = db_module._DB_PATH
    db_module._DB_PATH = path
    try:
        from backend.app import app
        with TestClient(app) as c:
            yield c
    finally:
        db_module._DB_PATH = original
        try:
            os.unlink(path)
        except Exception:
            pass


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    text = r.content.decode("utf-8", errors="ignore")
    assert "碳足迹" in text or "Agent" in text or "agent" in text.lower()


def test_match_empty(client):
    r = client.post("/api/match", json={"product_name": ""})
    assert r.status_code == 422 or r.status_code == 400


def test_match_product(client):
    r = client.post("/api/match", json={"product_name": "电力"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    data = body.get("data", body)
    assert "product_name" in data
    assert "carbon_type" in data
    assert "source" in data


def test_add_and_match_custom(client):
    """新增自定义产品后，查询应优先返回自定义数据"""
    r1 = client.post(
        "/api/products",
        json={
            "product_name": "测试办公纸",
            "carbon_type": "Scope 3",
            "carbon_footprint": "0.5kgCO2e/千克",
            "co2_per_unit": 0.5,
            "unit": "千克",
            "price_per_ton": 100,
        },
    )
    assert r1.status_code == 200
    r2 = client.post("/api/match", json={"product_name": "办公纸"})
    assert r2.status_code == 200
    body = r2.json()
    data = body.get("data", body)
    assert data.get("source") == "custom"
    assert "办公纸" in data.get("product_name", "")


def test_upload_invoice_pdf(client):
    """上传 PDF 发票后应返回分类结果并存入数据库"""
    pdf_bytes = _create_test_invoice_pdf()
    r = client.post(
        "/api/invoice/upload",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    data = body.get("data", body)
    assert "lines" in data
    assert len(data["lines"]) >= 2
    assert "aggregate" in data
    assert data["invoice_number"] == "99998888"
    # 验证每行都有 scope 和 match_type
    for line in data["lines"]:
        assert "scope" in line
        assert "match_type" in line
        assert line["scope"] in ("Scope 1", "Scope 2", "Scope 3")


def test_upload_invoice_rejects_non_pdf(client):
    """非 PDF 文件应被拒绝"""
    r = client.post(
        "/api/invoice/upload",
        files={"file": ("data.txt", b"not a pdf", "text/plain")},
    )
    assert r.status_code == 400


def test_invoice_stats_after_upload(client):
    """上传发票后统计接口应返回数据"""
    pdf_bytes = _create_test_invoice_pdf()
    client.post(
        "/api/invoice/upload",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
    )
    # 查询统计
    r = client.get("/api/invoice/stats")
    assert r.status_code == 200
    body = r.json()
    stats = body.get("data", body)
    assert len(stats) > 0
    for scope, s in stats.items():
        assert "count" in s
        assert "total_amount" in s
        assert "total_emission_kg" in s


def test_invoice_categories_after_upload(client):
    """上传发票后类别列表接口应返回记录"""
    pdf_bytes = _create_test_invoice_pdf()
    client.post(
        "/api/invoice/upload",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
    )
    r = client.get("/api/invoice/categories")
    assert r.status_code == 200
    body = r.json()
    categories = body.get("data", body)
    assert len(categories) >= 2
    for cat in categories:
        assert "line_name" in cat
        assert "scope" in cat
        assert "amount" in cat


def test_invoice_stats_empty(client):
    """无数据时统计接口应返回空"""
    r = client.get("/api/invoice/stats")
    assert r.status_code == 200
    body = r.json()
    stats = body.get("data", body)
    assert stats == {}
