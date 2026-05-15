# 🏦 Vibe Trading India v2

> **AI-powered autonomous paper trading for Indian markets (NSE/BSE/NFO)**
> Self-improving • Self-healing • 50/25/25 Profit Split • Zero cost

---

## 💰 Profit Distribution (50/25/25 Rule)

```
PROFIT DAY: +₹12,450
├── 50% → ₹6,225 reinvested to principal (compounding)
├── 25% → ₹3,112 to AI improvement fund (buy better models/data)
└── 25% → ₹3,112 to owner (your money)

LOSS DAY: -₹5,000
└── 100% absorbed by principal only (AI fund & owner never debited)
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                     OCI Free Tier ARM VM                              │
│               (4 OCPU · 24GB RAM · Ubuntu 22.04)                     │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐  │
│  │   Ollama     │  │ india-trade  │  │      Orchestrator v2       │  │
│  │ Llama 3.1 8B│→ │    -cli      │→ │  10-phase daily cycle      │  │
│  │ Qwen2.5 7B  │  │  7 AI agents │  │  capital_manager.py        │  │
│  └─────────────┘  └──────────────┘  │  ai_fund_manager.py        │  │
│         ↑                ↑           │  strategy_portfolio.py     │  │
│         │                │           │  live_graduation.py        │  │
│  ┌──────┴────────────────┴───┐      │  options_flow.py           │  │
│  │     Market Data Layer      │      │  telegram_dashboard.py     │  │
│  │  yfinance · NSE · Kite    │      └────────────────────────────┘  │
│  └────────────────────────────┘               ↓                      │
│                                    ┌────────────────────┐            │
│                                    │   Capital Engine    │            │
│                                    │  50% → Principal    │            │
│                                    │  25% → AI Fund      │            │
│                                    │  25% → Owner        │            │
│                                    └────────────────────┘            │
├──────────────────────────────────────────────────────────────────────┤
│                    External APIs (Free)                                │
│  Kite MCP (mcp.kite.trade) │ OpenRouter │ NVIDIA NIM │ Telegram      │
└──────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Option A: Direct Setup (OCI VM)

```bash
# 1. Clone this repo to your OCI VM
git clone <your-repo-url> ~/vibe-trading
cd ~/vibe-trading

# 2. Run setup script
chmod +x scripts/setup_oci.sh
./scripts/setup_oci.sh

# 3. Edit .env with your API keys
nano .env

# 4. Test health
python -m orchestrator.daily_cycle --health

# 5. Start daemon
sudo systemctl enable --now vibe-trading
```

### Option B: Docker Compose

```bash
docker compose up -d
docker compose logs -f orchestrator
```

## Daily Schedule (10 Phases)

| IST Time | Phase | What Happens |
|---|---|---|
| 08:45 | Pre-market | FII/DII flows, global cues, sector heat |
| 09:15 | Analysis | 7-agent deep analysis + multi-strategy signals |
| 09:30 | Execute | Kelly-sized paper orders with portfolio constraints |
| 12:30 | Mid-day | Position review, risk alerts, stop adjustments |
| 15:15 | EOD | Square off intraday, daily P&L summary |
| **15:30** | **💰 Capital Split** | **50/25/25 profit distribution** |
| 16:00 | Auto-improve | LLM reflection + AI fund spending evaluation |
| 17:00 | Auto-heal | Service health, data quality, fallback chain |
| **17:30** | **📱 Dashboard Report** | **Full daily report via Telegram** |
| **18:00** | **🎓 Graduation Check** | **Paper→Live transition evaluation** |

## Live Trading Graduation Path

```
PAPER → SHADOW → MICRO_LIVE → FULL_LIVE

Requirements (ALL must pass for 60+ trading days):
  ✅ Win rate ≥ 50%
  ✅ Sharpe ratio ≥ 1.0
  ✅ Max drawdown ≤ 10%
  ✅ Profit factor ≥ 1.5
  ✅ Model accuracy ≥ 55%
```

## Manual Commands

```bash
# Run specific phase
python -m orchestrator.daily_cycle --phase capital_split
python -m orchestrator.daily_cycle --phase graduation_check

# Capital management
python -m orchestrator.capital_manager status
python -m orchestrator.capital_manager report
python -m orchestrator.capital_manager simulate 12450

# AI fund
python -m orchestrator.ai_fund_manager evaluate
python -m orchestrator.ai_fund_manager history

# Graduation
python -m orchestrator.live_graduation

# Options intelligence
python -m orchestrator.options_flow
```

## Project Structure

```
vibe-trading/
├── .env                         # Master configuration
├── docker-compose.yml           # Container orchestration
├── orchestrator/                # 🧠 Core system
│   ├── daily_cycle.py           # 10-phase daily orchestrator
│   ├── config.py                # Typed config loader
│   ├── capital_manager.py       # 💰 50/25/25 profit split engine
│   ├── ai_fund_manager.py       # 🤖 AI self-improvement spending
│   ├── strategy_portfolio.py    # 📊 Multi-strategy + Kelly sizing
│   ├── live_graduation.py       # 🎓 Paper→Live transition
│   ├── options_flow.py          # 📈 Options intelligence (PCR/OI/IV)
│   ├── telegram_dashboard.py    # 📱 Telegram trading dashboard
│   ├── market_data.py           # Free market data layer
│   └── sentiment_engine.py      # "What moved the candle?" analyzer
├── core-engine/                 # HKUDS/Vibe-Trading (backtest + swarm)
├── india-trade-cli/             # hopit-ai/india-trade-cli (7-agent)
├── kite-mcp/                    # zerodha/kite-mcp-server (broker bridge)
├── docker/                      # Dockerfiles
└── scripts/                     # Setup + utility scripts
```

## Cost

| Component | Cost |
|---|---|
| OCI VM (4 OCPU, 24GB) | ₹0 (free tier) |
| Ollama + models | ₹0 (self-hosted) |
| Zerodha personal | ₹0 (free plan) |
| OpenRouter free tier | ₹0 |
| NVIDIA NIM free tier | ₹0 |
| **Total** | **₹0/month** |




---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OCI Free Tier ARM VM                      │
│              (4 OCPU · 24GB RAM · Ubuntu 22.04)             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   Ollama     │  │ india-trade  │  │   Orchestrator    │  │
│  │ Llama 3.1 8B│→ │    -cli      │→ │  (daily_cycle.py) │  │
│  │ Qwen2.5 7B  │  │  7 AI agents │  │  auto-improve     │  │
│  └─────────────┘  └──────────────┘  │  auto-heal         │  │
│         ↑                ↑           └───────────────────┘  │
│         │                │                    ↓              │
│  ┌──────┴────────────────┴────────────────────┴──────────┐  │
│  │              Trade Memory + Journal                    │  │
│  │         ~/.trading_platform/                           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                    External APIs (Free)                       │
│  Kite MCP (mcp.kite.trade) │ OpenRouter │ NVIDIA NIM         │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Option A: Direct Setup (OCI VM)

```bash
# 1. Clone this repo to your OCI VM
git clone <your-repo-url> ~/vibe-trading
cd ~/vibe-trading

# 2. Run setup script
chmod +x scripts/setup_oci.sh
./scripts/setup_oci.sh

# 3. Edit .env with your API keys
nano .env

# 4. Test health
python -m orchestrator.daily_cycle --health

# 5. Start daemon
sudo systemctl enable --now vibe-trading
```

### Option B: Docker Compose

```bash
# 1. Edit .env with your API keys
# 2. Start everything
docker compose up -d

# 3. Check logs
docker compose logs -f orchestrator
```

## Daily Schedule

| IST Time | Phase | What Happens |
|---|---|---|
| 08:45 | Pre-market | FII/DII flows, global cues, sector heat |
| 09:15 | Analysis | 7-agent deep analysis of top 5 NIFTY stocks |
| 09:30 | Execute | Paper orders placed via shadow broker |
| 12:30 | Mid-day | Position review, risk alerts, stop adjustments |
| 15:15 | EOD | Square off intraday, daily P&L summary |
| 16:00 | Auto-improve | LLM reflection → backtest → promote winners |
| 17:00 | Auto-heal | Service health, data quality, fallback chain |

## Manual Commands

```bash
# Run specific phase
python -m orchestrator.daily_cycle --phase premarket
python -m orchestrator.daily_cycle --phase analysis
python -m orchestrator.daily_cycle --phase auto_improve

# Run all phases sequentially
python -m orchestrator.daily_cycle --phase all

# Health check only
python -m orchestrator.daily_cycle --health

# Use india-trade-cli directly
cd india-trade-cli
trade analyze RELIANCE
trade morning-brief
trade portfolio
trade risk-report
trade memory stats
trade drift
```

## Project Structure

```
vibe-trading/
├── .env                    # Master configuration
├── docker-compose.yml      # Container orchestration
├── orchestrator/           # 🧠 Daily cycle + auto-improve + auto-heal
│   ├── config.py           # Typed config loader
│   └── daily_cycle.py      # 7-phase daily orchestrator
├── core-engine/            # 🔧 HKUDS/Vibe-Trading (backtest + swarm)
├── india-trade-cli/        # 🇮🇳 hopit-ai/india-trade-cli (7-agent analysis)
├── kite-mcp/               # 📡 zerodha/kite-mcp-server (broker bridge)
├── docker/                 # Dockerfiles
└── scripts/                # Setup + utility scripts
    └── setup_oci.sh        # OCI ARM VM bootstrap
```

## LLM Fallback Chain

```
Ollama (local, unlimited) → OpenRouter (free, ~50/day) → NVIDIA NIM (free, 5000 credits)
```

## Safety

- ⚠️ **TRADING_MODE=PAPER** is enforced — the orchestrator refuses to start in LIVE mode
- All paper trades are logged to `~/.trading_platform/journal/`
- Trade memory persists at `~/.trading_platform/trade_memory.json`
- Strategies are sandboxed with AST validation (no `exec`, `eval`, `open`)

## Cost

| Component | Cost |
|---|---|
| OCI VM (4 OCPU, 24GB) | ₹0 (free tier) |
| Ollama + models | ₹0 (self-hosted) |
| Zerodha personal | ₹0 (free plan) |
| OpenRouter free tier | ₹0 |
| NVIDIA NIM free tier | ₹0 |
| **Total** | **₹0/month** |
