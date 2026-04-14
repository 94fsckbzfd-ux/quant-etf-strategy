# -*- coding: utf-8 -*-
"""
V8.7.1 实盘信号引擎 (满血终极版 - 腾讯专线 + 溢价平替雷达 + 净榜单隔离 + 硬止损熔断 + PushPlus)
V8.7.1 变更：
- [回滚] 恢复 V8.7 纯 RSRS(r³/std_x) 动量算法，移除双因子及波动率平价
- [新增] send_pushplus() 微信实盘信号自动推送功能
"""
import sys
import os

# 🛡️ 强制清空代理环境变量，防止翻墙软件拦截
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['all_proxy'] = ''
os.environ['ALL_PROXY'] = ''

class DummyStream:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def isatty(self): return False

if sys.stdout is None: sys.stdout = DummyStream()
if sys.stderr is None: sys.stderr = DummyStream()

import argparse
import json
import datetime
import warnings
import time
from io import StringIO
from pathlib import Path
import numpy as np
import pandas as pd
import akshare as ak
import requests
import urllib3
# 👇 修改这里的导入语句，匹配合法的配置文件名
from v8_7_1_live_config import Config

warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LIVE_START_DATE = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y%m%d")

direct_session = requests.Session()
direct_session.trust_env = False 
direct_session.verify = False 
direct_session.headers.update({
"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
})

_orig_api_request = requests.api.request
def _patched_api_request(method, url, **kwargs):
    kwargs["verify"] = False
    kwargs["proxies"] = {"http": None, "https": None}
    headers = kwargs.get("headers", {})
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    kwargs["headers"] = headers
    return _orig_api_request(method, url, **kwargs)
requests.api.request = _patched_api_request

_orig_session_request = requests.Session.request
def _patched_session_request(self, method, url, **kwargs):
    kwargs["verify"] = False
    kwargs["proxies"] = {"http": None, "https": None}
    headers = kwargs.get("headers", {})
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    kwargs["headers"] = headers
    return _orig_session_request(self, method, url, **kwargs)
requests.Session.request = _patched_session_request

def _to_jsonable(obj):
    try:
        import numpy as _np
        import pandas as _pd
    except Exception:
        _np = None; _pd = None
    if obj is None: return None
    if isinstance(obj, dict): return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_to_jsonable(v) for v in obj]
    if _pd is not None:
        if _pd.api.types.is_scalar(obj) and _pd.isna(obj): return None
        if isinstance(obj, _pd.Timestamp): return obj.isoformat()
        if isinstance(obj, _pd.Timedelta): return float(obj.total_seconds())
    if _np is not None and isinstance(obj, _np.generic):
        val = obj.item()
        if isinstance(val, float) and _np.isnan(val): return None
        return val
    if isinstance(obj, float):
        import math
        if math.isnan(obj): return None
    if isinstance(obj, (str, int, float, bool)): return obj
    return str(obj)

def infer_market(code: str) -> str:
    if code.startswith(("5", "6", "11")) or code.startswith("588"): return "SH"
    if code.startswith(("0", "1", "3", "15", "16")): return "SZ"
    return "CN"

def lot_size(code: str) -> int:
    return int(getattr(Config, "LOT_SIZE_BY_CODE", {}).get(code, getattr(Config, "DEFAULT_LOT_SIZE", 100)))

def safe_set_for_crisis() -> set:
    if getattr(Config, "EXCLUDE_GOLD_IN_CRISIS", True): return {Config.BOND_10Y_CODE}
    return set(Config.SAFE_POOL.keys())

def get_name_for_code(code: str) -> str:
    name = getattr(Config, "ALL_POOL", {}).get(code, "")
    if not name:
        for sub in getattr(Config, "SUBSTITUTES", {}).values():
            if sub["code"] == code: 
                name = sub["name"] + "(平替)"
                break
    if not name:
        if code == getattr(Config, "CASH_CODE", "511880"): name = getattr(Config, "CASH_NAME", "银华日利")
        else: name = "未知标的"
    return name

# ==========================================
# 微信 PushPlus 推送函数 (V8.7.1 新增)
# ==========================================
def send_pushplus(token: str, title: str, content: str):
    if not token:
        return
    url = "http://www.pushplus.plus/send"
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown"
    }
    try:
        resp = direct_session.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"\n✅ [PushPlus] 微信推送成功！")
        else:
            print(f"\n❌ [PushPlus] 微信推送失败，返回信息: {resp.text}")
    except Exception as e:
        print(f"\n❌ [PushPlus] 微信推送异常: {e}")

# ==========================================
# 🌟 V8.7 原版 RSRS 评分引擎
# ==========================================
def calculate_rsrs(series: pd.Series, n: int) -> pd.Series:
    if len(series) < n: return pd.Series(np.nan, index=series.index)
    x_full = pd.Series(np.arange(len(series)), index=series.index)
    r = series.rolling(n).corr(x_full)
    std_x = np.std(np.arange(n)) 
    out = (r ** 3) / std_x
    std_y = series.rolling(n).std(ddof=0)
    out[std_y == 0] = 0.0
    has_nan = series.isna().rolling(n).sum() > 0
    out[has_nan] = np.nan
    return out

def last_trading_day(close_panel: pd.DataFrame) -> pd.Timestamp:
    return close_panel.dropna(how="all").index[-1]

def pick_signal_day(close_panel: pd.DataFrame, lag: int) -> pd.Timestamp:
    idx = close_panel.dropna(how="all").index
    if len(idx) < 5: return idx[-1]
    return idx[max(len(idx) - 1 - max(int(lag), 0), 0)]

def compute_scores(close_panel: pd.DataFrame) -> pd.DataFrame:
    rsrs = pd.DataFrame(index=close_panel.index)
    target_codes = set(list(getattr(Config, "RISK_POOL", {}).keys()) + list(getattr(Config, "SAFE_POOL", {}).keys()) + [getattr(Config, "CASH_CODE", "511880"), str(getattr(Config, "MARKET_ANCHOR", "")).zfill(6)])
    for code in close_panel.columns:
        if code in target_codes:
            rsrs[code] = calculate_rsrs(close_panel[code], getattr(Config, "N_DAYS", 18))
    return rsrs

# ==========================================
# [#8] 溢价缓存：lru_cache → 带 TTL 的手动缓存
# ==========================================
_premium_cache = {}
_PREMIUM_TTL = 600

def get_historical_premium_mean(code: str, n_days: int = 20) -> float:
    cache_key = (code, n_days)
    now = time.time()
    if cache_key in _premium_cache:
        ts, val = _premium_cache[cache_key]
        if now - ts < _PREMIUM_TTL:
            return val
    result = _fetch_historical_premium_mean(code, n_days)
    _premium_cache[cache_key] = (now, result)
    return result

def _fetch_historical_premium_mean(code: str, n_days: int) -> float:
    try:
        nav_df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        nav_df['date'] = pd.to_datetime(nav_df['净值日期'])
        nav_series = pd.to_numeric(nav_df.set_index('date')['单位净值'], errors='coerce').dropna()

        s = fetch_from_tencent(code)
        if s.empty: return np.nan

        df = pd.concat([s.rename('close'), nav_series.rename('nav')], axis=1).dropna()
        if df.empty: return np.nan
        df['premium'] = (df['close'] / df['nav'] - 1.0) * 100.0
        return float(df['premium'].tail(n_days).mean())
    except Exception: return np.nan

# ==========================================

def fetch_from_tencent(code: str) -> pd.Series:
    market = 'sh' if code.startswith(('5', '6', '11', '588')) else 'sz'
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{code},day,,,250,qfq"
    resp = direct_session.get(url, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    node = data.get("data", {}).get(f"{market}{code}", {})
    k_list = node.get("qfqday", node.get("day", []))
    if not k_list: raise ValueError("腾讯接口无返回数据")
    dates, closes = [], []
    for row in k_list:
        dates.append(row[0]) 
        closes.append(float(row[2])) 
    df = pd.DataFrame({'date': pd.to_datetime(dates), code: closes})
    s = df.set_index('date')[code]
    return s.loc[s.index >= pd.to_datetime(LIVE_START_DATE)]

def fetch_close_panel(codes: list[str]) -> pd.DataFrame:
    series = []
    print("\n📡 正在连接行情服务器同步数据 (已启用 VPN物理击穿 + 腾讯 HTTP 直连专线)...")
    total = len(codes)
    for i, code in enumerate(codes, 1):
        str_code = str(code).strip().zfill(6) 
        success = False
        last_err = ""
        name = get_name_for_code(str_code)
        print(f"  [{i:02d}/{total:02d}] 拉取 {str_code} {name:<10} ...", end=" ", flush=True)
        try:
            time.sleep(0.1)
            s = fetch_from_tencent(str_code)
            if len(s) > 0:
                series.append(s)
                success = True
                print("✅ 成功 (腾讯专线)")
        except Exception as e: last_err = f"腾讯: {e}"

        if not success:
            try:
                time.sleep(0.5)
                df = ak.stock_zh_a_hist(symbol=str_code, period="daily", start_date=LIVE_START_DATE, end_date=Config.END_DATE, adjust="hfq")
                if df is not None and not df.empty and "收盘" in df.columns:
                    df = df[["日期", "收盘"]].rename(columns={"日期": "date", "收盘": str_code})
                    df["date"] = pd.to_datetime(df["date"])
                    df[str_code] = pd.to_numeric(df[str_code], errors="coerce")
                    s = df.dropna().sort_values("date").set_index("date")[str_code]
                    if len(s) > 0:
                        series.append(s)
                        success = True
                        print("✅ 成功 (东财备用)")
            except Exception as e: last_err += f" | 东财: {e}"
            if not success: print(f"❌ 失败 ({last_err})")

    if not series: 
        print("\n" + "🚨" * 20)
        print("【致命错误】主备双通道均拉取失败！无米下炊！")
        print("🚨" * 20 + "\n")
        raise RuntimeError("No data fetched.")
    close_panel = pd.concat(series, axis=1).sort_index()
    for c in close_panel.columns:
        fv = close_panel[c].first_valid_index()
        if fv is not None: close_panel.loc[fv:, c] = close_panel.loc[fv:, c].ffill()
    return close_panel.loc[close_panel.index >= pd.to_datetime(LIVE_START_DATE)]

# ==========================================
# [#6] 数据完整性校验
# ==========================================
def validate_data_integrity(close_panel: pd.DataFrame, required_codes: list[str]):
    """校验 close_panel 数据质量，打印警告但不中断流程"""
    n_days = getattr(Config, "N_DAYS", 18)
    total_rows = len(close_panel)
    issues = []

    for code in required_codes:
        name = get_name_for_code(code)
        if code not in close_panel.columns:
            issues.append((code, name, "完全缺失", "❌"))
            continue

        col = close_panel[code]
        valid_count = col.notna().sum()
        missing_count = total_rows - valid_count
        missing_pct = missing_count / total_rows if total_rows > 0 else 0

        # 检查尾部连续有效天数是否覆盖 RSRS 窗口
        tail_valid = 0
        for v in col.iloc[::-1]:
            if pd.notna(v):
                tail_valid += 1
            else:
                break

        # 检查最近5个交易日是否有停牌（全部相同价格）
        recent = col.dropna().tail(5)
        stale = len(recent) >= 5 and recent.nunique() == 1

        # 汇总问题
        warns = []
        if missing_pct > 0.10:
            warns.append(f"缺失率 {missing_pct:.1%}")
        if tail_valid < n_days:
            warns.append(f"尾部连续有效仅 {tail_valid} 天 < RSRS窗口 {n_days} 天")
        if stale:
            warns.append("近5日价格完全相同(疑似停牌)")
        if valid_count == 0:
            warns.append("无任何有效数据")

        if warns:
            severity = "❌" if valid_count == 0 or tail_valid < n_days else "⚠️"
            issues.append((code, name, "; ".join(warns), severity))

    if issues:
        print("\n" + "-" * 70)
        print("🔍 [数据完整性校验]")
        print("-" * 70)
        for code, name, msg, sev in issues:
            print(f"  {sev} {code} {name:<12} → {msg}")
        print("-" * 70)

        critical = sum(1 for _, _, _, s in issues if s == "❌")
        if critical > 0:
            print(f"  ⛔ {critical} 个标的存在严重数据问题，RSRS 评分可能失真！")
            print()
    else:
        print("\n✅ [数据完整性校验] 全部标的数据质量正常。\n")

# ==========================================

def fetch_macro_us10y(index_like: pd.DatetimeIndex) -> pd.DataFrame:
    macro = pd.DataFrame(index=index_like, columns=["us10y", "ma20"], dtype=float)
    try:
        sym = getattr(Config, "US10Y_STOOQ_SYMBOL", "10yusy.b").lower()
        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        resp = direct_session.get(url, timeout=10) 
        if resp.status_code == 200:
            df = pd.read_csv(StringIO(resp.text))
            df["Date"] = pd.to_datetime(df["Date"])
            y = df.sort_values("Date").set_index("Date").rename(columns={"Close": "us10y"})[["us10y"]]
            y["us10y"] = pd.to_numeric(y["us10y"], errors="coerce")
            y["ma20"] = y["us10y"].rolling(20).mean()
            return y.reindex(index_like, method="ffill")[["us10y", "ma20"]]
    except Exception: pass
    try:
        df_yield = ak.bond_zh_us_rate()
        target_col = [c for c in df_yield.columns if "美国" in c and ("10年" in c or "10Y" in c.upper())][0]
        y = df_yield[["日期", target_col]].rename(columns={"日期": "date", target_col: "us10y"})
        y["date"] = pd.to_datetime(y["date"])
        y["us10y"] = pd.to_numeric(y["us10y"], errors="coerce")
        y = y.dropna().sort_values("date").set_index("date")
        y["ma20"] = y["us10y"].rolling(20).mean()
        return y.reindex(index_like, method="ffill")[["us10y", "ma20"]]
    except Exception: pass
    try:
        fred_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
        resp = direct_session.get(fred_url, timeout=10)
        if resp.status_code == 200:
            df = pd.read_csv(StringIO(resp.text))
            if "DATE" in df.columns and "DGS10" in df.columns:
                df["DATE"] = pd.to_datetime(df["DATE"])
                df["DGS10"] = pd.to_numeric(df["DGS10"].replace(".", pd.NA), errors="coerce")
                s = df.set_index("DATE")["DGS10"].sort_index().dropna()
                y = pd.DataFrame({"us10y": s})
                y["ma20"] = y["us10y"].rolling(20).mean()
                return y.reindex(index_like, method="ffill")[["us10y", "ma20"]]
    except Exception: pass
    return macro

def realtime_prices_and_premium(codes: list[str]) -> tuple[dict, dict]:
    px, premium = {}, {}
    try:
        spot = ak.fund_etf_spot_em()
        col_code = [c for c in spot.columns if "代码" in c][0]
        col_px = [c for c in spot.columns if "最新价" in c or "价格" in c][0]
        col_iopv = [c for c in spot.columns if "IOPV" in c.upper() or "参考净值" in c]

        has_iopv = len(col_iopv) > 0
        iopv_key = col_iopv[0] if has_iopv else None

        for _, row in spot.iterrows():
            c = str(row[col_code]).zfill(6)
            if c not in codes: continue

            p = pd.to_numeric(row[col_px], errors="coerce")
            if pd.notna(p) and p > 0: px[c] = float(p)

            if has_iopv and iopv_key:
                iopv_val = pd.to_numeric(row[iopv_key], errors="coerce")
                if pd.notna(iopv_val) and iopv_val > 0 and pd.notna(p):
                    premium[c] = (float(p) - float(iopv_val)) / float(iopv_val) * 100.0
    except Exception: pass

    return px, premium

def regime_on_day(scores: pd.Series, macro_row: pd.Series) -> tuple[str, dict]:
    us_y = macro_row.get("us10y", np.nan)
    us_ma = macro_row.get("ma20", np.nan)
    drift = float(getattr(Config, "MACRO_DRIFT", 0.05))
    macro_tight = bool(np.isfinite(us_y) and np.isfinite(us_ma) and (us_y > us_ma + drift))
    anchor_ok = bool(Config.MARKET_ANCHOR in scores.index and pd.notna(scores.get(Config.MARKET_ANCHOR, np.nan)))
    anchor_score = float(scores.get(Config.MARKET_ANCHOR, np.nan)) if anchor_ok else np.nan
    is_crisis = bool(macro_tight and anchor_ok and (anchor_score < 0))
    is_half = bool(getattr(Config, "HALF_CRISIS_ENABLED", True) and macro_tight and anchor_ok and (anchor_score >= 0))
    dbg = dict(macro_tight=macro_tight, us10y=float(us_y) if np.isfinite(us_y) else None, us10y_ma20=float(us_ma) if np.isfinite(us_ma) else None, anchor_ok=anchor_ok, anchor_score=float(anchor_score) if np.isfinite(anchor_score) else None)
    if is_crisis: return "crisis", dbg
    if is_half: return "half", dbg
    return "normal", dbg

def target_weights(strategy: str, scores: pd.Series, regime: str) -> dict:
    scores = scores.dropna()
    if regime == "crisis":
        safe_set = safe_set_for_crisis()
        safe_scores = scores[scores.index.isin(safe_set)].sort_values(ascending=False)
        return {safe_scores.index[0]: 1.0} if len(safe_scores) > 0 else {Config.CASH_CODE: 1.0}

    if regime == "half" and ((strategy == "final") or (strategy == "pure" and getattr(Config, "HALF_CRISIS_APPLY_TO_PURE", False))):
        rs = scores[scores.index.isin(Config.RISK_POOL.keys())]
        r1 = rs[rs > Config.RSRS_THRESHOLD].sort_values(ascending=False).index.tolist()[:1]
        rw_eff = getattr(Config, "HALF_CRISIS_RISK_WEIGHT", 0.5) if r1 else 0.0
        ss = scores[scores.index.isin(Config.SAFE_POOL.keys())]
        s1 = ss[ss > -0.5].sort_values(ascending=False).index.tolist()
        s_tgt = s1[0] if s1 else Config.CASH_CODE
        w = {s_tgt: 1.0 - rw_eff}
        if r1 and rw_eff > 0: w[r1[0]] = rw_eff
        s = sum(w.values())
        return {k: v / s for k, v in w.items()} if s > 0 else {Config.CASH_CODE: 1.0}

    pool = Config.ALL_POOL if strategy == "pure" else Config.RISK_POOL
    cand = scores[scores.index.isin(pool.keys())]
    picks = cand[cand > Config.RSRS_THRESHOLD].sort_values(ascending=False).index.tolist()[:Config.TOP_N]
    if not picks: return {Config.CASH_CODE: 1.0}
    final_list = list(picks)
    while len(final_list) < Config.TOP_N: final_list.append(Config.CASH_CODE)
    return {c: 1.0 / Config.TOP_N for c in final_list}

def build_orders(state: dict, target_w: dict, prices: dict) -> list[dict]:
    pos = state.get("positions", {}) or {}
    cash = float(state.get("cash_cny", 0.0))
    mv = {c: float(sh) * prices.get(c, 0) for c, sh in pos.items() if prices.get(c, 0) > 0}
    total = cash + sum(mv.values())
    if total <= 0: return []
    target_mv = {c: float(w) * total for c, w in target_w.items() if c != "_CASH_"}
    if not target_mv: target_mv = {Config.CASH_CODE: total}
    orders = []
    for c in set(mv) | set(target_mv):
        delta = target_mv.get(c, 0.0) - mv.get(c, 0.0)
        if abs(delta) < float(getattr(Config, "MIN_ORDER_NOTIONAL", 2000.0)): continue
        if delta > 0: delta = delta * 0.995 
        p = float(prices.get(c, 0))
        if p <= 0: continue
        lot = lot_size(c)
        shares = int(abs(delta) / p / lot) * lot
        if shares == 0: continue
        orders.append({"code": c, "market": infer_market(c), "side": "BUY" if delta > 0 else "SELL", "shares": shares, "price_ref": round(p, 4), "notional_ref": round(shares * p, 2)})
    orders.sort(key=lambda x: (x["side"] == "BUY", x["code"]))
    return orders

# ==========================================
# [#9] 硬止损 & 熔断 (V8.7 新增)
# ==========================================
def check_hard_stops(state: dict, prices: dict) -> tuple[bool, dict, str]:
    if not getattr(Config, "HARD_STOP_ENABLED", False):
        return False, {}, ""

    cooldown_until = state.get("cooldown_until", None)
    if cooldown_until:
        cd_date = pd.to_datetime(cooldown_until)
        if datetime.datetime.now() < cd_date:
            reason = f"🧊 仍在冷静期中 (至 {cooldown_until})，强制100%现金"
            return True, {Config.CASH_CODE: 1.0}, reason

    pos = state.get("positions", {}) or {}
    entry_prices = state.get("entry_prices", {}) or {}
    if not pos:
        return False, {}, ""

    single_stop = float(getattr(Config, "SINGLE_POSITION_STOP", -0.08))
    stopped_codes = []
    for code, shares in pos.items():
        if float(shares) <= 0: continue
        ep = entry_prices.get(code)
        if ep is None or float(ep) <= 0: continue
        cur_px = prices.get(code, 0)
        if cur_px <= 0: continue
        pnl_pct = (cur_px - float(ep)) / float(ep)
        if pnl_pct <= single_stop:
            stopped_codes.append((code, pnl_pct))

    if stopped_codes:
        details = ", ".join([f"{c}({pnl:+.2%})" for c, pnl in stopped_codes])
        reason = f"🛑 单只硬止损触发: {details} ≤ {single_stop:.0%} → 强制清仓相关持仓"
        cash = float(state.get("cash_cny", 0.0))
        mv = {c: float(sh) * prices.get(c, 0) for c, sh in pos.items() if prices.get(c, 0) > 0}
        total = cash + sum(mv.values())
        if total <= 0:
            return True, {Config.CASH_CODE: 1.0}, reason
        stopped_set = {c for c, _ in stopped_codes}
        new_tw = {}
        for c, sh in pos.items():
            if c in stopped_set: continue
            c_mv = float(sh) * prices.get(c, 0)
            if c_mv > 0:
                new_tw[c] = c_mv / total
        if not new_tw:
            new_tw = {Config.CASH_CODE: 1.0}
        return True, new_tw, reason

    drawdown_stop = float(getattr(Config, "PORTFOLIO_DRAWDOWN_STOP", -0.12))
    peak_value = float(state.get("peak_value", 0))
    cash = float(state.get("cash_cny", 0.0))
    mv = {c: float(sh) * prices.get(c, 0) for c, sh in pos.items() if prices.get(c, 0) > 0}
    current_value = cash + sum(mv.values())

    if peak_value > 0 and current_value > 0:
        drawdown = (current_value - peak_value) / peak_value
        if drawdown <= drawdown_stop:
            cooldown_weeks = int(getattr(Config, "COOLDOWN_WEEKS", 2))
            cd_until = (datetime.datetime.now() + datetime.timedelta(weeks=cooldown_weeks)).strftime("%Y-%m-%d")
            state["cooldown_until"] = cd_until
            reason = (f"🔥 组合熔断触发: 净值={current_value:,.2f} 峰值={peak_value:,.2f} "
                      f"回撤={drawdown:+.2%} ≤ {drawdown_stop:.0%} → 全面清仓 + 冷静期至 {cd_until}")
            return True, {Config.CASH_CODE: 1.0}, reason

    return False, {}, ""

def update_state_after_orders(state: dict, orders: list[dict], prices: dict) -> dict:
    pos = dict(state.get("positions", {}) or {})
    cash = float(state.get("cash_cny", 0.0))
    entry_prices = dict(state.get("entry_prices", {}) or {})

    for od in orders:
        code = od["code"]
        shares = int(od["shares"])
        px = float(od["price_ref"])
        notional = shares * px

        if od["side"] == "SELL":
            old_sh = float(pos.get(code, 0))
            new_sh = max(old_sh - shares, 0)
            cash += notional
            if new_sh <= 0:
                pos.pop(code, None)
                entry_prices.pop(code, None)
            else:
                pos[code] = int(new_sh)
        else:  # BUY
            old_sh = float(pos.get(code, 0))
            old_ep = float(entry_prices.get(code, 0))
            old_cost = old_sh * old_ep if old_ep > 0 else 0
            new_cost = old_cost + notional
            new_sh = old_sh + shares
            cash -= notional
            pos[code] = int(new_sh)
            entry_prices[code] = round(new_cost / new_sh, 6) if new_sh > 0 else px

    pos = {c: sh for c, sh in pos.items() if int(sh) > 0}
    entry_prices = {c: ep for c, ep in entry_prices.items() if c in pos}

    mv = sum(float(sh) * prices.get(c, 0) for c, sh in pos.items() if prices.get(c, 0) > 0)
    current_value = cash + mv
    peak_value = float(state.get("peak_value", 0))
    peak_value = max(peak_value, current_value)

    state["positions"] = pos
    state["cash_cny"] = round(cash, 2)
    state["entry_prices"] = entry_prices
    state["peak_value"] = round(peak_value, 2)
    state["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return state

def save_state(state: dict, state_path: str):
    data = _to_jsonable(state)
    Path(state_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 [AUTO_SAVE] portfolio_state.json 已自动回写 ({state_path})")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=["pure", "final"], default="final")
    args = ap.parse_args()
    strategy = args.strategy

    if not hasattr(Config, "ALL_POOL") or not Config.ALL_POOL:
        Config.ALL_POOL = {**getattr(Config, "RISK_POOL", {}), **getattr(Config, "SAFE_POOL", {})}

    substitute_codes = [v["code"] for v in getattr(Config, "SUBSTITUTES", {}).values()]
    codes = sorted(set(list(Config.RISK_POOL.keys()) + list(Config.SAFE_POOL.keys()) + [Config.CASH_CODE, Config.MARKET_ANCHOR] + substitute_codes))

    close_panel = fetch_close_panel(codes)
    validate_data_integrity(close_panel, codes)  # [#6] 数据完整性校验
    macro = fetch_macro_us10y(close_panel.index)

    rsrs = compute_scores(close_panel)
    last_day = last_trading_day(close_panel)
    signal_day = pick_signal_day(close_panel, getattr(Config, "SIGNAL_LAG_DAYS", 1))
    scores = rsrs.loc[signal_day].dropna()

    reg, dbg = regime_on_day(scores, macro.loc[signal_day] if signal_day in macro.index else pd.Series(dtype=float))
    px_rt, premium_rt = realtime_prices_and_premium(codes)

    # --- 读取 state ---
    state_path = getattr(Config, "PORTFOLIO_STATE_PATH", "portfolio_state.json")
    if Path(state_path).exists():
        try:
            state = json.loads(Path(state_path).read_text(encoding="utf-8"))
        except:
            state = {"cash_cny": Config.INITIAL_CAPITAL, "positions": {}, "entry_prices": {}, "peak_value": 0, "cooldown_until": None, "last_update": None}
    else:
        state = {"cash_cny": Config.INITIAL_CAPITAL, "positions": {}, "entry_prices": {}, "peak_value": 0, "cooldown_until": None, "last_update": None}

    # 兼容旧格式 state，补全新字段
    state.setdefault("entry_prices", {})
    state.setdefault("peak_value", 0)
    state.setdefault("cooldown_until", None)
    state.setdefault("last_update", None)

    # --- 构建全标的价格字典（硬止损需要） ---
    prices = {c: px_rt.get(c, float(close_panel.loc[last_day, c]) if c in close_panel and pd.notna(close_panel.loc[last_day, c]) else 0) for c in set(list(Config.RISK_POOL.keys()) + list(Config.SAFE_POOL.keys()) + [Config.CASH_CODE] + list(state.get("positions", {}).keys()) + substitute_codes)}

    # ==========================================
    # [#9] 硬止损检测 — 在 target_weights 之前执行
    # ==========================================
    hard_stop_triggered, hard_stop_tw, hard_stop_reason = check_hard_stops(state, prices)

    if hard_stop_triggered:
        tw = hard_stop_tw
        orders = build_orders(state, tw, prices)
        substitute_logs = []
        do_rebal = True  
    else:
        # --- 正常流程：target_weights + 溢价平替 ---
        tw_raw = target_weights(strategy=strategy, scores=scores, regime=reg)

        current_holdings = list(state.get("positions", {}).keys())
        tw = {}
        substitute_logs = [] 

        for tgt_code, weight in tw_raw.items():
            sub_info = getattr(Config, "SUBSTITUTES", {}).get(tgt_code)
            if sub_info: 
                sub_code, sub_name, orig_name = sub_info["code"], sub_info["name"], get_name_for_code(tgt_code)

                orig_prem = premium_rt.get(tgt_code, 0.0)
                sub_prem = premium_rt.get(sub_code, 0.0)

                # 🌟 修复三：非交易时间实时溢价通常为 0，启用历史溢价兜底
                if orig_prem == 0.0:
                    fb = get_historical_premium_mean(tgt_code, 1)
                    orig_prem = fb if pd.notna(fb) else 0.0
                if sub_prem == 0.0:
                    fb = get_historical_premium_mean(sub_code, 1)
                    sub_prem = fb if pd.notna(fb) else 0.0

                diff = orig_prem - sub_prem

                if sub_code in current_holdings:
                    tw[sub_code] = weight
                    substitute_logs.append({"action": "lock", "orig_code": tgt_code, "orig_name": orig_name, "sub_code": sub_code, "sub_name": sub_name})
                else:
                    if orig_prem > 1.0:
                        orig_mean = get_historical_premium_mean(tgt_code, 20)
                        sub_mean = get_historical_premium_mean(sub_code, 20)
                        if diff > 1.0: 
                            tw[sub_code] = weight
                            if hasattr(Config, "ALL_POOL"): Config.ALL_POOL[sub_code] = sub_name 
                            substitute_logs.append({
                                "action": "swap", "orig_code": tgt_code, "orig_name": orig_name,
                                "orig_prem": orig_prem, "orig_mean": orig_mean,
                                "sub_code": sub_code, "sub_name": sub_name,
                                "sub_prem": sub_prem, "sub_mean": sub_mean, "diff": diff
                            })
                        else: 
                            tw[tgt_code] = weight
                            substitute_logs.append({
                                "action": "keep", "orig_code": tgt_code, "orig_name": orig_name,
                                "orig_prem": orig_prem, "orig_mean": orig_mean,
                                "sub_code": sub_code, "sub_name": sub_name,
                                "sub_prem": sub_prem, "sub_mean": sub_mean, "diff": diff
                            })
                    else: tw[tgt_code] = weight
            else: tw[tgt_code] = weight

        # 更新 prices 以覆盖 tw 中所有标的
        for c in tw.keys():
            if c not in prices:
                prices[c] = px_rt.get(c, float(close_panel.loc[last_day, c]) if c in close_panel and pd.notna(close_panel.loc[last_day, c]) else 0)

        mv = sum(float(sh) * prices.get(c, 0) for c, sh in state.get("positions", {}).items())
        total_val = float(state.get("cash_cny", 0)) + mv

        cur_w = {c: (float(sh) * prices.get(c, 0))/total_val for c, sh in state.get("positions", {}).items() if total_val > 0 and prices.get(c, 0) > 0}
        if total_val > 0 and float(state.get("cash_cny", 0)) > 0: cur_w["_CASH_"] = float(state.get("cash_cny", 0)) / total_val

        new_w = dict(tw)
        sum_asset = sum(new_w.values())
        new_w["_CASH_"] = max(1.0 - sum_asset, 0.0) if round(sum_asset, 4) < 1.0 else 0.0

        to = sum(abs(cur_w.get(k, 0) - new_w.get(k, 0)) for k in set(cur_w) | set(new_w)) * 0.5
        do_rebal = not (getattr(Config, "MIN_REBAL_ENABLED", True) and total_val > 0 and to < float(getattr(Config, "MIN_REBAL_TURNOVER", 0.05)))
        orders = build_orders(state, tw, prices) if do_rebal else []

    # ==========================================
    # Dashboard 输出
    # ==========================================
    pos = state.get("positions", {}) or {}
    mv_total = sum(float(sh) * prices.get(c, 0) for c, sh in pos.items() if prices.get(c, 0) > 0)
    portfolio_value = float(state.get("cash_cny", 0)) + mv_total
    peak_value = float(state.get("peak_value", 0))
    if peak_value > 0:
        current_drawdown = (portfolio_value - peak_value) / peak_value
    else:
        current_drawdown = 0.0

    print("\n" + "=" * 90)
    print(f"🚀 V8.7.1 LIVE DASHBOARD | Strategy: {strategy.upper()} | Momentum: {Config.N_DAYS}D | Lag: {Config.SIGNAL_LAG_DAYS}")
    print("=" * 90)

    u_val, m_val, anc_val = dbg.get('us10y'), dbg.get('us10y_ma20'), dbg.get('anchor_score')
    u_str = f"{u_val:.3f}%" if pd.notna(u_val) else "N/A(断联)"
    m_str = f"{m_val:.3f}%" if pd.notna(m_val) else "N/A"
    anc_str = f"{anc_val:.4f}" if pd.notna(anc_val) else "N/A(计算失败或停牌)"

    print(f"Regime : {reg.upper()} | US10Y={u_str} | MA20={m_str}")

    anchor_code = str(Config.MARKET_ANCHOR).strip().zfill(6)
    anchor_prem = premium_rt.get(anchor_code, 0.0)
    if anchor_prem == 0.0:
        fb = get_historical_premium_mean(anchor_code, 1)
        anchor_prem = fb if pd.notna(fb) else 0.0
    print(f"Market Anchor ({anchor_code}) : Score = {anc_str} | 当前测算溢价 = {anchor_prem:.2f}%")

    hs_enabled = getattr(Config, "HARD_STOP_ENABLED", False)
    cooldown_until = state.get("cooldown_until", None)
    if hs_enabled:
        hs_status = "🟢 正常"
        if hard_stop_triggered:
            hs_status = "🔴 已触发"
        elif cooldown_until:
            cd_date = pd.to_datetime(cooldown_until)
            if datetime.datetime.now() < cd_date:
                hs_status = f"🧊 冷静期至 {cooldown_until}"
        print(f"Hard Stop  : {hs_status} | 单只止损={getattr(Config, 'SINGLE_POSITION_STOP', -0.08):.0%} | 组合熔断={getattr(Config, 'PORTFOLIO_DRAWDOWN_STOP', -0.12):.0%} | 冷静期={getattr(Config, 'COOLDOWN_WEEKS', 2)}周")
    else:
        print(f"Hard Stop  : ⚪ 已关闭")

    print(f"Portfolio  : 净值=¥{portfolio_value:,.2f} | 峰值=¥{peak_value:,.2f} | 当前回撤={current_drawdown:+.2%}")

    if hard_stop_triggered:
        print("\n" + "🛑" * 30)
        print(f"【硬止损/熔断触发】{hard_stop_reason}")
        print("🛑" * 30 + "\n")

    if reg in ["crisis", "half"] and str(anchor_code) in ["513500", "159655", "513800"]:
        print("\n" + "🚨" * 30)
        print("【宏观风控人工核验警报】：系统当前触发 CRISIS/HALF (避险模式)！")
        if anchor_prem < -1.0 or anchor_prem > 3.0:
            print(f"⚠️ 数据透视：标普当前溢价异常 ({anchor_prem:.2f}%)，极可能是国内溢价杀跌导致假摔！")
            print(f"👉 如果外盘 SPX 根本没跌，请主观否决本次避险指令！")
        print("🚨" * 30 + "\n")

    print("-" * 90)
    print("🎯 Target weights (最终穿透目标仓位):")
    for c, w in sorted(tw.items(), key=lambda x: -x[1]):
        print(f"  - {c} {get_name_for_code(c):<12} {w:>6.2%}")

    print("-" * 90)

    valid_rank_codes = list(Config.RISK_POOL.keys()) + list(Config.SAFE_POOL.keys())
    rank = scores[scores.index.isin(valid_rank_codes)].sort_values(ascending=False)

    print("📊 Top ranking (RSRS动量与溢价监控榜单):")
    for i, (c, s) in enumerate(rank.head(8).items(), 1):
        current_prem = premium_rt.get(c, 0.0)
        if current_prem == 0.0:
            fb = get_historical_premium_mean(c, 1)
            current_prem = fb if pd.notna(fb) else 0.0

        prem_str = ""
        if current_prem > 1.0:
            hist_mean = get_historical_premium_mean(c, n_days=20)
            if pd.notna(hist_mean):
                if current_prem - hist_mean > 2.0: 
                    prem_str = f" | ⚠️ 溢价 {current_prem:.2f}% (均值 {hist_mean:.2f}%) -> 偏高警告"
                else:
                    prem_str = f" | ℹ️ 溢价 {current_prem:.2f}% (均值 {hist_mean:.2f}%)"
            else:
                prem_str = f" | 溢价 {current_prem:.2f}%"
        elif current_prem != 0.0:
            prem_str = f" | 溢价 {current_prem:.2f}%"

        safe_s = float(s) if pd.notna(s) else 0.0
        print(f"  #{i:02d} {c} {get_name_for_code(c):<12} score={safe_s: .4f}{prem_str}")

    if substitute_logs:
        print("\n" + "*" * 90)
        print("💡 智能平替比价引擎 (底层已为您自动拦截改单):")
        for log in substitute_logs:
            if log["action"] == "lock":
                print(f"  [持仓锁仓] 目标买入: {log['orig_code']} {log['orig_name']:<10}")
                print(f"    👉 结论: 账户已持有低溢价平替【{log['sub_code']}】，系统维持锁仓免除摩擦！")
            else:
                orig_m = f"{log['orig_mean']:.2f}%" if pd.notna(log['orig_mean']) else "N/A"
                sub_m = f"{log['sub_mean']:.2f}%" if pd.notna(log['sub_mean']) else "N/A"
                print(f"  [发现平替机会] 目标买入: {log['orig_code']} {log['orig_name']:<10}")
                print(f"    - 原标的溢价 : {log['orig_prem']:.2f}% (历史均值: {orig_m})")
                print(f"    - 备选平替项 : {log['sub_code']} {log['sub_name']:<10} 当前溢价: {log['sub_prem']:.2f}% (历史均值: {sub_m})")
                if log["action"] == "swap":
                    print(f"    👉 结论: 换买【{log['sub_code']}】大概率可为您节省 {log['diff']:.2f}% 的成本！(指令已自动改写)")
                else:
                    print(f"    👉 结论: 溢价差异不大 ({log['diff']:.2f}%)，维持买入原标的 {log['orig_code']}。")
            print("")
        print("*" * 90)

    print("-" * 90)
    if orders:
        print("🛒 Order suggestions (实盘下单指令 - 先卖后买):")
        for od in orders:
            color = f"📉 {od['side']}" if od['side'] == 'SELL' else f"📈 {od['side']}"
            print(f"  - {color:<5} {od['code']} {get_name_for_code(od['code']):<12} shares={od['shares']:<8} ref_px={od['price_ref']:<8} ref_amt=¥{od['notional_ref']:,.2f}")
    else:
        print("🟢 无调仓需求或换手不足 5%，本周安心躺平！")
    print("=" * 90 + "\n")

    # ==========================================
    # 构造微信 PushPlus 推送内容 (V8.7.1 新增)
    # ==========================================
    push_lines = []
    
    # 状态与净值信息
    push_lines.append(f"### 📊 账户与市场环境")
    push_lines.append(f"- **市场状态**: {reg.upper()}")
    push_lines.append(f"- **账户净值**: ¥{portfolio_value:,.2f}")
    push_lines.append(f"- **当前回撤**: {current_drawdown:+.2%}")
    if hard_stop_triggered:
        push_lines.append(f"\n> **⚠️ 注意: {hard_stop_reason}**")
        
    # 目标仓位
    push_lines.append(f"\n### 🎯 目标穿透仓位")
    for c, w in sorted(tw.items(), key=lambda x: -x[1]):
        push_lines.append(f"- {c} {get_name_for_code(c)}: **{w:.1%}**")

    # 调仓指令
    push_lines.append(f"\n### 🛒 实盘调仓指令")
    if orders:
        for od in orders:
            action = "📉 卖出" if od['side'] == 'SELL' else "📈 买入"
            push_lines.append(f"- {action} {od['code']} **{get_name_for_code(od['code'])}** | {od['shares']}股 | 约¥{od['notional_ref']:,.2f}")
    else:
        push_lines.append("- 🟢 无调仓需求或换手不足5%，本周安心躺平！")

    # 平替记录简报
    if substitute_logs:
        push_lines.append(f"\n### 💡 溢价平替雷达")
        for log in substitute_logs:
            if log["action"] == "swap":
                push_lines.append(f"- 拦截高溢价【{log['orig_name']}】，已自动换买【{log['sub_name']}】节省成本约 {log['diff']:.2f}%")
            elif log["action"] == "lock":
                push_lines.append(f"- 目标【{log['orig_name']}】，账户已持有平替【{log['sub_name']}】，维持锁仓免除摩擦")

    push_content = "\n".join(push_lines)
    
    # 发送推送 (支持直接读取 Config 或系统环境变量)
    push_token = getattr(Config, "PUSHPLUS_TOKEN", "") or os.environ.get("PUSHPLUS_TOKEN", "")
    if push_token:
        send_pushplus(push_token, f"🎯 V8.7.1 调仓信号: {reg.upper()}", push_content)
    else:
        print("ℹ️ 未配置 PUSHPLUS_TOKEN，跳过微信推送。")

    # ==========================================
    # 订单后状态更新 & 自动回写
    # ==========================================
    if orders:
        state = update_state_after_orders(state, orders, prices)
        print(f"📝 [STATE UPDATE] 已假设订单全部成交，更新 positions / entry_prices / peak_value")
    else:
        mv_now = sum(float(sh) * prices.get(c, 0) for c, sh in state.get("positions", {}).items() if prices.get(c, 0) > 0)
        val_now = float(state.get("cash_cny", 0)) + mv_now
        old_peak = float(state.get("peak_value", 0))
        state["peak_value"] = round(max(old_peak, val_now), 2)
        state["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if getattr(Config, "AUTO_SAVE_STATE", False):
        save_state(state, state_path)

if __name__ == "__main__":
    main()
