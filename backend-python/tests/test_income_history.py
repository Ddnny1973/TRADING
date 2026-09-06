"""
T22 — get_income_history(): cliente Binance para /fapi/v1/income (historial de
funding/ingresos). Envía los parámetros firmados correctos y devuelve lista o
None si la llamada falla (sin red real, _signed_request mockeado).
"""

import asyncio
from unittest.mock import AsyncMock

from app.services.binance_client import BinanceClient


def test_income_history_devuelve_lista_y_parametros():
    client = BinanceClient()
    esperado = [
        {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "income": "-0.0432", "time": 1000},
    ]
    signed = AsyncMock(return_value=list(esperado))
    client._signed_request = signed  # type: ignore[assignment]

    result = asyncio.run(
        client.get_income_history(income_type="FUNDING_FEE", start_time=123, limit=1000)
    )

    assert result == esperado
    args, kwargs = signed.call_args
    assert args[0] == "GET"
    assert args[1] == "/fapi/v1/income"
    params = kwargs["params"]
    assert params["incomeType"] == "FUNDING_FEE"
    assert params["startTime"] == 123
    assert params["limit"] == 1000


def test_income_history_sin_filtros_no_envia_income_type():
    client = BinanceClient()
    signed = AsyncMock(return_value=[])
    client._signed_request = signed  # type: ignore[assignment]

    asyncio.run(client.get_income_history())

    params = signed.call_args.kwargs["params"]
    assert "incomeType" not in params
    assert "startTime" not in params


def test_income_history_none_cuando_falla():
    client = BinanceClient()
    client._signed_request = AsyncMock(return_value=None)  # type: ignore[assignment]

    result = asyncio.run(client.get_income_history())
    assert result is None


def test_income_history_no_devuelve_dict_como_lista():
    client = BinanceClient()
    client._signed_request = AsyncMock(return_value={"algo": "raro"})  # type: ignore[assignment]

    result = asyncio.run(client.get_income_history())
    assert result is None