# -*- coding: utf-8 -*-
"""
V8.7.1 Live Config (18日动量 + 标普宏观真锚 + 宏观防抖 + 自动平替拦截 + 硬止损熔断 + PushPlus推送)
"""
import datetime
import os  # 👈 关键修复：极有可能是之前漏掉了这个自带库的导入，导致读取 Token 时崩溃！

class Config:

    # === 📱 微信推送配置 ===
    # 优先读取系统环境变量（如 GitHub Secrets）。如果是在本地运行，可以直接把 Token 填在后面的引号里。
    PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")

    # 实盘设为去年的某一天（如 "20240101"）以极大提升数据抓取速度
    START_DATE = "20240101"
    END_DATE = datetime.datetime.now().strftime("%Y%m%d")

    # === 🌟 核心动量参数 (经过严苛矩阵验证的最优错峰解) ===
    N_DAYS = 18 
    RSRS_THRESHOLD = 0.0 
    TOP_N = 2
    SIGNAL_LAG_DAYS = 1  # 盘中(周五14:45)执行必须设为1，防前视偏差

    # --- 宏观风控阀门 ---
    US10Y_STOOQ_SYMBOL = "10yusy.b"
    MACRO_DRIFT = 0.05  # [宏观钝化]: 增加5个基点缓冲，防均线附近微幅震荡导致来回切割
    HALF_CRISIS_ENABLED = True
    HALF_CRISIS_RISK_WEIGHT = 0.5
    HALF_CRISIS_APPLY_TO_PURE = True 
    MIN_REBAL_ENABLED = True
    MIN_REBAL_TURNOVER = 0.05

    # === 🛑 硬止损 & 熔断参数 (V8.7 新增) ===
    HARD_STOP_ENABLED = False            # 硬止损总开关
    SINGLE_POSITION_STOP = -0.08        # 单只持仓从买入价跌8%强制清仓
    PORTFOLIO_DRAWDOWN_STOP = -0.12     # 组合从净值峰值回撤12%全面熔断
    COOLDOWN_WEEKS = 2                  # 熔断后冷静期周数
    AUTO_SAVE_STATE = True              # 运行后自动回写 portfolio_state.json

    # === 资产池 (完美融合版) ===
    RISK_POOL = {
    "510880": "红利ETF",
    "510300": "沪深300",
    "510500": "中证500",
    "512100": "中证1000",
    "588000": "科创50",
    "513500": "标普500",
    "513100": "纳指100", 
    "513030": "德国DAX",
    "513520": "日经225", 
    "513400": "道琼斯",
    }

    # === 🌟 高溢价防守平替池 (实盘自动拦截改单机制) ===
    SUBSTITUTES = {
    "513520": {"code": "513880", "name": "日经ETF(华安)"}, 
    "513100": {"code": "159941", "name": "纳指ETF(广发)"}, 
    "513030": {"code": "159561", "name": "德国DAX(嘉实)"}, 
    "513500": {"code": "159655", "name": "标普500(天弘)"}, 
    "513400": {"code": "159655", "name": "标普500(天弘)"}, 
    }

    GOLD_CODE = "518880"
    BOND_10Y_CODE = "511260"
    SAFE_POOL = {GOLD_CODE: "黄金ETF", BOND_10Y_CODE: "10年国债"}
    EXCLUDE_GOLD_IN_CRISIS = True  # 极端危机坚决剔除黄金防通杀，仅在半危机参与

    CASH_CODE = "511880"
    CASH_NAME = "银华日利"
    ALL_POOL = {**RISK_POOL, **SAFE_POOL}

    # ✅ [致敬您的宏观逻辑：坚决还原全球流动性危机定价之真锚]
    MARKET_ANCHOR = "513500"

    # --- 实盘订单生成约束 ---
    INITIAL_CAPITAL = 100000.0
    PORTFOLIO_STATE_PATH = "portfolio_state.json"
    DEFAULT_LOT_SIZE = 100
    LOT_SIZE_BY_CODE = {"511880": 100, "511260": 100, "518880": 100}
    USE_REALTIME_PRICE = True
    MIN_ORDER_NOTIONAL = 2000.0
