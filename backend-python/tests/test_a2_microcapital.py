"""
Tests for A2: perfil microcapital en demo (docs/analisis-bot/05 §9).

- capped_balance: min(balance, BALANCE_CAP_USDT); 0 = sin tope.
- /auto-params dimensiona con el balance limitado y lo avisa en warnings.
- fetch_min_notional: con MIN_NOTIONAL_FROM_MAINNET usa max(testnet, mainnet)
  y sigue con el de testnet si mainnet falla.
- check_daily_drawdown: el umbral del kill-switch sale del balance limitado.
"""

import asyncio
import sqlite3
from decimal import Decimal
from unittest.mock import AsyncMock

from app.auto_params import fetch_min_notional
from app.config_auto_params import capped_balance
from app.core.config import settings
from tests.test_auto_params_veto import _fake_auto_params_result
from tests.test_kill_switch import make_service, memory_db  # noqa: F401 (fixture)


# --- capped_balance ---

def test_capped_balance_sin_tope(monkeypatch):
    monkeypatch.setattr(settings, "BALANCE_CAP_USDT", 0.0)
    assert capped_balance(4630.0) == 4630.0


def test_capped_balance_con_tope(monkeypatch):
    monkeypatch.setattr(settings, "BALANCE_CAP_USDT", 100.0)
    assert capped_balance(4630.0) == 100.0
    # Un balance menor que el tope no se infla
    assert capped_balance(80.0) == 80.0


# --- /auto-params ---

def test_auto_params_usa_balance_limitado(client, monkeypatch):
    monkeypatch.setattr(settings, "BALANCE_CAP_USDT", 100.0)
    seen = {}
    result = _fake_auto_params_result()
    selection = {
        "selected": {"symbol": "BTCUSDT", "score": 1.0, "er": 0.1, "volume_24h_usdt": 5_000_000},
        "top_3": [{"symbol": "BTCUSDT", "score": 1.0, "er": 0.1, "volume_24h_m": 5}] * 3,
        "candidates_evaluated": 50,
        "candidates_passed_filters": 8,
    }

    async def fake_pick_best_pair(**kwargs):
        seen["pick_balance"] = kwargs["balance"]
        return selection

    async def fake_auto_derive_params(symbol, balance, client=None):
        seen["derive_balance"] = balance
        return result

    monkeypatch.setattr("app.main.pick_best_pair", fake_pick_best_pair)
    monkeypatch.setattr("app.main.auto_derive_params", fake_auto_derive_params)

    response = client.get("/auto-params", params={"balance": 5000})
    assert response.status_code == 200
    assert seen["pick_balance"] == 100.0
    assert seen["derive_balance"] == Decimal("100.0")
    assert any("microcapital" in w for w in response.json()["warnings"])


# --- fetch_min_notional ---

def _client_with_testnet_min_notional(value):
    client = AsyncMock()
    client.get_symbol_filters = AsyncMock(return_value={
        "min_notional": Decimal(value), "step_size": Decimal("0.001"), "tick_size": Decimal("0.1"),
    })
    return client


def test_min_notional_toma_el_mayor_de_mainnet(monkeypatch):
    monkeypatch.setattr(settings, "MIN_NOTIONAL_FROM_MAINNET", True)
    monkeypatch.setattr("app.pair_selector.mainnet_min_notionals",
                        AsyncMock(return_value={"BTCUSDT": 100.0}))
    value = asyncio.run(fetch_min_notional(_client_with_testnet_min_notional("50"), "BTCUSDT"))
    assert value == Decimal("100.0")


def test_min_notional_no_baja_si_mainnet_pide_menos(monkeypatch):
    monkeypatch.setattr(settings, "MIN_NOTIONAL_FROM_MAINNET", True)
    monkeypatch.setattr("app.pair_selector.mainnet_min_notionals",
                        AsyncMock(return_value={"BTCUSDT": 5.0}))
    value = asyncio.run(fetch_min_notional(_client_with_testnet_min_notional("50"), "BTCUSDT"))
    assert value == Decimal("50")


def test_min_notional_sigue_con_testnet_si_mainnet_falla(monkeypatch):
    monkeypatch.setattr(settings, "MIN_NOTIONAL_FROM_MAINNET", True)
    monkeypatch.setattr("app.pair_selector.mainnet_min_notionals",
                        AsyncMock(side_effect=ValueError("HTTP 451")))
    value = asyncio.run(fetch_min_notional(_client_with_testnet_min_notional("50"), "BTCUSDT"))
    assert value == Decimal("50")


def test_min_notional_sin_flag_no_consulta_mainnet(monkeypatch):
    monkeypatch.setattr(settings, "MIN_NOTIONAL_FROM_MAINNET", False)
    mainnet = AsyncMock(return_value={"BTCUSDT": 100.0})
    monkeypatch.setattr("app.pair_selector.mainnet_min_notionals", mainnet)
    value = asyncio.run(fetch_min_notional(_client_with_testnet_min_notional("50"), "BTCUSDT"))
    assert value == Decimal("50")
    mainnet.assert_not_called()


# --- kill-switch ---

def test_kill_switch_usa_balance_limitado(memory_db, monkeypatch):  # noqa: F811
    """Con tope 100, una pérdida de 4 USD (4%) dispara aunque la cuenta tenga 1.000."""
    monkeypatch.setattr(settings, "BALANCE_CAP_USDT", 100.0)
    svc = make_service(monkeypatch)
    monkeypatch.setattr(svc.binance, "get_account_balance", AsyncMock(
        return_value={"balances": [{"asset": "USDT", "balance": "1000"}]}))
    conn = sqlite3.connect(memory_db)
    conn.execute(
        "INSERT INTO grid_closures (grid_id, symbol, trigger_condition, total_pnl) "
        "VALUES ('g1', 'BTCUSDT', 'SL', '-4')")
    conn.commit()
    conn.close()

    result = asyncio.run(svc.check_daily_drawdown())
    assert result is not None
    assert result["balance"] == 100.0
