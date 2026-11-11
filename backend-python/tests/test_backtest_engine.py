"""
Backtester (N6): mercado histórico sin mirar el futuro y motor de punta a punta
sobre un mercado sintético (sin red).
"""

import asyncio
import math
from decimal import Decimal

import pytest

from app import auto_params
from app.backtest.data import BASE_MS, Bars, HistClient, HistoricalMarket
from app.backtest.engine import Backtest, policy_overrides
from app.backtest.grid_sim import SimConfig
from app.backtest.report import format_text, summarize
from app.core.config import settings

DAY = 24 * 60 * 60 * 1000
FILTERS = {"tick_size": Decimal("0.01"), "step_size": Decimal("0.01"), "min_notional": Decimal("5")}


def synthetic_bars(days: int, base: float, period: float, amplitude: float, phase: float = 0.0,
                   drift_per_bar: float = 0.0) -> Bars:
    """Precio = base · (1 + amplitud·sin) con deriva opcional; volumen alto."""
    rows = []
    prev = base
    for i in range(days * 288):
        close = base * (1 + amplitude * math.sin(i / period + phase)) * (1 + drift_per_bar) ** i
        high, low = max(prev, close) * 1.0005, min(prev, close) * 0.9995
        rows.append((i * BASE_MS, prev, high, low, close, 400_000.0))
        prev = close
    return Bars(rows)


# -------------------------------------------------------------------- mercado

def test_klines_asof_does_not_look_ahead():
    bars = synthetic_bars(3, 100.0, 40.0, 0.02)
    market = HistoricalMarket({"AUSDT": bars}, {"AUSDT": FILTERS})
    now = 2 * DAY + 7 * BASE_MS            # 7 velas de 5m dentro de la hora en curso
    klines = market.klines_asof("AUSDT", "1h", 5, now)
    assert len(klines) == 5

    i = bars.index_at(now)
    assert bars.t[i] == now - BASE_MS
    start = i - 6                          # la hora empezó 7 velas atrás
    forming = klines[-1]
    assert float(forming["close"]) == bars.c[i]
    assert float(forming["open"]) == bars.o[start]
    assert float(forming["high"]) == max(bars.h[start:i + 1])
    assert float(forming["low"]) == min(bars.l[start:i + 1])

    closed = klines[-2]                    # la hora anterior, completa
    assert float(closed["high"]) == max(bars.h[start - 12:start])
    assert float(closed["close"]) == bars.c[start - 1]

    # Cambiar el futuro no altera lo que se ve hoy.
    bars.h[i + 1] *= 2
    assert market.klines_asof("AUSDT", "1h", 5, now)[-1] == forming


def test_hist_client_serves_auto_derive_params():
    bars = synthetic_bars(70, 100.0, 40.0, 0.03)
    market = HistoricalMarket({"AUSDT": bars}, {"AUSDT": FILTERS})
    client = HistClient(market)
    client.now_ms = 65 * DAY
    cfg = SimConfig()
    with policy_overrides(cfg):
        result = asyncio.run(auto_params.auto_derive_params("AUSDT", Decimal("100"), client=client))
    assert result["grid_viable"] is True
    p = result["params"]
    assert p["lower_price"] < result["current_price"] < p["upper_price"]
    assert result["current_price"] == pytest.approx(market.price("AUSDT", client.now_ms))
    # 25 % de 100 USDT de margen como máximo (perfil A2)
    margin = p["levels"] * p["quantity_per_order"] * result["current_price"] / p["leverage"]
    assert margin <= 25.0 + 1e-6


def test_policy_overrides_are_restored():
    before = (auto_params.MAX_RISK_PCT, auto_params.GRID_STOP_LOSS_PCT_OF_BALANCE,
              auto_params.ER_MAX_TRADEABLE, settings.MIN_NOTIONAL_FROM_MAINNET)
    with policy_overrides(SimConfig(max_risk_pct=0.5, stop_loss_pct=0.05, er_max_tradeable=0.2)):
        assert auto_params.MAX_RISK_PCT == Decimal("0.5")
        assert auto_params.GRID_STOP_LOSS_PCT_OF_BALANCE == Decimal("0.05")
        assert auto_params.ER_MAX_TRADEABLE == Decimal("0.2")
        assert settings.MIN_NOTIONAL_FROM_MAINNET is False
    assert before == (auto_params.MAX_RISK_PCT, auto_params.GRID_STOP_LOSS_PCT_OF_BALANCE,
                      auto_params.ER_MAX_TRADEABLE, settings.MIN_NOTIONAL_FROM_MAINNET)


# ---------------------------------------------------------------------- motor

def run_backtest(bars_by_symbol, cfg=None, days=20, warmup=55):
    market = HistoricalMarket(bars_by_symbol, {s: FILTERS for s in bars_by_symbol})
    bt = Backtest(market, cfg or SimConfig(), list(bars_by_symbol), warmup * DAY, (warmup + days) * DAY)
    return asyncio.run(bt.run())


def lateral_market(n=6, days=75):
    return {f"S{k}USDT": synthetic_bars(days, 50.0 + 10 * k, 30.0 + 7 * k, 0.03, phase=k)
            for k in range(n)}


def test_lateral_market_harvests_cycles_and_accounting_is_consistent():
    result = run_backtest(lateral_market())
    summary = summarize(result)

    assert result.stats["grids_launched"] >= 2
    assert summary["totals"]["cycles"] > 20
    assert summary["totals"]["cycles_net"] > 0
    # Nunca más grids simultáneos que el tope, ni dos sobre el mismo símbolo.
    events = sorted([(r.opened_ms, 1) for r in result.records] + [(r.closed_ms, -1) for r in result.records
                                                                  if r.trigger != "OPEN_AT_END"],
                    key=lambda e: (e[0], e[1]))
    live = peak = 0
    for _, delta in events:
        live += delta
        peak = max(peak, live)
    assert peak <= 2
    # El total de los grids coincide con el último punto de la curva de capital.
    assert summary["totals"]["true_pnl"] == pytest.approx(result.equity[-1][1], abs=1e-6)
    # closure_drag es, por definición, lo que separa la cosecha del resultado.
    t = summary["totals"]
    assert t["cycles_net"] + t["closure_drag"] == pytest.approx(t["true_pnl"])
    assert "Resultado real" in format_text(summary, "test")


def test_backtest_is_deterministic():
    a = summarize(run_backtest(lateral_market()))
    b = summarize(run_backtest(lateral_market()))
    assert a["totals"] == b["totals"]


def test_trending_universe_launches_nothing():
    """Con todo el universo en tendencia limpia (ER≈1) la puerta no deja lanzar."""
    bars = {f"T{k}USDT": synthetic_bars(75, 50.0, 30.0, 0.0, drift_per_bar=0.00002 * (k + 1))
            for k in range(6)}
    result = run_backtest(bars, days=5)
    assert result.stats.get("grids_launched", 0) == 0
    assert result.records == []


def test_fewer_than_five_candidates_is_vetoed():
    result = run_backtest(lateral_market(n=4), days=5)
    assert result.stats.get("grids_launched", 0) == 0
    assert result.stats.get("launch_vetoed", 0) > 0


def test_tighter_stop_loss_closes_more_grids():
    """El perfil es un parámetro: cambiar el SL cambia el resultado."""
    wide = summarize(run_backtest(lateral_market(), SimConfig(stop_loss_pct=0.05)))
    tight = summarize(run_backtest(lateral_market(), SimConfig(stop_loss_pct=0.001)))
    sl = lambda s: s["by_trigger"].get("STOP_LOSS", {"grids": 0})["grids"]
    assert sl(tight) > sl(wide)
