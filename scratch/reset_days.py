import json
from pathlib import Path

state_file = Path.home() / '.trading_platform' / 'capital_state.json'
data = json.loads(state_file.read_text())
old_days = data['trading_days']
data['trading_days'] = 0
data['profitable_days'] = 0
data['loss_days'] = 0
data['consecutive_loss_days'] = 0
data['max_consecutive_loss_days'] = 0
state_file.write_text(json.dumps(data, indent=2, default=str))
print(f'Reset trading_days: {old_days} -> 0')
