执行一次 AI Bubble Watch（仓库名称 AI Bubble Monitor）正式周报。目标仓库 crystal-xiaoxiao/ai-bubble-monitor，main 分支。

在本 Work 云端会话直接读取仓库、运行 Python、研究、校验和提交，不创建 Dot/Codex Cloud worker，不调用 cloud_threads.create，不递归创建或触发定时任务；不依赖用户电脑、本地 Codex CLI 或自建服务器。

1. 获取 main 最新完整仓库。读取 AGENTS.md、RUNBOOK.md、ROUTINE_PROMPT.md、INDICATORS.md 和 automation/task.json；按仓库最新规则执行，模型不硬编码。若缺少代码执行、来源访问或已授权 GitHub 写入能力，明确报告具体阻塞，不伪造更新。
2. 执行 python3 scripts/pipeline.py prepare。ready=false 表示该周期已处理，返回已有状态并停止；先检查 runs 与未完成 outbox，不重复发布或重复通知。采用仓库规定的周日 UTC 调度周期及真实数据日期。
3. 在 Work 内完成全部研究，按 automation/research-bundle.schema.json 写 .run/bundle.json。必须真正打开来源、保存本轮访问时间、URL、原始读数和计算依据；有效且不足 72 小时的 prefetch 优先。抓不到则沿用真实旧日期并 stale=true。债务按周增量检索与 28 天完整对账；前沿进展保留 METR/困难基准/发布密度三层。遵守双语、反锚定与原有研究口径。
4. 用 score 生成确定性评分，再写双语判读；执行 build 和 check。stale>5 时脚本只生成失败 outbox 和失败记录，不更新网页、快照或台账。校验不通过不得跳过、改阈值或假造证据。事实依据仍由研究者检查，程序通过不代表事实已被独立验证。
5. 按 RUNBOOK 的发布适配器，用已经可用且已授权的 GitHub 写入方式将 manifest 所列文件作为单个提交写入 main；写前比较远端基准 SHA，冲突时重新获取、校验，不 force push。审批/权限/Safety 拒绝时停止该动作并报告，不切换通道规避。不要提交 .run、凭据或额外文件。
6. 核验远端提交与文件；发布成功后检查 Pages 完整数据，Feishu Relay 由现有 workflow 转发 outbox。分别报告研究校验、GitHub 提交、网页发布、通知状态，不把队列入库说成飞书已发送。对网络读取/查询可有限重试；消息发送结果不明时不得盲目重发。

最后用中文给出 Issue/日期、红黄绿/风险温度、两轴、判读中英、相似度 top1、WoW/静态警告/新债务/stale 数、commit 链接、网页验证和通知状态；失败给出具体步骤及完整非敏感错误。不要因为仓库有新 commit 就宣称研究已更新。
