# 🏦 Vibe Trading India

> **AI-powered autonomous paper trading for Indian markets (NSE/BSE/NFO)**
> Self-improving • Self-healing • Zero cost

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
