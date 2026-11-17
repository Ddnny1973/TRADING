"""
Funding extremo como señal: dirección, umbral, permanencia, controles (invertido y
desfasado), ausencia de información del futuro y funding de la entrada. Sintético,
sin red.
"""

from decimal import Decimal

import pytest

from app.backtest.fundsig import FundingSignalBacktest, FundingSignalConfig
from app.backtest.trend import TrendBacktest, TrendConfig

FILTERS = {"tick_size": Decimal("0.01"), "step_size": Decimal("0.001"), "min_notional": Decimal("5")}
FREE = dict(slippage_bps=0.0, taker_fee=0.0)


def flat(days=200, price=100.0, spread=1.0, volume=1e8):
    return {d: (price, price + spread, price - spread, price, volume) for d in range(days)}


def run(bars, funding, cfg=None, start=100, end=None):
    end = end or max(max(b) for b in bars.values()) + 1
    cfg = cfg or FundingSignalConfig(**FREE)
    bt = FundingSignalBacktest(bars, {s: FILTERS for s in bars}, funding, cfg, start, end)
    return bt, bt.run()


def rate_from(day, high, low=0.0):
    """Funding diario: `high` desde `day`, `low` antes (0,0015 ≈ 55 %/año; es la suma de 3 cobros)."""
    return lambda d: high if d >= day else low


def fund(symbol, fn, days=200):
    return {symbol: {d: fn(d) for d in range(days)}}


def test_high_funding_opens_short_next_open_and_exits_after_hold_days():
    bars = {"AUSDT": flat()}
    funding = fund("AUSDT", rate_from(120, 0.0015))             # > 50 %/año desde el día 120
    _, result = run(bars, funding, FundingSignalConfig(hold_days=5, risk_pct=0.2, **FREE))
    t = result.trades[0]
    # La media de 3 días supera el umbral al cierre del 122 → entra a la apertura del 123.
    assert (t.side, t.entry_day, t.exit_day, t.reason) == (-1, 123, 128, "TIME")
    assert t.funding > 0                                         # el corto cobra con tasa positiva
    assert t.pnl == pytest.approx(t.funding)                     # precio plano, sin costos


def test_negative_funding_opens_long_and_pays_nothing_extra():
    bars = {"AUSDT": flat()}
    funding = fund("AUSDT", rate_from(120, -0.0015))
    _, result = run(bars, funding, FundingSignalConfig(risk_pct=0.2, **FREE))
    t = result.trades[0]
    assert t.side == 1 and t.funding > 0                         # el largo cobra con tasa negativa
    _, no_long = run(bars, funding, FundingSignalConfig(risk_pct=0.2, allow_long=False, **FREE))
    assert no_long.trades == []


def test_below_threshold_never_trades_and_threshold_is_configurable():
    bars = {"AUSDT": flat()}
    funding = fund("AUSDT", lambda d: 0.0005)                    # ≈ 18 %/año
    _, none = run(bars, funding)
    assert none.trades == []
    _, some = run(bars, funding, FundingSignalConfig(entry_apr=0.1, risk_pct=0.2, **FREE))
    assert some.trades and some.trades[0].side == -1


def test_entry_day_funding_counts_two_thirds():
    bars = {"AUSDT": flat()}
    funding = fund("AUSDT", lambda d: 0.0015)
    cfg = FundingSignalConfig(hold_days=2, risk_pct=0.2, **FREE)
    _, two_thirds = run(bars, funding, cfg)
    _, full = run(bars, funding, FundingSignalConfig(hold_days=2, risk_pct=0.2, entry_funding_share=1.0, **FREE))
    t, f = two_thirds.trades[0], full.trades[0]
    per_day = t.qty * 100.0 * 0.0015
    assert f.funding - t.funding == pytest.approx(per_day / 3.0, rel=1e-6)
    assert t.funding == pytest.approx(per_day * (2 / 3 + 1.0), rel=1e-6)


def test_no_lookahead_future_funding_does_not_change_past_decisions():
    bars = {"AUSDT": flat()}
    a = fund("AUSDT", lambda d: 0.0015 if d < 130 else 0.0)
    b = fund("AUSDT", lambda d: 0.0015 if d < 130 else -0.01)
    _, ra = run(bars, a, end=130)
    _, rb = run(bars, b, end=130)
    assert ra.equity == rb.equity
    assert [(t.entry_day, t.qty) for t in ra.trades] == [(t.entry_day, t.qty) for t in rb.trades]


def test_invert_flips_the_side_and_shift_uses_other_moment():
    bars = {"AUSDT": flat()}
    funding = fund("AUSDT", rate_from(120, 0.0015))
    _, inv = run(bars, funding, FundingSignalConfig(invert=True, risk_pct=0.2, **FREE))
    assert inv.trades[0].side == 1
    assert inv.trades[0].funding < 0                             # a favor de la multitud: paga

    # Con el funding desplazado 40 días (dando la vuelta en [100, 200)), el cambio ocurre antes.
    shifted = FundingSignalConfig(shift_days=40, span=(100, 200), risk_pct=0.2, **FREE)
    _, sh = run(bars, funding, shifted)
    assert sh.trades[0].entry_day < 123


def test_stop_closes_before_hold_period():
    # El precio sube con fuerza el día 124: el corto toca su stop antes de cumplir los 5 días.
    bars = {"AUSDT": flat()}
    for d in range(124, 200):
        bars["AUSDT"][d] = (130.0, 131.0, 129.0, 130.0, 1e8)
    funding = fund("AUSDT", rate_from(120, 0.0015))
    _, result = run(bars, funding, FundingSignalConfig(hold_days=10, risk_pct=0.2, **FREE))
    t = result.trades[0]
    assert t.reason == "STOP" and t.exit_day == 124 and t.pnl < 0


def test_top_k_limits_new_entries_per_side_and_day():
    syms = {f"S{k}USDT": flat(volume=1e8 + k) for k in range(6)}
    funding = {s: {d: (0.0015 + 0.0001 * k if d >= 120 else 0.0) for d in range(200)}
               for k, s in enumerate(syms)}
    _, result = run(syms, funding, FundingSignalConfig(top_k=2, hold_days=3, risk_pct=0.05, **FREE))
    first_day = min(t.entry_day for t in result.trades)
    assert sum(1 for t in result.trades if t.entry_day == first_day) == 2
    assert all(t.side == -1 for t in result.trades)


def test_trend_engine_is_unchanged_by_the_hook():
    """La base sigue operando con su propia señal (canal) y etiqueta CHANNEL."""
    up = [100.0 + 2 * i for i in range(1, 31)]
    bars = {"AUSDT": {**flat(120)}}
    prev = 100.0
    for i, c in enumerate(up + [up[-1] - 8 * k for k in range(1, 6)]):
        bars["AUSDT"][120 + i] = (prev, max(prev, c) + 1, min(prev, c) - 1, c, 1e8)
        prev = c
    bt = TrendBacktest(bars, {"AUSDT": FILTERS}, {}, TrendConfig(stop_atr=50.0, risk_pct=0.2, **FREE),
                       100, 160)
    trades = bt.run().trades
    assert trades and trades[0].reason == "CHANNEL"
