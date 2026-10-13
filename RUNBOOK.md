# AI Bubble Watch — Work 执行与迁移手册

当前调度入口是 ChatGPT Work，仓库仍叫 AI Bubble Monitor。北京时间每周一 07:00（周日 23:00 UTC）运行。GitHub Actions 保留原有 prefetch、飞书转发和 Pages；不增加第二个研究调度器。无需个人电脑开机或另养服务器。

## 职责与可迁移边界

| 层 | 真理来源 | 换模型 / 换调度器时 |
|---|---|---|
| 指标、阈值、来源、研究纪律 | `INDICATORS.md` | 原样保留；修改聚合规则时同步脚本及测试 |
| 研究及写作规范 | `ROUTINE_PROMPT.md` | 同一契约交给新模型 |
| 模型交付接口 | `automation/research-bundle.schema.json` | 新模型生成相同 JSON |
| 周期、数据闸门、入口 | `automation/task.json`、`scripts/pipeline.py` | 同一 Python 命令 |
| 历史与运行记录 | `docs/data/`、`runs/` | 随仓库迁移 |
| 调度、模型调用、授权写入 | Work prompt / 将来的 Actions adapter | 只替换这层 |

`model: null` 表示不把模型选择写进研究逻辑，不代表平台提供了特定模型或自动切换承诺。迁到 Actions 时另行配置受支持的无人值守模型认证、额度、研究工具和写权限；本迁移未验证订阅登录凭据能否用于未来的 Actions，也未配置任何凭据。

## 结构修复生效边界

2026-10-18 UTC调度周期起按更新后的指标口径执行，不补跑、重算或改写已发布#28。已有快照/台账仍为历史事实；新的basis首期在中英文note与raw中注明不可比，并写raw.basis_switch=true；pipeline排除该项跨口径WoW/动量比较。历史相似度矩阵不变，首期判读必须说明定义切换限制解释。四项变更是KPMG显著员工采用的季度Δ、逐项已签NVDA承诺、同basis实际ARR增长二阶变化、ABS/项目融资信用状态。已发布历史不因前端增加freshness而回写。

## Work 正常执行

1. 获取远端 `main` 最新完整仓库，在独立工作目录执行。确认可以运行 Python 3，并可通过当前授权方式写 GitHub。读取 AGENTS、研究规范、指标定义、上期数据、债务/已签NVDA承诺/实际ARR台账、原始台账、prefetch。
2. `python3 scripts/pipeline.py prepare` 生成 `.run/context.json`。调度周期是最近已到达的周日 23:00 UTC 对应日期；输出日期取本轮开始的 UTC 日期，数据自身 `as_of` 保留真实日期。`ready=false` 时不再研究/发布。脚本也会阻止未处理 outbox 与历史快照覆盖。
3. 本轮证据写 `.run/bundle.json`。禁止拿旧新闻/上期值假装本轮抓到数据。模型填指标、证据、双语分析、债务台账与 WoW，脚本负责数值阈值校验、汇总、历史相似度、滞回、同值警告、快照和 outbox 组装。
4. `python3 scripts/pipeline.py score --bundle .run/bundle.json` 使用 prepare 的 `.run/context.json`；自定义上下文路径时加 `--context`，评分与 build 必须使用同一周期和准备日期。在得到确定性结果后写双语判读。定性状态、来源真实性、原始读数口径、ECI/SOTA 比较和分析质量仍必须逐项人工式研究检查；程序不替代研究判断。
5. `python3 scripts/pipeline.py build --bundle .run/bundle.json` 仅生成 `.run/release/`，不直接覆盖线上数据。
6. `python3 scripts/pipeline.py check --bundle .run/bundle.json` 重新校验并逐字节检查待发布文件。修正候选包后使用新的空 `--release .run/release-v2`，以免混入旧文件。
7. 按下节单个提交发布 manifest 中所有文件。失败时不要把其他工作区文件混入提交。
8. 核对远端提交的完整文件、Actions 结果及 `python3 scripts/pipeline.py check-site --expected .run/release/docs/data/latest.json`。失败报告不调用 check-site 验证新期，因为没有新期数据。Pages/CDN 可能延迟，可每次间隔不超过 60 秒、总计最多约 5 分钟查询；仍未更新则报告“已提交，网页尚未验证”，不能写“全链路成功”。

`build` 输出失败通知（stale>5）时是成功生成一个**失败记录包**，不是研究成功。manifest 只有 outbox + runs；不递增已发布 Issue、不改 docs。其他结构/证据/权限错误在当前 Work 任务中明确报告，不伪造可发布包。

## 研究包字段

根字段：`schema_version=1`、`cycle`（来自context）、`indicators`、`evidence`、`verdict_desc`、`verdict_desc_en`、`wow_changes`、`debt_ledger`、`debt_review`。可选 `nvda_commitments` / `arr_ledger` 为两份台账的完整候选对象；不提供则用仓库已存版本，同样执行结构校验。每条 indicator 沿用 INDICATORS 的完整双语字段；不要自算/填快照 summary。

`evidence` 以每个指标 ID 为键，每个值包括：

- `kind`: `prefetch` / `web` / `current` / `carry`；`checked_at`: 本轮实际检查时刻 ISO UTC；`rationale`: 原始数字、比较、定性判断或失败原因。
- `raw`: 本期原始读数对象。prefetch 模式由脚本从缓存复制实际 data，不能以模型提供的值替换。web 模式保存实际读数、真实观测期；current 模式仅用于实际核实仍为最新、未超龄的 periodic 披露，保留原始读数、latest_release_date、next_expected 和真实 as_of；carry 模式保存沿用的原始读数及实际失败原因。来源获取失败由脚本标记 `fetch_failed`；债务到期未完成对账须另行记录对账原因，不能误称来源访问失败。
- `urls`: 真正打开的研究来源 URL；`attempted_urls`: 获取失败时实际尝试过的主源和备源。不要把搜索结果标题当作已读取原文。
- 派生环比/比值可填 `calculation: {operator: "change_pct"|"ratio_pct"|"ratio", current: 120, previous: 100}`，脚本校验算术。依然必须在 raw/rationale 说明分子分母的出处和观测期；多项综合指标按 INDICATORS 写完整拆解，不能把不相关数字拿来凑结果。

`raw_history` 由脚本追加，保留过去 26 期及原有 `_meta`，不会让模型整文件替换。活源的稳定 raw 锚定字段见 `task.json.static_core_keys`，别名组内任选一个已定义键；这是历史数据兼容映射，不是评分阈值。数连续未变的绝对值、缺失期数和连续估算，不能因派生百分比变化重置。若更换真实数据口径，需要显式更新映射及测试，不能伪造键值凑过关。季度/低频调查不因周度未更新视为同值异常；本期实际核实同一披露且未超龄可 current。live/scan 不允许 current；全部 Cadence 和年龄界限在 INDICATORS。成功/失败包均记录 new/current/stale 数。扫描 evidence.raw 的 window/queries/sources_checked/events 按研究规范填写，空事件可以是有效扫描，不能伪造查询或成功访问。

`debt_review` 必填 `searched_urls`、`weekly_search_note`（无新增也要写）；距上次完整对账达到28天时优先实际重建，实际完成才填 `full_reconciliation:true`、`reconciliation_note` 并更新 last_full_recon。**2026-10-18 UTC周期起，每次到期未完成时填 `full_reconciliation:false`，记录真实尝试及未完成原因；pipeline 将 debt_capex_ratio 标 stale、原样沿用上期 value/status/as_of 及双语显示值，并保留原债务台账与真实 last_full_recon。** 该项计入 stale>5 闸门，未完成不再单独阻断整期发布；成功和失败 outbox 都单列“⚠ 债务完整对账逾期 N 天”（N=距上次对账天数−28，到期当天0天也提示未完成）。本期实际读取内容保留在 `evidence.raw.attempted_observations`，新增/修订候选交易及候选年度分子/分母保留在 `raw.pending_debt_updates`（`changed_deals`、`proposed_ms_anchor`、`proposed_capex_denominator_usd_b`），供后续真实对账恢复；这些是待核对线索，不当作已入账新债务或 WoW 发布。成功期证据随 raw_history/run 保留，失败期随 run 保留，下次研究先读取尚未对账线索并去重；未到期继续正常周度增量流程。完成对账时必须更新真实last_full_recon、全口径年度分子与capex分母及出处，并提供reconciliation_note及 `reconciliation_sources:[{scope,url,checked_at,raw_reading}]`：scope 至少覆盖 financing_anchor、capex_denominator、deal_reconciliation 各一条，本轮实际访问且在 searched_urls 中、checked_at为本轮时刻，raw_reading保留非空真实读数/拆解。不能只列URL宣称对账完成，不以周度扫描或旧锚代替。改旧 deal 时提供 `corrections: [{borrower, date, reason, source_url}]`；新 deal 按借款人、近似金额、±7 日去重。单笔新债务 ≥$10B 必须出现在 WoW 和通知。分子、分母保持全口径，周度台账只作下限；不要拿不完备的台账替换全量融资估计。

## 新台账与新鲜度接口

`docs/data/nvda_commitments.json` 保存每笔已签 equity/loan/convertible/担保；条件性总额仅纳入已签部分，担保纳入签署上限并区分实际付款。`docs/data/arr_ledger.json` 保存实际ARR/run-rate，gross/net及公司分开，原始数据日与披露日分开。两份台账只在成功release中有变化且通过校验时进入manifest；失败包不写台账。保留既有entry/point不可变ID，修订用新增superseding记录保留原条目，不覆盖旧值。pipeline从已校验台账生成raw.numerator_signed_usd_bn、ltm_revenue_usd_bn、nvda_coverage及raw.arr_calculations（实际端点/滞后日数/两段增速/acceleration_pp），模型不得把自由raw数字当权威台账。ARR截止日按最新实际读数日T（非报道发布日）往前3/6个日历月取，使用截止日或之前最新实际点，最大lag31天，真实日期/截止日/lag及原文限定全部可见；lag>0时中英文note明确披露序列/披露点及disclosed-series/reported observations；近9个月之前一个opening基线可作为明确标记的计算背景，周/月日期注明精度和区间终点；只称已披露序列增长代理，不称精确截止日经济增长、不插值。未来目标和预测不能作为已实现ARR；旧43–45%不能倒推NVDA清单。

新快照每项 `freshness`=new/current/stale：new不加角标；current显示“最新披露”/“Latest filing”并保留真实as_of；stale显示STALE。旧文件缺字段按原stale/as_of兼容，不能把旧“沿用”追溯称为本期核实最新披露。三态计数由pipeline生成并写成功/失败通知。

## 发布适配器与竞争处理

发布开始前选择当前**已经可用且获授权**的方式；两种方式都提交相同 manifest 文件。这是运行环境适配，不是被拒绝后更换通道。

- Work 的 GitHub 连接器：读取 main HEAD 和 base tree；确认它等于 context.base_commit。将 manifest.files 中的 UTF-8 文件作为 tree entries 一次创建 tree、创建以该 HEAD 为 parent 的 commit，再以 `expected_sha`、`force=false` 更新 main。不要逐个 Contents API 提交，避免数据、快照和 outbox 分开上线。读取远端文件比对哈希。若新 commit 已是 HEAD 的祖先且文件匹配（例如 relay 紧接着删 outbox），按已成功处理，不重复提交。
- 已提供认证的 git runner：确认工作区只有本次工作；把 release 中 manifest-listed 文件复制到同名路径，仅 `git add` 这些路径；单个 `git commit`、普通 `git push origin HEAD:main`。不 `git add -A`，不 force push，不读取/复制本地账号凭据。

远端 SHA 变化时先刷新完整仓库并重新 `prepare`、`build`、`check`。只有研究输入未变化且证据仍有效才复用候选包；否则更新受影响研究。不要把旧结果直接覆盖新一期，不把并发冲突当成授权错误。读请求/明确未送达的写请求最多有限重试；写结果不明时先读远端确认。若触发 Safety/权限/审批拒绝，保留错误并停止受阻动作，不换通道绕过。

## 重试、通知与完成标准

`runs/<cycle>.json` 记录每轮基准、输入哈希、证据、attempt、`failed_data` 或 `validated_release`。`validated_release` 只指通过质量闸门的发布包，不能当作 Pages/飞书已完成证明。正常调度默认不重跑已处理周期。

明确授权重试失败周期后，可用 `prepare --cycle YYYY-MM-DD --retry-failed`；先确认现有失败 outbox 已处理，消息结果不明时先查 relay logs。不要自动重发整期成功周报。已发布历史快照不可覆盖；研究更正应作为明确的新更正流程审阅。

飞书仍由现有 `feishu-relay.yml` 转发，迁移只加串行执行、读取最新 main、请求超时与 JSON 解析，避免并发读取旧 outbox。外部 POST 和 Git 提交并非同一事务：发送已成功但删除 outbox 的提交失败时，结果可能不明，必须检查日志后人工处置，不能声称 exactly-once。未发送迁移测试消息。

四个状态分开报告：研究校验 / GitHub 提交 / Pages 全量 JSON 比对 / 飞书 relay 结果。只有四项均有实际证据才称本轮全链路通过。首次无人值守运行还需观察实际结果。

## 迁移记录（2026-10-10）

- 仓库最新成功期为 #27 · 2026-09-27。Oct 8 名为 Issue #28 的提交只包含失败 outbox，未发布新期；本迁移不改任何研究数据。
- 可见旧 ChatGPT 任务在迁移前已经 paused，ID 见 task.json。工具列表未能识别另一个独立 Codex Cloud 任务，不能声称其已停止；若有独立任务，应取得其实际 ID/链接后停用，避免多个调度器同时写同一仓库。
- `automation/archive/CLAUDE_ROUTINE_PROMPT.md` 仅保留更早的 Claude 配置历史；不声称已操作过该第三方调度器。
- Work 的有效任务 prompt 与 `automation/WORK_PROMPT.md` 相同；日程保持每周一北京时间 07:00。迁移时原 prefetch 为周日21:00 UTC；2026-10-12 取数修复后改为周六13:23、周日15:23 UTC，保留72小时有效期。prepare 显示不可用先检查 Actions；正在跑则最多等15分钟、单次≤60秒，完成后获取最新 main 并重新 prepare。insider/token 不在 Work 直连认证 API，缓存不可用则 stale。

## 维护验证

`python3 -m unittest discover -s tests -v` 覆盖 stale 边界、假刷新日期、prefetch 过期/partial、原始值同值预警、基准冲突、重复周期、current 年龄/Cadence、空事件扫描、债务对账逾期警告、数值阈值及降档滞回。测试使用临时目录合成输入，不写远端、不发送消息。

`python3 scripts/pipeline.py check-site` 比对当前库中的整份 latest 与网页 JSON。它证明当前网页和仓库一致，不证明下一轮定时研究或飞书投递一定成功。
