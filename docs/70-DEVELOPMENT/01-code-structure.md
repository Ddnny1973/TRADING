# Code Structure - Anatomía del Backend

## Árbol de Directorios

```
backend-python/
├── app/
│   ├── __init__.py                 # Inicialización de módulo
│   ├── main.py                     # FastAPI + endpoints + lifespan
│   │
│   ├── core/                       # Configuración y seguridad
│   │   ├── __init__.py
│   │   ├── config.py               # Env vars, parámetros por defecto
│   │   ├── security.py             # HMAC-SHA256, validaciones
│   │   └── time_sync.py            # Sincronización de reloj Binance
│   │
│   ├── services/                   # Lógica de negocio
│   │   ├── __init__.py
│   │   ├── binance_client.py       # Wrapper de Binance API REST
│   │   ├── grid_service.py         # Orquestación de grids
│   │   ├── grid_engine.py          # Cálculos de grid (niveles, órdenes)
│   │   └── indicators.py           # ATR, SMA, PnL, validaciones
│   │
│   ├── database/                   # Persistencia
│   │   ├── __init__.py
│   │   ├── connection.py           # SQLite + PostgreSQL connection
│   │   ├── models.py               # Modelos SQLAlchemy/ORM
│   │   └── queries.py              # Queries SQL útiles
│   │
│   └── schemas/                    # Validación de input/output
│       ├── __init__.py
│       ├── grid.py                 # CreateGridRequest, GridResponse, etc.
│       ├── order.py                # OrderResponse, OrderStatus
│       └── account.py              # AccountResponse
│
├── tests/                          # Suite de tests
│   ├── __init__.py
│   ├── test_grid_service.py        # Tests de grid logic
│   ├── test_binance_client.py      # Tests de API wrapper
│   ├── test_indicators.py          # Tests de ATR, SMA
│   └── test_endpoints.py           # Tests de FastAPI endpoints
│
├── .env.example                    # Template de configuración
├── requirements.txt                # Python dependencies
├── docker-compose.yml              # Orquestación de contenedores
├── Dockerfile                      # Imagen de backend
├── grid_trading.db                 # SQLite (generado en runtime)
└── README.md                       # Este directorio

n8n-workflows/
├── workflow1-market-decision.json  # Workflow 1 importable
├── workflow2-monitor.json          # Workflow 2 importable
└── README.md                       # Guía de setup
```

---

## main.py - Punto de Entrada

### FastAPI Initialization
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Grid Trading API", version="1.0")

# CORS (permite que n8n conecte)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Inicialización al arranque"""
    initialize_database()
    initialize_binance_client()
    start_background_tasks()

@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza al apagar"""
    close_database()
    close_binance_client()
```

### Endpoints Principales (reales en app/main.py)
```python
@app.get("/health")
async def health_check() -> dict:
    """Health check simple"""

@app.get("/")
async def root() -> dict:
    """Info general + running_grids count"""

@app.get("/api/v1/market-analysis/{symbol}")
async def analyze_market(symbol: str, atr_period: int = 14, atr_multiplier: float = 2.0,
                         klines_interval: str = "4h", risk_pct: float = None, levels: int = None):
    """Analiza mercado: ATR, precios sugeridos, cantidad y viabilidad"""

@app.post("/api/v1/grids")
async def create_grid(request: GridRequest) -> GridDetailResponse:
    """Crea nueva grid con órdenes en Binance"""

@app.get("/api/v1/grids")
async def list_grids(status: str = None) -> List[GridResponse]:
    """Lista grids, filtrables por status (RUNNING, CANCELED, etc.)"""

@app.get("/api/v1/grids/{grid_id}")
async def get_grid(grid_id: str) -> GridDetailResponse:
    """Detalle de grid con órdenes"""

@app.post("/api/v1/grids/{grid_id}/refresh")
async def refresh_grid_orders(grid_id: str) -> GridDetailResponse:
    """Sync órdenes con Binance + replenish automático de fills"""

@app.get("/api/v1/grids/{grid_id}/pnl")
async def get_grid_pnl(grid_id: str) -> GridPnlResponse:
    """PnL realizado + unrealizado (neto, fees 0.02% deducidos)"""

@app.post("/api/v1/grids/{grid_id}/check-close")
async def check_close_grid(grid_id: str) -> GridCloseCheckResponse:
    """Evalúa SL/TP/EXPIRED y cierra si aplica"""

@app.delete("/api/v1/grids/{grid_id}")
async def cancel_grid(grid_id: str) -> GridDetailResponse:
    """Cancela todas las órdenes (cierre manual)"""
```

---

## core/config.py - Configuración

```python
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # Binance API
    BINANCE_API_KEY: str = Field(..., env="BINANCE_API_KEY")
    BINANCE_API_SECRET: str = Field(..., env="BINANCE_API_SECRET")
    BINANCE_TESTNET_URL: str = Field(
        default="https://demo-fapi.binance.com",
        env="BINANCE_TESTNET_URL"
    )
    
    # Grid Trading
    DEFAULT_RISK_PCT: float = Field(default=0.02)  # 2%
    DEFAULT_LEVERAGE: int = Field(default=1)        # Sin leverage
    DEFAULT_MARGIN_TYPE: str = Field(default="ISOLATED")
    MAX_CONCURRENT_GRIDS: int = Field(default=2)
    MIN_STEP_FEE_MULTIPLE: float = Field(default=5.0)
    
    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///grid_trading.db",
        env="DATABASE_URL"
    )
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

---

## services/binance_client.py - API Wrapper

```python
import aiohttp
import hmac
import hashlib
from datetime import datetime

class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.session = aiohttp.ClientSession()
    
    def _sign_request(self, query_string: str) -> str:
        """Firma HMAC-SHA256 para autenticación"""
        return hmac.new(
            self.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 100):
        """Obtiene velas históricas"""
        path = "/dapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "timestamp": int(datetime.now().timestamp() * 1000)
        }
        # Firmar y ejecutar request
        return await self._execute_request("GET", path, params)
    
    async def place_order(self, symbol: str, side: str, quantity: float, price: float):
        """Coloca una orden LIMIT"""
        path = "/dapi/v1/order"
        params = {
            "symbol": symbol,
            "side": side,  # BUY o SELL
            "type": "LIMIT",
            "quantity": quantity,
            "price": price,
            "timeInForce": "GTC",  # Good-Til-Cancelled
            "timestamp": int(datetime.now().timestamp() * 1000)
        }
        return await self._execute_request("POST", path, params)
    
    async def cancel_order(self, symbol: str, order_id: int):
        """Cancela una orden abierta"""
        path = "/dapi/v1/order"
        params = {
            "symbol": symbol,
            "orderId": order_id,
            "timestamp": int(datetime.now().timestamp() * 1000)
        }
        return await self._execute_request("DELETE", path, params)
    
    async def get_position(self, symbol: str):
        """Consulta posición abierta"""
        path = "/dapi/v1/positionRisk"
        params = {
            "symbol": symbol,
            "timestamp": int(datetime.now().timestamp() * 1000)
        }
        return await self._execute_request("GET", path, params)
    
    async def get_mark_price(self, symbol: str):
        """Mark price actual (para PnL)"""
        path = "/dapi/v1/premiumIndex"
        params = {"symbol": symbol}
        return await self._execute_request("GET", path, params)
    
    async def _execute_request(self, method: str, path: str, params: dict):
        """Ejecuta request HTTP con firma"""
        # Construir URL con query string
        # Firmar
        # Ejecutar con aiohttp
        # Retornar JSON
        pass

# Singleton global
binance_client = None

async def initialize_binance():
    global binance_client
    binance_client = BinanceClient(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        base_url=settings.BINANCE_TESTNET_URL
    )
```

---

## services/grid_service.py - Orquestación

```python
class GridService:
    def __init__(self, binance_client, db_session):
        self.binance = binance_client
        self.db = db_session
    
    async def create_grid(self, request: CreateGridRequest) -> GridResponse:
        """
        Crea una nueva grid:
        1. Valida parámetros
        2. Calcula órdenes (grid_engine)
        3. Coloca órdenes en Binance
        4. Guarda en BD
        """
        # Validaciones
        self._validate_grid_params(request)
        
        # Calcular órdenes
        orders = GridEngine.calculate_grid_orders(
            lower_price=request.lower_price,
            upper_price=request.upper_price,
            levels=request.levels,
            risk_pct=request.risk_pct
        )
        
        # Colocar en Binance
        binance_orders = []
        for order in orders:
            try:
                binance_order = await self.binance.place_order(
                    symbol=request.symbol,
                    side=order['side'],
                    quantity=order['quantity'],
                    price=order['price']
                )
                binance_orders.append(binance_order)
            except Exception as e:
                # Rollback: cancela órdenes ya colocadas
                for bo in binance_orders:
                    await self.binance.cancel_order(request.symbol, bo['orderId'])
                raise
        
        # Guardar en BD
        grid_id = self._generate_grid_id()
        grid = Grid(
            id=grid_id,
            symbol=request.symbol,
            status="RUNNING",
            lower_price=request.lower_price,
            upper_price=request.upper_price,
            levels=request.levels,
            created_at=datetime.now()
        )
        self.db.add(grid)
        
        for binance_order in binance_orders:
            order = Order(
                id=binance_order['orderId'],
                grid_id=grid_id,
                order_type=binance_order['side'],
                status="OPEN",
                quantity=binance_order['origQty'],
                price=binance_order['price'],
                created_at=datetime.now()
            )
            self.db.add(order)
        
        self.db.commit()
        
        return GridResponse(
            grid_id=grid_id,
            symbol=request.symbol,
            status="RUNNING",
            orders_created=len(binance_orders)
        )
    
    async def refresh_grid(self, grid_id: str):
        """Sincroniza órdenes con Binance"""
        grid = self.db.query(Grid).filter(Grid.id == grid_id).first()
        
        # Fetch órdenes abiertas de Binance
        binance_orders = await self.binance.get_open_orders(grid.symbol)
        
        # Actualizar BD
        for bo in binance_orders:
            order = self.db.query(Order).filter(Order.id == bo['orderId']).first()
            if order:
                order.status = "FILLED" if bo['status'] == 'FILLED' else "OPEN"
                order.executed_qty = bo['executedQty']
                order.avg_price = bo['avgPrice']
        
        self.db.commit()
    
    async def replenish_grid(self, grid_id: str):
        """Crea órdenes nuevas en fills"""
        grid = self.db.query(Grid).filter(Grid.id == grid_id).first()
        
        # Buscar órdenes FILLED sin su par
        filled_buys = self.db.query(Order).filter(
            Order.grid_id == grid_id,
            Order.order_type == "BUY",
            Order.status == "FILLED",
            ~Order.paired_sell_id.isnot(None)
        ).all()
        
        # Por cada FILLED BUY → crear SELL
        for buy_order in filled_buys:
            sell_price = buy_order.avg_price * 1.004  # +0.4%
            sell_order = await self.binance.place_order(
                symbol=grid.symbol,
                side="SELL",
                quantity=buy_order.executed_qty,
                price=sell_price
            )
            # Guardar en BD
            self.db.add(Order(
                id=sell_order['orderId'],
                grid_id=grid_id,
                order_type="SELL",
                status="OPEN",
                quantity=sell_order['origQty'],
                price=sell_order['price'],
                created_at=datetime.now()
            ))
        
        self.db.commit()
    
    async def close_grid(self, grid_id: str):
        """Cierra grid (cancela todo)"""
        grid = self.db.query(Grid).filter(Grid.id == grid_id).first()
        
        # Cancelar todas las órdenes OPEN
        open_orders = self.db.query(Order).filter(
            Order.grid_id == grid_id,
            Order.status == "OPEN"
        ).all()
        
        for order in open_orders:
            await self.binance.cancel_order(grid.symbol, order.id)
            order.status = "CANCELED"
        
        # Marcar grid como CLOSED
        grid.status = "CLOSED"
        grid.closed_at = datetime.now()
        
        self.db.commit()
```

---

## services/grid_engine.py - Cálculos

```python
class GridEngine:
    @staticmethod
    def calculate_grid_levels(
        lower_price: float,
        upper_price: float,
        levels: int,
        mode: str = "ARITHMETIC"
    ) -> list:
        """
        Calcula precios de niveles
        
        ARITHMETIC: espacios iguales en USDT
        GEOMETRIC: espacios iguales en %
        """
        if mode == "ARITHMETIC":
            step = (upper_price - lower_price) / (levels - 1)
            return [lower_price + step * i for i in range(levels)]
        else:  # GEOMETRIC
            ratio = (upper_price / lower_price) ** (1 / (levels - 1))
            return [lower_price * ratio ** i for i in range(levels)]
    
    @staticmethod
    def calculate_grid_orders(
        lower_price: float,
        upper_price: float,
        levels: int,
        risk_pct: float,
        balance: float = 10000
    ) -> list:
        """
        Calcula órdenes (cantidad, precio, side)
        """
        prices = GridEngine.calculate_grid_levels(lower_price, upper_price, levels)
        
        # Capital a arriesgar
        capital_to_risk = balance * risk_pct
        
        # Precio promedio
        avg_price = (lower_price + upper_price) / 2
        
        # Cantidad por orden (dividida entre BUYs)
        buy_levels = len([p for p in prices if p <= avg_price])
        quantity_per_order = capital_to_risk / (buy_levels * avg_price)
        
        # Crear órdenes
        orders = []
        for price in prices:
            if price <= avg_price:
                orders.append({
                    "side": "BUY",
                    "price": price,
                    "quantity": quantity_per_order
                })
            else:
                orders.append({
                    "side": "SELL",
                    "price": price,
                    "quantity": quantity_per_order
                })
        
        return orders
```

---

## database/models.py - Esquema

```python
from sqlalchemy import Column, String, Float, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Grid(Base):
    __tablename__ = "grids"
    
    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False)
    status = Column(String, nullable=False)  # RUNNING, CLOSED, CANCELED
    lower_price = Column(Float)
    upper_price = Column(Float)
    levels = Column(Integer)
    pnl_realized = Column(Float, default=0.0)
    created_at = Column(DateTime)
    closed_at = Column(DateTime, nullable=True)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(String, primary_key=True)
    grid_id = Column(String, nullable=False)  # FK to Grid
    order_type = Column(String)  # BUY, SELL
    status = Column(String)  # OPEN, FILLED, CANCELED
    quantity = Column(Float)
    price = Column(Float)
    executed_qty = Column(Float, default=0.0)
    avg_price = Column(Float, nullable=True)
    created_at = Column(DateTime)
    executed_at = Column(DateTime, nullable=True)

class PnLHistory(Base):
    __tablename__ = "pnl_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    grid_id = Column(String)
    pnl_realized = Column(Float)
    pnl_unrealized = Column(Float)
    timestamp = Column(DateTime)
```

---

## schemas/ - Validación

```python
# Schemas reales en app/schemas/grid_schema.py

class GridRequest(BaseModel):
    symbol: str
    lower_price: Optional[float] = None  # Si omite, calcula por ATR
    upper_price: Optional[float] = None  # Si omite, calcula por ATR
    levels: int = Field(default=10)
    grid_type: str = Field(default="GEOMETRIC")
    quantity_per_order: float          # Obligatorio
    stop_loss: Optional[float] = None  # En USDT de PnL
    take_profit: Optional[float] = None
    atr_period: int = 14
    atr_multiplier: float = 2.0
    klines_interval: str = "4h"
    max_duration_hours: Optional[float] = None

class GridResponse(BaseModel):
    id: str
    symbol: str
    status: str   # RUNNING, CLOSED, CANCELED
    lower_price: float
    upper_price: float
    levels: int
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    max_duration_hours: Optional[float] = None
    created_at: datetime

class MarketAnalysisResponse(BaseModel):
    symbol: str
    current_price: float
    atr: float
    suggested_lower_price: float
    suggested_upper_price: float
    suggested_range: float
    suggested_quantity_per_order: Optional[float] = None  # Solo si levels pasado
    allocated_capital: Optional[float] = None             # Solo si levels pasado
    suggested_stop_loss: Optional[float] = None           # Solo si levels pasado
    min_viable_quantity: Optional[float] = None           # Solo si levels pasado
    grid_viable: Optional[bool] = None                    # Solo si levels pasado
    required_risk_pct: Optional[float] = None             # Solo si levels pasado
```

---

Ver también: [Testing Strategy](02-testing-strategy.md)
