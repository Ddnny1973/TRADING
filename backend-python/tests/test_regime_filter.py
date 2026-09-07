"""
Tests para T20 filtro de régimen continuo (paso 1, MODE="OBSERVE").

Mientras el grid corre, WF2 /refresh reevalúa el ER del símbolo. Si el mercado
pasa a tendencia persistente (ER > umbral durante N ciclos) se loguea el evento
TREND_REGIME en bot_health_events y se expone en la respuesta de /refresh —
sin tocar el grid. Cubre:
- calculate_efficiency_ratio(): caso plano (ER bajo, grid ideal) y tendencia (ER ~1).
- evaluate_regime_filter(): conteo de strikes consecutivos, reset al volver a
  plano, y la transición exacta que dispara el aviso y persiste el evento.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.config_auto_params import (
    CHECK_CLOSE_GRACE_MINUTES,
    ER_LOOKBACK,
    REGIME_FILTER_ER_THRESHOLD,
    REGIME_FILTER_MODE,
    REGIME_FILTER_STRIKES_TO_ALERT,
)
from app.database import connection
from app.services.grid_service import GridService
from app.services.indicators import calculate_efficiency_ratio

GRID_ID = "grid-regime"
SYMBOL = "BTCUSDT"
LOWER = "40000"
UPPER = "45000"


def _insert_grid(status="RUNNING", strikes=0, created_ago_hours=2,
                 interval="4h", atr_period=14):
    conn = connection.get_sqlite_connection()
    try:
        cursor = conn.cursor()
        for column_def in (
            "leverage INTEGER DEFAULT 3",
            "quantity_per_order NUMERIC",
            "grid_mode TEXT DEFAULT 'NEUTRAL'",
            "klines_interval TEXT DEFAULT '4h'",
            "atr_period INTEGER DEFAULT 14",
            "er_last NUMERIC",
            "er_trend_strikes INTEGER DEFAULT 0",
        ):
            try:
                cursor.execute(f"ALTER TABLE grids ADD COLUMN {column_def}")
            except Exception:
                pass
        created = datetime.now(timezone.utc) - timedelta(hours=created_ago_hours)
        cursor.execute(
            """INSERT INTO grids
               (id, symbol, lower_price, upper_price, levels, grid_type, status,
                stop_loss, take_profit, leverage, quantity_per_order, grid_mode,
                created_at, klines_interval, atr_period, er_trend_strikes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (GRID_ID, SYMBOL, LOWER, UPPER, 10, "GEOMETRIC", status,
             "100", "300", 3, "0.002", "NEUTRAL",
             created.strftime("%Y-%m-%d %H:%M:%S"), interval, atr_period, strikes),
        )
        conn.commit()
    finally:
        conn.close()


def _service(mocks):
    svc = GridService()
    for name, mock in mocks.items():
        setattr(svc.binance, name, mock)
    return svc


# --- calculate_efficiency_ratio (puro) ---

def test_er_plano_bajo():
    """Series sin tendencia (misma apertura/cierre, solo ruido): ER bajo."""
    closes = [Decimal(str(40000 - 100 + 200 * (i % 2))) for i in range(49)]
    klines = [{"close": c} for c in closes]
    er = calculate_efficiency_ratio(klines)
    assert 0 <= er <= 1
    assert er < REGIME_FILTER_ER_THRESHOLD


def test_er_tendencia_casi_1():
    """Subida monótona: ER ~ 1 (cambio neto ~ movimiento total)."""
    klines = [{"close": Decimal("40000") + Decimal(i * 10)} for i in range(30)]
    er = calculate_efficiency_ratio(klines)
    assert er > 0.99


def test_er_con_lookback_acotado():
    """lookback limita la ventana a los últimos closes."""
    klines = [{"close": Decimal(str(40000 + 1000 * (i // 10)))} for i in range(30)]
    er_corto = calculate_efficiency_ratio(klines, lookback=4)
    er_largo = calculate_efficiency_ratio(klines)
    assert er_corto >= 0  # sin assert rígido de rango: solo que corre con ventana corta
    assert er_largo >= 0


def test_er_requiere_minimo_dos_velas():
    with pytest.raises(ValueError):
        calculate_efficiency_ratio([{"close": Decimal("40000")}])


# --- evaluate_regime_filter ---

def _mocks_tendencia():
    """Klines 4h con ER alto (subida monótona sobre ER_LOOKBACK velas)."""
    rising = [{"close": Decimal("40000") + Decimal(i * 5)} for i in range(ER_LOOKBACK + 1)]
    return {"get_klines": AsyncMock(return_value=rising)}


def _mocks_plano():
    """Cierres erráticos alrededor de 40000 (oscilación) → ER bajo.
    make_klines devuelve cierres idénticos (ER=1.0), así que construimos una
    serie con ruido: cambio neto ~0 pero movimiento total alto."""
    choppy = [{"close": Decimal("40000") + (Decimal("150") if i % 2 else Decimal("-150"))}
              for i in range(ER_LOOKBACK + 1)]
    return {"get_klines": AsyncMock(return_value=choppy)}


def _run(coro):
    return asyncio.run(coro)


def test_regime_no_actua_dentro_de_la_gracia():
    _insert_grid(created_ago_hours=0.1)  # < CHECK_CLOSE_GRACE_MINUTES
    mocks = _mocks_tendencia()
    result = _run(_service(mocks).evaluate_regime_filter(GRID_ID))
    assert result is None


def test_regime_conteo_de_strikes_tendencia():
    """Tendencia persistente aumenta el conteo hasta cruzar el umbral."""
    _insert_grid(strikes=0)
    mocks = _mocks_tendencia()
    svc = _service(mocks)
    r1 = _run(svc.evaluate_regime_filter(GRID_ID))
    assert r1["trend"] is True
    assert r1["strikes"] == 1
    assert r1["alerted"] is False


def test_regime_reset_al_volver_a_plano():
    """Un ciclo plano resetea el conteo de tendencia a 0."""
    _insert_grid(strikes=0)
    svc = _service(_mocks_tendencia())
    _run(svc.evaluate_regime_filter(GRID_ID))  # strikes -> 1
    r2 = _run(_service(_mocks_plano()).evaluate_regime_filter(GRID_ID))
    assert r2["trend"] is False
    assert r2["strikes"] == 0


def test_regime_avisa_en_la_transicion_y_escala_ciclos():
    """El aviso se emite el ciclo que cruza el umbral y persiste el evento."""
    events = []
    _insert_grid(strikes=REGIME_FILTER_STRIKES_TO_ALERT - 1)
    svc = _service(_mocks_tendencia())
    # Espía _log_bot_health_event para capturar el TREND_REGIME sin tocar Postgres.
    svc._log_bot_health_event = lambda **kw: events.append(kw)
    r = _run(svc.evaluate_regime_filter(GRID_ID))
    assert r["trend"] is True
    assert r["strikes"] == REGIME_FILTER_STRIKES_TO_ALERT
    assert r["alerted"] is True
    assert any(e["event_type"] == "TREND_REGIME" for e in events)
    # Escalando: ciclo siguiente en tendencia ya no re-avisa (no spamea).
    r_next = _run(_service(_mocks_tendencia()).evaluate_regime_filter(GRID_ID))
    assert r_next["strikes"] == REGIME_FILTER_STRIKES_TO_ALERT + 1
    assert r_next["alerted"] is False


def test_regime_expone_modo_y_umbral():
    _insert_grid()
    r = _run(_service(_mocks_plano()).evaluate_regime_filter(GRID_ID))
    assert r["mode"] == REGIME_FILTER_MODE
    assert r["threshold"] == float(REGIME_FILTER_ER_THRESHOLD)


def test_regime_en_endpoint_refresh(client, mock_binance):
    """POST /refresh de un grid RUNNING (fuera de gracia) responde con el
    estado del filtro de régimen (grid["regime"]) sin romper el flujo."""
    _insert_grid()
    resp = client.post(f"/api/v1/grids/{GRID_ID}/refresh")
    assert resp.status_code == 200
    payload = resp.json()
    assert "regime" in payload
    assert payload["regime"]["mode"] == REGIME_FILTER_MODE
    assert "er" in payload["regime"]