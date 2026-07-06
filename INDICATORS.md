# AI Bubble Monitor — 24 Indicators (Single Source of Truth)

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

每个指标另带 **Axis 标签**（`stage` 或 `trigger`），用于第二层聚合，含义见「聚合判读」。

## 数据抓取纪律（反锚定自检）

抓数最常见的失败模式是**锚定上期值**：搜到相似文章后复读上期数字，`as_of` 每周更新、value 却常年不动（历史上 insider_sell_buy 曾连续 5 期 ~8x、token_volume_mom 连续 5 期 +35%）。为杜绝静默沿用：

1. **原始数据点强制**：数据源为活源（日更/周更，如 openinsider、OpenRouter、FRED、barchart）的数值型指标，note 里**必须写出本期实际抓到的原始数据点**——例如 `insider_sell_buy` 要写「30 日卖出 $X.XB / 买入 $XM」、`token_volume_mom` 要写本期 token 绝对量。给不出原始数据点 = 本期没抓到数 = 沿用上期并标 `stale: true`，不允许"as_of 更新了、值是抄的"。
2. **原始值台账**：每次运行把各数值型指标的本期原始输入追加进 `docs/data/raw_history.json`（结构：`{"indicator_id": [{"date": "YYYY-MM-DD", "raw": {...自由字段...}, "value": N}]}`，每指标保留最近 26 期）。**环比/增速/比值一律用台账里的上期原始值计算**，不允许直接 web_search 搜"环比增速"抄结论。
3. **同值预警**：活源数值型指标连续 3 期 value 完全相同 → 该指标输出 `suspect_static: true`（可选字段，前端可忽略），并在飞书推送里单列一行「⚠ 疑似静态：{指标} 连续 {N} 期 = {value}，请人工核查」。周期性/低频指标不适用本条（debt_capex_ratio 的对账节奏、enterprise_deploy 等季度调查类）。

## 聚合判读

评分基元：**红=100 / 黄=50 / 绿=0**。指标总数 N 以本文件实际定义的指标数为准（当前 24）——所有公式用 N 表达，不硬编码具体数字。

### 第一层：风险温度（延续历史口径，喂趋势图）

```
red_pct = red_count / N * 100
weighted_risk_score = (red_count + yellow_count * 0.5) / N * 100
```

红灯比例是"温度计"而非"触顶概率"——对外表述统一用**风险温度**，不要写成概率。

### 第二层：两轴分数（主判读框架）

- **stage 轴（泡沫成熟度）**：慢变量——估值、资金结构、发行热度、叙事成熟度。回答"泡沫有多大"。这些指标可以红好几年（1997-2000 CAPE 一直 >35），单独不构成卖出时点。
- **trigger 轴（破裂临近度）**：快变量——信用利差、市场广度、内部人行为、算力商品价格、私募标价、货币政策。回答"引线是否点燃"。历史顶部都是 stage 高位 + trigger 快速抬升的组合。

```
stage_score   = stage 轴指标分均值（0-100）
trigger_score = trigger 轴指标分均值（0-100）
```

区间标签（写入 stage_label / trigger_label）：
- stage_score：<30 早期 Displacement / 30-50 扩张 Boom / 50-70 亢奋 Euphoria / ≥70 极端 Mania
- trigger_score：<25 引线未燃 Fuse Unlit / 25-45 零星火花 Sparks / 45-65 引线点燃 Fuse Lit / ≥65 破裂进行中 Unwinding

### 第三层：类别分

```
category_scores = 每个类别内指标分的均值（6 个 0-100 值）
```

类别指标数不同（估值 4 vs 基本面 5）不再影响相互间权重；升级规则与前端类别视图都用它。

### 判读档位（verdict）

基础档位按 red_pct：`≥60 系统性顶部信号 / ≥40 高风险预警 / ≥25 中度警戒 / 否则 观察期`。再依次套用：

1. **共振升级（保留原规则）**：估值类红灯 ≥2 AND 资金面红灯 ≥3 → 强制升级到至少"高风险预警"。历史上估值 + 资金面同时大面积亮红是泡沫顶部最一致的领先信号。
2. **两轴升级**：stage_score ≥ 60 AND trigger_score ≥ 50 → 至少"高风险预警"；stage_score ≥ 60 AND trigger_score ≥ 65 → "系统性顶部信号"（泡沫大且引线烧到中段 = 防御）。
3. **降档滞回**：**升档即时生效，降档需连续 2 期**——本期与上期快照的基础判读都低于现档位才允许下调（防 29.2%→25.0% 这类单周横跳来回翻档）。比较对象 = 上期 snapshot 的 summary。

若基础判读本身更高，取较高者。任一升级规则触发时，verdict_desc 末尾注明触发的是哪条（如「估值 + 资金面双类共振触发分类强制升级」）。

### 动量（边际变化）

```
momentum = { "deteriorated": 本期状态恶化的指标数, "improved": 好转数, "net": deteriorated - improved }
```

对比上期快照的 status 迁移；绿→黄、黄→红各算恶化 1，绿→红算恶化 2（两级），好转对称计。上期快照中不存在的指标（新增/换入首期）不计入 momentum 与 wow_changes。`net ≥ +4` 时 verdict_desc 必须提示「边际恶化加速」；`net ≤ -4` 提示「边际普遍改善」。

### 历史相似度（模式识别）

用文末【历史校准表】把当前指标颜色向量与四个历史时点逐一比对：

```
match_pct = Σ per-indicator(同色=1 / 相邻色=0.5 / 红绿对立=0) ÷ 该时点有定义(非—)的指标数 × 100
```

输出 `similarity` 数组（全部 4 个时点），verdict_desc 引用相似度最高的 1-2 个（如「当前格局与 1999-06（顶前 9 个月）相似度 83%」），并**点名当前与 2000-02（顶前 1 个月）向量的主要差异指标**——这告诉读者接下来看什么信号确认进入顶部前夜。

### 判读到颜色的映射（用于 dashboard 头部主色）

```
系统性顶部 → red    (#7C1D1D)
高风险预警 → orange (#A8761A 偏深 / #C25E2A)
中度警戒  → yellow (#A8761A)
观察期    → green  (#1F4D2C)
```

---

## 估值 Valuation (4)

### `cape` — Shiller CAPE 周期调整 PE
- **Axis**: stage
- **Source**: https://www.multpl.com/shiller-pe（页面顶部当前值）
- **Direction**: high_bad
- **Thresholds**: red=35, yellow=25
- **Anchor**: 1999-2000 峰值 44.19。>35 历史上只在 2000 / 2021 / 2024-26 出现

### `top5_weight` — S&P 500 前 5 大权重占比 (%)
- **Axis**: stage
- **Source**: https://www.slickcharts.com/sp500（取前 5 行权重相加）
- **Direction**: high_bad
- **Thresholds**: red=25, yellow=18
- **Anchor**: 2000 峰值约 18%；当前约 28% 是 50 年新高

### `nvda_fpe` — NVDA Forward P/E
- **Axis**: stage
- **Source**: web_search "NVDA forward PE current" / yfinance / GuruFocus
- **Direction**: high_bad
- **Thresholds**: red=40, yellow=30
- **Anchor**: 1999 MSFT NTM PE 60x

### `private_secondary_marks` — AI 私募二级市场标价
- **Axis**: trigger
- **Source**: web_search Forge Global / Caplight / Hiive 上 OpenAI / Anthropic / xAI 的二级市场隐含估值，对比各自最近一轮 primary 估值；隐含估值绝对值记入 raw_history
- **Direction**: qualitative（标价走弱=坏）
- **Status mapping**: 任一旗舰标的二级转折价（低于最近一轮 5%+）或标价环比明显下跌 = red / 溢价收窄且卖压>买压 = yellow / 溢价稳定或扩大 = green
- **Anchor**: 一级市场退潮最先出现在二级标价——2000-03 顶前 pre-IPO 二级溢价先萎缩。`vc_ai_share` 测的是量，本指标测的是价。

---

## 资金面 Capital (4)

### `hyperscaler_capex_yoy` — Mag4 资本开支 YoY (%)
- **Axis**: stage
- **Source**: web_search MSFT/GOOGL/AMZN/META 最新季报 capex 指引 vs 去年同期
- **Direction**: extreme_bad（加速=黄、下调指引=红、稳健=绿）
- **Thresholds**: 由 LLM 直接判断 status

### `mag4_fcf_yoy` — Mag4 自由现金流 YoY (%)
- **Axis**: trigger
- **Source**: web_search Barclays / Morgan Stanley / BofA 最新 Mag4 FCF 估算
- **Direction**: low_bad
- **Thresholds**: red=-20, yellow=0
- **Note**: capex 烧掉 FCF 是泡沫晚期典型特征；自有燃料耗尽 = 转向外部融资 = 引线之一

### `vc_ai_share` — AI / Total VC Funding (%)
- **Axis**: stage
- **Source**: web_search PitchBook / CB Insights 最新数据
- **Direction**: high_bad
- **Thresholds**: red=50, yellow=30
- **Anchor**: 健康水位 <30%；2025 创新高 ~70%

### `nvda_invest_revenue` — NVDA 客户投资 / LTM 收入 (%)
- **Axis**: stage
- **Source**: web_search NVDA 对 OpenAI/CoreWeave/xAI 等的 equity+loan 承诺，分子；NVDA LTM revenue 分母
- **Direction**: high_bad
- **Thresholds**: red=30, yellow=15
- **Anchor**: Lucent 1999 vendor financing 24% 已是末期；NVDA 当前 60%+
- **Note（常红处理）**：本指标已长期击穿红线，note 里要写明连续红灯期数与二阶变化（承诺额环比在扩大还是收敛），避免"常红麻木"丢失边际信息。

---

## 市场结构 Market Structure (3)

### `breadth_50d` — S&P 500 50 日均线上方比例 (%)
- **Axis**: trigger
- **Source**: web_search "% S&P 500 above 50-day moving average current" 或 https://www.barchart.com/stocks/quotes/$S5FI
- **Direction**: low_bad
- **Thresholds**: red=40, yellow=60
- **Anchor**: 指数新高时 <40% = 头部独自上涨，历史上是顶部信号

### `insider_sell_buy` — AI 内幕交易 30 日 卖/买 美元比 (倍数)
- **Axis**: trigger
- **Source**: http://openinsider.com/screener?s=NVDA / AVGO / AMD / MSFT / GOOGL / META / AMZN / ORCL / TSM / MU / ARM / PLTR；聚合卖出美元 / 买入美元。备源：secform4.com → SEC EDGAR full-text search（efts.sec.gov, forms=4）→ web_search 新闻层
- **Direction**: high_bad
- **Thresholds**: red=20, yellow=5
- **Anchor**: 2000 峰值 23x

### `ai_ipo_pipeline` — AI IPO/SPAC 管道状态
- **Axis**: stage
- **Source**: web_search 未来 6 个月 AI IPO 公告数 + 近期 SPAC 合并
- **Direction**: qualitative
- **Status mapping**: 洪流（10+）= red / 升温（3-9）= yellow / 平静（<3）= green

---

## 信用 Credit (4)

### `hy_oas` — 高收益债期权调整利差 (bps)
- **Axis**: trigger
- **Source**: https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2 （取最新一行）
- **Direction**: high_bad
- **Thresholds**: red=500, yellow=350
- **Anchor**: 2000/2008/2020 风险事件 >500bps

### `dc_abs_spread` — 数据中心 ABS 利差状态
- **Axis**: trigger
- **Source**: web_search KBRA / Fitch 数据中心 ABS 最新报告。备源：Finsight（finsight.com）ABS 新发行数据库按数据中心筛
- **Direction**: qualitative
- **Status mapping**: 走阔 50bps+ = red / 稳定 = yellow / 收窄 = green

### `neocloud_credit` — Neocloud 90 日信用事件数
- **Axis**: trigger
- **Source**: web_search CoreWeave / Nebius / Nscale / Lambda / Crusoe 评级下调、违约、压力交换
- **Direction**: any_bad
- **Status mapping**: 任何已确认事件 = red / Watch 评级 = yellow / 无 = green

### `debt_capex_ratio` — 全口径债务/Capex 流量比 (%)
- **Axis**: stage
- **Direction**: high_bad
- **Thresholds**: red=70, yellow=50
- **Anchor**: 互联网/电信基建周期顶点 80-100%；当前 AI 周期（2026）自下而上估算约 55%（区间 50-60%）。测"这轮基建有多少靠借债烧"，与信用压力指标（HY 利差/ABS/neocloud 事件）互补——测信用累积而非压力
- **更新节奏（周度增量台账 + 28 天完整对账）**：
  - **每周必做（增量台账）**：web_search「过去 7-10 天新公告的 AI/数据中心债务融资」（关键词轮换使用：AI data center bond issuance / private credit data center deal / GPU-backed ABS / hyperscaler bond offering / Stargate financing 等，避免每周同一查询）。把搜到的新 deal **去重后追加**进 `docs/data/debt_ledger.json`（结构见下）。然后更新本指标：
    - `value` = 年化分子（ms_anchor 锚定值，用台账 YTD 累计交叉校准；若台账 run-rate 与锚定值偏离 >15%，以两者区间呈现并在 note 说明）÷ 分母 capex_denominator
    - note **必须给出周度边际**：「本周新增 $XB（列出 deal 名），YTD 台账累计 $YB，年化 run-rate 对应比值 Z%」；本周无新 deal 就写「本周无新增 deal，YTD 累计 $YB」——这本身也是边际信息
    - `as_of` 更新为本期日期；单笔 ≥$10B 的新 deal 写进 wow_changes 并上飞书
  - **每 28 天（完整对账）**：若 `今天 − debt_ledger.json 的 last_full_recon ≥ 28 天`，执行下面【完整拆解】，用结果修正台账（ms_anchor、capex_denominator、漏记的 deal），并把 `last_full_recon` 更新为今天。
  - `docs/data/debt_ledger.json` 结构：`{"last_full_recon": "YYYY-MM-DD", "ms_anchor": {"numerator_usd_b": N, "as_of": "YYYY-MM-DD", "source": "..."}, "capex_denominator_usd_b": N, "deals": [{"date": "YYYY-MM-DD", "borrower": "...", "instrument": "bond|loan|abs|private_credit|spv_jv", "amount_usd_b": N, "source_url": "..."}]}`。去重键 = borrower + amount 近似 + 公告日 ±7 天；同一 deal 的多篇报道只记一次。
  - 只有当周度搜索与 ms_anchor 都拿不到任何可用数据时才标 `stale: true`（真失败）。
- **【完整拆解】流量口径 = 2026E 全口径 AI 新增债务 ÷ 2026E 全口径 AI 基建 capex**。分子分母口径必须对齐（都用"全口径/all-in"，否则比值失真）：
  - **分子（新增债务，流量）**：web_search 当年 AI 相关新发债务总额。优先抓 Morgan Stanley「AI debt issuance / AI debt monitor」年度估算（最新一期，含已发 vs 全年预测）——它是全口径（公开债 + 私募信用 + ABS + JV/SPV）。交叉核对三块：① hyperscaler + JV 发债（MSFT/META/AMZN/GOOGL/Oracle 债券、Stargate 等）；② neoclouds 全部新增债务（CoreWeave/Nebius/Crusoe/Lambda 的债券、银行贷款、GPU 抵押 ABS）；③ 表外 SPV / 经营租赁融资（Meta Hyperion、Oracle Stargate-Abilene、Blue Owl/PIMCO/Blackstone 私募信用 SPV）。
  - **分母（capex，流量）**：web_search 2026E 全口径 AI 基建 capex。基线 = 五大 hyperscaler（含 Oracle）合计，**再加** neoclouds、Apple、中国、主权及其他 → 全口径约 $1.0-1.1T。**别只用 big-4 的 ~$700B 当分母**（会漏掉 neocloud capex，与全口径分子不匹配、比值虚高）。
  - **算比值**：分子 ÷ 分母，给**中心值 + 区间**（区间主要来自分母宽窄）。note 里写清分子数、分母数、来源与日期，便于追溯。

---

## 基本面 Fundamentals (5)

### `token_volume_mom` — 行业 Token 量月度环比 (%)
- **Axis**: trigger
- **Source**: OpenRouter 公开吞吐数据（https://openrouter.ai/rankings，记录绝对 token 量入 raw_history，环比从台账上期算）+ web_search OpenAI/Anthropic 披露交叉核对
- **Direction**: low_bad
- **Thresholds**: 由 LLM 直接返回 status（收缩=red / 减速=yellow / 加速=green）

### `gpu_rental_price` — GPU 租赁现货价格
- **Axis**: trigger
- **Source**: web_search H100/H200 现货租价（SemiAnalysis H100 租价指数 / Thunder Compute 月度市场报告 / getdeploying.com 价格对比页），$/hr 绝对值记入 raw_history，环比从台账算
- **Direction**: qualitative（租价走弱=坏）
- **Status mapping**: 现货/合约价环比下跌 >15% 或普遍供过于求 = red / 温和阴跌、空置率上升 = yellow / 稳定、上涨或紧俏 = green
- **Anchor**: 2000 年暗光纤价格在电信股崩盘前先行崩塌——算力商品价格是供需最直接的温度计，租价崩 = 供给过剩确认。本体系其余指标都在看资金端与情绪端，只有它直接看算力供需的成交价。

### `arr_2nd_deriv` — AI ARR 二阶导
- **Axis**: trigger
- **Source**: web_search Anthropic + OpenAI 最近 3 个月 ARR；本期增速 vs 上期（原始 ARR 值记入 raw_history，从台账算二阶导）
- **Direction**: low_bad
- **Status mapping**: 减速=red / 平稳=yellow / 加速=green

### `enterprise_deploy` — 企业生产环境部署率 (%)
- **Axis**: stage
- **Source**: web_search Deloitte / Gartner / IDC 最新季度企业 AI 调查
- **Direction**: low_bad
- **Thresholds**: red=50, yellow=65

### `cloud_rpo_growth` — 云厂商递延收入增速状态
- **Axis**: trigger
- **Source**: web_search Google Cloud / Azure / AWS 最近一季报 RPO
- **Direction**: low_bad
- **Status mapping**: 负增长=red / 减速=yellow / 加速=green

---

## 宏观与情绪 Macro & Sentiment (4)

### `accounting_events` — 会计造假/round-tripping 事件
- **Axis**: trigger
- **Source**: web_search 重要 AI 公司的 SEC 执法、审计师担忧
- **Direction**: any_bad
- **Status mapping**: 任何已确认 = red / 调查中 = yellow / 无 = green

### `fed_policy` — Fed 政策方向
- **Axis**: trigger
- **Source**: web_search CME FedWatch 下次 FOMC 隐含动作
- **Direction**: tighten_bad
- **Status mapping**: 隐含加息 = red / 维持高利率(通胀压力) = yellow / 隐含降息 = green

### `capex_reaction` — 资本开支指引市场反应
- **Axis**: trigger
- **Source**: web_search 最近一轮 Mag7 财报中上调 capex 当日股价反应
- **Direction**: punish_bad
- **Status mapping**: 系统性惩罚 = red / 偶发惩罚 = yellow / 奖励 = green

### `ceo_hedging` — CEO 表态对冲程度
- **Axis**: stage
- **Source**: web_search Sam Altman / Sundar Pichai / Jamie Dimon / Satya Nadella / Mark Zuckerberg 最近公开发言中"bubble" "irrational" "overheated"等
- **Direction**: hedging_bad
- **Status mapping**: 普遍承认过热 = red / 部分 = yellow / 无 = green

---

## 历史校准表（相似度比对用）

四个历史时点的指标颜色向量。R=红 Y=黄 G=绿，`—`=该时点无合理类比（不计入该时点 match 分母）。AI 特有指标按括号内类比资产判定。**本表为初稿判定（2026-07-06），阈值随研究演进校订。**

| 指标 | 1999-06<br>(dot-com 顶前 9 月) | 2000-02<br>(顶前 1 月) | 2007-10<br>(金融危机股顶) | 2021-11<br>(成长股/SPAC 顶) |
|---|---|---|---|---|
| cape | R | R | Y | R |
| top5_weight | Y | R | G | Y |
| nvda_fpe（类比 MSFT/CSCO/TSLA 龙头远期 PE） | R | R | G | R |
| private_secondary_marks（pre-IPO 二级标价动能） | G | G | Y | G |
| hyperscaler_capex_yoy（类比电信 capex） | Y | Y | G | Y |
| mag4_fcf_yoy（类比龙头 FCF） | Y | R | G | G |
| vc_ai_share（类比互联网占 VC 比） | R | R | G | R |
| nvda_invest_revenue（类比 Lucent/Nortel vendor financing） | Y | R | G | G |
| breadth_50d | Y | R | R | R |
| insider_sell_buy | Y | R | Y | R |
| ai_ipo_pipeline | R | R | Y | R |
| hy_oas | Y | Y | Y | G |
| dc_abs_spread（类比电信债利差 / 2007=ABX） | Y | Y | R | G |
| neocloud_credit（类比 CLEC / 2007=影子银行信用事件） | G | Y | R | G |
| debt_capex_ratio（基建债务占比） | Y | R | — | G |
| token_volume_mom（类比互联网流量增速） | G | G | — | G |
| gpu_rental_price（类比暗光纤/带宽价格） | G | Y | — | G |
| arr_2nd_deriv（类比龙头收入加速度） | G | Y | — | G |
| enterprise_deploy（真实采用度） | G | Y | — | G |
| cloud_rpo_growth（订单积压） | G | G | — | G |
| accounting_events | G | Y | Y | Y |
| fed_policy | R | R | G | R |
| capex_reaction | G | Y | — | G |
| ceo_hedging | G | Y | Y | Y |

判定依据速记：1999-06 = Fed 开始加息、IPO 洪流、估值极端，但信用/广度/流量全部健康（红灯比例约 25%——与 2026-07 惊人相似）；2000-02 = 内部人 23x 减持、breadth 崩、vendor financing 24%、电信债利差走阔，红灯约 55%+；2007-10 = 信用型顶部，估值/科技侧指标多不适用；2021-11 = 估值+发行+内部人极端但信用面干净，Fed 转鹰是引线。

---

## 输出 JSON Schema（双语）

JSON 喂给两个 dashboard：中文版（aibubble-cn.github.io）和英文版（bubblewatch.github.io）。所以**每条文字字段都要中英文都出**。

```json
{
  "issue_number": 4,
  "as_of_date": "YYYY-MM-DD",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "summary": {
    "total_indicators": 24,
    "red_count": 6,
    "yellow_count": 7,
    "green_count": 10,
    "red_pct": 26.1,
    "weighted_risk_score": 41.3,
    "stage_score": 60.0,
    "stage_label": "亢奋 Euphoria",
    "stage_label_en": "Euphoria",
    "trigger_score": 21.4,
    "trigger_label": "引线未燃",
    "trigger_label_en": "Fuse Unlit",
    "momentum": { "deteriorated": 0, "improved": 1, "net": -1 },
    "category_scores": { "valuation": 50.0, "capital": 87.5, "market_structure": 50.0, "credit": 12.5, "fundamentals": 0.0, "macro": 37.5 },
    "similarity": [
      { "period": "1999-06", "label_zh": "互联网泡沫顶前 9 个月", "label_en": "9 months before dot-com top", "match_pct": 83 }
    ],
    "verdict_label": "中度警戒",
    "verdict_label_en": "Moderate Caution",
    "verdict_desc": "中文判读说明...",
    "verdict_desc_en": "English verdict description..."
  },
  "wow_changes": [
    {
      "indicator_id": "capex_reaction",
      "type": "status_upgrade",
      "from": "green",
      "to": "yellow",
      "note": "中文一句话",
      "note_en": "English one-liner"
    }
  ],
  "indicators": [
    {
      "id": "cape",
      "category": "valuation",
      "category_zh": "估值",
      "axis": "stage",
      "name_en": "Shiller CAPE",
      "name_zh": "CAPE 周期调整 PE",
      "value": 38.5,
      "unit": "",
      "value_display": "38.5",
      "value_display_en": "38.5",
      "status": "red",
      "threshold_text": ">35 红 / 25-35 黄 / <25 绿",
      "threshold_text_en": ">35 red / 25-35 yellow / <25 green",
      "note": "中文 1-2 句解读",
      "note_en": "English 1-2 sentence interpretation",
      "source_name": "multpl.com",
      "source_url": "https://www.multpl.com/shiller-pe",
      "as_of": "YYYY-MM-DD",
      "stale": false
    }
  ]
}
```

### 双语字段约定

- `value_display_en`：仅当 `value_display` 是中文文本时（如 "升温"/"加速中"/"强劲"）需要给英文翻译；纯数字单位（如 "+22%", "279 bps"）不需要 _en
- `note_en` / `verdict_desc_en` / `wow_changes[].note_en`：**必须**给。译文不要逐字对译，写得自然像英文新闻
- `verdict_label_en` 取以下固定映射，不要改：
  - 系统性顶部信号 → Systemic Top Signal
  - 高风险预警 → High Risk Alert
  - 中度警戒 → Moderate Caution
  - 观察期 → Observation
- `threshold_text_en`：用 `red / yellow / green` 替代 `红 / 黄 / 绿`，其它结构保持一致
- `suspect_static`（indicator 级可选字段）：仅当「数据抓取纪律」第 3 条触发时输出 `true`，其余情况省略该字段。前端可忽略。
- `axis` / `stage_score` / `trigger_score` / `momentum` / `category_scores` / `similarity`：2026-07-06 起新增；前端对缺失做了兼容，但 routine 每期都应完整输出。
