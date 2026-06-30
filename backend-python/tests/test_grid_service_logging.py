"""
Unit tests for GridService._log_grid_closure - the historical_grid_logs
(Postgres) write path. No real Postgres is available in this environment,
so a fake session captures merge()/commit() calls instead (equivalent to
the manual `SELECT ... FROM historical_grid_logs` check in
docs/manual-test-plan-swagger.md section 8).
"""

from decimal import Decimal

from app.services.grid_service import GridService


class FakeSession:
    def __init__(self):
        self.merged = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def merge(self, obj):
        self.merged.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class ExplodingSession(FakeSession):
    def commit(self):
        raise RuntimeError("simulated Postgres outage")


def test_log_grid_closure_writes_historical_log(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr("app.services.grid_service.SessionLocal", lambda: fake_session)

    grid = {"id": "grid-123", "symbol": "BTCUSDT", "created_at": "2026-01-01 00:00:00"}
    pnl = {"total_pnl": Decimal("12.5")}

    GridService()._log_grid_closure(grid, pnl, "TAKE_PROFIT")

    assert len(fake_session.merged) == 1
    entry = fake_session.merged[0]
    assert entry.grid_id == "grid-123"
    assert entry.symbol == "BTCUSDT"
    assert entry.total_pnl == Decimal("12.5")
    assert entry.trigger_condition == "TAKE_PROFIT"
    assert fake_session.committed is True
    assert fake_session.closed is True


def test_log_grid_closure_defaults_pnl_to_zero_when_unavailable(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr("app.services.grid_service.SessionLocal", lambda: fake_session)

    GridService()._log_grid_closure(
        {"id": "grid-456", "symbol": "ETHUSDT", "created_at": None}, None, "MANUAL"
    )

    assert fake_session.merged[0].total_pnl == Decimal("0")
    assert fake_session.merged[0].trigger_condition == "MANUAL"


def test_log_grid_closure_swallows_exceptions_without_blocking_cancellation(monkeypatch):
    fake_session = ExplodingSession()
    monkeypatch.setattr("app.services.grid_service.SessionLocal", lambda: fake_session)

    # Must not raise - a Postgres failure should never block a cancel that
    # already happened on Binance/SQLite (see grid_service.py docstring).
    GridService()._log_grid_closure(
        {"id": "grid-789", "symbol": "BTCUSDT", "created_at": None}, None, "MANUAL"
    )

    assert fake_session.rolled_back is True
    assert fake_session.closed is True


def test_log_grid_closure_noop_when_postgres_unavailable(monkeypatch):
    monkeypatch.setattr("app.services.grid_service.SessionLocal", None)

    # Must not raise even though no session can be created.
    GridService()._log_grid_closure(
        {"id": "grid-000", "symbol": "BTCUSDT", "created_at": None}, None, "MANUAL"
    )
