import sys
sys.path.insert(0, '/home/ubuntu/Vibe_trading/india-trade-cli')
from market.quotes import get_ltp
print(get_ltp('NSE:INFY'))
