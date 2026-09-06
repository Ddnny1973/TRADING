"""
T9: el ROI del período se calcula sobre el PnL de la estrategia y el balance
inicial, NO sobre la variación del balance de la billetera (las recargas del
faucet de testnet y el funding la inflan sin ser resultado de la estrategia).
Tests del helper puro compute_roi (sin Postgres, sin mock de red).
"""

from app.services.dashboard_data import compute_roi


def test_roi_mide_estrategia_no_billetera():
    # Billetera +10% por recarga del faucet, pero la estrategia rindió -0.8%.
    # El ROI del período DEBE ser -0.8% (honesto); la variación de billetera
    # queda aparte como diagnóstico.
    roi, balance_roi = compute_roi(strategy_pnl=-8.0, first_balance=1000.0, last_balance=1100.0)
    assert roi == -0.8
    assert balance_roi == 10.0


def test_roi_positivo_coincide_con_billetera_sin_faucet():
    roi, balance_roi = compute_roi(strategy_pnl=25.0, first_balance=1000.0, last_balance=1025.0)
    assert roi == 2.5
    assert balance_roi == 2.5


def test_roi_sin_balance_es_none():
    assert compute_roi(strategy_pnl=5.0, first_balance=None, last_balance=None) == (None, None)


def test_roi_zero_balance_no_divide_por_cero():
    assert compute_roi(strategy_pnl=-8.0, first_balance=0.0, last_balance=0.0) == (None, None)


def test_roi_sin_ultimo_balance_deja_billetera_en_none():
    roi, balance_roi = compute_roi(strategy_pnl=5.0, first_balance=1000.0, last_balance=None)
    assert roi == 0.5
    assert balance_roi is None