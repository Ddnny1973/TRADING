"""
Unit tests for the deterministic, non-networked pieces of the Binance
integration: kline parsing and HMAC signing. The HTTP-calling methods
(get_mark_price, place_limit_order, etc.) are exercised indirectly through
the mocked-Binance endpoint tests in test_api_grids.py rather than here,
since unit-testing them directly would require mocking aiohttp itself.
"""

from decimal import Decimal

from app.core.security import BinanceSecurityManager
from app.services.binance_client import BinanceClient

RAW_KLINE = [
    1700000000000,      # open_time
    "42000.10000000",   # open
    "42500.50000000",   # high
    "41900.00000000",   # low
    "42300.25000000",   # close
    "123.456",           # volume
    1700003599999,      # close_time
    "5234567.89",        # quote_volume
    321,                  # num_trades
]


def test_parse_kline_converts_ohlcv_to_decimal():
    parsed = BinanceClient._parse_kline(RAW_KLINE)

    assert parsed["open"] == Decimal("42000.10000000")
    assert parsed["high"] == Decimal("42500.50000000")
    assert parsed["low"] == Decimal("41900.00000000")
    assert parsed["close"] == Decimal("42300.25000000")
    assert parsed["volume"] == Decimal("123.456")
    assert parsed["quote_volume"] == Decimal("5234567.89")
    assert parsed["open_time"] == 1700000000000
    assert parsed["close_time"] == 1700003599999
    assert parsed["num_trades"] == 321


def test_generate_signature_is_deterministic_and_key_dependent():
    security = BinanceSecurityManager("api-key", "secret-1")
    params = {"symbol": "BTCUSDT", "side": "BUY", "timestamp": 1700000000000}

    sig_a = security.generate_signature(params)
    sig_b = security.generate_signature(dict(params))  # same content, new dict
    assert sig_a == sig_b

    other_secret = BinanceSecurityManager("api-key", "secret-2")
    assert other_secret.generate_signature(params) != sig_a


def test_get_headers_includes_api_key():
    security = BinanceSecurityManager("my-api-key", "my-secret")
    headers = security.get_headers()
    assert headers["X-MBX-APIKEY"] == "my-api-key"


def test_validate_recv_window_bounds():
    assert BinanceSecurityManager.validate_recv_window(5000) is True
    assert BinanceSecurityManager.validate_recv_window(0) is False
    assert BinanceSecurityManager.validate_recv_window(60000) is True
    assert BinanceSecurityManager.validate_recv_window(60001) is False
