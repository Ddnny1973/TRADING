"""
Tests for build_equity_curve: curva de equity horaria del dashboard.

Antes se agrupaba pnl_snapshots por taken_at, pero cada grid escribe con su
propio timestamp: cada punto era un solo grid y la línea saltaba entre grids.
"""

from datetime import datetime, timedelta

from app.services.dashboard_data import build_equity_curve

H0 = datetime(2026, 10, 1, 0, 0)


def h(n):
    return H0 + timedelta(hours=n)


def snap(hour, grid_id, pnl, balance=4600.0):
    return {"hour": h(hour), "grid_id": grid_id, "total_pnl": pnl, "account_balance": balance}


def test_suma_los_grids_abiertos_en_la_misma_hora():
    curve = build_equity_curve([snap(0, "a", 2.0), snap(0, "b", -1.0)], [], {"a", "b"})
    assert [p["total_pnl"] for p in curve] == [1.0]


def test_arrastra_el_ultimo_valor_de_un_grid_sin_snapshot_en_esa_hora():
    curve = build_equity_curve(
        [snap(0, "a", 2.0), snap(0, "b", 1.0), snap(1, "a", 3.0)], [], {"a", "b"})
    # Hora 1: a=3 (nuevo) + b=1 (arrastrado)
    assert [p["total_pnl"] for p in curve] == [3.0, 4.0]


def test_cierre_pasa_de_abierto_a_acumulado_sin_salto():
    snaps = [snap(0, "a", 5.0), snap(0, "b", 1.0), snap(2, "b", 1.5)]
    closures = [{"grid_id": "a", "closed_at": h(1) + timedelta(minutes=30), "total_pnl": 5.0}]
    curve = build_equity_curve(snaps, closures, {"b"})
    assert [p["total_pnl"] for p in curve] == [6.0, 6.5]
    assert curve[-1]["closed_pnl"] == 5.0
    assert curve[-1]["open_pnl"] == 1.5


def test_cierres_anteriores_al_primer_snapshot_entran_al_acumulado():
    closures = [{"grid_id": "viejo", "closed_at": h(-10), "total_pnl": -3.0}]
    curve = build_equity_curve([snap(0, "a", 1.0)], closures, {"a"})
    assert curve[0]["total_pnl"] == -2.0


def test_cierre_posterior_al_ultimo_snapshot_agrega_punto_final():
    closures = [{"grid_id": "a", "closed_at": h(5), "total_pnl": 4.0}]
    curve = build_equity_curve([snap(0, "a", 3.0)], closures, set())
    assert [p["total_pnl"] for p in curve] == [3.0, 4.0]


def test_grid_terminado_sin_cierre_sale_tras_su_ultimo_snapshot():
    # "huerfano" = re-centrado antes de A1a: no cerró y ya no está RUNNING
    snaps = [snap(0, "huerfano", -7.0), snap(0, "a", 1.0), snap(1, "a", 2.0)]
    curve = build_equity_curve(snaps, [], {"a"})
    assert [p["total_pnl"] for p in curve] == [-6.0, 2.0]


def test_sin_sqlite_conserva_los_huerfanos():
    snaps = [snap(0, "huerfano", -7.0), snap(0, "a", 1.0), snap(1, "a", 2.0)]
    curve = build_equity_curve(snaps, [], None)
    assert [p["total_pnl"] for p in curve] == [-6.0, -5.0]


def test_sin_datos():
    assert build_equity_curve([], [], set()) == []
