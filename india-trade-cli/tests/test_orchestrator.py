import pytest
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from orchestrator.capital_manager import (
    CapitalState,
    process_daily_pnl,
    should_halt_trading,
    STATE_DIR
)
from orchestrator.live_graduation import (
    GraduationState,
    evaluate_graduation,
    GraduationCriteria
)

def test_process_daily_pnl_profit():
    state = CapitalState(
        principal=1000000.0,
        ai_fund_balance=5000.0,
        owner_pending=5000.0
    )
    # Gain of ₹10,000 should split 50/25/25
    split = process_daily_pnl(state, 10000.0)
    assert state.principal == 1005000.0
    assert state.ai_fund_balance == 7500.0
    assert state.owner_pending == 7500.0
    assert split["reinvest_amount"] == 5000.0
    assert split["ai_fund_amount"] == 2500.0
    assert split["owner_amount"] == 2500.0

def test_process_daily_pnl_loss_symmetric():
    state = CapitalState(
        principal=1000000.0,
        ai_fund_balance=5000.0,
        owner_pending=5000.0
    )
    # Loss of ₹10,000 should split symmetrically 50/25/25
    split = process_daily_pnl(state, -10000.0)
    assert state.principal == 995000.0
    assert state.ai_fund_balance == 2500.0
    assert state.owner_pending == 2500.0
    assert split["reinvest_amount"] == -5000.0
    assert split["ai_fund_amount"] == -2500.0
    assert split["owner_amount"] == -2500.0

def test_process_daily_pnl_loss_insufficiency_overflow():
    state = CapitalState(
        principal=1000000.0,
        ai_fund_balance=1000.0,  # Insufficient to absorb 25% of 10k (-2500)
        owner_pending=5000.0
    )
    # Loss of ₹10,000 should split 50/25/25
    # AI Fund absorbs -1000 (its full balance), and overflows the remaining -1500 to principal
    # Owner pending absorbs -2500 cleanly (leaving 2500)
    # Reinvestment absorbs -5000 + -1500 (overflow) = -6500
    split = process_daily_pnl(state, -10000.0)
    assert state.ai_fund_balance == 0.0
    assert state.owner_pending == 2500.0
    assert state.principal == 993500.0
    assert split["reinvest_amount"] == -6500.0
    assert split["ai_fund_amount"] == -1000.0
    assert split["owner_amount"] == -2500.0

def test_should_halt_trading_emergency_stop():
    state = CapitalState(principal=100000.0, max_principal=100000.0)
    emergency_file = STATE_DIR / "emergency_stop.flag"
    
    # Ensure flag file doesn't exist initially
    if emergency_file.exists():
        emergency_file.unlink()
        
    halt, reason = should_halt_trading(state)
    assert not halt
    
    # Create the emergency stop flag file
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        emergency_file.touch()
        halt, reason = should_halt_trading(state)
        assert halt
        assert "Emergency Stop" in reason
    finally:
        # Clean up
        if emergency_file.exists():
            emergency_file.unlink()

def test_evaluate_graduation():
    # Test that evaluate_graduation checks all criteria correctly
    state = GraduationState(
        current_mode="PAPER",
        trading_days=65,
        win_rate=0.55,
        sharpe_ratio=1.2,
        max_drawdown_pct=5.0,
        profit_factor=1.6,
        max_consecutive_losses=3,
        model_accuracy=0.60
    )
    criteria = GraduationCriteria()
    result = evaluate_graduation(state, criteria)
    assert result["all_passed"]
    assert result["recommended_mode"] == "SHADOW"
