# AI Bubble Watch / AI Bubble Monitor

监测美股 AI 泡沫风险，按 `INDICATORS.md` 定义的指标、两轴判读和历史向量生成双语周报，并更新网页。

**Dashboard**: https://crystal-xiaoxiao.github.io/ai-bubble-monitor/

## 当前执行方式

ChatGPT Work 每周一北京时间 07:00（周日 23:00 UTC）在云端直接研究和运行仓库脚本。GitHub 保存代码、台账与运行记录；原有 Actions 负责 prefetch、飞书转发和 Pages。无需个人电脑开机或自建服务器。

| 组件 | 作用 |
|---|---|
| `INDICATORS.md` | 指标定义、阈值、研究纪律、历史校准、双语输出要求 |
| `ROUTINE_PROMPT.md` | 与模型无关的研究和写作规范 |
| `automation/task.json` | 周期、数据闸门与运行配置；不绑定研究模型 |
| `automation/research-bundle.schema.json` | 可替换模型的统一交付接口 |
| `scripts/pipeline.py` | prepare / score / build / check / check-site |
| `RUNBOOK.md` | Work 执行、发布与失败恢复；将来迁 Actions 的边界 |
| `automation/WORK_PROMPT.md` | Work 定时任务的启动指令副本 |
| `docs/data/` | 当前网页数据、不可覆盖的历史快照、债务及原始值台账 |
| `runs/<cycle>.json` | 每周期证据、输入哈希、attempt 与发布包状态 |
| `feishu_outbox/` | 已入库待转发的消息；relay 发送后删除 |
| `.github/workflows/` | 现有 prefetch、feishu-relay、token-backfill |

## 数据质量与恢复

有效 prefetch 优先；过期或 partial/error 走备源。抓取失败保留旧值和真实日期并标 stale，超过 5 项则只产生失败通知，保留上期网页。评分、两轴、相似度、滞回、同值预警与发布文件由脚本统一处理；定性研究和原始来源真实性仍需研究者核验。

同一周期按 runs/已发布快照去重，发布前校验基准 SHA，一次提交所有相关文件。研究校验、GitHub 提交、网页发布和飞书送达分别验收，不能凭新 commit 或 outbox 入库宣称整轮成功。

## 运维

运行测试：`python3 -m unittest discover -s tests -v`

检查当前网页与仓库数据一致：`python3 scripts/pipeline.py check-site`

迁移详情、正式执行和失败重试见 [RUNBOOK.md](RUNBOOK.md)。修改模型只更换研究适配层；改为 GitHub Actions 调度时保留仓库契约/脚本/台账，另行验证新的模型认证与额度。

指标 ID 保持稳定；阈值变化须说明原因。指标数、axis、direction、数值阈值、历史颜色从 INDICATORS 读取；修改聚合公式时同步 pipeline 与测试。样式在 `docs/index.html`，本次迁移未改网页设计或历史研究内容。

## 迁移时的真实状态

2026-10-10 迁移时，最新已发布数据为 **Issue #27 · 2026-09-27**。10 月 8 日标为 Issue #28 的提交只包含数据不足的失败通知，未更新网页。本次只迁移执行架构，不补造一期研究。首次 Work 无人值守运行的研究、网页、通知结果需届时观察。
