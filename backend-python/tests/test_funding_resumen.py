"""
T22 — resumir_income() del script de cuantificación de funding: agrupa
registros de /fapi/v1/income por incomeType y por símbolo para FUNDING_FEE.
Puro, sin red ni DB.
"""

from app.scripts.funding_resumen import resumir_income

REGISTROS = [
    {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "income": "-0.0432"},
    {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "income": "-0.0105"},
    {"symbol": "ETHUSDT", "incomeType": "FUNDING_FEE", "income": "0.0021"},
    {"symbol": "BTCUSDT", "incomeType": "COMMISSION", "income": "-0.0008"},
    {"symbol": "BTCUSDT", "incomeType": "TRANSFER", "income": "500.0000"},
    {"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "1.2500"},
]


def test_agrupa_por_tipo_y_funding_por_simbolo():
    por_tipo, funding_simbolo = resumir_income(REGISTROS)

    assert por_tipo["FUNDING_FEE"] == -0.0432 - 0.0105 + 0.0021
    assert por_tipo["COMMISSION"] == -0.0008
    assert por_tipo["TRANSFER"] == 500.0
    assert por_tipo["REALIZED_PNL"] == 1.25

    assert funding_simbolo["BTCUSDT"] == -0.0432 - 0.0105
    assert funding_simbolo["ETHUSDT"] == 0.0021


def test_income_ausente_se_suma_como_cero():
    por_tipo, funding_simbolo = resumir_income([])
    assert por_tipo == {}
    assert funding_simbolo == {}


def test_valores_no_numericos_tolerados():
    sucios = [
        {"symbol": "X", "incomeType": "FUNDING_FEE", "income": None},
        {"symbol": "X", "incomeType": "FUNDING_FEE", "income": "-0.5"},
    ]
    _, funding_simbolo = resumir_income(sucios)
    assert funding_simbolo["X"] == -0.5