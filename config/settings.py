"""
Enterprise Production Settings & Environment Configuration for Razorpay RiskIQ (Sentinel).
Uses pydantic-settings for strict type-safe environment configuration.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ENV: str = Field("development", description="Environment: development, staging, production")
    DEBUG: bool = Field(False, description="Debug mode flag")
    
    # API Server Config
    HOST: str = Field("0.0.0.0", description="API host IP binding")
    PORT: int = Field(8000, description="API port binding")
    WORKERS: int = Field(4, description="Uvicorn worker count for production")
    
    # Security & Anthropic Config
    ANTHROPIC_API_KEY: str = Field("", description="API key for Anthropic Claude API")
    SECRET_KEY: str = Field("razorpay_riskiq_secret_key_prod_2026", description="API secret key")
    RAZORPAY_WEBHOOK_SECRET: str = Field("rzp_webhook_secret_sandbox_2026", description="Razorpay webhook signature secret")
    
    # Redis Feature Store Config
    REDIS_HOST: str = Field("localhost", description="Redis host")
    REDIS_PORT: int = Field(6379, description="Redis port")
    REDIS_DB: int = Field(0, description="Redis DB index")
    REDIS_PASSWORD: str = Field("", description="Redis password")
    
    # Kafka Stream Config
    KAFKA_BOOTSTRAP_SERVERS: str = Field("localhost:9092", description="Kafka bootstrap servers")
    KAFKA_TOPIC_TRANSACTIONS: str = Field("riskiq.transactions.v1", description="Transaction stream topic")
    KAFKA_GROUP_ID: str = Field("riskiq-scoring-group", description="Kafka consumer group ID")
    
    # Risk Engine Threshold Policy
    SCORE_FLAG_THRESHOLD: float = Field(0.40, description="Threshold above which transaction triggers agent investigation")
    SCORE_BLOCK_THRESHOLD: float = Field(0.70, description="Threshold above which transaction is automatically blocked")
    FP_UNIT_COST_INR: float = Field(500.0, description="Estimated unit cost per false positive in INR")


# Global settings instance
settings = Settings()
