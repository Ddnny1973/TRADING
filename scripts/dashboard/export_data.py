#!/usr/bin/env python3
"""
export_data.py — Genera dashboard.html con la evolución del bot leyendo
postgres-trading (el Postgres de históricos/analítica del backend).

Uso local (en tu PC):
    pip install -r scripts/dashboard/requirements.txt
    python scripts/dashboard/export_data.py

Conexión (prioridad: env vars > scripts/dashboard/db.conf > .env raíz > defaults):
    POSTGRES_HOST       default 46.224.72.175 (IP pública del servidor)
    POSTGRES_PORT       default 9043          (puerto publicado en docker-compose)
    POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB (default trading_history)

Config:
- scripts/dashboard/db.conf  -> config local del dashboard (gitignoreada).
  Pon ahí las credenciales reales del servidor (tómalas de /data/odoo/43/.env).
- El .env raíz es plantilla de docker-compose (host=postgres-trading, puerto
  interno 5432) y NO sirve tal cual para conexión local; db.conf tiene prioridad.
- Si accedes por túnel SSH: POSTGRES_HOST=localhost POSTGRES_PORT=9043.
- Salida: scripts/dashboard/dashboard.html — abrir en el navegador (sin
  servidor, datos incrustados). Re-ejecutar el script para actualizar.
"""

import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DASH_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(ROOT, ".env")
DB_CONF = os.path.join(DASH_DIR, "db.conf")
OUT_FILE = os.path.join(DASH_DIR, "dashboard.html")

# Template compartido con el backend (GET /dashboard): fuente única.
TEMPLATE_FILE = os.path.join(ROOT, "backend-python", "app", "templates", "dashboard.html")

PLACEHOLDER_USER = "trading_user"
PLACEHOLDER_PASS = "secure_password_change_this"


def load_env_file(path):
    """Carga un .env simple (KEY=VALUE, ignorando comentarios) sin deps."""
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def get_conn_params():
    """Env vars > db.conf > .env raíz > defaults. Detecta credenciales placeholder."""
    root_env = load_env_file(ENV_FILE)
    dash_conf = load_env_file(DB_CONF)

    def pick(key, default):
        return os.environ.get(key) or dash_conf.get(key) or root_env.get(key) or default

    host = pick("POSTGRES_HOST", "46.224.72.175")
    if host in ("postgres-trading", "postgres"):  # nombres internos del contenedor
        host = "46.224.72.175"
    port = int(pick("POSTGRES_PORT", "9043"))
    user = pick("POSTGRES_USER", "")
    password = pick("POSTGRES_PASSWORD", "")
    db = pick("POSTGRES_DB", "trading_history")

    if not user or not password:
        print("AVISO: faltan credenciales (POSTGRES_USER / POSTGRES_PASSWORD).")
        print("  Opción 1: edita scripts/dashboard/db.conf con las credenciales reales")
        print("            (tómalas del .env del servidor: /data/odoo/43/.env).")
        print("  Opción 2: pásalas por env vars:")
        print("            $env:POSTGRES_USER='...'; $env:POSTGRES_PASSWORD='...'")
        print("            python scripts/dashboard/export_data.py")
    elif user == PLACEHOLDER_USER and password == PLACEHOLDER_PASS:
        print("AVISO: credenciales del .env raíz son placeholder (trading_user / secure_password_change_this).")
        print("  Configura las reales en scripts/dashboard/db.conf o por env vars.")
    return host, port, user, password, db


def connect(host, port, user, password, db):
    try:
        import psycopg2
    except ImportError:
        print("Falta psycopg2. Instálalo con: pip install -r scripts/dashboard/requirements.txt")
        sys.exit(1)
    return psycopg2.connect(
        host=host, port=port, user=user, password=password,
        dbname=db, connect_timeout=10,
    )


def fetch(conn, query, params=()):
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        cur.close()


def num(v):
    """Decimal/None -> float/None (psycopg2 devuelve Decimal para NUMERIC)."""
    return float(v) if v is not None else None


def iso(dt):
    """datetime/date -> str ISO (None -> None)."""
    return dt.isoformat() if dt is not None else None


def main():
    host, port, user, password, db = get_conn_params()
    print(f"Conectando a postgres://{user}@{host}:{port}/{db} ...")
    conn = connect(host, port, user, password, db)

    # ---- Consultas ----
    overview = fetch(conn, """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(net_pnl), 0)    AS net_pnl,
               COALESCE(SUM(gross_pnl), 0)  AS gross_pnl,
               COALESCE(SUM(fee_paid), 0)   AS fees,
               COUNT(*) FILTER (WHERE net_pnl > 0) AS wins
        FROM grid_cycles
    """)[0]

    closed = fetch(conn, """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(total_pnl), 0) AS pnl,
               COALESCE(AVG(total_pnl), 0) AS avg_pnl
        FROM historical_grid_logs
    """)[0]

    latest_snapshot = fetch(conn, """
        SELECT DISTINCT ON (grid_id) grid_id, symbol, taken_at,
               realized_pnl, unrealized_pnl, total_pnl, account_balance, open_orders_count
        FROM pnl_snapshots
        ORDER BY grid_id, taken_at DESC
    """)

    equity = fetch(conn, """
        SELECT taken_at,
               SUM(total_pnl)      AS total_pnl,
               SUM(realized_pnl)   AS realized_pnl,
               SUM(unrealized_pnl) AS unrealized_pnl,
               MAX(account_balance) AS account_balance
        FROM pnl_snapshots
        GROUP BY taken_at
        ORDER BY taken_at
    """)

    per_day = fetch(conn, """
        SELECT DATE(completed_at) AS day, COUNT(*) AS total,
               COALESCE(SUM(net_pnl), 0) AS net_pnl
        FROM grid_cycles
        GROUP BY DATE(completed_at)
        ORDER BY day
    """)

    by_symbol = fetch(conn, """
        SELECT symbol, COUNT(*) AS total,
               COALESCE(SUM(net_pnl), 0)   AS net_pnl,
               COUNT(*) FILTER (WHERE net_pnl > 0) AS wins,
               COALESCE(SUM(gross_pnl), 0) AS gross_pnl,
               COALESCE(SUM(fee_paid), 0)  AS fees
        FROM grid_cycles
        GROUP BY symbol
        ORDER BY net_pnl DESC
    """)

    last_cycles = fetch(conn, """
        SELECT grid_id, symbol, cycle_number, buy_price, sell_price, quantity,
               fee_paid, gross_pnl, net_pnl, completed_at
        FROM grid_cycles
        ORDER BY completed_at DESC, id DESC
        LIMIT 15
    """)

    closed_grids = fetch(conn, """
        SELECT grid_id, symbol, total_pnl, trigger_condition, opened_at, closed_at
        FROM historical_grid_logs
        ORDER BY closed_at DESC NULLS LAST, created_at DESC
        LIMIT 20
    """)

    cycles_by_grid = fetch(conn, """
        SELECT grid_id, symbol, COUNT(*) AS cycles,
               COUNT(*) FILTER (WHERE net_pnl > 0) AS wins,
               COALESCE(SUM(net_pnl), 0)   AS net_pnl,
               COALESCE(SUM(fee_paid), 0)  AS fees
        FROM grid_cycles
        GROUP BY grid_id, symbol
    """)

    avg_cycle = fetch(conn, """
        SELECT COALESCE(AVG(net_pnl), 0) AS avg_net,
               COALESCE(AVG(buy_price * quantity), 0) AS avg_notional
        FROM grid_cycles
    """)[0]

    conn.close()

    # ---- Estructura de datos para el HTML ----
    total_cycles = overview["total"]
    wins = overview["wins"]
    win_rate = (wins / total_cycles) if total_cycles else None
    fees_pct = (overview["fees"] / overview["gross_pnl"] * 100) if overview["gross_pnl"] else None

    cycles_pnl_f = num(overview["net_pnl"])
    closed_pnl_f = num(closed["pnl"])

    # ROI del período basado en el balance de cuenta de los snapshots
    balances = [e["account_balance"] for e in equity if e["account_balance"] is not None]
    first_balance = balances[0] if balances else None
    last_balance = balances[-1] if balances else None
    roi_period_pct = num(((last_balance - first_balance) / first_balance * 100) if first_balance else None)

    # Retorno promedio por ciclo (%): net_pnl / notional (buy_price * quantity)
    avg_net = num(avg_cycle["avg_net"]) or 0.0
    avg_notional = num(avg_cycle["avg_notional"]) or 0.0
    cycle_return_pct = (avg_net / avg_notional * 100) if avg_notional else None

    # Rentabilidad por grid: fusiona ciclos (grid_cycles) + cierres (historical_grid_logs) + estado actual
    cycles_map = {r["grid_id"]: r for r in cycles_by_grid}
    closed_map = {r["grid_id"]: r for r in closed_grids}
    current_map = {r["grid_id"]: r for r in latest_snapshot}
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

    data = {
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
    }

    render(data)


def render(data):
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as fh:
        template = fh.read()
    html = template.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"OK: dashboard generado en {OUT_FILE}")


if __name__ == "__main__":
    main()
