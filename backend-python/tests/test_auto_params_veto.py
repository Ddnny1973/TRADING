"""
Tests for T13 deterministic gate (veto_reasons) in /auto-params.

T13 (paso 1 = instrumentación): el endpoint reporta en `veto_reasons` las
razones deterministas que desaconsejan lanzar el grid, espejo de los criterios
del prompt del LLM, PERO sin forzar grid_viable=False durante el periodo de
observación (la comparación determinista-vs-LLM es lo que se instrumenta).
"""

from unittest.mock import AsyncMock

from app.auto_params import derive_leverage_atr_veto


# --- derive_leverage_atr_veto (criterio "leverage > 5x con ATR% > 2%") ---

def test_lev_atr_veto_disparado_con_leverage_alto_y_volatilidad_alta():
    reason = derive_leverage_atr_veto(10, 0.025)
    assert reason is not None
    assert "10x" in reason
    assert "2.50%" in reason


def test_lev_atr_veto_no_dispara_con_leverage_alto_pero_volatilidad_baja():
    assert derive_leverage_atr_veto(10, 0.015) is None


def test_lev_atr_veto_no_dispara_con_volatilidad_alta_pero_leverage_bajo():
    assert derive_leverage_atr_veto(3, 0.05) is None


def test_lev_atr_veto_respetar_limites_estrictos():
    # leverage == 5 y atr == 2% exactos NO deben vetar (criterio es >, no >=).
    assert derive_leverage_atr_veto(5, 0.02) is None
    assert derive_leverage_atr_veto(6, 0.0201) is not None


# --- Merge en el endpoint /auto-params (auto mode) ---

def _fake_auto_params_result():
    """Resultado mínimo de auto_derive_params con veto_reasons per-symbol."""
    return {
        "symbol": "BTCUSDT",
        "current_price": 42500.0,
        "grid_viable": True,
        "params": {
            "levels": 8, "risk_pct": 0.0111, "atr_multiplier": 2.0,
            "klines_interval": "4h", "atr_period": 14, "leverage": 3,
            "quantity_per_order": 0.001, "lower_price": 40000.0,
            "upper_price": 45000.0, "stop_loss": None, "take_profit": None,
        },
        "veto_reasons": [],
        "reasoning": {},
        "policy": {},
    }


def test_auto_params_merge_veto_autoselection(client, monkeypatch):
    """
    En auto mode, con pocos candidatos (< 5), /auto-params debe reportar el veto
    determinista de selección en veto_reasons además del de auto_derive_params.
    """
    result = _fake_auto_params_result()
    result["symbol_selection"] = {
        "method": "auto",
        "top_3": [{"symbol": "BTCUSDT", "score": 1.0, "er": 0.1, "volume_24h_m": 5}],
        "candidates_passed_filters": 3,
        "candidates_evaluated": 50,
        "selected_reason": "Score 1.00: ER=0.10, vol=5M USDT",
    }

    async def fake_pick_best_pair(**kwargs):
        return result["symbol_selection"]

    async def fake_auto_derive_params(symbol, balance, client=None):
        return result

    monkeypatch.setattr("app.main.pick_best_pair", fake_pick_best_pair)
    monkeypatch.setattr("app.main.auto_derive_params", fake_auto_derive_params)
    monkeypatch.setattr("app.main.SYMBOL_CACHE_TTL_SECONDS", 0)

    response = client.get("/auto-params", params={"balance": 5200})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["veto_reasons"], list)
    # candidates_passed_filters = 3 (< 5) -> debe aparecer el veto de candidatos
    assert any("3 candidatos" in r for r in data["veto_reasons"])
    # grid_viable no debe caer por el veto (paso 1 solo instrumenta)
    assert data["grid_viable"] is True


def test_auto_params_vetoreasons_ausente_cuando_seleccion_ok(client, monkeypatch):
    result = _fake_auto_params_result()
    result["symbol_selection"] = {
        "method": "auto",
        "top_3": [{"symbol": "BTCUSDT", "score": 1.0, "er": 0.1, "volume_24h_m": 5}],
        "candidates_passed_filters": 8,
        "candidates_evaluated": 50,
        "selected_reason": "Score 1.00",
    }

    async def fake_pick_best_pair(**kwargs):
        return result["symbol_selection"]

    async def fake_auto_derive_params(symbol, balance, client=None):
        return result

    monkeypatch.setattr("app.main.pick_best_pair", fake_pick_best_pair)
    monkeypatch.setattr("app.main.auto_derive_params", fake_auto_derive_params)
    monkeypatch.setattr("app.main.SYMBOL_CACHE_TTL_SECONDS", 0)

    response = client.get("/auto-params", params={"balance": 5200})
    assert response.status_code == 200
    data = response.json()
    assert data["veto_reasons"] == []