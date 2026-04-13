# 📈 V8.8 跨资产ETF动量轮动策略

> 每18天轮换一次，手动操作，无需券商API接口。

## 系统概览

本系统基于18日RSRS动量指标与3月动量因子的合成评分，在全球10只风险ETF + 2只避险ETF中进行轮动，每周五14:45自动生成交易信号。

### V8.8 版本更新

| 更新项 | 说明 |
|--------|------|
| RSRS 公式修正 | r³/std_x → 滚动OLS斜率 z-score，阈值 0.0 具备统计含义 |
| 合成双因子评分 | RSRS z-score × 0.5 + 3月动量 z-score × 0.5 |
| 波动率平价权重 | 替换等权，按已实现波动率倒数分配仓位 |
| 推送方式升级 | 邮件通知 → 微信 PushPlus 推送 |

## 文件说明

| 文件 | 说明 |
|------|------|
| `v8_live_signal.py` | 主策略引擎，负责数据获取、信号计算和订单生成 |
| `v8_live_config.py` | 策略配置文件，包含所有可调参数 |
| `portfolio_state.json` | 账户持仓状态文件，每次运行后自动更新 |
| `requirements.txt` | Python依赖列表 |
| `.github/workflows/weekly_signal.yml` | GitHub Actions自动化工作流 |

## 自动化运行（GitHub Actions）

本仓库已配置GitHub Actions，**每周五14:45（北京时间）自动运行**策略并通过微信 PushPlus 发送通知。

### 配置步骤

在仓库的 **Settings → Secrets and variables → Actions** 中添加以下 Secret：

| Secret名称 | 说明 |
|-----------|------|
| `PUSHPLUS_TOKEN` | PushPlus 用户 Token（在 [pushplus.plus](https://www.pushplus.plus) 登录后获取） |

### 获取 PushPlus Token

1. 访问 [pushplus.plus](https://www.pushplus.plus) 并使用微信扫码登录
2. 登录后在首页即可看到您的 **用户Token**
3. 将 Token 复制并添加到 GitHub 仓库的 Secrets 中（名称为 `PUSHPLUS_TOKEN`）

### 手动触发

在 **Actions → 📈 V8.8 ETF动量轮动** 页面，点击 **Run workflow** 可以立即手动触发一次运行。

## 更新持仓

每次手动操作完成后，如果系统未能自动更新（例如手动出入金），请编辑 `portfolio_state.json`：

```json
{
  "cash_cny": 您的可用现金,
  "positions": {"ETF代码": 持有股数},
  "entry_prices": {},
  "peak_value": 历史最高净值,
  "last_update": "2024-01-01T00:00:00",
  "cooldown_until": null
}
```

## 策略模式切换

- **FINAL模式**（默认，进攻型）：强制满仓风险池最强2只
- **PURE模式**（稳健型）：股债金同台竞技，回撤更小

手动运行时切换模式：
```bash
python v8_live_signal.py --strategy pure
```

## 执行SOP

1. 等待微信 PushPlus 推送通知（每周五约14:45发出）
2. 查看推送中的下单指令
3. 打开东方财富App，**先执行SELL，再执行BUY**
4. 按照系统给出的股数下单，价格挂市价或卖五档价
