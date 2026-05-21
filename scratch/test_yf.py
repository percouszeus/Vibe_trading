import yfinance as yf
print("Fetching...")
try:
    df = yf.Ticker("RELIANCE.NS").history(period="1mo")
    print("Columns:", df.columns)
    print("Data size:", len(df))
except Exception as e:
    print("Error:", e)
