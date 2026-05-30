import json
from pathlib import Path

p = Path("~/.trading_platform/capital_state.json").expanduser()
if p.exists():
    d = json.loads(p.read_text())
    d["trading_days"] = 9
    p.write_text(json.dumps(d, indent=2))
    print("Successfully corrected trading days to 9!")
else:
    print("capital_state.json not found!")
