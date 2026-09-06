"""
Endpoint-level tests for T17: verify residual position check after grid close.

Covers:
- cancel_grid logs CRITICAL + emits RESIDUAL_POSITION bot_health_event when
  position_amt != 0 after place_market_close.
- cancel_grid does NOT emit the event when the close left no residual.
- _log_bot_health_event degrades gracefully when Postgres is unavailable.
"""

from app.main import grid_service


def _create_grid(client):
    payload = {
        "symbol": "BTCUSDT",
        "lower_price": 40000.0,
        "upper_price": 45000.0,
        "levels": 10,
        "grid_type": "GEOMETRIC",
        "quantity_per_order": 0.002,  # 0.002 * 40000 = 80 USDT (> min_notional 50)
    }
    response = client.post("/api/v1/grids", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_cancel_grid_emits_residual_position_event(client, mock_binance, monkeypatch):
    grid = _create_grid(client)
    # Position has amt 0.05 BEFORE the close (so place_market_close runs) and
    # the same residual AFTER the close (the market close did not flatten it).
    mock_binance["get_position"].side_effect = [
        {"positionAmt": "0.05"},
        {"positionAmt": "0.05"},
    ]

    events = []

    def spy_log(event_type, grid_id, symbol, severity="warning", message="", details=None):
        events.append({
            "event_type": event_type,
            "grid_id": grid_id,
            "symbol": symbol,
            "severity": severity,
            "message": message,
            "details": details,
        })

    monkeypatch.setattr(grid_service, "_log_bot_health_event", spy_log)

    response = client.delete(f"/api/v1/grids/{grid['id']}")
    assert response.status_code == 200
    assert mock_binance["place_market_close"].await_count == 1
    assert len(events) == 1
    assert events[0]["event_type"] == "RESIDUAL_POSITION"
    assert events[0]["grid_id"] == grid["id"]
    assert events[0]["symbol"] == "BTCUSDT"
    assert events[0]["severity"] == "critical"
    assert events[0]["details"]["position_amt"] == "0.05"
    assert events[0]["details"]["trigger_condition"] == "MANUAL"
    assert "residual" in events[0]["message"].lower()


def test_cancel_grid_no_event_when_position_closes_to_zero(client, mock_binance, monkeypatch):
    grid = _create_grid(client)
    # Position is already 0 -> no market close needed, no residual to report.
    events = []

    def spy_log(event_type, grid_id, symbol, severity="warning", message="", details=None):
        events.append(event_type)

    monkeypatch.setattr(grid_service, "_log_bot_health_event", spy_log)

    response = client.delete(f"/api/v1/grids/{grid['id']}")
    assert response.status_code == 200
    assert mock_binance["place_market_close"].await_count == 0
    assert events == []


def test_log_bot_health_event_skips_when_no_postgres(monkeypatch):
    monkeypatch.setattr("app.services.grid_service.postgres_engine", None)
    # Same code path as a fresh service instance: must not raise.
    service = grid_service
    service._log_bot_health_event("RESIDUAL_POSITION", "g1", "BTCUSDT")