# test_yf.py
import yfinance as yf
try:
    print(yf.Ticker('RELIANCE.NS').history(period='5d'))
except Exception as e:
    print("Error:", e)
