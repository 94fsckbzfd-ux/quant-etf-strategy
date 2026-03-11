import yfinance as yf
from datetime import datetime

def analyze(ticker, name):
    data = yf.download(ticker, period="1mo", interval="1d", progress=False, auto_adjust=True)
    if data.empty or len(data) < 2:
        print(f"{name}({ticker}): 数据不足")
        return

    closes = data["Close"].dropna()
    latest = float(closes.iloc[-1])
    first  = float(closes.iloc[0])
    high_1m = float(closes.max())

    change_1m  = (latest - first) / first * 100
    drawdown   = (latest - high_1m) / high_1m * 100
    change_5d  = (latest - float(closes.iloc[-5]))  / float(closes.iloc[-5])  * 100 if len(closes) >= 5  else 0
    change_10d = (latest - float(closes.iloc[-10])) / float(closes.iloc[-10]) * 100 if len(closes) >= 10 else 0

    print(f"\n{'='*52}")
    print(f"  {name} ({ticker})")
    print(f"{'='*52}")
    print(f"  最新收盘价  : {latest:>10,.2f}")
    print(f"  近 5 日涨跌 : {change_5d:>+10.2f}%")
    print(f"  近10 日涨跌 : {change_10d:>+10.2f}%")
    print(f"  近 1 月涨跌 : {change_1m:>+10.2f}%")
    print(f"  距月内高点  : {drawdown:>+10.2f}%")
    print(f"  最新日期    : {closes.index[-1].strftime('%Y-%m-%d')}")

print(f"\n{'#'*52}")
print(f"  外盘核验报告  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"  用于判断 V8.7 策略 CRISIS 信号真假")
print(f"{'#'*52}")

analyze("^GSPC", "标普500 SPX")
analyze("^NDX",  "纳斯达克100 NDX")
analyze("^VIX",  "恐慌指数 VIX")
analyze("GLD",   "黄金 GLD")

print(f"\n{'='*52}")
print("  判断标准：")
print("  近10日 SPX 跌幅 < 5%  → 可能假摔，考虑否决CRISIS")
print("  近10日 SPX 跌幅 > 5%  → 真实危机，遵循CRISIS指令")
print("  VIX 最新值 < 20       → 市场平静，倾向假摔")
print("  VIX 最新值 > 25       → 市场恐慌，遵循CRISIS指令")
print(f"{'='*52}\n")
