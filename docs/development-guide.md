# Grid Trading Hybrid - Development Guide

## Setup Local Development

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Git

### Installation Steps

1. **Clone repository**
   ```bash
   git clone <repository-url>
   cd trading-grid-hybrid
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   # Edit .env with your Binance Testnet credentials
   ```

3. **Start Docker services**
   ```bash
   docker-compose up -d
   ```

4. **Check service health**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:5678  # n8n dashboard
   ```

## API Endpoints

### Health Check
- `GET /health` - Service health status
- `GET /` - API root information

### Grid Trading (To be implemented)
- `POST /api/v1/grids` - Create new grid
- `GET /api/v1/grids` - List active grids
- `GET /api/v1/grids/{id}` - Get grid details
- `DELETE /api/v1/grids/{id}` - Stop grid

## Testing

Run tests with pytest:
```bash
pytest tests/
```

## Documentation

- [Architecture](./arquitectura.md)
- [API Reference](./api-endpoints.md)
- [Database Schema](./database-schema.md)
