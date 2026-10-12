执行一次 AI Bubble Watch（仓库名称 AI Bubble Monitor）正式周报。目标仓库 crystal-xiaoxiao/ai-bubble-monitor，main 分支。2026-10-18 UTC周期起按仓库更新口径执行，不补跑、重算或覆盖已发布#28。

在本 Work 云端会话直接读取仓库、运行 Python、研究、校验和提交，不创建 Dot/Codex Cloud worker，不调用 cloud_threads.create，不递归创建或触发定时任务；不依赖用户电脑、本地 Codex CLI 或自建服务器。

1. 获取 main 最新完整仓库。读取 AGENTS.md、RUNBOOK.md、ROUTINE_PROMPT.md、INDICATORS.md 和 automation/task.json；按仓库最新规则执行，模型不硬编码。若缺少代码执行、来源访问或已授权 GitHub 写入能力，明确报告具体阻塞，不伪造更新。
2. 执行 python3 scripts/pipeline.py prepare。ready=false 表示该周期已处理，返回已有状态并停止；先检查 runs 与未完成 outbox，不重复发布或重复通知。采用仓库规定的周日 UTC 调度周期及真实数据日期。
3. 在 Work 内完成全部研究，按 automation/research-bundle.schema.json 写 .run/bundle.json。必须真正打开来源、保存本轮访问时间、URL、原始读数和计算依据；有效且不足 72 小时的 prefetch 优先。按 Cadence 执行 new/current/stale 三态：实际核实仍是最新且未超龄的 periodic 可 current，保留旧 value/status/as_of 并填 latest_release_date/next_expected；抓不到才 stale。扫描保留 window/queries/sources_checked/events，空事件可通过。prefetch 不可用先查正在运行的 Actions，最多等15分钟（单次≤60秒）后刷新 main、重新 prepare；Work 不直连 OpenRouter API 或 efts.sec.gov。债务按周增量与28天完整对账，通常未完成警告逾期；2026-10-18周期必须实际完成完整对账并更新真实日期、全口径分子分母及deal对账并写三类reconciliation_sources的本轮真实访问/原始读数，未完成不得发布成功包，不以警告代替。前沿使用 ECI 主锚/困难基准/发布密度三层，METR 有更新时参考。复合锚、增量台账、basis 切换和媒体/snippet证据按最新研究规范。enterprise用KPMG同一显著员工采用问题的季度Δpp（≥+3绿，−3至<+3黄，<−3红），取消旧72%锚和水平阈值；NVDA按已签逐项equity/loan/convertible/担保台账只计已签部分或担保上限；ARR取近9个月实际披露，gross/net分开，以最新实际读数日T（非报道发布日）及前3/6个日历月截止日比较两段增速，端点只用截止日或之前最新实际读数且lag≤31天，保留实际日期/lag/限定，只称已披露序列增长代理，不含预测或插值；dc_abs_spread为近90天ABS/项目融资信用状态，事件阈值按最新INDICATORS。新台账只增量追加/有出处修订，首个basis切换期双语明示不可比并填raw.basis_switch=true，pipeline不算该项跨口径WoW/动量；首期判读说明定义变化限制历史相似度解释，历史矩阵不回写。遵守双语、反锚定与最新研究口径。
新快照freshness三态需与证据一致：new无角标，current“最新披露”/“Latest filing”且保留真实披露日，stale显示STALE，历史缺字段只兼容不回写。
4. 用 score 生成确定性评分，再写双语判读；执行 build 和 check。stale>5 时脚本只生成失败 outbox 和失败记录，不更新网页、快照或台账。校验不通过不得跳过、改阈值或假造证据。事实依据仍由研究者检查，程序通过不代表事实已被独立验证。
5. 按 RUNBOOK 的发布适配器，用已经可用且已授权的 GitHub 写入方式将 manifest 所列文件作为单个提交写入 main；写前比较远端基准 SHA，冲突时重新获取、校验，不 force push。审批/权限/Safety 拒绝时停止该动作并报告，不切换通道规避。不要提交 .run、凭据或额外文件。
6. 核验远端提交与文件；发布成功后检查 Pages 完整数据，Feishu Relay 由现有 workflow 转发 outbox。分别报告研究校验、GitHub 提交、网页发布、通知状态，不把队列入库说成飞书已发送。对网络读取/查询可有限重试；消息发送结果不明时不得盲目重发。

最后用中文给出 Issue/日期、红黄绿/风险温度、两轴、判读中英、相似度 top1、WoW/静态警告/新债务及 new/current/stale 数、债务对账逾期警告、commit 链接、网页验证和通知状态；失败给出具体步骤及完整非敏感错误。不要因为仓库有新 commit 就宣称研究已更新。
