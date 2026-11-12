"""
Backtest de cobro de funding con posición cubierta: que la cobertura neutralice
el precio, que el funding y los costos se contabilicen bien y que las señales no
usen información del futuro. Todo sintético, sin red.
"""

import pytest

from app.backtest.carry import CarryBacktest, CarryConfig, format_text, spot_symbol, summarize

PF = {"step_size": 0.001, "min_notional": 5}
SF = {"step_size": 0.001, "min_notional": 5.0}
FREE = dict(spot_fee=0.0, perp_fee=0.0, slippage_bps=0.0)


def series(closes, start_day=0, volume=1e8):
    bars, prev = {}, closes[0]
    for i, c in enumerate(closes):
        bars[start_day + i] = (prev, max(prev, c), min(prev, c), c, volume)
        prev = c
    return bars


def market(prices, rate, days=200, basis=0.0):
    """Un símbolo con spot = prices y perpetuo = spot × (1 + basis), funding diario `rate`."""
    closes = prices if isinstance(prices, list) else [prices] * days
    spot = {"AUSDT": series(closes)}
    perp = {"AUSDT": series([c * (1 + basis) for c in closes])}
    funding = {"AUSDT": {d: (rate(d) if callable(rate) else rate) for d in range(len(closes))}}
    return perp, spot, funding


def run(perp, spot, funding, cfg, start=100, end=None):
    end = end or max(perp["AUSDT"]) + 1
    filters = {s: PF for s in perp}
    spot_filters = {spot_symbol(s)[0]: SF for s in perp}
    bt = CarryBacktest(perp, spot, funding, filters, spot_filters, cfg, start, end)
    return bt, bt.run()


def test_spot_symbol_mapping():
    assert spot_symbol("ETHUSDT") == ("ETHUSDT", 1.0)
    assert spot_symbol("1000PEPEUSDT") == ("PEPEUSDT", 1000.0)
    assert spot_symbol("1000000MOGUSDT") == ("MOGUSDT", 1000000.0)


def test_hedge_cancels_price_and_funding_is_the_result():
    # El precio se duplica: con la cobertura el resultado es solo el funding.
    closes = [100.0] * 110 + [100.0 + 2 * i for i in range(1, 51)]
    perp, spot, funding = market(closes, 0.001)          # 0,1 %/día ≈ 36,5 %/año
    cfg = CarryConfig(max_positions=1, rebalance_move=10.0, **FREE)
    _, result = run(perp, spot, funding, cfg)
    t = result.trades[0]
    assert t.entry_day == 101 and t.reason == "END"
    assert t.basis_pnl == pytest.approx(0.0, abs=1e-9)
    assert t.pnl == pytest.approx(t.funding) and t.funding > 0
    # 2/3 del capital en spot (apalancamiento 2 en el perpetuo).
    assert t.notional == pytest.approx(100.0 * 2 / 3, rel=0.01)
    assert result.equity[-1][1] == pytest.approx(100.0 + t.pnl)


def test_entry_day_counts_two_thirds_of_funding_and_short_pays_when_negative():
    perp, spot, funding = market(100.0, 0.0009, days=104)
    cfg = CarryConfig(max_positions=1, **FREE)
    _, result = run(perp, spot, funding, cfg, end=103)     # entra el 101, cierra tras el 102
    t = result.trades[0]
    assert t.funding == pytest.approx(t.notional * 0.0009 * (2 / 3 + 1), rel=1e-6)

    # Con always_on se mantiene aunque la tasa sea negativa: el corto paga.
    perp, spot, funding = market(100.0, -0.0005, days=120)
    _, neg = run(perp, spot, funding, CarryConfig(max_positions=1, always_on=True, **FREE))
    assert neg.trades[0].funding < 0 and neg.equity[-1][1] < 100.0


def test_entry_and_exit_follow_trailing_funding_without_lookahead():
    # Funding alto hasta el día 129, negativo después.
    rate = lambda d: 0.001 if d < 130 else -0.001
    perp, spot, funding = market(100.0, rate, days=200)
    cfg = CarryConfig(max_positions=1, lookback_days=7, min_hold_days=7, **FREE)
    bt, result = run(perp, spot, funding, cfg)
    t = result.trades[0]
    # La media de 7 días se vuelve negativa al cierre del 133 (4 días a −0,1 %) → sale el 134.
    assert bt.trailing_apr("AUSDT", 132) > 0 > bt.trailing_apr("AUSDT", 133)
    assert (t.entry_day, t.exit_day, t.reason) == (101, 134, "SIGNAL")
    assert len(result.trades) == 1                           # no vuelve a entrar con funding negativo

    # Cambiar el futuro no cambia lo ya decidido.
    _, other = run(*market(100.0, lambda d: 0.001 if d < 130 else 0.005, days=200), cfg, end=125)
    _, same = run(perp, spot, funding, cfg, end=125)
    assert other.equity == same.equity


def test_below_entry_threshold_never_enters():
    perp, spot, funding = market(100.0, 0.0001, days=200)    # ≈ 3,65 %/año < 10 %
    _, result = run(perp, spot, funding, CarryConfig(max_positions=1))
    assert result.trades == [] and result.equity[-1][1] == 100.0


def test_costs_basis_and_rebalance():
    perp, spot, funding = market(100.0, 0.001, days=160)
    _, free = run(perp, spot, funding, CarryConfig(max_positions=1, **FREE))
    _, paid = run(perp, spot, funding, CarryConfig(max_positions=1))
    t = paid.trades[0]
    # Ida y vuelta: (0,10 % + 0,05 %) de comisión por lado + slippage en las dos patas.
    assert t.fees == pytest.approx(t.notional * 2 * 0.0015, rel=0.01)
    assert t.basis_pnl < 0                                   # el slippage se ve en la base
    assert paid.equity[-1][1] < free.equity[-1][1]

    # Si el perpetuo entra con prima y converge, la base suma.
    closes = [100.0] * 160
    spot = {"AUSDT": series(closes)}
    perp = {"AUSDT": series([101.0] * 130 + [100.0] * 30)}
    _, conv = run(perp, spot, funding, CarryConfig(max_positions=1, **FREE))
    assert conv.trades[0].basis_pnl == pytest.approx(conv.trades[0].notional / 100.0 * 1.0, rel=0.01)

    # Una subida de +40 % obliga a mover margen y eso cuesta.
    up = [100.0] * 110 + [140.0] * 50
    _, reb = run(*market(up, 0.001), CarryConfig(max_positions=1))
    assert reb.stats["rebalances"] == 1 and reb.trades[0].rebalances == 1


def test_rebalance_resizes_to_target_so_funding_does_not_grow_with_price():
    """Si el precio se multiplica, el nocional vuelve a su objetivo: no hay capital para más."""
    closes = [100.0] * 110 + [100.0 * 1.05 ** i for i in range(1, 41)]      # ×7
    perp, spot, funding = market(closes, 0.001)
    bt, result = run(perp, spot, funding, CarryConfig(max_positions=1, **FREE))
    t = result.trades[0]
    assert t.rebalances >= 5
    # El resultado de precio sigue siendo ~0 (cobertura) y el funding es el de un
    # nocional acotado: como mucho 2/3 del capital × (1 + 30 %) por día.
    assert t.basis_pnl == pytest.approx(0.0, abs=1e-6)
    days = t.exit_day - t.entry_day + 1
    assert t.funding <= 110.0 * (2 / 3) * 1.30 * 0.001 * days
    assert result.equity[-1][1] == pytest.approx(100.0 + t.funding)


def test_min_notional_blocks_small_accounts_and_summary_adds_up():
    perp, spot, funding = market(100.0, 0.001, days=160)
    _, tiny = run(perp, spot, funding, CarryConfig(balance=6.0, max_positions=1))
    assert tiny.trades == [] and tiny.stats["entry_skipped_min_notional"] >= 1

    _, result = run(perp, spot, funding, CarryConfig(max_positions=1))
    s = summarize(result)
    assert s["final_equity"] == pytest.approx(100.0 + s["funding"] + s["basis_pnl"] - s["fees"])
    assert s["invested_days_pct"] > 90
    assert "Funding cobrado" in format_text(s, "test")
