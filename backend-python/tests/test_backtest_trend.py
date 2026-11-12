"""
Backtest de seguimiento de tendencia: reglas de entrada/salida, tamaño por
riesgo, costos y que nunca use información del futuro. Todo sintético, sin red.
"""

from decimal import Decimal

import pytest

from app.backtest.trend import TrendBacktest, TrendConfig, summarize, format_text

FILTERS = {"tick_size": Decimal("0.01"), "step_size": Decimal("0.001"), "min_notional": Decimal("5")}


def flat_then(prices, start_day=0, flat_days=120, flat=100.0, spread=1.0, volume=1e8):
    """Velas diarias: `flat_days` planas en `flat` (rango ±spread) y luego los cierres dados."""
    bars = {}
    day = start_day
    for _ in range(flat_days):
        bars[day] = (flat, flat + spread, flat - spread, flat, volume)
        day += 1
    prev = flat
    for close in prices:
        bars[day] = (prev, max(prev, close) + spread, min(prev, close) - spread, close, volume)
        prev = close
        day += 1
    return bars


def run(bars_by_symbol, cfg=None, start=100, end=None, funding=None):
    end = end or max(max(b) for b in bars_by_symbol.values()) + 1
    bt = TrendBacktest(bars_by_symbol, {s: FILTERS for s in bars_by_symbol}, funding or {},
                       cfg or TrendConfig(), start, end)
    return bt, bt.run()


def test_breakout_enters_next_open_and_sizes_by_risk():
    # Día 120: cierre 105 > máximo previo (101) → largo a la apertura del 121 (105).
    bars = {"UPUSDT": flat_then([105, 110, 115, 120, 125])}
    cfg = TrendConfig(slippage_bps=0.0, taker_fee=0.0, use_funding=False)
    bt, result = run(bars, cfg)
    trade = result.trades[0]
    assert (trade.side, trade.entry_day, trade.entry_price) == (1, 121, 105.0)
    # ATR al día 120: 19 rangos de 2 y uno de 6 (105+1 − (100−1)... rango 99..106 = 7)
    atr = bt._atr("UPUSDT", 120)
    stop_dist = 2.0 * atr
    assert trade.qty == pytest.approx(0.01 * 100.0 / stop_dist, abs=0.001)   # arriesga 1 % del capital
    assert trade.reason == "END" and trade.pnl > 0
    assert result.equity[-1][1] == pytest.approx(100.0 + trade.pnl)


def test_no_lookahead_signal_uses_only_closed_days():
    """Cambiar el futuro no cambia lo decidido hasta hoy."""
    a = {"XUSDT": flat_then([105, 110, 115, 120, 125])}
    b = {"XUSDT": flat_then([105, 110, 60, 50, 40])}
    _, ra = run(a, end=123)
    _, rb = run(b, end=123)
    assert [(t.entry_day, t.entry_price, t.qty) for t in ra.trades] == \
           [(t.entry_day, t.entry_price, t.qty) for t in rb.trades]
    assert ra.equity[:2] == rb.equity[:2]


def test_stop_exits_at_stop_or_at_gap_open():
    cfg = TrendConfig(slippage_bps=0.0, taker_fee=0.0, use_funding=False)
    # Entra en 105 (día 121). El día 122 cae fuerte dentro del día: sale al stop.
    bt, result = run({"XUSDT": flat_then([105, 106, 90, 90])}, cfg)
    t = result.trades[0]
    stop = 105.0 - 2.0 * bt._atr("XUSDT", 120)
    assert t.reason == "STOP" and t.exit_price == pytest.approx(stop)
    assert t.pnl == pytest.approx(-0.01 * 100.0, rel=0.02)        # pierde ≈ el 1 % arriesgado

    # Si el día ABRE por debajo del stop, sale a la apertura (pierde más del 1 %).
    bars = flat_then([105, 106])
    bars[max(bars) + 1] = (80.0, 81.0, 79.0, 80.0, 1e8)
    _, gap = run({"XUSDT": bars}, cfg)
    g = gap.trades[0]
    assert g.reason == "STOP" and g.exit_price == 80.0 and g.pnl < t.pnl


def test_channel_exit_and_short_side():
    # Stop muy lejano para que solo actúe el canal; más riesgo para superar el nocional mínimo.
    cfg = TrendConfig(slippage_bps=0.0, taker_fee=0.0, use_funding=False, stop_atr=50.0, risk_pct=0.2)
    # Sube 30 días y luego cae bajo el mínimo de 10 días → salida por canal al día siguiente.
    up = [100 + 2 * i for i in range(1, 31)]
    down = [up[-1] - 8 * i for i in range(1, 6)]
    _, result = run({"XUSDT": flat_then(up + down)}, cfg)
    first = result.trades[0]
    assert first.side == 1 and first.reason == "CHANNEL" and first.pnl > 0

    # Un mercado que solo cae abre un corto; con --long-only no opera.
    falling = {"DUSDT": flat_then([95, 90, 85, 80, 75])}
    _, short = run(falling, cfg)
    assert short.trades[0].side == -1 and short.trades[0].pnl > 0
    _, none = run(falling, TrendConfig(allow_short=False))
    assert none.trades == []


def test_costs_and_funding_reduce_pnl():
    bars = {"UPUSDT": flat_then([105, 110, 115, 120, 125])}
    free = TrendConfig(slippage_bps=0.0, taker_fee=0.0, use_funding=False)
    _, a = run(bars, free)
    _, b = run(bars, TrendConfig(use_funding=False))
    assert b.trades[0].pnl < a.trades[0].pnl and b.trades[0].fees > 0

    # Funding positivo: el largo paga.
    funding = {"UPUSDT": {d: 0.001 for d in range(121, 126)}}
    _, c = run(bars, TrendConfig(slippage_bps=0.0, taker_fee=0.0), funding=funding)
    assert c.trades[0].funding < 0
    assert c.trades[0].pnl == pytest.approx(a.trades[0].pnl + c.trades[0].funding)


def test_min_notional_and_leverage_caps():
    bars = {"UPUSDT": flat_then([105, 110, 115])}
    # Con 10 USDT, el 1 % de riesgo da un nocional menor al mínimo: no entra.
    _, tiny = run(bars, TrendConfig(balance=10.0))
    assert tiny.trades == [] and tiny.stats["entry_skipped_min_notional"] >= 1
    # El nocional de una posición nunca supera max_position_pct del capital.
    _, capped = run(bars, TrendConfig(risk_pct=0.5, max_position_pct=0.3, slippage_bps=0.0))
    t = capped.trades[0]
    assert t.qty * t.entry_price <= 0.3 * 100.0 + 1e-6


def test_universe_is_ranked_by_past_volume_and_needs_history():
    big = flat_then([], flat_days=200, volume=5e8)
    small = flat_then([], flat_days=200, volume=1e6)
    new = flat_then([], start_day=150, flat_days=50, volume=9e9)      # mucho volumen, poca historia
    bt = TrendBacktest({"BIGUSDT": big, "SMALLUSDT": small, "NEWUSDT": new, "USDCUSDT": big},
                       {}, {}, TrendConfig(universe_size=1), 100, 200)
    assert bt.universe(190) == ["BIGUSDT"]                             # NEW no tiene 90 días; USDC excluido
    assert TrendBacktest({"BIGUSDT": big, "SMALLUSDT": small}, {}, {},
                         TrendConfig(universe_size=5), 100, 200).universe(190) == ["BIGUSDT", "SMALLUSDT"]


def test_lateral_market_does_not_trade_and_summary_formats():
    bars = {"FLATUSDT": flat_then([], flat_days=300)}
    _, result = run(bars)
    assert result.trades == []
    summary = summarize(result)
    assert summary["total_return_pct"] == 0 and summary["max_drawdown_pct"] == 0
    assert "Capital final" in format_text(summary, "test")


def test_summary_accounting_adds_up():
    up = [100 + 2 * i for i in range(1, 31)]
    down = [up[-1] - 8 * i for i in range(1, 12)]
    _, result = run({"AUSDT": flat_then(up + down), "BUSDT": flat_then(down[:5] + up)})
    s = summarize(result)
    assert s["final_equity"] == pytest.approx(100.0 + sum(t.pnl for t in result.trades))
    assert s["pnl_long"] + s["pnl_short"] == pytest.approx(sum(t.pnl for t in result.trades))
    assert 0 <= s["max_drawdown_pct"] < 100
