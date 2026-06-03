import json
from pathlib import Path

# Reset capital_state.json
p = Path("~/.trading_platform/capital_state.json").expanduser()
if p.exists():
    d = json.loads(p.read_text())
    d["trading_days"] = 0
    d["profitable_days"] = 0
    d["loss_days"] = 0
    d["cumulative_pnl"] = 0.0
    d["realized_pnl_today"] = 0.0
    d["unrealized_pnl"] = 0.0
    d["best_day_pnl"] = 0.0
    d["worst_day_pnl"] = 0.0
    d["consecutive_loss_days"] = 0
    d["max_consecutive_loss_days"] = 0
    p.write_text(json.dumps(d, indent=2))
    print("Successfully reset capital_state.json!")

# Reset graduation_state.json
g = Path("~/.trading_platform/graduation_state.json").expanduser()
if g.exists():
    d = json.loads(g.read_text())
    d["trading_days"] = 0
    d["win_rate"] = 0.0
    d["sharpe_ratio"] = 0.0
    d["max_drawdown_pct"] = 0.0
    d["profit_factor"] = 0.0
    d["max_consecutive_losses"] = 0
    d["model_accuracy"] = 0.0
    d["live_profitable_days"] = 0
    # reset criteria_met
    for k in d.get("criteria_met", {}):
        if k == "max_drawdown" or k == "consecutive_losses":
            d["criteria_met"][k] = True
        else:
            d["criteria_met"][k] = False
    g.write_text(json.dumps(d, indent=2))
    print("Successfully reset graduation_state.json!")

# Clear capital_history.jsonl
h = Path("~/.trading_platform/capital_history.jsonl").expanduser()
if h.exists():
    h.write_text("")
    print("Successfully cleared capital_history.jsonl!")
