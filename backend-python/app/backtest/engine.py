"""
Motor del backtest: recorre el tiempo vela a vela (5 min) y hace lo que en
producción hacen n8n + el backend.

- WF1 (cada 4 h, al cerrar un grid, o por watchdog): elegir par → derivar
  parámetros → puerta determinista → crear grid. La derivación NO se copia:
  se llama a `auto_derive_params` y a las funciones de `pair_selector` reales
  con un cliente que sirve las velas históricas.
- WF2 (cada 5 min): kill-switch → reposición → check-close (y re-centrado).

Aproximaciones conocidas (ver docs/analisis-bot/06-backtester.md):
universo = lista de símbolos dada; sin filtro de spread; funding = 0;
filtros del exchange de hoy; LLM ignorado (desde A3 no decide).
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app import auto_params, config_auto_params as policy, pair_selector
from app.backtest.data import BASE_MS, HistClient, HistoricalMarket
from app.backtest.grid_sim import (
    GridRecord, GridRejected, SimConfig, SimGrid, max_duration_hours,
)
from app.core.config import settings
from app.services.indicators import calculate_atr

_DAY_MS = 24 * 60 * 60 * 1000
_HOUR_MS = 60 * 60 * 1000


@contextmanager
def policy_overrides(cfg: SimConfig):
    """
    Aplica el perfil del backtest a las constantes que `auto_params` y
    `pair_selector` leen a nivel de módulo, y las restaura al salir.
    """
    patches: List[tuple] = []

    def patch(obj: Any, name: str, value: Any) -> None:
        patches.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    patch(auto_params, "MAX_RISK_PCT", Decimal(str(cfg.max_risk_pct)))
    if cfg.stop_loss_pct is not None:
        patch(auto_params, "GRID_STOP_LOSS_PCT_OF_BALANCE", Decimal(str(cfg.stop_loss_pct)))
    if cfg.take_profit_pct is not None:
        patch(auto_params, "GRID_TAKE_PROFIT_PCT_OF_BALANCE", Decimal(str(cfg.take_profit_pct)))
    if cfg.er_max_tradeable is not None:
        er = Decimal(str(cfg.er_max_tradeable))
        patch(auto_params, "ER_MAX_TRADEABLE", er)
        patch(pair_selector, "ER_MAX_TRADEABLE", er)
    # Los filtros del mercado histórico ya son los de mainnet: no ir a la red.
    patch(settings, "MIN_NOTIONAL_FROM_MAINNET", False)
    try:
        yield
    finally:
        for obj, name, old in reversed(patches):
            setattr(obj, name, old)


@dataclass
class BacktestResult:
    config: SimConfig
    symbols: List[str]
    start_ms: int
    end_ms: int
    records: List[GridRecord] = field(default_factory=list)
    equity: List[tuple] = field(default_factory=list)      # (ms, pnl acumulado real)
    stats: Dict[str, int] = field(default_factory=dict)


class Backtest:
    def __init__(self, market: HistoricalMarket, cfg: SimConfig, symbols: List[str],
                 start_ms: int, end_ms: int):
        self.market = market
        self.cfg = cfg
        self.symbols = [s for s in symbols if s in market.bars and s in market.filters]
        self.start_ms = start_ms - start_ms % BASE_MS
        self.end_ms = end_ms
        self.client = HistClient(market)
        self.running: List[SimGrid] = []
        self.records: List[GridRecord] = []
        self.realized_true = 0.0
        self.closed_bot_by_day: Dict[int, float] = {}
        self.kill_switch_until: Optional[int] = None
        self.empty_cycles = 0
        self.stats: Dict[str, int] = {}

    def _bump(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    # ------------------------------------------------------------ lanzamiento

    async def _select_pair(self, now_ms: int) -> Optional[Dict[str, Any]]:
        """Espejo de pair_selector.select_best_pair + pick_best_pair."""
        balance = self.cfg.balance
        min_levels = policy.LEVELS_BOUNDS[0]
        capital = balance * self.cfg.max_risk_pct * policy.LEVERAGE_BOUNDS[1] / min_levels

        volumes: Dict[str, float] = {}
        for s in self.symbols:
            price = self.market.price(s, now_ms)
            if not price or price <= 0:
                continue
            if float(self.market.filters[s]["min_notional"]) > capital:
                continue
            vol = self.market.volume_24h(s, now_ms)
            if vol < policy.MIN_VOLUME_24H_USDT:
                continue
            volumes[s] = vol
        if len(volumes) < 3:
            return None

        candidates = sorted(volumes, key=volumes.get, reverse=True)[:policy.MAX_CANDIDATES_TO_SCORE]
        evaluated = []
        for s in candidates:
            e = await pair_selector._evaluate_candidate(self.client, s)
            if e is not None:
                evaluated.append(e)
        if not evaluated:
            return None

        max_volume = max(volumes[e["symbol"]] for e in evaluated)
        for e in evaluated:
            e["score"] = pair_selector.score_candidate(
                e["symbol"], e["er"], e["atr_pct"], volumes[e["symbol"]], 0.0, max_volume
            )
            lev = auto_params.derive_leverage(e["atr_pct"])
            margin_min = (min_levels * float(self.market.filters[e["symbol"]]["min_notional"])
                          * float(policy.CAPITAL_BUFFER) / lev)
            e["viable_for_balance"] = (margin_min / balance) <= self.cfg.max_risk_pct
        evaluated.sort(key=lambda e: e["score"], reverse=True)
        viable = [e for e in evaluated if e["viable_for_balance"]]
        ranked = viable or evaluated

        running_symbols = {g.symbol for g in self.running}
        free = [e for e in ranked if e["symbol"] not in running_symbols]
        if not free:
            return None
        return {"selected": free[0], "top_3": ranked[:3], "passed_filters": len(volumes)}

    async def _attempt_launch(self, now_ms: int) -> None:
        """Una corrida de WF1."""
        self._bump("wf1_runs")
        if self.kill_switch_until is not None:
            self._bump("launch_blocked_kill_switch")
            return
        if len(self.running) >= self.cfg.max_concurrent_grids:
            self._bump("launch_skipped_slots_full")
            return

        selection = await self._select_pair(now_ms)
        if selection is None:
            self._bump("launch_no_candidate")
            return
        symbol = selection["selected"]["symbol"]
        try:
            result = await auto_params.auto_derive_params(
                symbol, Decimal(str(self.cfg.balance)), client=self.client
            )
        except ValueError:
            self._bump("launch_params_error")
            return

        # Puerta determinista (A3): grid_viable y sin vetos. Los vetos de
        # selección son los que agrega GET /auto-params en main.py.
        vetoes = list(result.get("veto_reasons") or [])
        if not selection["top_3"]:
            vetoes.append("top_3 vacío")
        if selection["passed_filters"] < 5:
            vetoes.append("menos de 5 candidatos")
        if not result["grid_viable"]:
            self._bump("launch_not_viable")
            return
        if vetoes:
            self._bump("launch_vetoed")
            return

        p = result["params"]
        price = self.market.price(symbol, now_ms)
        try:
            grid = SimGrid(
                self.cfg, symbol, p["lower_price"], p["upper_price"], p["levels"],
                p["quantity_per_order"], p["leverage"], p["stop_loss"], p["take_profit"],
                max_duration_hours(p["klines_interval"], p["atr_period"]),
                "NEUTRAL", now_ms, price, self.market.filters[symbol],
            )
        except GridRejected:
            self._bump("launch_rejected")
            return
        self.running.append(grid)
        self._bump("grids_launched")

    # ----------------------------------------------------------------- cierre

    def _book(self, record: GridRecord) -> None:
        self.records.append(record)
        day = record.closed_ms // _DAY_MS
        self.closed_bot_by_day[day] = self.closed_bot_by_day.get(day, 0.0) + record.bot_pnl

    def _close(self, grid: SimGrid, now_ms: int, price: float, trigger: str) -> None:
        record = grid.close_market(now_ms, price, trigger)
        self.realized_true += record.true_pnl
        self._book(record)
        self.running.remove(grid)

    def _atr_4h(self, symbol: str, now_ms: int) -> Optional[float]:
        klines = self.market.klines_asof(symbol, "4h", policy.ATR_PERIOD + 1, now_ms)
        if not klines or len(klines) < policy.ATR_PERIOD + 1:
            return None
        return float(calculate_atr(klines, policy.ATR_PERIOD))

    def _recenter(self, grid: SimGrid, now_ms: int, price: float) -> None:
        """
        Espejo de recenter_grid: conserva el inventario y reconstruye el grid
        alrededor del precio actual con los DEFAULTS de create_grid
        (ATR(14) de 4h × 2.0), en modo LONG/SHORT según la posición heredada.
        """
        units = grid.pos_units
        mode = "LONG" if units > 0 else "SHORT" if units < 0 else "NEUTRAL"
        atr = self._atr_4h(grid.symbol, now_ms)
        child: Optional[SimGrid] = None
        if atr and atr > 0 and price - 2.0 * atr > 0 and self.kill_switch_until is None:
            try:
                child = SimGrid(
                    self.cfg, grid.symbol, price - 2.0 * atr, price + 2.0 * atr,
                    grid.levels, grid.qty, grid.leverage, grid.stop_loss, grid.take_profit,
                    grid.max_duration, mode, now_ms, price, grid.filters,
                    recenter_count=grid.recenter_count + 1, root_id=grid.root_id,
                    inherited_units=units,
                )
            except GridRejected:
                child = None
        if child is None:
            # En producción el padre ya quedó CANCELED y la posición suelta.
            # Aquí se liquida para no arrastrar inventario sin dueño.
            self._bump("recenter_failed")
            self._close(grid, now_ms, price, "RECENTER_FAILED")
            return
        record = grid.close_keep_inventory(now_ms, price, "RECENTERED")
        self.realized_true += record.true_pnl
        self._book(record)
        self.running.remove(grid)
        self.running.append(child)

    # ------------------------------------------------------------------ ciclo

    def _check_kill_switch(self, now_ms: int) -> None:
        if not self.cfg.kill_switch or policy.MAX_DAILY_DRAWDOWN_PCT <= 0:
            return
        if self.kill_switch_until is not None:
            if now_ms >= self.kill_switch_until:
                self.kill_switch_until = None
            return
        daily = self.closed_bot_by_day.get(now_ms // _DAY_MS, 0.0)
        prices = {}
        for g in self.running:
            prices[g] = self.market.price(g.symbol, now_ms)
            daily += g.bot_pnl(prices[g])
        if daily <= -float(policy.MAX_DAILY_DRAWDOWN_PCT) * self.cfg.balance:
            self._bump("kill_switch_engaged")
            for g in list(self.running):
                self._close(g, now_ms, prices[g], "KILL_SWITCH")
            self.kill_switch_until = (now_ms // _DAY_MS + 1) * _DAY_MS

    async def _cycle(self, now_ms: int) -> None:
        """Una corrida de WF2 (más el WF1 que dispare)."""
        self.client.now_ms = now_ms
        self._check_kill_switch(now_ms)

        closed_any = False
        recenter_policy = self.cfg.out_of_range_policy or policy.OUT_OF_RANGE_POLICY
        for grid in list(self.running):
            price = self.market.price(grid.symbol, now_ms)
            grid.replenish(price)
            trigger = grid.check_close(now_ms, price, lambda g=grid: self._atr_4h(g.symbol, now_ms))
            if trigger is None:
                continue
            closed_any = True
            can_recenter = (
                trigger == "OUT_OF_RANGE" and recenter_policy == "RECENTER"
                and (self.cfg.max_recenters is None or grid.recenter_count < self.cfg.max_recenters)
            )
            if can_recenter:
                self._recenter(grid, now_ms, price)
            else:
                self._close(grid, now_ms, price, trigger)

        launch = closed_any  # WF2 relanza WF1 al cerrar un grid (T10)
        if self.running:
            self.empty_cycles = 0
        else:
            self.empty_cycles += 1
            if self.empty_cycles >= self.cfg.watchdog_cycles:  # T12
                self.empty_cycles = 0
                launch = True
        if now_ms % (self.cfg.wf1_interval_hours * _HOUR_MS) == 0:
            launch = True
        if launch:
            await self._attempt_launch(now_ms)

    # -------------------------------------------------------------------- run

    def _equity(self, now_ms: int) -> float:
        total = self.realized_true
        for g in self.running:
            total += g.true_pnl_marked(self.market.price(g.symbol, now_ms))
        return total

    async def run(self) -> BacktestResult:
        cycle_ms = self.cfg.cycle_minutes * 60 * 1000
        equity: List[tuple] = []
        with policy_overrides(self.cfg):
            now = self.start_ms + BASE_MS
            while now <= self.end_ms:
                for grid in self.running:
                    bars = self.market.bars[grid.symbol]
                    i = bars.index_at(now)
                    if i >= 0 and bars.t[i] == now - BASE_MS and bars.t[i] >= grid.created_ms:
                        grid.apply_bar(bars.h[i], bars.l[i])
                if now % cycle_ms == 0:
                    await self._cycle(now)
                if now % _HOUR_MS == 0:
                    equity.append((now, self._equity(now)))
                now += BASE_MS

            # Lo que siga abierto se valora a precio de marca, sin liquidar.
            last = now - BASE_MS
            for grid in list(self.running):
                record = grid.close_keep_inventory(last, self.market.price(grid.symbol, last), "OPEN_AT_END")
                self.realized_true += record.true_pnl
                self.records.append(record)
            self.running = []

        return BacktestResult(
            config=self.cfg, symbols=self.symbols, start_ms=self.start_ms,
            end_ms=self.end_ms, records=self.records, equity=equity, stats=self.stats,
        )
