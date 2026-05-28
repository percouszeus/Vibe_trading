# 🇮🇳 Vibe Trading India

> **Fully autonomous AI paper trader for Indian markets (NSE/BSE/NFO)**
> Running 24/7 on OCI Free Tier · Zero cost · Self-improving · Production-grade

[![Deployed on OCI](https://img.shields.io/badge/Deployed-OCI%20Free%20Tier-orange?logo=oracle)](https://cloud.oracle.com/free)
[![Mode](https://img.shields.io/badge/Mode-PAPER%20TRADING-blue)](/)
[![Capital](https://img.shields.io/badge/Capital-%E2%82%B91%2C00%2C000-green)](/)
[![LLM](https://img.shields.io/badge/LLM-NVIDIA%20NIM%20%2B%20OpenRouter-76b900?logo=nvidia)](/)

---

## What This Is

An autonomous AI trading system that:
- **Analyzes** the top 5 NIFTY 50 stocks every morning using a 7-agent debate pipeline
- **Places** paper orders with real-world position sizing and margin rules
- **Tracks** P&L, drawdown, win rate, and Sharpe ratio over time
- **Self-improves** nightly via LLM reflection and walk-forward backtesting
- **Graduates** to live trading automatically when performance thresholds are met
- **Never sleeps** — running as a systemd daemon on an OCI ARM VM in the cloud

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         OCI Free Tier ARM VM                              │
│                   (4 OCPU · 24 GB RAM · Ubuntu 22.04)                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    Orchestrator (daily_cycle.py)                     │  │
│  │                    10-Phase State Machine Daemon                     │  │
│  └─────────┬───────────────────────┬────────────────────┬──────────────┘  │
│            │                       │                    │                  │
│  ┌─────────▼──────────┐  ┌────────▼────────┐  ┌───────▼──────────────┐  │
│  │  india-trade-cli   │  │ Capital Manager  │  │   Logic Auditor      │  │
│  │  7-Agent Pipeline  │  │  50/25/25 Split  │  │  StateAuditor engine │  │
│  │                    │  │  Kelly Sizing     │  │  Gap detection       │  │
│  │ • TechnicalAnalyst │  │  Margin tracking  │  │  Silent failure logs │  │
│  │ • FundamentalAnalyst│  └─────────────────┘  └──────────────────────┘  │
│  │ • OptionsAnalyst   │                                                    │
│  │ • NewsMacroAnalyst │  ┌─────────────────┐  ┌──────────────────────┐   │
│  │ • SentimentAnalyst │  │   PaperBroker   │  │  System Monitor      │   │
│  │ • BullResearcher   │  │  Persistent P&L  │  │  API usage tracker   │   │
│  │ • BearResearcher   │  │  Real margin sim │  │  Audit log analyzer  │   │
│  │ • FundManager      │  │  Order fills     │  └──────────────────────┘   │
│  └────────────────────┘  └─────────────────┘                              │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                         LLM Failover Chain                                 │
│                                                                            │
│  ① NVIDIA NIM: openai/gpt-oss-120b          (primary, 35 req/min)        │
│      ↓ fails                                                               │
│  ② NVIDIA NIM: nvidia/nemotron-3-super-120b  (failover 1, reasoning)      │
│      ↓ fails                                                               │
│  ③ NVIDIA NIM: minimaxai/minimax-m2.7        (failover 2, lightweight)    │
│      ↓ fails                                                               │
│  ④ OpenRouter:  deepseek/deepseek-r1         (last resort, 50 req/day)    │
│                 [rate-limited: 15/min, 50/day — persistent quota tracker] │
├──────────────────────────────────────────────────────────────────────────┤
│                           Market Data Layer                                │
│    Zerodha Kite Connect  ·  yfinance fallback  ·  NSE options chain       │
│    FII/DII flows  ·  Market breadth  ·  Bulk/block deals  ·  Events       │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## The 7-Agent Analysis Pipeline

Each stock goes through a structured multi-agent debate before a trade decision is made:

```
Phase 1 — Analyst Team (pure Python, no LLM, runs in parallel)
────────────────────────────────────────────────────────────────
 Technical   Fundamental   Options   News/Macro   Sentiment   ML Ensemble
    │              │           │          │             │           │
    └──────────────┴───────────┴──────────┴─────────────┴───────────┘
                                     │
                            AnalystReport[]  (structured data)

Phase 2 — Debate (LLM, 5 calls per stock)
──────────────────────────────────────────
 Bull Researcher ←── debate ──→ Bear Researcher
    Round 1: bull case  +  bear counter
    Round 2: bull rebuttal  +  bear rebuttal
    Facilitator: weighs arguments, identifies winner

Phase 3 — Synthesis (LLM, 1 call per stock)
─────────────────────────────────────────────
 Fund Manager → final verdict + entry/stop/target + position size

Total LLM calls per stock: ~8 calls  ·  Per full cycle: ~40 calls/day
All within free-tier NIM quota (35 req/min)
```

---

## Daily Cycle (10 Phases)

| IST Time | Phase | What Happens |
|----------|-------|--------------|
| 08:45 | **Pre-Market** | FII/DII flows, global cues, sector heat, morning brief |
| 09:15 | **Analysis** | 7-agent deep analysis of top 5 NIFTY50 stocks |
| 09:30 | **Execute** | Kelly-sized paper orders via PaperBroker with margin rules |
| 12:30 | **Mid-Day** | Position review, risk alerts, dynamic stop adjustments |
| 15:15 | **EOD** | Square off intraday, daily P&L summary |
| 15:30 | **💰 Capital Split** | 50% reinvest → 25% AI fund → 25% owner |
| 16:00 | **Auto-Improve** | LLM reflection + walk-forward backtest + strategy promotion |
| 17:00 | **Auto-Heal** | Service health, data quality, fallback chain verification |
| 17:30 | **📱 Report** | Full daily report via Telegram |
| 18:00 | **🎓 Graduation Check** | Evaluate paper→live transition eligibility |

---

## Capital & Risk Engine

### 50/25/25 Profit Split
```
PROFIT DAY  → +₹12,450
  ├── 50% → ₹6,225   reinvested (compounding principal)
  ├── 25% → ₹3,112   AI improvement fund
  └── 25% → ₹3,112   owner withdrawal

LOSS DAY    → -₹5,000
  └── 100% absorbed by principal only
      AI fund and owner are NEVER debited on loss days
```

### Position Sizing (Kelly Criterion)
- Fractional Kelly (0.25×) applied to every trade
- Max single position: 20% of capital
- Max portfolio: 5 concurrent positions
- Daily loss limit: 3% of capital
- Emergency stop: 15% drawdown

### PaperBroker (Realistic Simulation)
- Persistent state at `~/.trading_platform/paper_portfolio.json`
- Real margin calculations (equity + F&O)
- Limit order fill simulation with slippage
- Separate tracking of available vs margin-blocked capital

---

## Logic Auditing System

Every phase of the daily cycle is fully traced:

```
~/.trading_platform/audit_logs/state_YYYY-MM-DD.audit
```

The `StateAuditor` engine records:
- **Phase snapshots**: exact state at start/end of each phase
- **Signal flow**: how many symbols were analyzed vs executed
- **Order traces**: why each order was OPEN / FILLED / REJECTED
- **Gap detection**: auto-flags if analysis produces 0 executions (silent failure)

Run the logic gap report anytime:
```bash
python orchestrator/system_monitor.py
```

---

## Live Trading Graduation Path

```
PAPER → SHADOW → MICRO_LIVE → FULL_LIVE

All criteria must hold for 60+ consecutive trading days:
  ✅ Win rate          ≥ 50%
  ✅ Sharpe ratio      ≥ 1.0
  ✅ Max drawdown      ≤ 10%
  ✅ Profit factor     ≥ 1.5
  ✅ Model accuracy    ≥ 55%

Micro-live: ₹10,000 real capital with Zerodha Kite
Full live:  ₹1,00,000 capital, all auto-approved trades
```

---

## LLM Failover Chain (Smart & Rate-Limited)

The system uses 4 LLM providers in priority order:

| # | Provider | Model | Context | Limit | Cost |
|---|----------|-------|---------|-------|------|
| 1 | **NVIDIA NIM** | `openai/gpt-oss-120b` | 128k | 35 req/min | Free |
| 2 | **NVIDIA NIM** | `nvidia/nemotron-3-super-120b-a12b` | 128k | 35 req/min | Free |
| 3 | **NVIDIA NIM** | `minimaxai/minimax-m2.7` | 32k | 35 req/min | Free |
| 4 | **OpenRouter** | `deepseek/deepseek-r1` | 164k | **15/min, 50/day** | Free |

**OpenRouter quota is persistent** — usage is tracked in `~/.trading_platform/openrouter_usage.json` and survives service restarts. When daily quota is hit, the system logs it and stops rather than burning tokens silently.

Failover logs are clearly visible:
```
⚡ Failing over to model: nvidia/nemotron-3-super-120b-a12b
⚡ All NIM models failed — OpenRouter: deepseek/deepseek-r1 (quota left: 43/day, 15/min)
✗ OpenRouter skipped — daily limit reached (50/day). Resets at midnight UTC.
```

---

## Project Structure

```
Vibe_trading/
├── orchestrator/                  # 🧠 Core orchestration system
│   ├── daily_cycle.py             # 10-phase state machine daemon
│   ├── config.py                  # Typed configuration loader
│   ├── capital_manager.py         # 50/25/25 profit split engine
│   ├── ai_fund_manager.py         # AI self-improvement fund tracker
│   ├── strategy_portfolio.py      # Multi-strategy + Kelly sizing
│   ├── live_graduation.py         # Paper → Live transition evaluator
│   ├── options_flow.py            # PCR / OI / IV options intelligence
│   ├── telegram_dashboard.py      # Daily report via Telegram
│   ├── market_data.py             # Free market data abstraction layer
│   ├── sentiment_engine.py        # "What moved the candle?" analyzer
│   ├── walk_forward.py            # 15-split walk-forward backtester
│   ├── system_monitor.py          # API usage + logic gap analyzer
│   └── audit.py                   # StateAuditor engine (logic tracing)
│
├── india-trade-cli/               # 🤖 7-agent analysis engine (submodule)
│   ├── agent/
│   │   ├── core.py                # OpenAI provider + 4-layer failover chain
│   │   ├── multi_agent.py         # 7-agent pipeline (debate + synthesis)
│   │   └── prompts.py             # All LLM prompt templates
│   ├── engine/
│   │   ├── paper.py               # PaperBroker with realistic simulation
│   │   └── risk_limits.py         # Daily/weekly loss limit enforcement
│   ├── market/
│   │   ├── flow_intel.py          # FII/DII flow signal engine
│   │   └── events.py              # Earnings, expiry, RBI calendar
│   └── brokers/
│       ├── zerodha.py             # Zerodha Kite Connect integration
│       └── mock.py                # MockBroker for headless fallback
│
├── scripts/
│   ├── validate_setup.py          # Pre-flight environment checker
│   └── setup_kite.py              # Zerodha token refresh helper
│
├── .env.oci                       # OCI deployment configuration template
├── vibe_trading.service           # systemd unit file
├── deploy_oci.sh                  # One-shot OCI deployment script
└── docker-compose.yml             # Docker Compose alternative
```

---

## Deployment (OCI Free Tier)

### Prerequisites
- OCI Free Tier account (Ampere ARM VM, 4 OCPU, 24 GB RAM)
- [NVIDIA NIM API key](https://build.nvidia.com) — free, no credit card
- [OpenRouter API key](https://openrouter.ai) — free tier
- Optional: [Zerodha Kite](https://kite.trade) developer account for live market data

### Deploy

```bash
# On your OCI VM
git clone https://github.com/percouszeus/Vibe_trading ~/Vibe_trading
cd ~/Vibe_trading

# Fill in your API keys
cp .env.oci .env
nano .env  # add NIM_API_KEY, OPENROUTER_API_KEY

# Install and start
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e india-trade-cli/

# Validate setup
python scripts/validate_setup.py

# Run as systemd daemon
sudo cp vibe_trading.service /etc/systemd/system/
sudo systemctl enable --now vibe_trading

# Watch logs
sudo journalctl -u vibe_trading -f
```

### Monitor

```bash
# Live logs
sudo journalctl -u vibe_trading -f

# Logic gap report
python orchestrator/system_monitor.py

# Paper portfolio status
cat ~/.trading_platform/paper_portfolio.json

# Audit logs
ls ~/.trading_platform/audit_logs/
cat ~/.trading_platform/audit_logs/state_$(date +%Y-%m-%d).audit

# OpenRouter quota remaining
cat ~/.trading_platform/openrouter_usage.json
```

---

## Manual Commands

```bash
# Run a specific phase manually
python -m orchestrator.daily_cycle --phase premarket
python -m orchestrator.daily_cycle --phase analysis
python -m orchestrator.daily_cycle --phase capital_split
python -m orchestrator.daily_cycle --phase graduation_check

# Capital management
python -m orchestrator.capital_manager status
python -m orchestrator.capital_manager report
python -m orchestrator.capital_manager simulate 12450   # simulate ₹12,450 profit day

# Walk-forward backtest (historical analysis)
python -m orchestrator.walk_forward

# Options intelligence
python -m orchestrator.options_flow

# AI fund evaluation
python -m orchestrator.ai_fund_manager evaluate

# india-trade-cli directly
cd india-trade-cli
trade analyze RELIANCE
trade analyze TCS --exchange NSE
trade morning-brief
trade portfolio
trade risk-report
```

---

## Configuration Reference (`.env`)

```bash
# Trading mode — NEVER change to LIVE without graduating
TRADING_MODE=PAPER
TOTAL_CAPITAL=1000000       # ₹10 lakh starting capital
DEFAULT_RISK_PCT=2          # 2% risk per trade

# Primary LLM (NVIDIA NIM)
NIM_API_KEY=nvapi-...
NIM_MODEL=openai/gpt-oss-120b

# Final-resort failover (OpenRouter free tier: 15/min, 50/day)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=deepseek/deepseek-r1

# Broker (optional — uses PaperBroker if not set)
KITE_API_KEY=...
KITE_API_SECRET=...

# Graduation thresholds
GRAD_MIN_TRADING_DAYS=60
GRAD_MIN_WIN_RATE=0.50
GRAD_MIN_SHARPE=1.0
GRAD_MAX_DRAWDOWN=10
GRAD_MIN_PROFIT_FACTOR=1.5

# Safety limits
DAILY_LOSS_LIMIT_PCT=0.03
WEEKLY_LOSS_LIMIT_PCT=0.05
EMERGENCY_STOP_DRAWDOWN=0.15
```

---

## Cost Breakdown

| Component | Usage | Cost |
|-----------|-------|------|
| OCI VM (4 OCPU, 24 GB ARM) | 24/7 daemon | **₹0** (Always Free) |
| NVIDIA NIM | Primary LLM (40 calls/day) | **₹0** (free credits) |
| OpenRouter | Emergency failover only | **₹0** (free tier) |
| Zerodha Kite | Market data (optional) | **₹0** (personal account) |
| yfinance | Market data fallback | **₹0** (open source) |
| **Total** | | **₹0/month** |

---

## Safety Guardrails

- 🔒 `TRADING_MODE=PAPER` is enforced — the orchestrator refuses to start in LIVE mode without explicit graduation
- 🛑 Daily loss limit: 3% of capital → auto-halt
- 🛑 Weekly loss limit: 5% of capital → auto-halt
- 🛑 Emergency stop: 15% drawdown → full shutdown
- 🔍 All paper trades logged to `~/.trading_platform/journal/`
- 🔍 Strategy sandboxing with AST validation (no `exec`, `eval`, `open`)
- 🔍 Logic auditing on every phase — silent failures are flagged automatically
- 💾 Persistent state — portfolio, journal, and audit logs survive restarts

---

## What's Running Right Now

The daemon is live on the OCI VM and:
- Running pre-market scan at 08:45 IST daily
- Analyzing 5 NIFTY50 stocks sequentially through the 7-agent pipeline
- Placing paper orders via the PaperBroker with ₹10,00,000 virtual capital
- Logging all decisions to `~/.trading_platform/audit_logs/`
- Connected to AI-Trader social platform (Agent ID: 8748)

---

*Built by [@percouszeus](https://github.com/percouszeus)*
