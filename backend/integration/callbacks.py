from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("carbon_api.integration")


def notify_erp_carbon_result(payload: dict[str, Any]) -> None:
    """可选 webhook 回调；未配置时静默跳过。"""
    url = (os.environ.get("ERP_CARBON_RESULT_WEBHOOK_URL") or "").strip()
    if not url:
        return
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as exc:
        logger.warning("ERP 回调失败: %s", exc)

