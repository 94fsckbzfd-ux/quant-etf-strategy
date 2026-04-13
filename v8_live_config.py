更新Github策略及改为微信PushPlus推送 - Manus
Lite
收到！授权已确认。我正在为您执行最后的同步操作，这次将直接在当前会话中完成推送，确保不再需要重复授权。请稍候...
已确认授权成功，将在当前会话中直接推送策略文件到GitHub，避免再次授权延迟。准备完成推送。

发现登录状态无效，尝试用Token登录，但失败。下一步将请求用户重新授权，确保能推送代码。

Lite
非常抱歉，由于 GitHub CLI 的登录状态在沙盒环境中未能持久保存，我需要您再帮我完成最后一次授权。请在浏览器中输入以下新验证码：
授权链接：https://github.com/login/device
验证码：FFF8-4DDE
完成授权后请告诉我，我将立即为您同步 Manus Dock 中的最新策略到 GitHub。非常感谢您的耐心配合！这次我将确保在授权后立即执行推送操作。
你直接把代码给我，然后我自己更新到github对应文件里面
验证GitHub登录仍失败，将手动提供的文件内容下载后，准备手动更新仓库。下一步通知用户完成文件更新。

Lite
非常抱歉，由于 GitHub 认证在沙盒环境中的持久化问题，导致您多次重复授权仍未成功。为了不耽误您的时间，我已将 Manus Dock 中的最新策略文件直接提取并附在下方。
您可以直接下载这两个文件，并手动更新到您的 GitHub 仓库中。
文件说明：
v8_live_config.py：策略配置文件（V8.8 版本）。
v8_live_signal.py：主策略引擎（V8.8 版本）。
温馨提示：
由于我们之前已经将 GitHub Actions 的推送方式改为了 PushPlus，请确保您已在仓库的 Settings -> Secrets and variables -> Actions 中添加了名为 PUSHPLUS_TOKEN 的 Secret，否则自动化运行会报错。
再次对给您带来的不便表示诚挚的歉意。如果您在手动更新过程中遇到任何问题，请随时告诉我。
v8_live_config.py
代码 · 4.05 KB
v8_live_signal.py
代码 · 45.47 KB
查看此任务中的所有文件
已确认GitHub认证问题无法解决，已提供最新策略文件（两个文件）供用户手动下载和更新仓库。下一步等待用户操作。

任务已完成
这个结果怎么样？
推荐追问




# -*- coding: utf-8 -*-
"""
V8.8 Live Config (18日动量 + 标普宏观真锚 + 宏观防抖 + 自动平替拦截 + 硬止损熔断)
V8.7 变更：
- 新增 HARD_STOP 硬止损系列参数（单只-8%强制清仓、组合-12%全面熔断）
- 新增 COOLDOWN_WEEKS 冷静期
- 新增 AUTO_SAVE_STATE 自动回写 portfolio_state.json
V8.8 变更：
- 新增合成信号参数：RSRS_NORM_WINDOW / RSRS_WEIGHT / MOMENTUM_* / VOL_PARITY_*
"""
import datetime

class Config:

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

    # === 🛑 硬止损 & 熔断参数 (V8.7) ===
    HARD_STOP_ENABLED = True            # 硬止损总开关
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

    # === 合成信号参数 (V8.8 新增) ===
    # RSRS z-score: 对滚动OLS斜率做历史标准化，替换原有 r³/std_x 非标公式
    RSRS_NORM_WINDOW = 600      # z-score标准化的历史窗口（交易日），需配合3年数据拉取（约720根）
    RSRS_WEIGHT = 0.5           # 合成评分中 RSRS z-score 的权重

    # 3月动量因子: shift(5)/shift(68) 跳过最近1周避免短期反转
    MOMENTUM_LOOKBACK = 63      # 动量回溯期（交易日，约3个月）
    MOMENTUM_SKIP = 5           # 跳过最近N天
    MOMENTUM_NORM_WINDOW = 600  # 动量 z-score 标准化窗口
    MOMENTUM_WEIGHT = 0.5       # 合成评分中动量的权重

    # 波动率平价权重 (V8.8 新增): True=按波动率倒数分配，False=原等权
    VOL_PARITY_ENABLED = True
    VOL_PARITY_WINDOW = 20      # 已实现波动率计算窗口（交易日）
    VOL_PARITY_ANNUALIZE = 252

    # --- 实盘订单生成约束 ---
    INITIAL_CAPITAL = 100000.0
    PORTFOLIO_STATE_PATH = "portfolio_state.json"
    DEFAULT_LOT_SIZE = 100
    LOT_SIZE_BY_CODE = {"511880": 100, "511260": 100, "518880": 100}
    USE_REALTIME_PRICE = True
    MIN_ORDER_NOTIONAL = 2000.0
