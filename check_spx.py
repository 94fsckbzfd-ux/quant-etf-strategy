import requests
import json
from datetime import datetime

BASE_URL = "https://8000-iqjbebjp2fi2runee6u1k-a150fed8.us2.manus.computer"

def get_history(ticker, period="1mo"):
    url = f"{BASE_URL}/stock/{ticker}/history?period={period}&interval=1d"
    r = requests.get(url, timeout=15)
    return r.json()

def analyze(ticker, name):
    data = get_history(ticker, period="1mo")
    closes = []
    dates = []
    for row in data:
        if "Close" in row and row["Close"] is not None:
            closes.append(row["Close"])
            dates.append(row.get("Date", row.get("Datetime", "?")))
    
    if len(closes) < 2:
        print(f"{name}({ticker}): 数据不足")
        return

    latest = closes[-1]
    high_1m = max(closes)
    low_1m = min(closes)
    change_1m = (latest - closes[0]) / closes[0] * 100
    drawdown_from_high = (latest - high_1m) / high_1m * 100

    # 近5日
    if len(closes) >= 5:
        change_5d = (latest - closes[-5]) / closes[-5] * 100
    else:
        change_5d = 0

    # 近10日
    if len(closes) >= 10:
        change_10d = (latest - closes[-10]) / closes[-10] * 100
    else:
        change_10d = 0

    print(f"\n{'='*50}")
    print(f"  {name} ({ticker})")
    print(f"{'='*50}")
    print(f"  最新收盘价  : {latest:,.2f}")
    print(f"  近 5 日涨跌 : {change_5d:+.2f}%")
    print(f"  近10 日涨跌 : {change_10d:+.2f}%")
    print(f"  近 1 月涨跌 : {change_1m:+.2f}%")
    print(f"  月内最高价  : {high_1m:,.2f}")
    print(f"  距月内高点  : {drawdown_from_high:+.2f}%")
    print(f"  最新日期    : {dates[-1]}")

print(f"\n外盘核验报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("用于判断 V8.7 策略 CRISIS 信号真假")

analyze("^GSPC", "标普500 SPX")
analyze("^NDX",  "纳斯达克100 NDX")
analyze("^VIX",  "恐慌指数 VIX")
analyze("GLD",   "黄金 GLD")

print("\n" + "="*50)
print("判断标准：")
print("  近10日 SPX 跌幅 < 5%  → 可能是假摔，考虑否决CRISIS")
print("  近10日 SPX 跌幅 > 5%  → 真实危机，遵循CRISIS指令")
print("  VIX > 25              → 市场恐慌，遵循CRISIS指令")
print("  VIX < 20              → 市场平静，可能是假摔")
print("="*50)
