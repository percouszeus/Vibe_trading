import json
from pathlib import Path

# Fix capital_state.json
p = Path("~/.trading_platform/capital_state.json").expanduser()
if p.exists():
    d = json.loads(p.read_text())
    d["trading_days"] = 11
    p.write_text(json.dumps(d, indent=2))
    print("Successfully corrected capital_state.json trading days to 11!")

# Fix graduation_state.json
g = Path("~/.trading_platform/graduation_state.json").expanduser()
if g.exists():
    d = json.loads(g.read_text())
    d["trading_days"] = 11
    g.write_text(json.dumps(d, indent=2))
    print("Successfully corrected graduation_state.json trading days to 11!")
