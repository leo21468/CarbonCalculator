"""
企业记账系统对接：在标准发票核算 API 外包一层 erp_context，便于网关与审计。

详见 docs/ENTERPRISE_INTEGRATION.md
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from backend.integration.callbacks import notify_erp_carbon_result
from src.erp_invoice_normalize import normalize_invoice_request_body

from backend.routers.invoices import (
    process_invoice_json,
    process_invoice_json_with_daily_carbon_price,
)

router = APIRouter(prefix="/api/integration", tags=["integration"])

INTEGRATION_VERSION = "0.1"


class AccountingSyncRequest(BaseModel):
    """企业记账触发的同步核算请求。"""

    invoice: dict[str, Any] = Field(
        ...,
        description="与 POST /api/invoice/process 相同；可为标准 lines/items，或费控响应（data.page_info + invoice_detail.Items）",
    )
    carbon_price_per_ton: Optional[float] = Field(
        None,
        description="若填写则按指定碳价核算（同 process_with_daily_carbon_price）",
    )
    carbon_price_date: Optional[str] = Field(
        None,
        description="碳价对应日期，可选；可与发票 date 一致",
    )
    idempotency_key: Optional[str] = Field(None, description="调用方幂等键，当前仅回显")
    voucher_id: Optional[str] = Field(None, description="凭证号 / 记账单据号，当前仅回显")
    tenant_id: Optional[str] = Field(None, description="租户 / 账套标识，当前仅回显")


@router.post(
    "/accounting-sync",
    summary="记账同步：发票 JSON → 碳足迹核算",
    description=(
        "供企业财务/记账系统在录入发票后调用。"
        "invoice 字段与 /api/invoice/process 一致；"
        "可选碳价字段与 /api/invoice/process_with_daily_carbon_price 一致。"
        "响应中 erp_context 为回显字段；carbon_result 为核算结果。"
    ),
)
def accounting_sync(payload: AccountingSyncRequest = Body(...)) -> dict[str, Any]:
    try:
        body = normalize_invoice_request_body(dict(payload.invoice))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not body.get("lines") and not body.get("items"):
        raise HTTPException(
            status_code=400,
            detail="invoice 中需包含 lines/items，或费控格式 data.page_info",
        )

    erp_context = {
        "idempotency_key": payload.idempotency_key,
        "voucher_id": payload.voucher_id,
        "tenant_id": payload.tenant_id,
    }

    if payload.carbon_price_per_ton is not None:
        body["carbon_price_per_ton"] = float(payload.carbon_price_per_ton)
        if payload.carbon_price_date is not None:
            body["carbon_price_date"] = payload.carbon_price_date
        carbon_result = process_invoice_json_with_daily_carbon_price(body=body)
    else:
        carbon_result = process_invoice_json(body=body)

    out: dict[str, Any] = {
        "integration_version": INTEGRATION_VERSION,
        "erp_context": erp_context,
        "carbon_result": carbon_result,
    }

    if isinstance(carbon_result, dict) and carbon_result.get("success"):
        notify_erp_carbon_result(
            {
                "event": "carbon.accounting.completed",
                "integration_version": INTEGRATION_VERSION,
                "erp_context": erp_context,
                "carbon_result": carbon_result,
            }
        )

    return out


@router.get("/health", summary="对接模块自检")
def integration_health():
    return {
        "integration_version": INTEGRATION_VERSION,
        "mode": "sync_json",
        "webhook_configured": bool((os.environ.get("ERP_CARBON_RESULT_WEBHOOK_URL") or "").strip()),
    }
