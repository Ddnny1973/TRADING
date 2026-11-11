"""
Datos históricos para el backtester: descarga de velas públicas de mainnet,
caché en disco y un "mercado histórico" que responde como Binance *a una hora
dada* (sin mirar el futuro).

Solo se descargan velas de 5 min. Las de 1h/4h/1d que usa `auto_params` se
agregan desde ahí, incluida la vela en formación (igual que en vivo, donde la
última vela de `get_klines` todavía no cerró).
"""

import csv
import json
import os
import time
import urllib.parse
import urllib.request
from bisect import bisect_right
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

FAPI_BASE = "https://fapi.binance.com"
DEMO_FAPI_BASE = "https://demo-fapi.binance.com"  # el exchange donde opera el bot hoy
BASE_INTERVAL = "5m"
BASE_MS = 5 * 60 * 1000
INTERVAL_MS = {
    "5m": BASE_MS,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}
_KLINES_LIMIT = 1500


def _http_get_json(path: str, params: Optional[Dict[str, Any]] = None, retries: int = 4,
                   base: str = FAPI_BASE) -> Any:
    url = f"{base}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "grid-backtester"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # red inestable / 429: reintentar con espera
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {path} falló tras {retries} intentos: {last_error}")


# ---------------------------------------------------------------------------
# Velas
# ---------------------------------------------------------------------------

class Bars:
    """Velas de 5 min de un símbolo como listas paralelas de floats."""

    __slots__ = ("t", "o", "h", "l", "c", "qv", "_qv_prefix")

    def __init__(self, rows: List[Tuple[int, float, float, float, float, float]]):
        rows = sorted(rows, key=lambda r: r[0])
        self.t = [r[0] for r in rows]   # open_time en ms
        self.o = [r[1] for r in rows]
        self.h = [r[2] for r in rows]
        self.l = [r[3] for r in rows]
        self.c = [r[4] for r in rows]
        self.qv = [r[5] for r in rows]  # volumen en USDT
        prefix = [0.0]
        for v in self.qv:
            prefix.append(prefix[-1] + v)
        self._qv_prefix = prefix

    def __len__(self) -> int:
        return len(self.t)

    def index_at(self, close_ms: int) -> int:
        """Índice de la última vela ya cerrada a `close_ms` (-1 si no hay)."""
        return bisect_right(self.t, close_ms - BASE_MS) - 1

    def quote_volume(self, i: int, bars: int) -> float:
        """Volumen en USDT de las últimas `bars` velas hasta i (incluida)."""
        lo = max(0, i + 1 - bars)
        return self._qv_prefix[i + 1] - self._qv_prefix[lo]


def _cache_path(cache_dir: str, symbol: str) -> str:
    return os.path.join(cache_dir, f"{symbol}_{BASE_INTERVAL}.csv")


def _read_cache(path: str) -> List[Tuple[int, float, float, float, float, float]]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.reader(f):
            if not r or r[0] == "open_time":
                continue
            rows.append((int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    return rows


def _write_cache(path: str, rows: List[Tuple[int, float, float, float, float, float]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["open_time", "open", "high", "low", "close", "quote_volume"])
        for r in rows:
            w.writerow([r[0], repr(r[1]), repr(r[2]), repr(r[3]), repr(r[4]), repr(r[5])])


def _download_range(symbol: str, start_ms: int, end_ms: int, base: str = FAPI_BASE) -> List[Tuple[int, float, float, float, float, float]]:
    rows: List[Tuple[int, float, float, float, float, float]] = []
    cursor = start_ms
    while cursor < end_ms:
        data = _http_get_json("/fapi/v1/klines", {
            "symbol": symbol, "interval": BASE_INTERVAL,
            "startTime": cursor, "endTime": end_ms, "limit": _KLINES_LIMIT,
        }, base=base)
        if not data:
            break
        for k in data:
            rows.append((int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])))
        next_cursor = int(data[-1][0]) + BASE_MS
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(data) < _KLINES_LIMIT:
            break
        time.sleep(0.12)  # holgura frente al rate limit público
    return rows


def load_bars(symbol: str, start_ms: int, end_ms: int, cache_dir: str,
              offline: bool = False, base_url: str = FAPI_BASE) -> Bars:
    """
    Velas de 5 min de `symbol` en [start_ms, end_ms). Usa la caché en disco y
    descarga solo lo que falte por delante o por detrás. `base_url` permite
    bajar las velas del exchange demo (usar entonces otro `cache_dir`).
    """
    path = _cache_path(cache_dir, symbol)
    cached = _read_cache(path)
    by_time = {r[0]: r for r in cached}
    if not offline:
        first = min(by_time) if by_time else None
        last = max(by_time) if by_time else None
        missing: List[Tuple[int, int]] = []
        if first is None:
            missing.append((start_ms, end_ms))
        else:
            if start_ms < first - BASE_MS:
                missing.append((start_ms, first))
            if end_ms > last + 2 * BASE_MS:
                missing.append((last + BASE_MS, end_ms))
        for lo, hi in missing:
            try:
                downloaded = _download_range(symbol, lo, hi, base_url)
            except RuntimeError:
                downloaded = []  # símbolo inexistente en ese exchange
            for r in downloaded:
                by_time[r[0]] = r
        if missing:
            _write_cache(path, sorted(by_time.values()))
    rows = [r for t, r in by_time.items() if start_ms <= t < end_ms]
    return Bars(rows)


# ---------------------------------------------------------------------------
# Filtros del exchange y universo
# ---------------------------------------------------------------------------

def _parse_filters(symbol_info: Dict[str, Any]) -> Dict[str, Decimal]:
    out = {"tick_size": Decimal("0.01"), "step_size": Decimal("0.001"), "min_notional": Decimal("5")}
    for f in symbol_info.get("filters", []):
        ft = f.get("filterType")
        if ft == "PRICE_FILTER":
            out["tick_size"] = Decimal(f["tickSize"])
        elif ft == "LOT_SIZE":
            out["step_size"] = Decimal(f["stepSize"])
        elif ft in ("MIN_NOTIONAL", "NOTIONAL"):
            raw = f.get("notional", f.get("minNotional"))
            if raw is not None:
                out["min_notional"] = Decimal(str(raw))
    return out


def load_exchange_filters(cache_dir: str, offline: bool = False,
                          max_age_hours: float = 24.0) -> Dict[str, Dict[str, Decimal]]:
    """
    tick_size / step_size / min_notional de mainnet por símbolo (perpetuos USDT
    en TRADING). Son los filtros de HOY aplicados a toda la historia: una
    aproximación razonable, los mínimos cambian poco.
    """
    path = os.path.join(cache_dir, "exchange_filters.json")
    fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_hours * 3600
    if offline or fresh:
        if not os.path.exists(path):
            raise RuntimeError("Modo offline sin exchange_filters.json en la caché")
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        info = _http_get_json("/fapi/v1/exchangeInfo")
        raw = {}
        for s in info.get("symbols", []):
            if (s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL"
                    and s.get("quoteAsset") == "USDT"):
                raw[s["symbol"]] = {k: str(v) for k, v in _parse_filters(s).items()}
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f)
    return {sym: {k: Decimal(v) for k, v in flt.items()} for sym, flt in raw.items()}


def top_symbols_by_volume(n: int, filters: Dict[str, Dict[str, Decimal]]) -> List[str]:
    """
    Los `n` perpetuos USDT con más volumen en las últimas 24 h (HOY). Ojo: usar
    el ranking actual sobre el pasado introduce sesgo de supervivencia en el
    universo; preferir una lista explícita de símbolos cuando importe.
    """
    tickers = _http_get_json("/fapi/v1/ticker/24hr")
    ranked = sorted(
        (t for t in tickers if t.get("symbol") in filters),
        key=lambda t: float(t.get("quoteVolume") or 0), reverse=True,
    )
    return [t["symbol"] for t in ranked[:n]]


# ---------------------------------------------------------------------------
# Mercado histórico
# ---------------------------------------------------------------------------

class _Aggregated:
    """Velas de un timeframe mayor, agregadas desde las de 5 min."""

    __slots__ = ("first_idx", "candles", "_decimals")

    def __init__(self, bars: Bars, tf_ms: int):
        self.first_idx: List[int] = []          # índice 5m donde empieza cada vela
        self.candles: List[List[float]] = []    # [o, h, l, c]
        current_bucket = None
        for i, t in enumerate(bars.t):
            bucket = t // tf_ms
            if bucket != current_bucket:
                current_bucket = bucket
                self.first_idx.append(i)
                self.candles.append([bars.o[i], bars.h[i], bars.l[i], bars.c[i]])
            else:
                c = self.candles[-1]
                if bars.h[i] > c[1]:
                    c[1] = bars.h[i]
                if bars.l[i] < c[2]:
                    c[2] = bars.l[i]
                c[3] = bars.c[i]
        self._decimals: Dict[int, Dict[str, Decimal]] = {}

    def closed_decimal(self, k: int) -> Dict[str, Decimal]:
        d = self._decimals.get(k)
        if d is None:
            o, h, l, c = self.candles[k]
            d = {"open": _dec(o), "high": _dec(h), "low": _dec(l), "close": _dec(c)}
            self._decimals[k] = d
        return d


def _dec(x: float) -> Decimal:
    return Decimal(repr(x))


class HistoricalMarket:
    """Velas + filtros de varios símbolos, consultables "a la hora t"."""

    def __init__(self, bars: Dict[str, Bars], filters: Dict[str, Dict[str, Decimal]],
                 volume_bars: Optional[Dict[str, Bars]] = None):
        self.bars = bars
        self.filters = filters
        # El selector de pares mide el volumen SIEMPRE en mainnet (pair_selector
        # usa fapi.binance.com), aunque los precios vengan del demo.
        self.volume_bars = volume_bars if volume_bars is not None else bars
        self._agg: Dict[Tuple[str, str], _Aggregated] = {}

    def _aggregated(self, symbol: str, interval: str) -> _Aggregated:
        key = (symbol, interval)
        agg = self._agg.get(key)
        if agg is None:
            agg = _Aggregated(self.bars[symbol], INTERVAL_MS[interval])
            self._agg[key] = agg
        return agg

    def price(self, symbol: str, now_ms: int) -> Optional[float]:
        b = self.bars.get(symbol)
        if b is None:
            return None
        i = b.index_at(now_ms)
        return b.c[i] if i >= 0 else None

    def klines_asof(self, symbol: str, interval: str, limit: int,
                    now_ms: int) -> Optional[List[Dict[str, Decimal]]]:
        """
        Últimas `limit` velas de `interval` vistas a `now_ms`: las cerradas más
        la que está en formación (agregada solo con las velas de 5 min ya
        cerradas). Mismo formato que `BinanceClient.get_klines()`.
        """
        b = self.bars.get(symbol)
        if b is None or interval not in INTERVAL_MS:
            return None
        i = b.index_at(now_ms)
        if i < 0:
            return None
        agg = self._aggregated(symbol, interval)
        k = bisect_right(agg.first_idx, i) - 1
        start = agg.first_idx[k]
        forming = {
            "open": _dec(b.o[start]),
            "high": _dec(max(b.h[start:i + 1])),
            "low": _dec(min(b.l[start:i + 1])),
            "close": _dec(b.c[i]),
        }
        lo = max(0, k - (limit - 1))
        out = [agg.closed_decimal(j) for j in range(lo, k)]
        out.append(forming)
        return out

    def volume_24h(self, symbol: str, now_ms: int) -> float:
        b = self.volume_bars.get(symbol)
        if b is None:
            return 0.0
        i = b.index_at(now_ms)
        return b.quote_volume(i, 288) if i >= 0 else 0.0


class HistClient:
    """
    Sustituto de `BinanceClient` para `auto_derive_params` / `pair_selector`:
    responde klines y filtros a la hora simulada `now_ms`.
    """

    def __init__(self, market: HistoricalMarket):
        self.market = market
        self.now_ms = 0

    async def get_klines(self, symbol: str, interval: str = "4h", limit: int = 15):
        return self.market.klines_asof(symbol, interval, limit, self.now_ms)

    async def get_symbol_filters(self, symbol: str):
        return self.market.filters.get(symbol)
