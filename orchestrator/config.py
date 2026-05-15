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
class CapitalConfig:
    """Capital management — 50/25/25 profit split configuration."""

    initial_capital: float = 1_000_000.0
    reinvest_pct: float = 0.50         # 50% back to principal
    ai_fund_pct: float = 0.25          # 25% for AI improvements
    owner_pct: float = 0.25            # 25% for owner
    max_drawdown_pct: float = 15.0     # Circuit breaker: halt if exceeded
    min_trade_capital: float = 50_000   # Won't trade below this
    compounding_enabled: bool = True
    ai_auto_approve_limit: float = 500  # Auto-approve AI purchases up to ₹500


@dataclass
class GraduationConfig:
    """Paper → Live trading graduation criteria."""

    min_trading_days: int = 60
    min_win_rate: float = 0.50
    min_sharpe: float = 1.0
    max_drawdown_pct: float = 10.0
    min_profit_factor: float = 1.5
    max_consecutive_losses: int = 5
    min_model_accuracy: float = 0.55
    live_start_fraction: float = 0.10   # Start with 10% capital live
    scale_up_after_days: int = 20       # Add 10% every 20 profitable days
    daily_loss_limit_pct: float = 0.03  # Stop trading if -3% day
    weekly_loss_limit_pct: float = 0.05 # Stop trading if -5% week
    emergency_stop_drawdown: float = 0.15


@dataclass
class TelegramConfig:
    """Telegram dashboard configuration."""

    bot_token: str = ""
    chat_id: str = ""
    send_daily_report: bool = True
    send_trade_alerts: bool = True
    send_risk_alerts: bool = True


@dataclass
class AITraderConfig:
    """HKUDS AI-Trader Integration configuration."""

    email: str = ""
    password: str = ""



@dataclass
class Config:
    """Master configuration combining all sub-configs."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    auto_improve: AutoImproveConfig = field(default_factory=AutoImproveConfig)
    auto_heal: AutoHealConfig = field(default_factory=AutoHealConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    capital: CapitalConfig = field(default_factory=CapitalConfig)
    graduation: GraduationConfig = field(default_factory=GraduationConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    aitrader: AITraderConfig = field(default_factory=AITraderConfig)
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
        capital=CapitalConfig(
            initial_capital=float(os.getenv("INITIAL_CAPITAL", "1000000")),
            reinvest_pct=float(os.getenv("REINVEST_PCT", "50")) / 100.0,
            ai_fund_pct=float(os.getenv("AI_FUND_PCT", "25")) / 100.0,
            owner_pct=float(os.getenv("OWNER_PCT", "25")) / 100.0,
            max_drawdown_pct=float(os.getenv("MAX_DRAWDOWN_PCT", "15")),
            min_trade_capital=float(os.getenv("MIN_TRADE_CAPITAL", "50000")),
            ai_auto_approve_limit=float(os.getenv("AI_AUTO_APPROVE_LIMIT", "500")),
        ),
        graduation=GraduationConfig(
            min_trading_days=int(os.getenv("GRAD_MIN_TRADING_DAYS", "60")),
            min_win_rate=float(os.getenv("GRAD_MIN_WIN_RATE", "0.50")),
            min_sharpe=float(os.getenv("GRAD_MIN_SHARPE", "1.0")),
            max_drawdown_pct=float(os.getenv("GRAD_MAX_DRAWDOWN", "10")),
            min_profit_factor=float(os.getenv("GRAD_MIN_PROFIT_FACTOR", "1.5")),
            daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.03")),
            weekly_loss_limit_pct=float(os.getenv("WEEKLY_LOSS_LIMIT_PCT", "0.05")),
            emergency_stop_drawdown=float(os.getenv("EMERGENCY_STOP_DRAWDOWN", "0.15")),
        ),
        telegram=TelegramConfig(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            send_daily_report=os.getenv("TELEGRAM_DAILY_REPORT", "true").lower() == "true",
            send_trade_alerts=os.getenv("TELEGRAM_TRADE_ALERTS", "true").lower() == "true",
            send_risk_alerts=os.getenv("TELEGRAM_RISK_ALERTS", "true").lower() == "true",
        ),
        aitrader=AITraderConfig(
            email=os.getenv("AITRADER_EMAIL", ""),
            password=os.getenv("AITRADER_PASSWORD", ""),
        ),
    )
