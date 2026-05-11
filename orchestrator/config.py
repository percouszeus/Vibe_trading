"""
orchestrator/config.py
──────────────────────
Central configuration loader for the Vibe Trading India orchestrator.
Loads from .env at project root and provides typed access to all settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class LLMConfig:
    """LLM provider configuration with fallback chain."""

    # Primary (Ollama self-hosted)
    primary_provider: str = "ollama"
    primary_model: str = "llama3.1:8b"
    primary_base_url: str = "http://localhost:11434/v1"

    # Fallback 1 (OpenRouter)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "deepseek/deepseek-v3.2"

    # Fallback 2 (NVIDIA NIM)
    nim_api_key: str = ""
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_model: str = "meta/llama-3.1-70b-instruct"

    temperature: float = 0.0
    timeout: int = 120
    max_retries: int = 2


@dataclass
class TradingConfig:
    """Paper trading parameters."""

    mode: str = "PAPER"  # PAPER or LIVE — NEVER change without review
    total_capital: float = 1_000_000.0
    risk_pct: float = 2.0
    stock_universe: str = "NIFTY50"
    max_daily_analyses: int = 5


@dataclass
class AutoImproveConfig:
    """Auto-improve cycle parameters."""

    backtest_lookback_days: int = 90
    improvement_threshold: float = 1.05  # promote if Sharpe improves by 5%+
    min_trades_for_drift: int = 5
    max_strategies_to_test: int = 3


@dataclass
class AutoHealConfig:
    """Auto-heal / self-healing parameters."""

    health_check_interval_min: int = 5
    max_consecutive_failures: int = 3
    restart_delay_sec: int = 30
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


@dataclass
class BrokerConfig:
    """Zerodha Kite / Fyers broker configuration."""

    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_mcp_url: str = "https://mcp.kite.trade/mcp"
    fyers_app_id: str = ""
    fyers_secret_key: str = ""


@dataclass
class Config:
    """Master configuration combining all sub-configs."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    auto_improve: AutoImproveConfig = field(default_factory=AutoImproveConfig)
    auto_heal: AutoHealConfig = field(default_factory=AutoHealConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    project_root: Path = PROJECT_ROOT


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        llm=LLMConfig(
            primary_provider=os.getenv("LANGCHAIN_PROVIDER", "ollama"),
            primary_model=os.getenv("LANGCHAIN_MODEL_NAME", "llama3.1:8b"),
            primary_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v3.2"),
            nim_api_key=os.getenv("NIM_API_KEY", ""),
            nim_base_url=os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            nim_model=os.getenv("NIM_MODEL", "meta/llama-3.1-70b-instruct"),
            temperature=float(os.getenv("LANGCHAIN_TEMPERATURE", "0.0")),
            timeout=int(os.getenv("TIMEOUT_SECONDS", "120")),
            max_retries=int(os.getenv("MAX_RETRIES", "2")),
        ),
        trading=TradingConfig(
            mode=os.getenv("TRADING_MODE", "PAPER"),
            total_capital=float(os.getenv("TOTAL_CAPITAL", "1000000")),
            risk_pct=float(os.getenv("DEFAULT_RISK_PCT", "2")),
            stock_universe=os.getenv("STOCK_UNIVERSE", "NIFTY50"),
            max_daily_analyses=int(os.getenv("MAX_DAILY_ANALYSES", "5")),
        ),
        auto_improve=AutoImproveConfig(
            backtest_lookback_days=int(os.getenv("BACKTEST_LOOKBACK_DAYS", "90")),
            improvement_threshold=float(os.getenv("IMPROVEMENT_THRESHOLD", "1.05")),
        ),
        auto_heal=AutoHealConfig(
            health_check_interval_min=int(os.getenv("HEALTH_CHECK_INTERVAL", "5")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        ),
        broker=BrokerConfig(
            kite_api_key=os.getenv("KITE_API_KEY", ""),
            kite_api_secret=os.getenv("KITE_API_SECRET", ""),
            kite_mcp_url=os.getenv("KITE_MCP_URL", "https://mcp.kite.trade/mcp"),
            fyers_app_id=os.getenv("FYERS_APP_ID", ""),
            fyers_secret_key=os.getenv("FYERS_SECRET_KEY", ""),
        ),
    )
