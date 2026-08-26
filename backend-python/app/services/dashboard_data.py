"""
dashboard_data.py — Construye el dataset del dashboard leyendo postgres-trading
(grid_cycles, pnl_snapshots, historical_grid_logs) con el engine SQLAlchemy
del backend. Es el mismo dataset que genera scripts/dashboard/export_data.py
offline, pero en vivo y sin conexión externa (el backend comparte red con el
Postgres). Endpoints en app/main.py: GET /dashboard y GET /api/v1/dashboard/data.
"""

import json
import logging
import os
import time
from datetime import datetime

from sqlalchemy import text

from app.database.connection import get_sqlite_connection

logger = logging.getLogger("grid_trading")

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates",
    "dashboard.html",
)

# Cache simple en proceso (1 min): los datos se regeneran en cada refresh de
# WF2 cada ~15 min; no vale la pena golpear Postgres en cada recarga de página.
_CACHE_TTL_SECONDS = 60.0
_cache = {"ts": 0.0, "data": None}


def num(v):
    """Decimal/float/int/None -> float/None. Idempotente (double-cast seguro)."""
    if v is None:
        return None
    if isinstance(v, str):
        return float(v)
    return float(v)


def iso(dt):
    """datetime/str/None -> str ISO (None -> None). Idempotente (double-cast seguro)."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def cast_row(row, fields):
    """row: SQLAlchemy Row; fields: lista de (columna, función de cast)."""
    m = row._mapping
    return {name: (fn(m[name]) if m[name] is not None else None) for name, fn in fields}


def fetch(conn, sql, fields, params=None):
    rows = conn.execute(text(sql), params or {})
    return [cast_row(r, fields) for r in rows]


def _compute(engine):
    with engine.connect() as conn:
        overview = fetch(conn, """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(net_pnl), 0)    AS net_pnl,
                   COALESCE(SUM(gross_pnl), 0)  AS gross_pnl,
                   COALESCE(SUM(fee_paid), 0)   AS fees,
                   COUNT(*) FILTER (WHERE net_pnl > 0) AS wins
            FROM grid_cycles
        """, [
            ("total", int), ("net_pnl", num), ("gross_pnl", num),
            ("fees", num), ("wins", int),
        ])[0]

        closed = fetch(conn, """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(total_pnl), 0) AS pnl,
                   COALESCE(AVG(total_pnl), 0) AS avg_pnl
            FROM historical_grid_logs
        """, [("total", int), ("pnl", num), ("avg_pnl", num)])[0]

        latest_snapshot = fetch(conn, """
            SELECT DISTINCT ON (grid_id) grid_id, symbol, taken_at,
                   realized_pnl, unrealized_pnl, total_pnl, account_balance, open_orders_count
            FROM pnl_snapshots
            WHERE NOT EXISTS (SELECT 1 FROM historical_grid_logs h
                              WHERE h.grid_id = pnl_snapshots.grid_id)
            ORDER BY grid_id, taken_at DESC
        """, [
            ("grid_id", str), ("symbol", str), ("taken_at", iso),
            ("realized_pnl", num), ("unrealized_pnl", num),
            ("total_pnl", num), ("account_balance", num), ("open_orders_count", int),
        ])

        equity = fetch(conn, """
            SELECT taken_at,
                   SUM(total_pnl)      AS total_pnl,
                   SUM(realized_pnl)   AS realized_pnl,
                   SUM(unrealized_pnl) AS unrealized_pnl,
                   MAX(account_balance) AS account_balance
            FROM pnl_snapshots
            GROUP BY taken_at
            ORDER BY taken_at
        """, [
            ("taken_at", iso), ("total_pnl", num), ("realized_pnl", num),
            ("unrealized_pnl", num), ("account_balance", num),
        ])

        per_day = fetch(conn, """
            SELECT DATE(completed_at) AS day, COUNT(*) AS total,
                   COALESCE(SUM(net_pnl), 0) AS net_pnl
            FROM grid_cycles
            GROUP BY DATE(completed_at)
            ORDER BY day
        """, [("day", iso), ("total", int), ("net_pnl", num)])

        by_symbol = fetch(conn, """
            SELECT symbol, COUNT(*) AS total,
                   COALESCE(SUM(net_pnl), 0)   AS net_pnl,
                   COUNT(*) FILTER (WHERE net_pnl > 0) AS wins,
                   COALESCE(SUM(gross_pnl), 0) AS gross_pnl,
                   COALESCE(SUM(fee_paid), 0)  AS fees
            FROM grid_cycles
            GROUP BY symbol
            ORDER BY net_pnl DESC
        """, [
            ("symbol", str), ("total", int), ("net_pnl", num), ("wins", int),
            ("gross_pnl", num), ("fees", num),
        ])

        last_cycles = fetch(conn, """
            SELECT grid_id, symbol, cycle_number, buy_price, sell_price, quantity,
                   fee_paid, gross_pnl, net_pnl, completed_at
            FROM grid_cycles
            ORDER BY completed_at DESC, id DESC
            LIMIT 15
        """, [
            ("grid_id", str), ("symbol", str), ("cycle_number", int),
            ("buy_price", num), ("sell_price", num), ("quantity", num),
            ("fee_paid", num), ("gross_pnl", num), ("net_pnl", num),
            ("completed_at", iso),
        ])

        closed_grids = fetch(conn, """
            SELECT grid_id, symbol, total_pnl, trigger_condition, opened_at, closed_at
            FROM historical_grid_logs
            ORDER BY closed_at DESC NULLS LAST, created_at DESC
            LIMIT 20
        """, [
            ("grid_id", str), ("symbol", str), ("total_pnl", num),
            ("trigger_condition", str), ("opened_at", iso), ("closed_at", iso),
        ])

        cycles_by_grid = fetch(conn, """
            SELECT grid_id, symbol, COUNT(*) AS cycles,
                   COUNT(*) FILTER (WHERE net_pnl > 0) AS wins,
                   COALESCE(SUM(net_pnl), 0)   AS net_pnl,
                   COALESCE(SUM(fee_paid), 0)  AS fees
            FROM grid_cycles
            GROUP BY grid_id, symbol
        """, [
            ("grid_id", str), ("symbol", str), ("cycles", int), ("wins", int),
            ("net_pnl", num), ("fees", num),
        ])

        avg_cycle = fetch(conn, """
            SELECT COALESCE(AVG(net_pnl), 0) AS avg_net,
                   COALESCE(AVG(buy_price * quantity), 0) AS avg_notional
            FROM grid_cycles
        """, [("avg_net", num), ("avg_notional", num)])[0]

    # --- Active operations from SQLite (real-time) ---
    active_ops = {"count": 0, "grids": []}
    current_map = {r["grid_id"]: r for r in latest_snapshot}
    try:
        sqlite_conn = get_sqlite_connection()
        try:
            running_grids = sqlite_conn.execute(
                "SELECT id, symbol, lower_price, upper_price, levels, grid_type, "
                "leverage, quantity_per_order, grid_mode, created_at "
                "FROM grids WHERE status = 'RUNNING'"
            ).fetchall()
            for g in running_grids:
                gid = g["id"]
                orders = sqlite_conn.execute(
                    "SELECT status, COUNT(*) AS cnt FROM grid_orders "
                    "WHERE grid_id = ? GROUP BY status", (gid,)
                ).fetchall()
                order_counts = {r["status"]: r["cnt"] for r in orders}
                total_orders = sum(order_counts.values())
                open_orders = order_counts.get("NEW", 0) + order_counts.get("PARTIALLY_FILLED", 0)
                filled_orders = order_counts.get("FILLED", 0)
                canceled_orders = order_counts.get("CANCELED", 0) + order_counts.get("REJECTED", 0) + order_counts.get("EXPIRED", 0)
                # Latest snapshot for this grid (from postgres)
                snap = current_map.get(gid, {})
                active_ops["grids"].append({
                    "grid_id": gid,
                    "symbol": g["symbol"],
                    "lower_price": num(g["lower_price"]),
                    "upper_price": num(g["upper_price"]),
                    "levels": g["levels"],
                    "grid_type": g["grid_type"],
                    "leverage": g["leverage"],
                    "quantity_per_order": num(g["quantity_per_order"]),
                    "grid_mode": g["grid_mode"],
                    "created_at": iso(g["created_at"]),
                    "total_orders": total_orders,
                    "open_orders": open_orders,
                    "filled_orders": filled_orders,
                    "canceled_orders": canceled_orders,
                    "realized_pnl": num(snap.get("realized_pnl")),
                    "unrealized_pnl": num(snap.get("unrealized_pnl")),
                    "total_pnl": num(snap.get("total_pnl")),
                    "last_snapshot_at": iso(snap.get("taken_at")),
                })
            active_ops["count"] = len(active_ops["grids"])
        finally:
            sqlite_conn.close()
    except Exception as e:
        logger.warning(f"dashboard: no se pudo leer SQLite para active_operations: {e}")

    total_cycles = overview["total"]
    wins = overview["wins"]
    win_rate = (wins / total_cycles) if total_cycles else None
    fees_pct = (overview["fees"] / overview["gross_pnl"] * 100) if overview["gross_pnl"] else None

    cycles_pnl_f = num(overview["net_pnl"])
    closed_pnl_f = num(closed["pnl"])

    balances = [e["account_balance"] for e in equity if e["account_balance"] is not None]
    first_balance = balances[0] if balances else None
    last_balance = balances[-1] if balances else None
    roi_period_pct = num(((last_balance - first_balance) / first_balance * 100) if first_balance else None)

    avg_net = num(avg_cycle["avg_net"]) or 0.0
    avg_notional = num(avg_cycle["avg_notional"]) or 0.0
    cycle_return_pct = (avg_net / avg_notional * 100) if avg_notional else None

    cycles_map = {r["grid_id"]: r for r in cycles_by_grid}
    closed_map = {r["grid_id"]: r for r in closed_grids}
    per_grid = []
    for gid in set(cycles_map) | set(closed_map) | set(current_map):
        c = cycles_map.get(gid, {})
        cl = closed_map.get(gid, {})
        cu = current_map.get(gid, {})
        is_closed = gid in closed_map
        per_grid.append({
            "grid_id": gid,
            "symbol": cu.get("symbol") or c.get("symbol") or cl.get("symbol"),
            "status": "CERRADO" if is_closed else "RUNNING",
            "cycles": c.get("cycles", 0),
            "wins": c.get("wins", 0),
            "net_cycles_pnl": num(c.get("net_pnl", 0)),
            "fees": num(c.get("fees", 0)),
            "closed_pnl": num(cl.get("total_pnl")),
            "trigger": cl.get("trigger_condition"),
            "closed_at": iso(cl.get("closed_at")),
            "current_pnl": num(cu.get("total_pnl")),
            "last_snapshot_at": iso(cu.get("taken_at")),
        })
    per_grid.sort(key=lambda g: (g["status"] == "CERRADO", g["net_cycles_pnl"] + (g["closed_pnl"] or 0)), reverse=True)

    return {
        "generated_at": iso(datetime.now()),
        "overview": {
            "cycles": total_cycles,
            "wins": wins,
            "losses": total_cycles - wins,
            "win_rate": win_rate,
            "net_pnl": num(overview["net_pnl"]),
            "gross_pnl": num(overview["gross_pnl"]),
            "fees": num(overview["fees"]),
            "fees_pct": num(fees_pct),
            "closed_grids": closed["total"],
            "closed_pnl": num(closed["pnl"]),
            "closed_avg_pnl": num(closed["avg_pnl"]),
        },
        "current": [
            {
                "grid_id": r["grid_id"],
                "symbol": r["symbol"],
                "taken_at": iso(r["taken_at"]),
                "realized_pnl": num(r["realized_pnl"]),
                "unrealized_pnl": num(r["unrealized_pnl"]),
                "total_pnl": num(r["total_pnl"]),
                "account_balance": num(r["account_balance"]),
                "open_orders_count": r["open_orders_count"],
            }
            for r in latest_snapshot
        ],
        "equity": [
            {
                "taken_at": iso(r["taken_at"]),
                "total_pnl": num(r["total_pnl"]),
                "realized_pnl": num(r["realized_pnl"]),
                "unrealized_pnl": num(r["unrealized_pnl"]),
                "account_balance": num(r["account_balance"]),
            }
            for r in equity
        ],
        "per_day": [
            {"day": iso(r["day"]), "total": r["total"], "net_pnl": num(r["net_pnl"])}
            for r in per_day
        ],
        "by_symbol": [
            {
                "symbol": r["symbol"],
                "total": r["total"],
                "wins": r["wins"],
                "net_pnl": num(r["net_pnl"]),
                "gross_pnl": num(r["gross_pnl"]),
                "fees": num(r["fees"]),
            }
            for r in by_symbol
        ],
        "last_cycles": [
            {
                "grid_id": r["grid_id"],
                "symbol": r["symbol"],
                "cycle_number": r["cycle_number"],
                "buy_price": num(r["buy_price"]),
                "sell_price": num(r["sell_price"]),
                "quantity": num(r["quantity"]),
                "fee_paid": num(r["fee_paid"]),
                "gross_pnl": num(r["gross_pnl"]),
                "net_pnl": num(r["net_pnl"]),
                "completed_at": iso(r["completed_at"]),
            }
            for r in last_cycles
        ],
        "closed_grids": [
            {
                "grid_id": r["grid_id"],
                "symbol": r["symbol"],
                "total_pnl": num(r["total_pnl"]),
                "trigger_condition": r["trigger_condition"],
                "opened_at": iso(r["opened_at"]),
                "closed_at": iso(r["closed_at"]),
            }
            for r in closed_grids
        ],
        "strategy": {
            "name": "Grid Trading",
            "detail": "Única estrategia implementada. La tabla 'Rentabilidad por grid' desglosa PnL por grid.",
            "symbols": sorted({g["symbol"] for g in per_grid if g["symbol"]}),
        },
        "profitability": {
            "roi_period_pct": roi_period_pct,
            "cycle_return_pct": cycle_return_pct,
            "cycles_pnl": cycles_pnl_f,
            "closed_pnl": closed_pnl_f,
            "combined_pnl": cycles_pnl_f + closed_pnl_f,
            "strategy_roi_pct": num(((cycles_pnl_f + closed_pnl_f) / num(first_balance) * 100) if first_balance else None),
        },
        "per_grid": per_grid,
        "active_operations": active_ops,
    }


def build_dashboard_data(engine):
    """Dataset del dashboard, con cache de 1 min en proceso."""
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < _CACHE_TTL_SECONDS:
        return _cache["data"]
    try:
        data = _compute(engine)
    except Exception as e:
        logger.error(f"dashboard: fallo al consultar postgres-trading: {e}")
        raise
    _cache["ts"] = now
    _cache["data"] = data
    return data


def render_dashboard_html(data):
    """Sustituye __DATA__ en el template y devuelve el HTML listo."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as fh:
        template = fh.read()
    return template.replace("__DATA__", json.dumps(data, ensure_ascii=False))
