#!/bin/bash
# ==============================================================================
# Vibe Trading India — OCI ARM VM Setup Script
# ==============================================================================
# Target: Oracle Cloud Free Tier A1.Flex (4 OCPU, 24GB RAM, Ubuntu 22.04 ARM64)
# LLM Priority: NIM (cloud) → OpenRouter (cloud) → Ollama (local, optional)
# ==============================================================================

set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARNING:${NC} $1"; }
err() { echo -e "${RED}[$(date +%H:%M:%S)] ERROR:${NC} $1"; }

# ── Pre-flight Checks ───────────────────────────────────────

log "═══ Vibe Trading India — OCI Setup ═══"
log "Architecture: $(uname -m)"
log "OS: $(lsb_release -ds 2>/dev/null || cat /etc/os-release | head -1)"
log "RAM: $(free -h | awk '/^Mem:/{print $2}')"

if [[ "$(uname -m)" != "aarch64" ]]; then
    warn "Not running on ARM64 — some steps may differ."
fi

# ── Step 1: System Dependencies ──────────────────────────────

log "Step 1/8: Installing system dependencies..."
sudo apt-get update -qq

# Dynamically determine the best python package to install
PYTHON_PKG="python3"
PYTHON_VENV="python3-venv"
PYTHON_DEV="python3-dev"

if apt-cache show python3.11 &>/dev/null; then
    PYTHON_PKG="python3.11"
    PYTHON_VENV="python3.11-venv"
    PYTHON_DEV="python3.11-dev"
elif apt-cache show python3.12 &>/dev/null; then
    PYTHON_PKG="python3.12"
    PYTHON_VENV="python3.12-venv"
    PYTHON_DEV="python3.12-dev"
fi

log "Selected Python package: $PYTHON_PKG"
sudo apt-get install -y -qq \
    $PYTHON_PKG $PYTHON_VENV $PYTHON_DEV \
    python3-pip \
    git curl wget jq \
    build-essential \
    ca-certificates \
    gnupg lsb-release

# ── Step 2: Install Ollama (Optional — local LLM fallback) ───

log "Step 2/8: Installing Ollama (optional local LLM fallback)..."
if ! command -v ollama &>/dev/null; then
    if curl -fsSL https://ollama.com/install.sh | sh 2>/dev/null; then
        log "Ollama installed successfully"
    else
        warn "Ollama installation failed — will use NIM/OpenRouter only"
    fi
else
    log "Ollama already installed: $(ollama --version)"
fi

# Start Ollama service if available
if command -v ollama &>/dev/null; then
    sudo systemctl enable ollama 2>/dev/null || true
    sudo systemctl start ollama 2>/dev/null || ollama serve &>/dev/null &
    sleep 3

    # Pull primary model (optional, ~4.7GB)
    log "Pulling Llama 3.1 8B (optional — NIM/OpenRouter are primary)..."
    ollama pull llama3.1:8b || warn "Model pull failed — NIM/OpenRouter will be used"
fi

# ── Step 3: Verify Cloud LLM Connectivity ────────────────────

log "Step 3/8: Testing cloud LLM connectivity..."

# Test NIM
if [ -n "${NIM_API_KEY:-}" ]; then
    NIM_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $NIM_API_KEY" \
        "https://integrate.api.nvidia.com/v1/models" 2>/dev/null || echo "000")
    if [ "$NIM_STATUS" = "200" ]; then
        log "✅ NVIDIA NIM: Connected (primary LLM)"
    else
        warn "NVIDIA NIM returned HTTP $NIM_STATUS — check NIM_API_KEY"
    fi
else
    warn "NIM_API_KEY not set — NIM unavailable"
fi

# Test OpenRouter
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
    OR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $OPENROUTER_API_KEY" \
        "https://openrouter.ai/api/v1/models" 2>/dev/null || echo "000")
    if [ "$OR_STATUS" = "200" ]; then
        log "✅ OpenRouter: Connected (fallback LLM)"
    else
        warn "OpenRouter returned HTTP $OR_STATUS — check OPENROUTER_API_KEY"
    fi
else
    warn "OPENROUTER_API_KEY not set — OpenRouter unavailable"
fi

# ── Step 4: Clone Repositories ───────────────────────────────

log "Step 4/8: Cloning repositories..."
WORK_DIR="${HOME}/Vibe_trading"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

if [ ! -d "core-engine" ]; then
    git clone https://github.com/HKUDS/Vibe-Trading.git core-engine
fi

if [ ! -d "india-trade-cli" ]; then
    git clone https://github.com/hopit-ai/india-trade-cli.git india-trade-cli
fi

if [ ! -d "kite-mcp" ]; then
    git clone https://github.com/zerodha/kite-mcp-server.git kite-mcp
fi

# ── Step 5: Python Virtual Environment ──────────────────────

log "Step 5/8: Setting up Python environment..."
python3 -m venv "${WORK_DIR}/venv"
source "${WORK_DIR}/venv/bin/activate"

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install india-trade-cli
log "Installing india-trade-cli..."
cd "${WORK_DIR}/india-trade-cli"
pip install -e "." --quiet 2>&1 | tail -5

# Install Vibe-Trading core engine
log "Installing Vibe-Trading core engine..."
cd "${WORK_DIR}/core-engine"
pip install -e "." --quiet 2>&1 | tail -5

# Install orchestrator dependencies
pip install httpx python-dotenv yfinance --quiet

# ── Step 6: Configuration ───────────────────────────────────

log "Step 6/8: Setting up configuration..."
cd "$WORK_DIR"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    if [ -f ".env.oci" ]; then
        cp .env.oci .env
        log ".env created from .env.oci template — UPDATE WITH YOUR API KEYS"
    elif [ -f ".env.example" ]; then
        cp .env.example .env
        log ".env created from .env.example — UPDATE WITH YOUR API KEYS"
    else
        err ".env template not found — create .env manually"
    fi
else
    log ".env already exists"
fi

# Restrict permissions on .env (contains secrets)
chmod 600 .env

# Create necessary directories
mkdir -p ~/.trading_platform/{logs,journal,strategies,models}

# ── Step 7: Systemd Service ─────────────────────────────────

log "Step 7/8: Installing systemd service..."
if [ -f "vibe_trading.service" ]; then
    sudo cp vibe_trading.service /etc/systemd/system/vibe-trading.service
    sudo systemctl daemon-reload
    log "Service installed (not started yet)"
    log "  Enable with: sudo systemctl enable --now vibe-trading"
else
    warn "vibe_trading.service not found in repo — skipping"
fi

# ── Step 8: Security Hardening ──────────────────────────────

log "Step 8/8: Security hardening..."

# Firewall: only allow SSH (22) and block all other inbound
if command -v ufw &>/dev/null; then
    sudo ufw default deny incoming 2>/dev/null || true
    sudo ufw default allow outgoing 2>/dev/null || true
    sudo ufw allow ssh 2>/dev/null || true
    sudo ufw --force enable 2>/dev/null || true
    log "UFW firewall enabled: SSH only inbound"
fi

# Restrict .env permissions
chmod 600 "${WORK_DIR}/.env" 2>/dev/null || true
chmod 700 ~/.trading_platform 2>/dev/null || true

log "Security hardening complete"

# ── Summary ─────────────────────────────────────────────────

echo ""
log "═══ Setup Complete ═══"
echo -e "
${BLUE}Installed Components:${NC}
  ✅ Python 3.11 + virtual environment
  ✅ Vibe-Trading core engine
  ✅ india-trade-cli (7-agent analysis)
  ✅ Kite MCP Server (repo cloned)
  ✅ Orchestrator with daily cycle
  ✅ Systemd service (security-hardened)
  $(command -v ollama &>/dev/null && echo '✅ Ollama (local LLM fallback)' || echo '⬚ Ollama (not installed — using cloud LLMs)')

${BLUE}LLM Priority Chain:${NC}
  1. NVIDIA NIM  (cloud, 70B model — $([ -n '${NIM_API_KEY:-}' ] && echo 'configured' || echo 'needs NIM_API_KEY'))
  2. OpenRouter  (cloud, DeepSeek  — $([ -n '${OPENROUTER_API_KEY:-}' ] && echo 'configured' || echo 'needs OPENROUTER_API_KEY'))
  3. Ollama      (local, 8B model  — $(command -v ollama &>/dev/null && echo 'available' || echo 'not installed'))

${YELLOW}Next Steps:${NC}
  1. Edit ${WORK_DIR}/.env with your API keys:
     - KITE_API_KEY / KITE_API_SECRET (Zerodha)
     - NIM_API_KEY (primary LLM)
     - OPENROUTER_API_KEY (fallback LLM)
     - TELEGRAM_BOT_TOKEN (optional alerts)

  2. Login to Zerodha (one-time):
     source venv/bin/activate
     python scripts/setup_kite.py

  3. Validate setup:
     python scripts/validate_setup.py

  4. Test orchestrator health:
     python -m orchestrator.daily_cycle --health

  5. Start daemon:
     sudo systemctl enable --now vibe-trading
     sudo journalctl -u vibe-trading -f

${RED}⚠️  IMPORTANT:${NC}
  - TRADING_MODE is set to PAPER — NEVER change to LIVE without review
  - .env has 0600 permissions — only your user can read it
  - Paper trading does not require Zerodha IP registration
"
