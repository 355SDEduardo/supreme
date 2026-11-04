"""Configuration settings for Portal Contabilidade."""
import os
from pydantic import BaseModel


class Settings(BaseModel):
    PROJECT_NAME: str = "Portal Contábil e BPO Financeiro"
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secure-secret-key-for-portalcontabilidades-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # Max 30 minutes inactivity session policy (DoD Feature 10)
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5  # Brute force protection policy
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./portal_contabil.db")
    
    # Security & KMS
    # 32-byte hex key for AES-256-GCM encryption in the digital certificate vault
    MASTER_ENCRYPTION_KEY: str = os.getenv(
        "MASTER_ENCRYPTION_KEY", 
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )
    
    # File storage
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./storage/uploads")


settings = Settings()
