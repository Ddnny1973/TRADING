# API Endpoints Reference

## Base URL
```
http://localhost:8000
```

## Health & Status

### Health Check
```
GET /health
```
**Description:** Returns service health status for Docker healthcheck

**Response:**
```json
{
  "status": "healthy",
  "service": "grid-trading-backend",
  "version": "0.1.0"
}
```

### API Information
```
GET /
```
**Description:** Returns API metadata and documentation links

**Response:**
```json
{
  "service": "Grid Trading Hybrid - Backend",
  "status": "ready",
  "api_version": "v1",
  "docs": "/api/docs"
}
```

---

## Grid Trading Endpoints (Phase 1)

*The following endpoints are planned for Phase 1 implementation:*

### Create Grid
```
POST /api/v1/grids
```

### List Grids
```
GET /api/v1/grids
```

### Get Grid Details
```
GET /api/v1/grids/{grid_id}
```

### Cancel Grid
```
DELETE /api/v1/grids/{grid_id}
```

---

## Documentation

- **Swagger UI:** `/api/docs`
- **ReDoc:** `/api/redoc`
