# AI Bubble Monitor — 25 Indicators (Single Source of Truth)

> Routine 启动时读这个文件。改指标只改这里。指标 ID 一旦定下不要改（会破坏历史比对）。

## 2026-10-18 起生效的结构修复

以下新口径从 **2026-10-18 UTC 调度周期**生效。本次只改研究契约和后续执行，不补跑、重算或覆盖已发布 #28；历史快照、raw_history 旧条目及既有债务台账不重置。enterprise_deploy、nvda_invest_revenue、arr_2nd_deriv、dc_abs_spread 的首个新口径发布期必须在中英文 note 和 raw.basis 明示切换及不可比项；首期 raw.basis_switch=true，由pipeline排除跨口径 WoW/动量比较；不把口径差异写成 WoW 或动量改善。以后每次真实 basis 切换同样处理，原口径历史仍保留。

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

抓数最常见的失败模式是**锚定上期值**：搜到相似文章后复读上期数字，`as_of` 每周更新、value 却常年不动（历史上 insider_sell_buy 曾连续 5 期 ~8x、token_volume_mom 连续 5 期 +35%）。**2026-08 教训**：openinsider/openrouter 被 egress 403 后，insider 连续 5 期估算值、token 底层绝对量停更 10-12 周，但 as_of 每周照写新日期、同值预警只数派生 value（MoM% 变了计数就重置）——两个失效都没被发现。为杜绝静默沿用：

1. **prefetch 优先**：`docs/data/prefetch/latest.json` 由 GitHub Actions 每周六 13:23 UTC、周日 15:23 UTC 抓取；周六为保底，周日更新为主。凡 `_meta.fetched_at` 距今 <72 小时且对应源 `status=="ok"`，**必须以 prefetch 的 data/summary 为原始数据点**（note 引用其数字，`as_of` 保留数据自身日期）。四个映射源为 insider_sell_buy / token_volume / top5_weight / hy_oas，另有 frontier_eci 供前沿研究读取，后者不进入 task.json.prefetch 数值映射或 static_core_keys。`prefetch_usable` 有 false 时先只读查询 Actions；正在运行则最多等 15 分钟，每次等待不超过 60 秒，完成后获取最新 main 并重新 prepare。**Work 不直连 OpenRouter API 或 efts.sec.gov**；insider/token 只走 prefetch，不可用则 stale。其他源按各自备源链核实。
2. **原始数据点强制**：数据源为活源（日更/周更，如 SEC EDGAR、OpenRouter API、FRED、investing.com）的数值型指标，note 里**必须写出本期实际抓到的原始数据点**——例如 `insider_sell_buy` 要写「30 日卖出 $X.XB / 买入 $XM」、`token_volume_mom` 要写本期 30 日 token 绝对量。给不出原始数据点 = 本期没抓到数 = 沿用上期并标 `stale: true`，不允许"as_of 更新了、值是抄的"。
3. **原始值台账**：每次运行把各数值型指标的本期原始输入追加进 `docs/data/raw_history.json`（结构：`{"indicator_id": [{"date": "YYYY-MM-DD", "raw": {...自由字段...}, "value": N}]}`，每指标保留最近 26 期）。**环比/增速/比值一律用同口径台账原始值计算**，不允许直接 web_search 搜"环比增速"抄结论。
4. **同值预警（数原始绝对值，不数派生值）**：活源数值型指标的**核心原始绝对值**（`insider_sell_buy` 的 sell_usd/buy_usd、`token_volume_mom` 的 30 日 token 总量、`hy_oas` 的 bps 等，即 raw 里的锚定字段）连续 3 期不变**或连续 3 期缺失（拿不到新读数）** → 该指标输出 `suspect_static: true` 和 `static_weeks: N`（连续期数），并在飞书推送里单列一行「⚠ 疑似静态：{指标} 连续 {N} 期原始值未变/未获取 = {value_display}，请人工核查」。**判断方法：数 raw_history.json（含本期）该指标 raw 里核心原始值的连续情况**——派生值（MoM%、比值）在变不能重置计数，历史上 token 的 MoM 从 35→25→5 变来变去、底层绝对量却 10 周没动，就是只数派生值漏报的。前端会渲染 suspect_static 角标（「N 期未变」），不可省略。周期性/低频指标不适用本条（debt_capex_ratio 的对账节奏、enterprise_deploy 等季度调查类）。

### Cadence 与新鲜度三态

每个指标的 Cadence 和 periodic 最大年龄见各定义；最大年龄按本轮 UTC 日期与指标真实 `as_of` 之差计算。

| Cadence | 含义 | 允许状态 | 最大年龄 |
|---|---|---|---|
| live | 日更/周更数值源 | new / stale | current 不适用 |
| periodic | 季报、季度/年度调查、不定期披露 | new / current / stale | current ≤120 天；enterprise_deploy ≤200 天 |
| scan | 按定义窗口的事件/叙事扫描 | new / stale | 每周完成实际扫描 |

- **new**：本期取得新观测（含本周完成的有记录扫描），`stale=false`、evidence.kind 为 web 或 prefetch，`as_of` 写真实观测日。扫描没有发现事件也是本期扫描观测，不代表证明所有事件为零。
- **current（核实仍为最新）**：仅 periodic 可用。本期确实打开来源，核实最新披露仍是上期同一份，且未超过 Max age。value/status/as_of 及双语显示值与上期保持一致，`stale=false`、`evidence.kind="current"`；urls 非空，raw 必填 `latest_release_date`（实际披露日）及 `next_expected`（已公布的下次披露日期；未知时明确写“尚未公布”，不要推测日期）。raw 继续保留原始读数和 basis。current 不计入 stale 闸门，不允许仅复制上期值冒充核实。
- **stale**：本期未能核实当前状态（主备源失败、扫描工具不可用或 current 已超龄）。evidence.kind=carry，`stale=true`，保留上期 value/status/as_of。stale>5 的失败闸门不变。
- **扫描证据**：raw 必填 `window:{start:"YYYY-MM-DD",end:"YYYY-MM-DD"}`、非空 queries、非空 sources_checked（实际检查成功的 URL 字符串，或 `{url,status:"ok"}`）、`events:[{date,what,url}]`。events 可以为空；note 写“本周扫描未见新事件”，这是有记录的尽职扫描结论。实际访问失败写 attempted_urls，不能算成功来源；工具/来源全部失败必须 stale。窗口按具体定义取 7-10 天、60 天、90 天或未来 6 个月，扫描日写 as_of。
- 成功与失败通知都列出 new / current / stale 数量；current 披露日保持可见，不把“核实沿用”算成新增披露。

### 复合、台账与证据口径

- **复合指标看锚定分项**：按各定义的“更新锚”，锚本期有新读数即 new，其他分项可沿用；raw 给出每个分项日期，双语 note 点名沿用项。未取得锚不能以无关新数字代替。缺失辅助项如会实质影响 status，必须说明依据；不伪造分项或比较。
- **台账只做增量**：debt_capex_ratio、nvda_invest_revenue 的承诺分子、ai_ipo_pipeline 名单以上期 raw/台账为基线，每周只找新增或变化并去重。债务每28天完整对账；NVDA 承诺在其财报后完整核对。不要每周从零重建或清空旧台账。
- **口径变化显式记录**：raw 写 basis（如 gross/net、全球/美国、TTM/YTD、价格来源），双语 note 说明切换；跨口径不计算环比、增速二阶差分或 value_change WoW，状态依据同口径分项及有效方向证据判断。原始数值不能为达成阈值而换口径。
- **证据分级**：公司 IR/SEC 文件、官方统计与数据站可直接取数；Reuters、Bloomberg、CNBC、WSJ、FT、The Information、Axios 的具体报道数字可用，注明“媒体口径”。403/付费墙先查 Yahoo Finance、MarketScreener、Investing.com、TipRanks 的转载及 PR Newswire/BusinessWire/GlobeNewswire 新闻稿，真正打开可访问内容。只有搜索摘要时，至少两个**独立**来源数字一致（同一稿件转载不算独立），raw 写 `tier:"snippet"`、来源与对齐结果；snippet 不得作为红灯升级的唯一证据。材料不足就保留明确缺口，不从摘要补造完整数据。

## 聚合判读

评分基元：**红=100 / 黄=50 / 绿=0**。指标总数 N 以本文件实际定义的指标数为准（当前 25）——所有公式用 N 表达，不硬编码具体数字。**注意**：N 变化时 red_pct 会有纯分母效应（如 24→25 使同样 6 个红灯从 25.0% 变 24.0%），当期 verdict_desc 必须说明，趋势图跨期比较以方向为主。

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
- **Cadence**: live
- **Source**: https://www.multpl.com/shiller-pe（页面顶部当前值）
- **Direction**: high_bad
- **Thresholds**: red=35, yellow=25
- **Anchor**: 1999-2000 峰值 44.19。>35 历史上只在 2000 / 2021 / 2024-26 出现

### `top5_weight` — S&P 500 前 5 大权重占比 (%)
- **Axis**: stage
- **Cadence**: live
- **Source**: prefetch `top5_weight`（GitHub Actions 抓 slickcharts，`data.top5_single_class_pct` 为口径基准）。备源：WebFetch https://www.slickcharts.com/sp500（取前 5 行权重相加）→ SPY 持仓二手读
- **Direction**: high_bad
- **Thresholds**: red=25, yellow=18
- **Anchor**: 2000 峰值约 18%；当前约 28% 是 50 年新高

### `nvda_fpe` — NVDA Forward P/E
- **Axis**: stage
- **Cadence**: live
- **Source**: https://stockanalysis.com/stocks/nvda/statistics/ 的 Forward P/E；备源 yfinance / GuruFocus，记录所用一致口径
- **Direction**: high_bad
- **Thresholds**: red=40, yellow=30
- **Anchor**: 1999 MSFT NTM PE 60x

### `private_secondary_marks` — AI 私募二级市场标价
- **Axis**: trigger
- **Cadence**: live
- **Source**: 主序列 https://stockanalysis.com/private/anthropic/ 与 https://stockanalysis.com/private/openai/（Clarity，原 Hiive；二级价、隐含估值及最近一轮估值）。Forge 对应公司页仅交叉；弃用 Caplight 首页/Hiive 页面。raw 保存两家价、隐含估值、最近一轮估值和各自日期/basis；首期切换来源不能与 Forge 历史价算环比
- **更新锚**: OpenAI 与 Anthropic 的 stockanalysis 二级价及隐含估值；至少锚定读数确实更新，其他标的可明示沿用。
- **Direction**: qualitative（标价走弱=坏）
- **Status mapping**: 任一旗舰标的二级转折价（低于最近一轮 5%+）或标价环比明显下跌 = red / 溢价收窄且卖压>买压 = yellow / 溢价稳定或扩大 = green
- **Anchor**: 一级市场退潮最先出现在二级标价——2000-03 顶前 pre-IPO 二级溢价先萎缩。`vc_ai_share` 测的是量，本指标测的是价。

---

## 资金面 Capital (4)

### `hyperscaler_capex_yoy` — Mag4 资本开支 YoY (%)
- **Axis**: stage
- **Cadence**: periodic
- **Max age**: 120 days
- **Source**: 四家 IR 最新季报实际 capex 与去年同期（https://www.microsoft.com/en-us/Investor/、https://abc.xyz/investor/、https://ir.aboutamazon.com/、https://investor.atmeta.com/）；指引及卖方预测可用 Reuters/Bloomberg 等报道交叉。季报间隙实际核实最新披露仍相同则 current
- **更新锚**: 季报实际 capex；新指引仅辅助，不将未更新的实际观测改成新日期。
- **Direction**: extreme_bad（加速=黄、下调指引=红、稳健=绿）
- **Thresholds**: 由 LLM 直接判断 status

### `mag4_fcf_yoy` — Mag4 自由现金流 YoY (%)
- **Axis**: trigger
- **Cadence**: periodic
- **Max age**: 120 days
- **Source**: 四家 IR 季报经营现金流减 capex，与去年同期同口径比较；Barclays / Morgan Stanley / BofA 预测的媒体报道仅交叉，不能替代实际 FCF。季报间隙可核实 current
- **更新锚**: 季报实际 FCF（经营现金流−capex）。
- **Direction**: low_bad
- **Thresholds**: red=-20, yellow=0
- **Note**: capex 烧掉 FCF 是泡沫晚期典型特征；自有燃料耗尽 = 转向外部融资 = 引线之一

### `vc_ai_share` — AI / Total VC Funding (%)
- **Axis**: stage
- **Cadence**: periodic
- **Max age**: 120 days
- **Source**: 主序列 Crunchbase News 全球季度融资报告 https://news.crunchbase.com/（AI 融资 / 同期全球全部 VC 融资）；PitchBook-NVCA Venture Monitor 新闻稿、NVCA PDF https://nvca.org/research/ 仅交叉。2026-10-12 决策：由 PitchBook 美国序列切换到 Crunchbase 全球季度；首期 raw.basis=crunchbase_global_quarterly 并在双语 note 说明，跨序列不算 WoW；阈值不变
- **更新锚**: Crunchbase 全球季度 AI/全部融资占比。
- **Direction**: high_bad
- **Thresholds**: red=50, yellow=30
- **Anchor**: 健康水位 <30%；2025 创新高 ~70%

### `nvda_invest_revenue` — NVDA 已签署客户投资/融资承诺 / LTM 收入 (%)
- **Axis**: stage
- **Cadence**: periodic
- **Max age**: 120 days
- **Source**: 逐项读取公司公告、SEC文件及具名媒体报道，持久台账为 `docs/data/nvda_commitments.json`。分母优先 NVIDIA 最新 IR/SEC 的四季实际收入之和，保存各季期间/财报/算术并明示来源细微差异；https://stockanalysis.com/stocks/nvda/revenue/ 的真实 LTM revenue 作交叉核对；分子只汇总本口径可确认的已签署 equity、loan/可转债、担保承诺，不采用笼统新闻“总承诺”或传闻数字。
- **更新锚**: 最新 LTM 收入分母 + 已签署承诺清单的本周增量；财报后完整核对。每笔记录对象、类型、已签署日期/金额、币种、来源、状态及计入理由。条件性总额仅计已签署部分，未来可选部分/未签意向不计；已签但金额未公开的条目保留为未知并写覆盖缺口，不以0或估算填入，已知金额和只可称“可核实下限”，不得冒充完整总承诺；担保计已签署担保上限，不把上限当作已实际支付。重复报道及同一融资中的投资/担保不得重复计数；保留清单与修订依据。
- **Direction**: high_bad
- **Thresholds**: red=30, yellow=15
- **计算**: 已签署计入金额之和 ÷ 同期可核实 NVDA LTM revenue ×100；raw 写分子分项、分母日期和计算。首期由旧43–45%口径切换，必须明确“不可比”，不能用它倒推新台账总额或宣称变化；其后以上一版已签署台账为基线只追加有出处的新增/变化，不每周从零重建。历史条目不删除，纠错保留前后值、原因和来源。
- **Anchor**: Lucent 1999 vendor financing 24% 为历史类比，不代替本期 NVDA 逐项计数。
- **Note（常红处理）**: 连续红灯期数只在同口径序列内计算；同时说明已签署承诺扩大/收敛及担保或未支付承诺的组成，避免把上限误写为现金流出。

---

## 市场结构 Market Structure (3)

### `breadth_50d` — S&P 500 50 日均线上方比例 (%)
- **Axis**: trigger
- **Cadence**: live
- **Source**: https://www.investing.com/indices/s-p-500-stocks-above-50-day-average-historical-data，取最新实际收盘值与日期；弃用 Barchart/TradingView 作为常规来源。暂无新增 prefetch 自算源
- **Direction**: low_bad
- **Thresholds**: red=40, yellow=60
- **Anchor**: 指数新高时 <40% = 头部独自上涨，历史上是顶部信号
- **注**：暂无 prefetch 支持（免费机器源缺失）；估算值必须在 note 写明估算依据，连续 3 期估算触发 suspect_static

### `insider_sell_buy` — AI 内幕交易 30 日 卖/买 美元比 (倍数)
- **Axis**: trigger
- **Cadence**: live
- **Source**: prefetch `insider_sell_buy`（GitHub Actions 从 SEC EDGAR Form 4 直接聚合 NVDA/AVGO/AMD/MSFT/GOOGL/META/AMZN/ORCL/TSM/MU/ARM/PLTR 12 家 30 日公开市场卖(S)/买(P)美元额——这是本指标的定义口径）。Work 无备源：不要直连 efts.sec.gov，不用新闻代替12家公司30日完整聚合；prefetch 不可用就 stale。~~openinsider~~ 已弃用（2026-08 站点失效）
- **Direction**: high_bad
- **Thresholds**: red=20, yellow=5
- **Anchor**: 2000 峰值 23x（openinsider 时代口径）
- **口径注记**：① ARM/TSM 为外国私发行人，Form 4 申报有限（实测 TSM 内部人有申报、ARM 基本没有），篮子实际以 10 家美国发行人为主；② 买盘常态近零（prefetch `data.zero_buy=true`），此时比值无界且对分母极敏感——value 取 `min(ratio, 99)`，value_display 写明「买盘近零」，status 按 red 处理（sell/buy ≥20 显然成立）；note 必须同时给出卖出绝对额，避免"比值极端但绝对卖压其实不大"被误读；③ EDGAR 直聚口径自 2026-08 起启用，与此前 openinsider/估算口径的数值不可直接跨期比较，首 4 期观察后再校订阈值与校准表

### `ai_ipo_pipeline` — AI IPO/SPAC 管道状态
- **Axis**: stage
- **Cadence**: scan
- **Source**: https://stockanalysis.com/ipos/filings/ + https://stockanalysis.com/ipos/calendar/ 的公开递表及日历；秘密递表/SPAC 从主流媒体扫描。以上期名单做增量去重，raw 保存名单 `{name,status,date,url}`、本周 events 和扫描证据；只计定义范围的 AI 公司
- **更新锚**: 去重后的 AI IPO/SPAC 名单及本周变动。
- **Direction**: qualitative
- **Status mapping**: 洪流（10+）= red / 升温（3-9）= yellow / 平静（<3）= green

---

## 信用 Credit (4)

### `hy_oas` — 高收益债期权调整利差 (bps)
- **Axis**: trigger
- **Cadence**: live
- **Source**: prefetch `hy_oas`（GitHub Actions 走 FRED 官方 API，BAMLH0A0HYM2，`data.oas_bps` 已换算成 bps）。备源：Convex/TradingEconomics 镜像读数。~~fredgraph.csv~~ 已弃用（2026-08 确认超时不可达）
- **趋势图数据**：prefetch 每周同时全量重写 `docs/data/credit_spread_history.json`（HY=BAMLH0A0HYM2 / CCC=BAMLH0A3HYC / IG=BAMLC0A0CM 三序列、1 年日度、FRED 直拉），仅供三站前端「AI 基建信用利差」小倍数趋势图展示，**不参与红黄绿判读**，routine 不消费该文件
- **Direction**: high_bad
- **Thresholds**: red=500, yellow=350
- **Anchor**: 2000/2008/2020 风险事件 >500bps

### `dc_abs_spread` — 数据中心 ABS/项目融资信用状态
- **Axis**: trigger
- **Cadence**: scan
- **Source**: 近90天的数据中心 ABS 与项目融资发行、定价及信用事件；KBRA https://www.kbra.com/、S&P https://www.spglobal.com/ratings/、公司公告，以及 Reuters/Bloomberg 等可访问报道。包括项目融资，不限于 ABS/CMBS；CCC利差、Oracle/CoreWeave公司债价仅代理交叉，不能代替项目/ABS已确认事件。
- **更新锚**: 近90天已确认信用事件与发行状态列表；无事件的有效扫描也是本期观测。英文名固定为 Data-center ABS/project-finance credit status；保留原 id，旧利差状态不回写。
- **Direction**: qualitative
- **Status mapping**: red：已确认违约、不可抗力（force majeure）、评级下调、发行撤回、被迫大幅重定价，或报道确认同口径利差走阔≥50bp。yellow：已确认发行延迟或融资条款收紧，且没有 red 事件。green：顺利发行或完成扫描未见上述事件。先判 red 再 yellow；消息未证实不升级为已确认信用事件。
- **证据字段**: raw.basis=`dc_abs_project_finance_credit_status`；raw.window 为扫描日往前90天，queries/sources_checked 非空，events 每项为 `{date,what,url,event_type,confirmed}`。event_type 取 default / force_majeure / downgrade / issuance_withdrawal / forced_repricing / spread_widening / issuance_delay / terms_tightening / smooth_issuance；confirmed 为布尔值。spread_widening 另填真实 `spread_change_bps` 数字并保留同口径前后定价。空事件允许；未证实报道可记录 confirmed=false 及缺口，不能作为升红唯一依据。
- **切换说明**: 首期写明由“ABS利差状态”改为“ABS/项目融资信用状态”，不将旧 yellow 的“稳定利差”直接解读成新口径 green 的改善；不与旧值计算 WoW。

### `neocloud_credit` — Neocloud 90 日信用事件数
- **Axis**: trigger
- **Cadence**: scan
- **Source**: 按近90天窗口扫描 CoreWeave / Nebius / Nscale / Lambda / Crusoe 的穆迪 https://ratings.moodys.com/、标普 https://www.spglobal.com/ratings/、惠誉 https://www.fitchratings.com/ 新闻稿标题及 Reuters/Bloomberg 报道；公司8-K新闻转述交叉，raw 记录事件列表，尽职扫描 events=[] 时为 green
- **更新锚**: 90天信用事件与 watch 列表。
- **Direction**: any_bad
- **Status mapping**: 任何已确认事件 = red / Watch 评级 = yellow / 无 = green

### `debt_capex_ratio` — 全口径债务/Capex 流量比 (%)
- **Axis**: stage
- **Cadence**: scan
- **Source**: 周度新 deal 新闻扫描；完整对账取 Morgan Stanley / Goldman Sachs / JPMorgan 年度估算的可访问媒体转载，不依赖 FT 付费原文。
- **更新锚**: 台账增量 + 全口径 ms_anchor；台账只是下限，不替换全年全口径锚。
- **Direction**: high_bad
- **Thresholds**: red=70, yellow=50
- **Anchor**: 互联网/电信基建周期顶点 80-100%；当前 AI 周期（2026）自下而上估算约 55%（区间 50-60%）。测"这轮基建有多少靠借债烧"，与信用压力指标（HY 利差/ABS/neocloud 事件）互补——测信用累积而非压力
- **更新节奏（周度增量台账 + 28 天完整对账）**：
  - **每周必做（增量台账）**：web_search「过去 7-10 天新公告的 AI/数据中心债务融资」（关键词轮换使用：AI data center bond issuance / private credit data center deal / GPU-backed ABS / hyperscaler bond offering / Stargate financing 等，避免每周同一查询）。把搜到的新 deal **去重后追加**进 `docs/data/debt_ledger.json`（结构见下）。然后更新本指标：
    - `value` = 年化分子（ms_anchor 锚定值，用台账 YTD 累计交叉校准；若台账 run-rate 与锚定值偏离 >15%，以两者区间呈现并在 note 说明）÷ 分母 capex_denominator
    - note **必须给出周度边际**：「本周新增 $XB（列出 deal 名），YTD 台账累计 $YB，年化 run-rate 对应比值 Z%」；本周无新 deal 就写「本周无新增 deal，YTD 累计 $YB」——这本身也是边际信息
    - `as_of` 更新为本期日期；单笔 ≥$10B 的新 deal 写进 wow_changes 并上飞书
  - **每 28 天（完整对账）**：若 `今天 − debt_ledger.json 的 last_full_recon ≥ 28 天`，执行下面【完整拆解】，用结果修正台账（ms_anchor、capex_denominator、漏记的 deal），并把 `last_full_recon` 更新为今天。到期但无法完成时保留旧 last_full_recon、记录原因，输出“⚠ 债务完整对账逾期 N 天”（N=距上次对账天数−28）；通常为警告而非 stale/发布硬错误；**2026-10-18 周期例外：必须真正完成一次完整对账并更新 last_full_recon、分子、分母及出处，未完成不得发布成功包，不能只出逾期警告。** 周度增量不能替代本次完整对账。
  - `docs/data/debt_ledger.json` 结构：`{"last_full_recon": "YYYY-MM-DD", "ms_anchor": {"numerator_usd_b": N, "as_of": "YYYY-MM-DD", "source": "..."}, "capex_denominator_usd_b": N, "deals": [{"date": "YYYY-MM-DD", "borrower": "...", "instrument": "bond|loan|abs|private_credit|spv_jv", "amount_usd_b": N, "source_url": "..."}]}`。去重键 = borrower + amount 近似 + 公告日 ±7 天；同一 deal 的多篇报道只记一次。
  - 通常周度扫描成功且仍有可用 ms_anchor 时不因完整对账逾期标 stale；2026-10-18 的强制完整对账发布闸门仍必须通过；周度搜索与锚定数据均无法提供可核实依据才为真失败。每次扫描仍必须有查询、来源和真实日期，不将未执行的对账写成已完成。
- **【完整拆解】流量口径 = 2026E 全口径 AI 新增债务 ÷ 2026E 全口径 AI 基建 capex**。分子分母口径必须对齐（都用"全口径/all-in"，否则比值失真）：
  - **分子（新增债务，流量）**：web_search 当年 AI 相关新发债务总额。优先抓 Morgan Stanley「AI debt issuance / AI debt monitor」年度估算（最新一期，含已发 vs 全年预测）——它是全口径（公开债 + 私募信用 + ABS + JV/SPV）。交叉核对三块：① hyperscaler + JV 发债（MSFT/META/AMZN/GOOGL/Oracle 债券、Stargate 等）；② neoclouds 全部新增债务（CoreWeave/Nebius/Crusoe/Lambda 的债券、银行贷款、GPU 抵押 ABS）；③ 表外 SPV / 经营租赁融资（Meta Hyperion、Oracle Stargate-Abilene、Blue Owl/PIMCO/Blackstone 私募信用 SPV）。
  - **分母（capex，流量）**：web_search 2026E 全口径 AI 基建 capex。基线 = 五大 hyperscaler（含 Oracle）合计，**再加** neoclouds、Apple、中国、主权及其他 → 全口径约 $1.0-1.1T。**别只用 big-4 的 ~$700B 当分母**（会漏掉 neocloud capex，与全口径分子不匹配、比值虚高）。
  - **算比值**：分子 ÷ 分母，给**中心值 + 区间**（区间主要来自分母宽窄）。note 里写清分子数、分母数、来源与日期，便于追溯。

---

## 基本面 Fundamentals (6)

### `token_volume_mom` — 行业 Token 量月度环比 (%)
- **Axis**: trigger
- **Cadence**: live
- **Source**: prefetch `token_volume`（GitHub Actions 走 OpenRouter 官方 datasets API rankings-daily，2025-01 起日度全量；`data.mom_pct` = 滚动 30 日总量 vs 前 30 日，自包含口径，不依赖台账上期值）。raw_history 记 `last30_tokens_t` 绝对量。web_search OpenAI/Anthropic 披露仅作交叉印证。~~openrouter.ai/rankings 页面~~ 已弃用（CSR 页抓不到 + egress 403）
- **Direction**: low_bad
- **Thresholds**: 由 LLM 直接返回 status（收缩=red / 减速=yellow / 加速=green）

### `gpu_rental_price` — GPU 租赁现货价格
- **Axis**: trigger
- **Cadence**: live
- **Source**: 主序列 https://getdeploying.com/reference/cloud-gpu/nvidia-h100 的 H100 单卡 on-demand 中位价，raw 使用 `h100_median_on_demand_usd_hr` 并注明 basis=getdeploying、在库筛选/单卡/中位数计算样本。备源 Thunder Compute 月报只作水平值交叉、AIMultiple 正文可读时交叉；首期由旧 AIMultiple $3.25 序列切换，不算跨来源环比
- **更新锚**: getdeploying H100 单卡 on-demand 中位价。
- **Direction**: qualitative（租价走弱=坏）
- **Status mapping**: 现货/合约价环比下跌 >15% 或普遍供过于求 = red / 温和阴跌、空置率上升 = yellow / 稳定、上涨或紧俏 = green
- **Anchor**: 2000 年暗光纤价格在电信股崩盘前先行崩塌——算力商品价格是供需最直接的温度计，租价崩 = 供给过剩确认。本体系其余指标都在看资金端与情绪端，只有它直接看算力供需的成交价。

### `arr_2nd_deriv` — AI ARR 二阶导
- **Axis**: trigger
- **Cadence**: periodic
- **Max age**: 120 days
- **Source**: 最近9个月 Anthropic/OpenAI 已发生的实际 ARR/run-rate 披露，公司公告或 The Information / Reuters / CNBC / Axios / Bloomberg 的具体数字。`docs/data/arr_ledger.json` 持久保存每条公司、实际数据日、披露日、数值、单位、gross/net basis 及来源。预测、年底目标、未实现计划单独作为旁证，不计入数值台账或增长率。
- **更新锚**: 各公司的同口径实际 run-rate 序列。OpenAI gross 与 net 分开，不能拼成一条增长曲线；跨公司不互相补时间点。台账只追加新披露/带出处的修订，保留历史；资料不足不插值、猜测或用未来预测填满9个月。为计算窗口可保留9个月范围之前最近一个实际开盘基线，并显式标为 opening context；不是本期新观测。只知道周/月时 raw 写 as_of_precision 和 observed_interval，取区间终点作保守日期界限并明示非精确日。
- **Direction**: low_bad
- **Status mapping**: 同公司同 basis 的最近3个月增长率，相比此前3个月增长率下降=red / 不变=yellow / 上升=green；每家公司单列计算及实际端点日期，再形成有依据的整体判读。不能用近期绝对 ARR 更高证明二阶导加速。
- **计算**: 以同公司、同basis最新实际读数日T（非报道发布日）为锚，先确定T−3、T−6个日历月截止日；各端点优先取截止日实际读数，否则取截止日或之前最新一条实际披露，滞后最多31天。`g_recent=(R_T/R_anchor_3m−1)×100`，`g_prior=(R_anchor_3m/R_anchor_6m−1)×100`，二阶变化为 `g_recent−g_prior`（百分点）。raw保留每个截止日、实际数据日、滞后天数及原文“大于/约”等限定；有任何端点lag>0时中英文 note 必须明确“披露序列/披露点”与 disclosed-series/reported observations；原文大于/约等金额只称 reported-point estimate，不作精确真实值。稀疏披露只能称“已披露序列的3个月区间增长代理”，不能冒充截止日精确经济增长率。超31天或basis不明则没有可比窗口，不插值、不年化填补、不跨gross/net计算。复合更新时另家公司可以沿用真实日期，但不能把未计算分项写成已验证；主锚不足则 stale。
- **切换说明**: 首个新口径期在中英文 note 说明“近9个月实际披露、同 basis 两段3个月增长率”，旧混合/含预测的口径不可比，不回算已发布 #28。

### `enterprise_deploy` — 企业显著员工 AI 采用率 (%)
- **Axis**: stage
- **Cadence**: periodic
- **Max age**: 200 days
- **Source**: KPMG US AI Quarterly Pulse 的同一问题 significant workforce adoption。主源 https://kpmg.com/us/en/media/news/q3-ai-pulse-2026.html ，官方报告 https://kpmg.com/kpmg-us/content/dam/kpmg/pdf/2026/aipulsesurvey-q3.pdf 。2026-09-24 发布的 Q3 2026 全美大型企业样本披露44%，上季度23%，一年前10%；调查期2026-07-24至08-25，314名美国 $1B+ 企业高管。上述比较数由同一官方发布核实；它不是“构建/部署/开发agent”的62%问题，也不是全部美国企业或员工比例。
- **更新锚**: KPMG 同一调查问题的相邻季度变化（百分点），value 保留当前百分比，raw 保留当前/上期读数、季度、来源及真实披露日。取消旧72%“生产部署率”锚和 red=50/yellow=65 的水平阈值；不同调查/问题不可拼接。
- **Direction**: qualitative
- **Status mapping**: `change_pp=current_pct−previous_pct`；change_pp≥+3 为 green；−3≤change_pp<+3 为 yellow；change_pp<−3 为 red。边界+3归绿、−3归黄，按变化而非采用率水平评分。Q3 2026 44−Q2 2026 23=+21pp 只是官方读数的已核实例，不提前生成后续周期快照。
- **证据字段**: raw 包含 `basis:"kpmg_significant_workforce_adoption"`、`current_pct`/`previous_pct`（数值）、`current_quarter:"2026-Q3"`/`previous_quarter:"2026-Q2"`（相邻季度字符串）、`change_pp`（百分点）、实际 publication_date/调查期和来源。季度未更新时本期实际核实最新报告仍相同且≤200天可 current，保留真实披露日；不能把核实访问日改成新披露日。
- **切换说明**: 首期双语 note 明示由旧生产部署率/72%口径切换为 KPMG significant workforce adoption，旧水平值不可比；新序列将季度变化与周度沿用区分，不把切换形成的颜色差异算作真实 WoW 改善。

### `cloud_rpo_growth` — 云厂商递延收入增速状态
- **Axis**: trigger
- **Cadence**: periodic
- **Max age**: 120 days
- **Source**: Google Cloud / Microsoft / AWS 最新 IR 季报 RPO，同一统计期、定义的合计与变化；保留分项日期及公司披露边界。季报间隙核实最新披露则 current，不能把未来指引替换实际 RPO
- **更新锚**: 季报 RPO 合计及可比公司分项。
- **Direction**: low_bad
- **Status mapping**: 负增长=red / 减速=yellow / 加速=green

### `frontier_progress` — 前沿模型能力进展
- **Axis**: trigger
- **Cadence**: scan
- **Direction**: qualitative（进展放缓=坏）
- **为什么在这个体系里（本轮周期特有）**：本轮 capex 可持续性的第一性依据是"模型还在变好 → 解锁新场景 → 算力需求有支撑"。前沿能力持续推高 = non-trigger；提升放缓乃至停滞 = 本轮独有的顶部触发器。历轮泡沫没有这个维度（2000 年互联网技术本身没停滞，那是融资顶）——所以历史校准表中该行几乎全绿，它提供的是纯增量信息。
- **Source**: prefetch `frontier_eci`，数据来自 Epoch 官方 https://epoch.ai/data/benchmark_data.zip 的 `epoch_capabilities_index/eci_scores.csv`；研究 evidence.kind=web、urls 填实际检查的 Epoch 数据地址并注明本轮打开的仓库 prefetch，raw 写入真实 ECI 数字。仅使用未满72小时、status=ok 的缓存；不用 task.json.prefetch 数值映射或 static_core_keys（正常停在同一 SOTA 不应触发静态警告）。备源直接打开官方 ZIP/https://epoch.ai/eci 核实；不可读且缓存失效则 stale。
- **更新锚**: ECI 滚动 SOTA 与90天增幅；2026-10-12 已决策从 METR 切换，首期双语 note 明示。METR 历史序列自2026年4-5月后缺少新前沿观测，不把网站更新日当成新模型日。
- **量化方法（三层，主锚→辅锚→佐证）**：
  1. **主锚 = Epoch Capabilities Index**：按模型真实 date 的滚动最高 eci 取当前、90天前、180天前、365天前 SOTA；`gain_90d = current_sota − sota_90d`，`previous_gain_90d = sota_90d − sota_180d`，`avg_quarterly_gain_1y = (current_sota − sota_365d) / 4`。raw 保存分项数字、模型、真实日期、抓取时间、比较比值及近90天进入前沿的模型列表；当前模型发布日期不冒充扫描日。METR https://metr.org/time-horizons/ 只在有新数据时参考。
  2. **辅锚 = 困难基准90天 SOTA 位移**：Epoch 同一 ZIP 的 FrontierMath、SWE-bench Verified 等 CSV，及 HLE、ARC-AGI-2/3（https://arcprize.org/）。记录数值、模型及观测日；基准饱和（SOTA>85-90%）换入下一代困难基准，方法不变。缺少辅助层时明示，不能冒充完整更新。
  3. **佐证 = 发布密度与叙事**：过去90天 OpenAI/Anthropic/Google/xAI/DeepSeek 旗舰级发布数与模型清单；labs 叙事是否从能力转向效率/成本。完成查询和来源记录；不要仅凭发布日期数量否定能力提升。
- **Status mapping**（先检验停滞，再比较主锚速度；辅助两层供判读与交叉）:
  - red（停滞）：连续两个90天窗口 ECI SOTA 基本没有提升。数值操作定义为两个窗口增幅均 ≤0.01 ECI 点（CSV 两位小数的精度，识别未超舍入精度的零提升），保留“连续两个季度无实质 SOTA 提升”的原意；不凭发布密度单独升红。
  - green（正常/加速）：未触发 red，且 ECI 90天增幅 ≥ 过去一年季均增幅的50%。
  - yellow（放缓）：未触发 red，且 ECI 90天增幅低于过去一年季均增幅的50%。
  - 年增幅非正或缺少比较点时不得除以零/编造比值；补查真实官方序列，无法核实主锚则 stale。
- **反锚定**：note 写出实际 ECI SOTA、90天增幅与一年季均，辅层数据各带日期；用 raw_history 上期同口径数据核实边际。首期来源切换不作 METR 与 ECI 的跨指标环比。

---

## 宏观与情绪 Macro & Sentiment (4)

### `accounting_events` — 会计造假/round-tripping 事件
- **Axis**: trigger
- **Cadence**: scan
- **Source**: 按窗口扫描 SEC https://www.sec.gov/newsroom/ 新闻稿、诉讼公告及 Reuters/WSJ 报道；raw 记录已确认事件/调查列表。收入 gross/net 争议或质疑不等于已确认造假，尽职扫描未见新事件按原映射处理
- **更新锚**: 已确认事件与调查列表。
- **Direction**: any_bad
- **Status mapping**: 任何已确认 = red / 调查中 = yellow / 无 = green

### `fed_policy` — Fed 政策方向
- **Axis**: trigger
- **Cadence**: live
- **Source**: CME FedWatch https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html 下次 FOMC 隐含动作；备源 https://www.investing.com/central-banks/fed-rate-monitor ，保留下次会议日期、当前利率与各档概率
- **Direction**: tighten_bad
- **Status mapping**: 隐含加息 = red / 维持高利率(通胀压力) = yellow / 隐含降息 = green

### `capex_reaction` — 资本开支指引市场反应
- **Axis**: trigger
- **Cadence**: periodic
- **Max age**: 120 days
- **Source**: 最近一轮 Mag7 财报上调 capex 当日相对 QQQ 的收益；价格用 https://stockanalysis.com/stocks/ 的公司历史价及 https://stockanalysis.com/etf/qqq/history/，媒体报道交叉。raw 保留事件日、公告、两条价格及相对收益；季报间隙核实最新事件未变则 current
- **更新锚**: 最近财报 capex 上调事件当日相对 QQQ 收益。
- **Direction**: punish_bad
- **Status mapping**: 系统性惩罚 = red / 偶发惩罚 = yellow / 奖励 = green

### `ceo_hedging` — CEO 表态对冲程度
- **Axis**: stage
- **Cadence**: scan
- **Source**: 按近60天扫描 Sam Altman / Sundar Pichai / Jamie Dimon / Satya Nadella / Mark Zuckerberg 的具名公开发言（bubble / irrational / overheated 等），主流媒体或实际演讲原文；raw 保存发言者、实际日期、内容与 URL。未见新相关发言以有记录扫描结论处理；AI安全/能力言论不能替代泡沫表态
- **更新锚**: 60天具名相关发言列表。
- **Direction**: hedging_bad
- **Status mapping**: 普遍承认过热 = red / 部分 = yellow / 无 = green

---

## 历史校准表（相似度比对用）

四个历史时点的指标颜色向量。2026-10-18 起结构修复不回写此历史矩阵；首个新口径期的判读需明示部分定义改变使相似度仅供模式参照，不能视作完整同口径历史回测。R=红 Y=黄 G=绿，`—`=该时点无合理类比（不计入该时点 match 分母）。AI 特有指标按括号内类比资产判定。**本表为初稿判定（2026-07-06），阈值随研究演进校订。**

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
| frontier_progress（类比底层技术进展速度） | G | G | — | G |
| accounting_events | G | Y | Y | Y |
| fed_policy | R | R | G | R |
| capex_reaction | G | Y | — | G |
| ceo_hedging | G | Y | Y | Y |

判定依据速记：1999-06 = Fed 开始加息、IPO 洪流、估值极端，但信用/广度/流量全部健康（红灯比例约 25%——与 2026-07 惊人相似）；2000-02 = 内部人 23x 减持、breadth 崩、vendor financing 24%、电信债利差走阔，红灯约 55%+；2007-10 = 信用型顶部，估值/科技侧指标多不适用；2021-11 = 估值+发行+内部人极端但信用面干净，Fed 转鹰是引线。frontier_progress 行几乎全绿：历轮顶部时底层技术进展均未停滞（顶来自融资/信用/政策），该指标是本轮 AI 周期的增量维度——它转黄/红没有历史先例可比，权重上应视为独立的强 trigger。

> **insider_sell_buy 口径切换提示（2026-08）**：本表 2000 峰值 23x 为 openinsider 时代口径；EDGAR 直聚口径下买盘常态近零，比值量级可能显著不同（首期实测 ~440x），且首次实测发现此前"黄仁勋 8 月卖出 $13M×2"等具名细节在 EDGAR 中不存在（系被封期间从旧新闻错误锚定）。相似度比对沿用颜色向量不受影响；比值阈值观察 4 期后再校订。

---

## 输出 JSON Schema（双语）

JSON 喂给两个 dashboard：中文版（aibubble-cn.github.io）和英文版（bubblewatch.github.io）。所以**每条文字字段都要中英文都出**。

```json
{
  "issue_number": 4,
  "as_of_date": "YYYY-MM-DD",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "summary": {
    "total_indicators": 25,
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
      "stale": false,
      "freshness": "new"
    }
  ]
}
```

### 快照新鲜度显示

新快照每项增加 `freshness`（new / current / stale），语义由 evidence 和实际核实结果确定：new 不加角标；current 显示“最新披露”/“Latest filing”，并显示原真实 as_of；stale 显示 STALE。新字段与 stale 布尔值必须一致。旧快照缺少 freshness 时只按原有 stale/as_of 沿用兼容显示，不能追溯推断其已核实为 current，也不写回历史文件。成功/失败包中 new/current/stale 计数与各项一致。

### 双语字段约定

- `value_display_en`：仅当 `value_display` 是中文文本时（如 "升温"/"加速中"/"强劲"）需要给英文翻译；纯数字单位（如 "+22%", "279 bps"）不需要 _en
- `note_en` / `verdict_desc_en` / `wow_changes[].note_en`：**必须**给。译文不要逐字对译，写得自然像英文新闻
- `verdict_label_en` 取以下固定映射，不要改：
  - 系统性顶部信号 → Systemic Top Signal
  - 高风险预警 → High Risk Alert
  - 中度警戒 → Moderate Caution
  - 观察期 → Observation
- `threshold_text_en`：用 `red / yellow / green` 替代 `红 / 黄 / 绿`，其它结构保持一致
- `suspect_static`（indicator 级可选字段）：仅当「数据抓取纪律」第 4 条触发时输出 `true`，并同时输出 `static_weeks`（int，连续未变/未获取的期数），其余情况两个字段都省略。**前端渲染角标**（中文「N 期未变」/ 英文「UNCHANGED xN」），不再是可忽略字段。
- `axis` / `stage_score` / `trigger_score` / `momentum` / `category_scores` / `similarity`：2026-07-06 起新增；前端对缺失做了兼容，但 routine 每期都应完整输出。
