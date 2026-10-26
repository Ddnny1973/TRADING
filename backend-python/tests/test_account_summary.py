"""
A1b: resumen del resultado neto real leído de Binance (/fapi/v1/income +
/fapi/v2/account) y su endpoint GET /api/v1/account/income-summary.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.main import _income_summary_cache, grid_service
from app.services.account_summary import build_income_summary, summarize_income

DAY_MS = 1_792_886_400_000  # 2026-10-25T00:00:00Z

RECORDS = [
    {"symbol": "ETHUSDT", "incomeType": "REALIZED_PNL", "income": "3.0", "time": DAY_MS},
    {"symbol": "ETHUSDT", "incomeType": "COMMISSION", "income": "-0.4", "time": DAY_MS},
    {"symbol": "SOLUSDT", "incomeType": "REALIZED_PNL", "income": "-1.0", "time": DAY_MS - 86_400_000},
    {"symbol": "SOLUSDT", "incomeType": "FUNDING_FEE", "income": "0.1", "time": DAY_MS},
    {"symbol": "", "incomeType": "TRANSFER", "income": "500", "time": DAY_MS},
]
ACCOUNT = {"totalWalletBalance": "1001.7", "totalUnrealizedProfit": "-0.5",
           "totalMarginBalance": "1001.2", "availableBalance": "900"}


def test_summarize_income_excludes_transfers_and_adds_open_pnl():
    s = summarize_income(RECORDS, ACCOUNT)
    assert s["net_trading"] == pytest.approx(1.7)
    assert s["net_with_open"] == pytest.approx(1.2)
    assert s["transfers"] == pytest.approx(500)
    assert s["by_symbol"]["ETHUSDT"]["net"] == pytest.approx(2.6)
    assert s["by_symbol"]["SOLUSDT"]["funding"] == pytest.approx(0.1)
    assert "" not in s["by_symbol"]  # la transferencia no es de un símbolo operado
    assert [d["day"] for d in s["per_day"]] == ["2026-10-24", "2026-10-25"]
    assert s["account"]["margin_balance"] == pytest.approx(1001.2)


def test_summarize_income_without_account():
    s = summarize_income([], None)
    assert s["net_trading"] == 0 and s["net_with_open"] is None and s["account"] is None


def test_build_income_summary_paginates_and_caps_days():
    client = AsyncMock()
    page = [{"symbol": "X", "incomeType": "REALIZED_PNL", "income": "1", "time": DAY_MS + i} for i in range(1000)]
    client.get_income_history = AsyncMock(side_effect=[page, RECORDS[:1]])
    client.get_account_info = AsyncMock(return_value=ACCOUNT)

    s = asyncio.run(build_income_summary(client, days=400))

    assert s["period"]["days"] == 90
    assert s["records"] == 1001
    assert client.get_income_history.await_count == 2
    second_start = client.get_income_history.await_args_list[1].kwargs["start_time"]
    assert second_start == DAY_MS + 999 + 1


def test_income_summary_endpoint(client, monkeypatch):
    _income_summary_cache.clear()
    monkeypatch.setattr(grid_service.binance, "get_income_history", AsyncMock(return_value=RECORDS))
    monkeypatch.setattr(grid_service.binance, "get_account_info", AsyncMock(return_value=ACCOUNT))

    r = client.get("/api/v1/account/income-summary?days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["net_trading"] == pytest.approx(1.7)
    assert body["period"]["days"] == 7

    assert client.get("/api/v1/account/income-summary?days=0").status_code == 422
    assert client.get("/api/v1/account/income-summary?days=91").status_code == 422
    _income_summary_cache.clear()
