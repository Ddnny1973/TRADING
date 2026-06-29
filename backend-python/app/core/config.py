"""
Configuration management for Grid Trading Backend
Uses Pydantic Settings for environment variable validation
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # ==========================================
    # BINANCE API CONFIGURATION
    # ==========================================
    BINANCE_API_KEY: str
    BINANCE_API_SECRET: str
    BINANCE_TESTNET_URL: str = "https://testnet.binancefuture.com"
    BINANCE_RECV_WINDOW: int = 5000
    
    # ==========================================
    # FASTAPI CONFIGURATION
    # ==========================================
    FASTAPI_HOST: str = "0.0.0.0"
    FASTAPI_PORT: int = 8000
    DEBUG_MODE: bool = False
    LOG_LEVEL: str = "INFO"
    
    # ==========================================
    # REDIS CONFIGURATION
    # ==========================================
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: Optional[str] = None
    
    # ==========================================
    # POSTGRESQL CONFIGURATION
    # ==========================================
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    
    # ==========================================
    # API RATE LIMITING
    # ==========================================
    API_RATE_LIMIT_THRESHOLD: int = 1200  # Binance default per minute
    
    # ==========================================
    # GRID TRADING DEFAULTS
    # ==========================================
    DEFAULT_GRID_SYMBOL: str = "BTCUSDT"
    DEFAULT_GRID_LEVELS: int = 10
    DEFAULT_GRID_TYPE: str = "GEOMETRIC"  # GEOMETRIC or ARITHMETIC
    
    # ==========================================
    # NOTIFICATION CONFIGURATION
    # ==========================================
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    WHATSAPP_API_URL: Optional[str] = None
    WHATSAPP_API_KEY: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def REDIS_URL_FULL(self) -> str:
        """Generate Redis connection URL"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    @property
    def POSTGRES_URL(self) -> str:
        """Generate PostgreSQL connection URL"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


# Load settings
settings = Settings()
