# Testing Strategy

## Test Suite Overview

54 tests unitarios + integración que validan:
- ✅ Grid creation logic
- ✅ Order calculations
- ✅ Risk validations
- ✅ Binance API integration
- ✅ Database persistence
- ✅ Endpoint responses

---

## Ejecutar Tests

```bash
cd backend-python

# Todos los tests
pytest -v

# Tests específicos
pytest tests/test_grid_service.py -v
pytest tests/test_indicators.py::test_atr_calculation -v

# Con coverage
pytest --cov=app tests/

# Watch mode (re-run en cambios)
pytest-watch
```

---

## Test Modules

### test_grid_service.py
Validación de lógica de grid.

```python
def test_create_grid_valid():
    """Grid válida se crea correctamente"""
    request = CreateGridRequest(
        symbol="BTCUSDT",
        lower_price=62500,
        upper_price=65000,
        levels=15,
        risk_pct=0.02
    )
    response = grid_service.create_grid(request)
    assert response.status == "ACTIVE"
    assert response.orders_created == 15

def test_create_grid_step_too_small():
    """Grid con paso pequeño se rechaza"""
    request = CreateGridRequest(
        symbol="BTCUSDT",
        lower_price=62500,
        upper_price=62600,  # Rango muy pequeño
        levels=15,
        risk_pct=0.02
    )
    with pytest.raises(ValidationError):
        grid_service.create_grid(request)

def test_create_grid_max_grids_exceeded():
    """Al crear 3ª grid se rechaza (max 2)"""
    create_grid(request1)
    create_grid(request2)
    with pytest.raises(MaxGridsExceeded):
        create_grid(request3)

def test_replenish_grid():
    """Replenish crea SELL después de BUY ejecutado"""
    grid = create_grid(request)
    # Simular BUY ejecutado
    order = get_order(grid.id)
    order.status = "FILLED"
    
    replenish_result = grid_service.replenish_grid(grid.id)
    assert replenish_result.orders_replenished > 0

def test_close_grid():
    """Cierre de grid cancela todas las órdenes"""
    grid = create_grid(request)
    close_result = grid_service.close_grid(grid.id)
    assert close_result.status == "CLOSED"
    assert all(o.status == "CANCELED" for o in close_result.orders)
```

### test_indicators.py
Validación de cálculos técnicos.

```python
def test_atr_calculation():
    """ATR se calcula correctamente"""
    prices = [62500, 63000, 62700, 63500, 62600]
    atr = IndicatorsService.calculate_atr(prices, period=3)
    assert atr > 0
    assert isinstance(atr, float)

def test_sma_calculation():
    """SMA se calcula correctamente"""
    prices = [62500, 63000, 62700, 63500, 62600]
    sma = IndicatorsService.calculate_sma(prices, period=3)
    assert len(sma) == len(prices)
    assert all(isinstance(s, float) for s in sma)

def test_pnl_calculation():
    """PnL realizado se calcula con comisiones Binance (Fase 2: Rentabilidad)"""
    orders = [
        {"side": "BUY", "price": 62500, "quantity": 0.01, "status": "FILLED"},
        {"side": "SELL", "price": 62710, "quantity": 0.01, "status": "FILLED"},
    ]
    current_price = Decimal("62710")
    
    # calculate_grid_pnl now deducts fees (default fee_rate=0.0002 = 0.02% Binance)
    pnl = IndicatorsService.calculate_grid_pnl(
        orders, current_price, fee_rate=0.0002
    )
    # PnL neto debe ser menor que PnL bruto (por comisiones deducidas)
    gross_pnl = (62710 - 62500) * 0.01  # 2.1 USDT
    assert pnl["realized_pnl"] < gross_pnl  # Neto < Bruto
```

### test_binance_client.py
Validación de integración Binance.

```python
@pytest.mark.asyncio
async def test_binance_place_order(mock_binance):
    """place_order devuelve order_id válido"""
    result = await binance_client.place_order(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.01,
        price=62500
    )
    assert "orderId" in result
    assert result["status"] == "NEW"

@pytest.mark.asyncio
async def test_binance_get_klines(mock_binance):
    """get_klines devuelve datos formateados"""
    result = await binance_client.get_klines(
        symbol="BTCUSDT",
        interval="4h",
        limit=100
    )
    assert len(result) <= 100
    assert all("time" in k and "close" in k for k in result)

@pytest.mark.asyncio
async def test_binance_rate_limit(mock_binance):
    """Rate limit se respeta (reintento después de 60s)"""
    mock_binance.side_effect = RateLimitError()
    with pytest.raises(RateLimitError):
        await binance_client.get_klines(...)
```

### test_endpoints.py
Validación de API HTTP.

```python
@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)

def test_health_endpoint(client):
    """GET /health devuelve status healthy"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_grid_endpoint(client):
    """POST /create-grid crea grid"""
    payload = {
        "symbol": "BTCUSDT",
        "lower_price": 62500,
        "upper_price": 65000,
        "levels": 15,
        "risk_pct": 0.02
    }
    response = client.post("/create-grid", json=payload)
    assert response.status_code == 200
    assert "grid_id" in response.json()

def test_create_grid_invalid_params(client):
    """POST /create-grid con params inválidos falla"""
    payload = {
        "symbol": "BTCUSDT",
        "lower_price": 65000,
        "upper_price": 62500,  # upper < lower
        "levels": 15,
        "risk_pct": 0.02
    }
    response = client.post("/create-grid", json=payload)
    assert response.status_code == 400
    assert "error" in response.json()

def test_list_grids_endpoint(client):
    """GET /grids devuelve lista de grids"""
    response = client.get("/grids")
    assert response.status_code == 200
    assert "grids" in response.json()
```

---

## Mocking & Fixtures

```python
# conftest.py - Configuración compartida

@pytest.fixture
def mock_binance():
    """Mock de Binance API"""
    with patch('app.services.binance_client.BinanceClient') as mock:
        mock.place_order.return_value = {
            "orderId": "123456",
            "status": "NEW",
            "origQty": "0.01",
            "price": "62500"
        }
        yield mock

@pytest.fixture
def mock_db():
    """Mock de database"""
    with patch('app.database.connection.Session') as mock:
        yield mock

@pytest.fixture
def test_grid():
    """Grid de prueba"""
    return Grid(
        id="TEST_GRID_001",
        symbol="BTCUSDT",
        status="ACTIVE",
        lower_price=62500,
        upper_price=65000,
        levels=15,
        created_at=datetime.now()
    )
```

---

## Cobertura de Tests

```bash
# Ver cobertura
pytest --cov=app --cov-report=html tests/

# Abre coverage/index.html en navegador
# Busca áreas sin cobertura (líneas rojas)
```

### Objetivos
- ✅ > 80% cobertura general
- ✅ 100% en lógica crítica (validaciones, PnL)
- ✅ > 90% en servicios

---

## Test de Integración (E2E)

### test_full_scenario.py
Simula un ciclo completo.

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_grid_lifecycle():
    """
    Escenario completo:
    1. Crear grid
    2. Simular fills
    3. Replenish
    4. Cierre
    """
    # Crear grid
    grid = await grid_service.create_grid(request)
    assert grid.status == "ACTIVE"
    
    # Simular fill en BUY order
    binance_order = await mock_binance.get_order(...)
    binance_order['status'] = 'FILLED'
    
    # Refresh
    await grid_service.refresh_grid(grid.id)
    
    # Replenish
    await grid_service.replenish_grid(grid.id)
    
    # Verificar SELL creado
    sells = db.query(Order).filter(Order.order_type == "SELL").all()
    assert len(sells) > 0
    
    # Cierre
    await grid_service.close_grid(grid.id)
    assert grid.status == "CLOSED"
```

---

## CI/CD (GitHub Actions)

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - run: pip install -r backend-python/requirements.txt
      - run: pytest backend-python/tests/ -v --cov
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## Debugging Tests

```bash
# Run single test con output
pytest tests/test_grid_service.py::test_create_grid_valid -v -s

# Drop into debugger en fallo
pytest tests/ --pdb

# Verbose output
pytest tests/ -vv

# Mostrar print statements
pytest tests/ -s
```

---

## Pre-Commit Hooks

```bash
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest
        language: system
        types: [python]
        stages: [commit]
```

---

Ver también: [Code Structure](01-code-structure.md)
