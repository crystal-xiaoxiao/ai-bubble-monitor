# AI Bubble Monitor — 23 Indicators (Single Source of Truth)

> Routine 启动时读这个文件。改指标只改这里。指标 ID 一旦定下不要改（会破坏历史比对）。

## 评分规则

每个指标按 `direction` 和 `thresholds` 打分：

- `high_bad` — 值越高越坏。`value >= red` → 红；`value >= yellow` → 黄；否则绿
- `low_bad` — 值越低越坏。`value <= red` → 红；`value <= yellow` → 黄；否则绿
- `any_bad` — 出现即红。`count > 0` → 红；否则绿
- `extreme_bad` — 加速本身=黄（不可持续），下调指引=红，稳健=绿
- `tighten_bad` — 加息=红，通胀压力维持高利率=黄，降息=绿
- `punish_bad` — 系统性惩罚 capex 上调=红，偶发=黄，奖励=绿
- `hedging_bad` — CEO 普遍承认过热=红，部分对冲=黄，无=绿
- `qualitative` — LLM 直接返回 status，不走数值阈值

## 聚合判读

```
red_pct = red_count / 23 * 100
weighted_risk_score = (red_count + yellow_count * 0.5) / 23 * 100

red_pct >= 60  → 系统性顶部信号（建议进入防御）
red_pct >= 40  → 高风险预警（结构性风险显著）
red_pct >= 25  → 中度警戒（风险积累中，估值与资本结构已闪烁早期信号）
否则           → 观察期（风险可控）
```

---

## 估值 Valuation (3)

### `cape` — Shiller CAPE 周期调整 PE
- **Source**: https://www.multpl.com/shiller-pe（页面顶部当前值）
- **Direction**: high_bad
- **Thresholds**: red=35, yellow=25
- **Anchor**: 1999-2000 峰值 44.19。>35 历史上只在 2000 / 2021 / 2024-26 出现

### `top5_weight` — S&P 500 前 5 大权重占比 (%)
- **Source**: https://www.slickcharts.com/sp500（取前 5 行权重相加）
- **Direction**: high_bad
- **Thresholds**: red=25, yellow=18
- **Anchor**: 2000 峰值约 18%；当前 30% 是 50 年新高

### `nvda_fpe` — NVDA Forward P/E
- **Source**: web_search "NVDA forward PE current" / yfinance / GuruFocus
- **Direction**: high_bad
- **Thresholds**: red=40, yellow=30
- **Anchor**: 1999 MSFT NTM PE 60x

---

## 资金面 Capital (4)

### `hyperscaler_capex_yoy` — Mag4 资本开支 YoY (%)
- **Source**: web_search MSFT/GOOGL/AMZN/META 最新季报 capex 指引 vs 去年同期
- **Direction**: extreme_bad（加速=黄、下调指引=红、稳健=绿）
- **Thresholds**: 由 LLM 直接判断 status

### `mag4_fcf_yoy` — Mag4 自由现金流 YoY (%)
- **Source**: web_search Barclays / Morgan Stanley / BofA 最新 Mag4 FCF 估算
- **Direction**: low_bad
- **Thresholds**: red=-20, yellow=0
- **Note**: capex 烧掉 FCF 是泡沫晚期典型特征

### `vc_ai_share` — AI / Total VC Funding (%)
- **Source**: web_search PitchBook / CB Insights 最新数据
- **Direction**: high_bad
- **Thresholds**: red=50, yellow=30
- **Anchor**: 健康水位 <30%；2025 创新高 ~70%

### `nvda_invest_revenue` — NVDA 客户投资 / LTM 收入 (%)
- **Source**: web_search NVDA 对 OpenAI/CoreWeave/xAI 等的 equity+loan 承诺，分子；NVDA LTM revenue 分母
- **Direction**: high_bad
- **Thresholds**: red=30, yellow=15
- **Anchor**: Lucent 1999 vendor financing 24% 已是末期；NVDA 当前 67%

---

## 市场结构 Market Structure (4)

### `breadth_50d` — S&P 500 50 日均线上方比例 (%)
- **Source**: web_search "% S&P 500 above 50-day moving average current" 或 https://www.barchart.com/stocks/indices/sp/sp500
- **Direction**: low_bad
- **Thresholds**: red=40, yellow=60
- **Anchor**: 指数新高时 <40% = 头部独自上涨，历史上是顶部信号

### `spy_vs_rsp_6m` — SPY vs RSP 6 月收益差 (%)
- **Source**: web_search SPY 和 RSP 过去 6 个月收益率
- **Direction**: high_bad
- **Thresholds**: red=10, yellow=5
- **Note**: 大于 5% 表示头部独涨

### `insider_sell_buy` — AI 内幕交易 30 日 卖/买 美元比 (倍数)
- **Source**: http://openinsider.com/screener?s=NVDA / AVGO / AMD / MSFT / GOOGL / META / AMZN / ORCL / TSM / MU / ARM / PLTR；聚合卖出美元 / 买入美元
- **Direction**: high_bad
- **Thresholds**: red=20, yellow=5
- **Anchor**: 2000 峰值 23x

### `ai_ipo_pipeline` — AI IPO/SPAC 管道状态
- **Source**: web_search 未来 6 个月 AI IPO 公告数 + 近期 SPAC 合并
- **Direction**: qualitative
- **Status mapping**: 洪流（10+）= red / 升温（3-9）= yellow / 平静（<3）= green

---

## 信用 Credit (3)

### `hy_oas` — 高收益债期权调整利差 (bps)
- **Source**: https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2 （取最新一行）
- **Direction**: high_bad
- **Thresholds**: red=500, yellow=350
- **Anchor**: 2000/2008/2020 风险事件 >500bps

### `dc_abs_spread` — 数据中心 ABS 利差状态
- **Source**: web_search KBRA / Fitch 数据中心 ABS 最新报告
- **Direction**: qualitative
- **Status mapping**: 走阔 50bps+ = red / 稳定 = yellow / 收窄 = green

### `neocloud_credit` — Neocloud 90 日信用事件数
- **Source**: web_search CoreWeave / Nebius / Nscale / Lambda / Crusoe 评级下调、违约、压力交换
- **Direction**: any_bad
- **Status mapping**: 任何已确认事件 = red / Watch 评级 = yellow / 无 = green

---

## 基本面 Fundamentals (5)

### `token_volume_mom` — 行业 Token 量月度环比 (%)
- **Source**: web_search OpenAI 公布的 tokens/min（4 月 15B/min）+ OpenRouter 周度排行 + Anthropic 披露；估算 MoM 增速
- **Direction**: low_bad
- **Thresholds**: 由 LLM 直接返回 status（收缩=red / 减速=yellow / 加速=green）

### `token_revenue_ratio` — Token 增速 / 收入增速 (倍数)
- **Source**: 派生 = token_volume_mom 增速 ÷ AI ARR MoM 增速
- **Direction**: high_bad
- **Thresholds**: red=2, yellow=1
- **Note**: 收入跑赢 token = 单 token 价值上升 = 真实付费需求；反转是关键警报

### `arr_2nd_deriv` — AI ARR 二阶导
- **Source**: web_search Anthropic + OpenAI 最近 3 个月 ARR；本期增速 vs 上期
- **Direction**: low_bad
- **Status mapping**: 减速=red / 平稳=yellow / 加速=green

### `enterprise_deploy` — 企业生产环境部署率 (%)
- **Source**: web_search Deloitte / Gartner / IDC 最新季度企业 AI 调查
- **Direction**: low_bad
- **Thresholds**: red=50, yellow=65

### `cloud_rpo_growth` — 云厂商递延收入增速状态
- **Source**: web_search Google Cloud / Azure / AWS 最近一季报 RPO
- **Direction**: low_bad
- **Status mapping**: 负增长=red / 减速=yellow / 加速=green

---

## 宏观与情绪 Macro & Sentiment (4)

### `accounting_events` — 会计造假/round-tripping 事件
- **Source**: web_search 重要 AI 公司的 SEC 执法、审计师担忧
- **Direction**: any_bad
- **Status mapping**: 任何已确认 = red / 调查中 = yellow / 无 = green

### `fed_policy` — Fed 政策方向
- **Source**: web_search CME FedWatch 下次 FOMC 隐含动作
- **Direction**: tighten_bad
- **Status mapping**: 隐含加息 = red / 维持高利率(通胀压力) = yellow / 隐含降息 = green

### `capex_reaction` — 资本开支指引市场反应
- **Source**: web_search 最近一轮 Mag7 财报中上调 capex 当日股价反应
- **Direction**: punish_bad
- **Status mapping**: 系统性惩罚 = red / 偶发惩罚 = yellow / 奖励 = green

### `ceo_hedging` — CEO 表态对冲程度
- **Source**: web_search Sam Altman / Sundar Pichai / Jamie Dimon / Satya Nadella / Mark Zuckerberg 最近公开发言中"bubble" "irrational" "overheated"等
- **Direction**: hedging_bad
- **Status mapping**: 普遍承认过热 = red / 部分 = yellow / 无 = green

---

## 输出 JSON Schema

```json
{
  "issue_number": 2,
  "as_of_date": "YYYY-MM-DD",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "summary": {
    "total_indicators": 23,
    "red_count": 6,
    "yellow_count": 7,
    "green_count": 10,
    "red_pct": 26.1,
    "weighted_risk_score": 41.3,
    "verdict_label": "中度警戒",
    "verdict_desc": "..."
  },
  "wow_changes": [
    {"indicator_id": "capex_reaction", "type": "status_upgrade", "from": "green", "to": "yellow", "note": "..."}
  ],
  "indicators": [
    {
      "id": "cape",
      "category": "valuation",
      "category_zh": "估值",
      "name_en": "Shiller CAPE",
      "name_zh": "CAPE 周期调整 PE",
      "value": 38.5,
      "unit": "",
      "value_display": "38.5",
      "status": "red",
      "threshold_text": ">35 红 / 25-35 黄 / <25 绿",
      "note": "...",
      "source_name": "multpl.com",
      "source_url": "https://www.multpl.com/shiller-pe",
      "as_of": "YYYY-MM-DD",
      "stale": false
    }
  ]
}
```
