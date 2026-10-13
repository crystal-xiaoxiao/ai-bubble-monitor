# AI Bubble Watch — 模型无关研究规范

执行入口已于 2026-10-10 迁到 ChatGPT Work。仓库名、网页和研究产品仍为 AI Bubble Monitor。

- 研究契约与阈值以 `INDICATORS.md` 为准；本文保留完整研究、双语写作和质量要求。
- 执行、发布、去重、重试与通知按 `RUNBOOK.md`；线上 Work 启动 prompt 版本见 `automation/WORK_PROMPT.md`。
- 模型只提交 `automation/research-bundle.schema.json` 所定义的研究包。评分先跑 `score`，最终快照、历史追加和 outbox 由 `pipeline.py build/check` 生成与校验。以下“写入”描述输出要求，不授权手写绕过脚本。
- 不创建 Dot/Codex Cloud worker，不依赖特定模型、个人电脑或自建服务器。更早 Claude prompt 仅在 `automation/archive/` 留档，不再是当前执行指令。
- 日程保持每周一北京时间07:00；本次结构修复从2026-10-18 UTC调度周期生效，不补跑/重算/改写已发布#28。每项首期切换在双语 note/raw.basis 明示不可比，raw.basis_switch=true；pipeline排除跨口径WoW及动量比较，不当作真实改善。

### 1. 读配置和上周数据

仓库已 clone 在工作目录，直接读本地文件（读不到再用 WebFetch raw 兜底）：
- `INDICATORS.md` → 全部指标定义（**指标总数 N 以该文件为准**）、阈值、direction、axis 标签、聚合判读规则（两轴/动量/滞回/历史相似度及校准表）、JSON schema（含双语字段约定）
- `docs/data/latest.json` → 上期快照，用于 WoW 对比、降档滞回判断和 fallback
- `docs/data/debt_ledger.json` → 债务交易台账（debt_capex_ratio 的周度数据源）
- `docs/data/nvda_commitments.json` → 已签署 NVDA 客户股权投资/贷款/可转债/担保逐项台账，签署部分和上限必须可追溯；以后只追加/有证据修订，不从旧43–45%倒推总额
- `docs/data/arr_ledger.json` → 最近9个月实际 ARR/run-rate 披露台账，OpenAI gross/net 分开，公司/日期/basis 对齐；未来目标与预测不计
- `docs/data/raw_history.json` → 原始值台账（所有环比/增速/比值从这里的上期原始值计算）
- `docs/data/prefetch/latest.json` → GitHub Actions 每周六 13:23 UTC、周日 15:23 UTC 机械抓取的原始数据（insider_sell_buy / token_volume_mom / top5_weight / hy_oas 四个映射源，以及研究辅助 frontier_eci）。**读法：先查 `_meta.fetched_at` 距今 <3 天，再查对应 `sources.*.status=="ok"`，两者都满足才可用**；partial/error 或文件过期 → 先只读查看 prefetch Actions 是否正在运行；若在跑最多等15分钟（单次等待≤60秒），完成后取最新 main 并重新 prepare。仍不可用才走定义的备源链；insider/token 没有 Work 备源，必须 stale

新一期 issue_number = 上期 + 1
新一期 as_of_date = context.as_of_date（本轮开始的 UTC 日期；各指标 as_of 仍为真实观测日）

### 2. 抓全部指标当前值（尽量并行）

按 INDICATORS.md 里每个指标的 source：
- **prefetch 覆盖的指标（insider_sell_buy / token_volume_mom / top5_weight / hy_oas）一律先读 `docs/data/prefetch/latest.json`**（读法见第 1 步）：该源的 `data` 就是本期原始数据点，note 引用其 `summary` 里的数字，`as_of` 取该源的 `as_of` 字段（是数据自身日期，**不要改写成运行日期**）；prefetch 不可用才走 INDICATORS.md 里写明的备源链
- 稳定 URL（multpl 等）→ WebFetch；主源失败走 INDICATORS.md 里写明的备源链
- 指标按 Cadence 和最新主源表抓取；扫描类用有记录 WebSearch + 实际来源访问，periodic 核实最新披露。**Work 不直连 OpenRouter API 或 efts.sec.gov**，insider/token 只走 prefetch，公开新闻不替代聚合读数
- `debt_capex_ratio` → 严格按 INDICATORS.md「周度增量台账 + 28 天完整对账」规则：**每周**搜过去 7-10 天新公告的 AI/数据中心债务 deal（关键词轮换），去重后按正常增量流程更新台账，note 给出周度边际（本周新增 $XB / YTD 累计 / 年化 run-rate）。距 last_full_recon ≥28 天时优先实际完成自下而上拆解，核实全口径分子、分母及deal对账与出处，实际完成才更新 last_full_recon。**2026-10-18 UTC周期起，每次到期但未完成时，pipeline 将 debt_capex_ratio 标 stale，原样沿用上期 value/status/as_of 及双语显示值，保留原台账和真实 last_full_recon；计入 stale>5 闸门，成功/失败通知均单列到期或逾期警告。** 写出本期尝试、未完成原因与逾期天数，周度新线索保留在研究证据中供下次对账；未完成不再单独阻断整期发布，不伪造对账。未到期或本期完成时继续正常增量及本期 as_of 更新。
- `frontier_progress` → 按 INDICATORS.md 三层量化：Epoch ECI SOTA/90天增幅（主锚，优先有效 frontier_eci prefetch）+ 困难基准90天 SOTA 位移 + 发布密度与叙事。METR 仅有新观测时参考；按 INDICATORS 的50%季均比较与连续两个窗口停滞规则，首期写明主锚切换；判定必须与 raw_history 上期数值对比
- `enterprise_deploy` → KPMG同一问题 significant workforce adoption，以相邻季度 current_pct−previous_pct 的百分点变化评分：≥+3绿，−3≤变化<+3黄，<−3红。取消旧72%锚与红50/黄65的水平阈值；Q3 2026官方44%、Q2 23%、去年10%，真实披露日2026-09-24，不能把62%agent构建/部署问题混进来。季度间核实同一最新披露可 current，年龄≤200天。
- `nvda_invest_revenue` → 读逐项已签署台账；equity/loan/convertible/担保只计可确认已签部分，条件性总额与未签意向排除，担保用签署上限并明示并非实际支付。对照最新LTM收入计算，不与旧43–45%直接作环比。分子清单只增量更新并保留修订证据；未知已签金额保留未知及覆盖缺口，可核实和只称下限，不虚构完整总额。
- `arr_2nd_deriv` → 查近9个月实际披露，按同公司、同 gross/net basis 分开计算最近3个月增速与前3个月增速之差。相对最新实际读数日T（非报道发布日）取T、T−3及T−6个日历月截止日，优先截止日读数，允许取截止日或之前最新实际披露且滞后≤31天；raw必须保留真实日期、截止日、lag及原文限定。任何lag>0必须双语说明“披露序列/披露点”与 disclosed-series/reported observations；大于/约读数保留限定称 reported-point estimate。稀疏披露称“已披露序列的3个月区间增长代理”，不是精确经济增长。可保留9个月之前最近一个实际opening基线作计算背景，注明范围；周/月精度注明真实观测区间，不编造精确日。超31天或basis不明就不可比，不插值、不把预测/年底目标填入。每次新披露追加台账；绝对ARR上升不等于二阶导加速。
- `dc_abs_spread` → 近90天“数据中心 ABS/项目融资信用状态”；已确认违约/不可抗力/降级/撤回/被迫大幅重定价，或同口径利差报道走阔≥50bp为红；确认延迟/条款收紧为黄；顺利发行或有效扫描无事件为绿。保留原ID，raw按INDICATORS事件类型和 confirmed布尔值记录，不只扫描CMBS、也不把普通公司债价当项目/ABS实测利差。
- **反锚定纪律（全局，见 INDICATORS.md「数据抓取纪律」）**：活源数值型指标的 note 必须写出本期实际抓到的原始数据点（如 insider 卖/买总金额、token 30 日绝对量），给不出=没抓到=按 stale 处理；本期各数值型指标的原始输入写入研究包 evidence.raw，**由 pipeline 追加写入 raw_history.json**（每指标保留 26 期）；**同值预警数 raw 里的核心原始绝对值**（不数派生 value——MoM%/比值在变不能重置计数）：原始值连续 3 期不变或连续 3 期缺失 → 输出 `suspect_static: true` + `static_weeks: N` 并准备飞书提醒行

每个指标产出（**注意双语**）：
{
  id, value, value_display,
  value_display_en (仅当 value_display 是中文文本，比如"升温"/"加速中"，需要英文翻译；纯数字单位如 "+22%" 不需要),
  status, as_of, source_url,
  threshold_text (中文版, 例如 ">35 红 / 25-35 黄 / <25 绿"),
  threshold_text_en (英文版, 例如 ">35 red / 25-35 yellow / <25 green"),
  note (中文 1-2 句解读),
  note_en (英文 1-2 句解读，自然像英文新闻不要逐字对译),
  stale: false（new 或经本期实际核实且未超龄的 periodic current；详见下面三态）
}

**新鲜度三态（stale 表示“没能核实”，不是“没有新数据”）**
- **new**：本期取得新观测，as_of 保留真实观测日；有记录的本周扫描也是新观测。
- **current（核实仍为最新）**：仅 Cadence=periodic。本期确实打开非空 urls 的来源，确认最新披露仍是上期同一份；value/status/as_of/双语显示值原样保留，stale=false、evidence.kind=current，raw 保留原始读数及 `latest_release_date`、`next_expected`。next_expected 只写已公布日期，未知写“尚未公布”，不猜。年龄按真实 as_of 至本轮 UTC 日期计算，≤120天，enterprise_deploy ≤200天；超龄不能 current。current 不计 stale 闸门，不把旧披露写成本期日期。
- **stale**：本期主备源都无法核实、current 超龄，或2026-10-18 UTC周期起债务完整对账到期但未完成；kind=carry，沿用真实旧日期并计入闸门。债务对账未完成需如实写对应原因，不误称数据源不可用。

**扫描类证据**：本周实际完成定义窗口的扫描，kind=web，as_of=扫描日；raw 必有 `window:{start,end}`（真实日期）、非空 queries、非空 sources_checked（成功检查的 URL 字符串或 `{url,status:"ok"}`）、`events:[{date,what,url}]`。events 可为空，双语 note 写“本周扫描未见新事件”，这是尽职扫描结论，不是声称确认所有事件为零；失败 URL 放 attempted_urls，不计成功来源，搜索/来源全失败必须 stale。

**复合指标**：锚定分项按 INDICATORS 的“更新锚”；锚拿到新值即 new，其他分项可沿用但各带日期，双语 note 点名沿用项。不得以无关新数据代替锚；辅助缺口会改变状态时明确依据。

**台账指标**：debt_capex_ratio、NVDA承诺分子、IPO名单以上期 raw/台账为基线只找新增或变化并去重；债务每28天优先实际完整对账、NVDA财报后完整核对。2026-10-18 UTC周期起，债务到期未完成则保留原台账、该项标 stale 并单列警告，按总 stale 数决定发布。不清空历史。raw.basis 写 gross/net、全球/美国、TTM/YTD 或价格来源；跨口径不算环比、二阶差分或 value_change WoW，状态按同口径分项及方向证据判断。

**证据分级**：IR/SEC、官方统计、数据站，以及 Reuters/Bloomberg/CNBC/WSJ/FT/The Information/Axios 的具体报道数字可用，媒体数字标“媒体口径”。原文403/付费墙先找 Yahoo Finance/MarketScreener/Investing.com/TipRanks 转载或 PR Newswire/BusinessWire/GlobeNewswire 新闻稿并实际打开。仅搜索摘要时至少两个独立来源数字一致（同稿转载不是独立），raw.tier=snippet 并记录对应来源；snippet 不能成为红灯升级的唯一依据。

抓不到时（prefetch 与备源链全部失败）：
- 沿用 latest.json 上周值（包括 _en 字段），stale=true；**`as_of` 必须保留上期的真实 as_of，绝对禁止写成本期日期**；note 改为"沿用 {上期 as_of} 值（数据源暂不可用）"，note_en 改为 "Carrying value as of {上期 as_of} (source unavailable)"
- **红线：本期日期只用于本期新数值观测或实际完成的扫描；current 永远保留真实披露日；new 数值源也保留来源自身日期（可能早于运行日）**——历史教训：被封期间 as_of 每周照写新日期、stale 照写 false，导致停更 5 周在看板上完全不可见
- stale 累计 > 5 个 → 中止，跳到第 7 步发错误提醒

### 3. 评分

按 INDICATORS.md direction 规则给每个指标打 status (red / yellow / green)。
qualitative 指标由 WebSearch 结果直接判断 status。

### 4. 算聚合（全按 INDICATORS.md「聚合判读」，N = INDICATORS.md 定义的指标总数）

- red_count / yellow_count / green_count
- red_pct = red_count / N * 100（1 位小数）；weighted_risk_score = (red_count + yellow_count*0.5) / N * 100（1 位小数）
- **两轴**：按每个指标的 axis 标签分组，红=100/黄=50/绿=0 取均值 → stage_score / trigger_score（1 位小数），并按 INDICATORS.md 区间表给 stage_label(_en) / trigger_label(_en)
- **category_scores**：6 个类别各自的指标分均值
- **momentum**：对比上期快照的 status 迁移（恶化/好转计数，绿→红算 2 级；上期不存在的指标不计入），net ≥ +4 或 ≤ -4 时按规则在 verdict_desc 提示
- **similarity**：按 INDICATORS.md 文末【历史校准表】逐指标比对四个历史时点（同色=1/相邻=0.5/红绿对立=0，除以该时点有定义的指标数），输出 4 条 similarity 数组（按 match_pct 降序）

判读 verdict_label / verdict_label_en 取以下固定映射：
- 系统性顶部信号 / Systemic Top Signal
- 高风险预警 / High Risk Alert
- 中度警戒 / Moderate Caution
- 观察期 / Observation

档位判定顺序（INDICATORS.md 有完整规则）：基础档位（red_pct ≥ 60/40/25/else）→ ①共振升级（估值红 ≥2 且资金面红 ≥3 → 至少高风险预警）→ ②两轴升级（stage ≥60 且 trigger ≥50 → 至少高风险预警；stage ≥60 且 trigger ≥65 → 系统性顶部）→ ③降档滞回（升档即时；降档需本期与上期基础判读连续 2 期低于现档位）。触发任一升级在 verdict_desc 末尾注明哪条。

verdict_desc 和 verdict_desc_en 都要写；须引用相似度最高的历史时点，并点名当前与2000-02向量的主要差异指标。2026-10-18首个新口径期必须注明部分指标定义切换限制历史相似度解释；历史颜色矩阵和快照均不回写。

**verdict_desc(_en) 排版格式（两个语言版本同构，前端按此渲染）**：
- 用 `\n\n`（连续两个换行符）分成 **4-6 个短段落**，每段一个主题，不允许整段不分段
- **第一段是一句话结论（TL;DR 前置）**：本期最重要的判断 + 最主要的动因，中文 ≤80 字 / 英文 ≤50 词，段首用 `**一句话**：`（英文 `**Bottom line**: `）
- 其余每段段首用 `**2-6 字小标题**：`点明该段主题（如 `**广度**：`、`**信用面**：`、`**反向证据**：`、`**判读**：`）；档位升级注明、分母提醒、相似度引用等既有强制内容照常写，放进对应段落即可
- markdown 记号**只允许 `**` 加粗**，禁止 #、列表符、表格、斜体等其他记号
- 目标长度：中文全文 800-1500 字、英文 500-900 词；超长时优先砍过程性叙述，保留结论、数据点和反向证据

### 5. WoW 变化

对比 latest.json 每个指标上周 status：
- status_upgrade: green→yellow / yellow→red / green→red
- status_downgrade: red→yellow / yellow→green / red→green
- value_change: status 没变但数值变化 >10%（仅同口径数值型；来源/basis 切换首期不计；状态颜色差异也不当作真实升级/降级）

每条变化（双语）：{ indicator_id, type, from, to, note (中文一句话), note_en (英文一句话) }
保留最重要的 5 条（红灯转换优先）。上期快照不存在的指标（新增/换入首期）不计入。debt_ledger 本周若有单笔 ≥$10B 的新 deal，也要作为一条变化收录。

### 6. 拼新快照 JSON

按 INDICATORS.md 里的 schema（双语完整）。检查清单：
- history_seed: 从 latest.json 取出，append {week (MM-DD), red_pct, risk_score}，保留最近 10 条
- indicators 数组长度必须 = INDICATORS.md 定义的指标总数（id 清单逐一对得上，不增不减）
- summary.red+yellow+green = 指标总数
- summary 必有：verdict_label(_en) / verdict_desc(_en) / stage_score / stage_label(_en) / trigger_score / trigger_label(_en) / momentum / category_scores / similarity
- 每个 indicator 必有 note 和 note_en 及 axis；textual value 必有 value_display_en
- wow_changes 每条必有 note 和 note_en
- 确认 debt_ledger.json、nvda_commitments.json、arr_ledger.json 与 raw_history.json 按规定增量更新，只随脚本manifest发布
- 每项 freshness=new/current/stale 与 evidence/stale 一致；new无角标，current“最新披露”/“Latest filing”且保留真实日期，stale显示STALE；旧快照缺字段保留原有兼容，不回写历史

## 发布与运行总结

不得直接请求飞书 webhook，不读取其 secret，不把凭据写入文件。GitHub Actions 消费 pipeline 生成的 outbox。正常包包含 snapshot/latest/debt/raw_history/outbox/run；stale>5 的包只含失败 outbox 和失败 run。除本次明确改变的 enterprise季度Δ阈值与dc信用状态映射外，其余评分阈值及 stale>5 闸门不变；按最新 Cadence、来源和证据分级执行，不以达到预期 stale 数为目标牺牲事实核验。2026-10-18 UTC周期起，债务完整对账每次到期未完成都将该项标 stale 并计入总数，成功/失败通知单列警告；优先实际完成对账，未完成不再另设整期发布阻断，不伪造对账。

按 RUNBOOK 单次提交 manifest 文件，确认远端 SHA、Pages 整份 JSON 与 relay 状态。分别输出 Issue/日期、红黄绿/风险温度、两轴、判读中英、历史相似度 top1、WoW/静态预警/新债务及 new/current/stale 数、提交链接、网页和通知状态。权限或 Safety 拒绝要如实报告，不更换通道规避。未知消息结果不得盲目重发。

## 分析与写作风格（Crystal 偏好，2026-10-09）

本节规范分析文字怎么写；本任务既有的输出格式、字段、围栏、数据口径、质量闸门与禁止事项优先，不得为了风格删减或改动。

尤其在投资研究和深入分析中，请以形成判断、支持决策为目标。结论先行，明确给出你更倾向的观点、最可能的情景及其决策含义，再解释关键依据。围绕真正决定结果的核心因素展开，区分不同证据的重要性和可信度，避免机械地等量罗列 pros and cons，也不要在每个观点之后附加大量限制、反驳和 hedging comments。只突出可能实质改变结论或影响决策的关键风险，并说明什么新证据会让你改变判断。比较多个选项时，尽量给出明确排序和取舍。保留分析深度与事实准确性，独立判断，不迎合我；证据不足时明确指出具体缺口，避免泛泛而谈的免责声明。
