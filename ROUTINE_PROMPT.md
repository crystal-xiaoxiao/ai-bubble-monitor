# Routine Prompt — 线上周报 routine 的真理副本

> ⚠️ 这个文件是**线上正在跑的 routine 的版本化副本 + 运维说明**。改 routine 行为时，请同步改这里，保持一致。
>
> 历史提示：早期版本用过 GitHub PAT + Contents API + 直接 curl 飞书。**那套已废弃**。现在的机制见下方「工作机制」。

---

## ⚠ 必须同步（2026-08-23 周日 run 之前）

2026-08-17 修复数据源停更（openinsider/openrouter 等被沙箱 egress 403，值静默冻结数周）。本次改动：
1. **prefetch 优先**：GitHub Actions（`prefetch.yml`，周日 21:00 UTC）机械抓 4 个受限源写 `docs/data/prefetch/latest.json`，routine 对 insider_sell_buy / token_volume_mom / top5_weight / hy_oas 一律先读它；
2. **兜底诚实化**：沿用上期值时必须保留上期真实 `as_of` 并标 `stale=true`（此前写当期日期+false，导致停更不可见）；
3. **同值预警改口径**：数 raw 原始绝对值（不数派生 value），输出 `static_weeks`；
4. **insider 换 SEC EDGAR 直聚口径**：首期比值量级会大变（~440x vs 旧估算 25x），wow_changes 的 note 必须解释是口径切换而非市场突变。

**操作只需一次复制粘贴**（约 1 分钟）：
1. 打开 https://claude.ai/code/routines → 找到 "AI Bubble Monitor Weekly" → 编辑 prompt
2. 全选删除旧内容，把下方「## 线上 prompt」代码块**整段**复制粘贴进去
3. 保存。（也可以在有 /schedule 技能的 Claude Code 会话里说"把 ROUTINE_PROMPT.md 的线上 prompt 同步到 routine"，让 Claude 用 RemoteTrigger 代劳。）

同步完成后删掉本节。

---

## 当前 routine 身份

| 项 | 值 |
|---|---|
| 名称 | AI Bubble Monitor Weekly |
| Routine ID | `trig_01PWcXSgNk1CVHAPQN52Ye1z` |
| Cron | `0 23 * * 0`（每周日 UTC 23:00 = 周一北京 07:00） |
| Model | `claude-opus-4-8` |
| 仓库 | `crystal-xiaoxiao/ai-bubble-monitor`（沙箱自动 clone） |
| 管理页 | https://claude.ai/code/routines |

## 工作机制（重要，和老文档不同）

```
        每周日 UTC 23:00
              │
              ▼
   云端 routine（沙箱里 clone 好仓库）
   读 INDICATORS.md + 上周 latest.json
              │
   抓全部指标（N 以 INDICATORS.md 为准）→ 评分+两轴聚合 → 拼双语 JSON
              │
     ┌────────┴─────────┐
     ▼                  ▼
  写快照文件          写 feishu_outbox/{date}.json
  docs/data/*.json    （飞书 payload）
     │                  │
     └────────┬─────────┘
              ▼
   git add/commit/push origin HEAD:main   ← 沙箱自带 git 认证，无需 token
              │
     ┌────────┴───────────────────────┐
     ▼                                 ▼
  GH Pages 重建（三个看板）      feishu-relay.yml 触发
  从 latest.json 拉数据          POST 到 FEISHU_WEBHOOK_URL → 删 outbox 文件
```

**三条关键设计：**
1. **写仓库一律用 git 直推**（`git push origin HEAD:main`），沙箱自带 git 认证 —— **prompt 里不放任何 token**，不用 GitHub Contents API。
2. **飞书不能在沙箱里直接 curl**（Anthropic egress proxy 拦 `open.feishu.cn`，403）。所以 routine 把飞书消息写成 `feishu_outbox/{as_of_date}.json` 文件 push 上来，由 `.github/workflows/feishu-relay.yml` 检测、转发、删除。webhook 存在 GitHub Actions secret `FEISHU_WEBHOOK_URL` 里。
3. **双语**：中文站 aibubble-cn.github.io 与英文站 bubblewatch.github.io 共用同一份 `docs/data/latest.json`，所以每条文字字段必须中英文都出。

## 改 routine 怎么办

- **改指标定义/阈值/评分/拆解方法/节奏** → 只改 `INDICATORS.md`。routine 每次运行实时读它，**自动生效**，不用动 routine 本身。
- **改 routine prompt 本身**（如指标总数、`/N` 聚合公式、长度校验、流程步骤）→ 改下面这段「线上 prompt」，并同步更新线上 routine：
  - 网页：https://claude.ai/code/routines 编辑该 routine，或
  - 在 Claude Code 里用 `/schedule`（底层用 `RemoteTrigger` 工具：`list` → 找到 `trig_01PWcXSgNk1CVHAPQN52Ye1z` → `update` 替换 `job_config.ccr.events[].data.message.content`）。OAuth 走账号内，**无需任何密钥**。
- **删 routine** → 只能在 https://claude.ai/code/routines 手动删（API 不支持删除）。
- 加减指标时记得：`INDICATORS.md`（定义 + 头部数量 + 历史校准表行）+ `latest.json` 手动 seed（想立即上线的话）。线上 prompt 已去 N 化（2026-07-07 起）、三个前端计数已动态化（读 `total_indicators`），这两处不再需要逐次同步。前端 meta description 已改为不含具体数字。

## 一次性设置（已完成，留档备查）

1. **飞书机器人** → 拿到 webhook URL。
2. **GitHub Actions secret**：仓库 Settings → Secrets and variables → Actions → 新建 `FEISHU_WEBHOOK_URL` = 你的 webhook。（`feishu-relay.yml` 用它转发。）
3. **workflow**：`.github/workflows/feishu-relay.yml`（已在仓库里，push outbox 文件即触发）。
4. **routine**：已创建（见上方身份表）。

> 不再需要生成 GitHub PAT —— routine 用沙箱 git 认证，relay 用 Actions 自带的 `GITHUB_TOKEN`。

---

## 线上 prompt（完整内容 · 与 routine 一致）

```
调度说明：每周一北京时间 07:00（即每周日 UTC 23:00）运行一次。Cron 表达式：0 23 * * 0

你是 AI Bubble Monitor 周报 routine。每次运行执行完整流程：数据采集 → 评分 → 聚合（风险温度 + 两轴 + 动量 + 历史相似度）→ 写飞书 outbox → 提交快照到 GitHub。**指标定义、阈值、聚合公式、校验口径一律以仓库里的 INDICATORS.md 为准（指标总数 N 也以它为准），本 prompt 不硬编码任何指标数量。**

## 重要：仓库与提交方式（已改为 git 直推，不再用任何 token）

你的工作目录就是已经 clone 好的 `crystal-xiaoxiao/ai-bubble-monitor` 仓库，沙箱自带 git 认证，**不需要任何 GitHub token**。所有写仓库的操作都用 git：直接写/改文件 → `git add` → `git commit` → `git push origin HEAD:main`。**不要再用 GitHub Contents API，也不要在 prompt 或代码里放任何 token。**

如果 commit 报 "Author identity unknown"，先设本地身份：
`git config user.email "routine@aibubble.local" && git config user.name "AI Bubble Routine"`

## 重要：飞书发送方式

本 sandbox 出站到 open.feishu.cn 被 Anthropic egress proxy 拦截（403 Host not in allowlist）。所以飞书消息**不能**直接 curl 发送，必须改成：把 Feishu payload 写到仓库的 `feishu_outbox/{as_of_date}.json` 文件并 push 到 main，仓库里已经配置了 `.github/workflows/feishu-relay.yml`，会自动检测、转发到飞书、并删除文件。

## 重要：双语 JSON

本期 dashboard 有两个版本：
- 中文 https://aibubble-cn.github.io（读 verdict_desc / note / threshold_text 等中文字段）
- 英文 https://bubblewatch.github.io（读 verdict_desc_en / note_en / threshold_text_en 等英文字段）

两个版本都从同一个 latest.json 拉数据，所以 **每条文字字段都必须中英文都出**。具体字段约定见 INDICATORS.md 末尾的 JSON Schema 段落。

仓库: crystal-xiaoxiao/ai-bubble-monitor

## 步骤

### 1. 读配置和上周数据

仓库已 clone 在工作目录，直接读本地文件（读不到再用 WebFetch raw 兜底）：
- `INDICATORS.md` → 全部指标定义（**指标总数 N 以该文件为准**）、阈值、direction、axis 标签、聚合判读规则（两轴/动量/滞回/历史相似度及校准表）、JSON schema（含双语字段约定）
- `docs/data/latest.json` → 上期快照，用于 WoW 对比、降档滞回判断和 fallback
- `docs/data/debt_ledger.json` → 债务交易台账（debt_capex_ratio 的周度数据源）
- `docs/data/raw_history.json` → 原始值台账（所有环比/增速/比值从这里的上期原始值计算）
- `docs/data/prefetch/latest.json` → GitHub Actions 每周日 21:00 UTC 机械抓取的原始数据（insider_sell_buy / token_volume_mom / top5_weight / hy_oas 四个 egress 受限源）。**读法：先查 `_meta.fetched_at` 距今 <3 天，再查对应 `sources.*.status=="ok"`，两者都满足才可用**；partial/error 或文件过期 → 该指标走 INDICATORS.md 的备源链

新一期 issue_number = 上期 + 1
新一期 as_of_date = 今天日期 (YYYY-MM-DD)

### 2. 抓全部指标当前值（尽量并行）

按 INDICATORS.md 里每个指标的 source：
- **prefetch 覆盖的指标（insider_sell_buy / token_volume_mom / top5_weight / hy_oas）一律先读 `docs/data/prefetch/latest.json`**（读法见第 1 步）：该源的 `data` 就是本期原始数据点，note 引用其 `summary` 里的数字，`as_of` 取该源的 `as_of` 字段（是数据自身日期，**不要改写成运行日期**）；prefetch 不可用才走 INDICATORS.md 里写明的备源链
- 稳定 URL（multpl 等）→ WebFetch；主源失败走 INDICATORS.md 里写明的备源链
- 定性指标（capex 指引、CEO 表态、IPO pipeline、ARR、GPU 租价、私募二级标价等）→ WebSearch（token 量已由 prefetch 覆盖，web_search 只作交叉印证）
- `debt_capex_ratio` → 严格按 INDICATORS.md「周度增量台账 + 28 天完整对账」规则：**每周**搜过去 7-10 天新公告的 AI/数据中心债务 deal（关键词轮换），去重后追加进 debt_ledger.json，note 给出周度边际（本周新增 $XB / YTD 累计 / 年化 run-rate），as_of 更新为本期；距 last_full_recon ≥28 天才做完整自下而上拆解并修正台账
- `frontier_progress` → 按 INDICATORS.md 三层量化：METR time horizon（主锚）+ 困难基准 90 天 SOTA 位移（HLE/FrontierMath/ARC-AGI 等）+ 发布密度与叙事；判定必须与 raw_history 上期数值对比
- **反锚定纪律（全局，见 INDICATORS.md「数据抓取纪律」）**：活源数值型指标的 note 必须写出本期实际抓到的原始数据点（如 insider 卖/买总金额、token 30 日绝对量），给不出=没抓到=按 stale 处理；本期各数值型指标的原始输入**追加写入 raw_history.json**（每指标保留 26 期）；**同值预警数 raw 里的核心原始绝对值**（不数派生 value——MoM%/比值在变不能重置计数）：原始值连续 3 期不变或连续 3 期缺失 → 输出 `suspect_static: true` + `static_weeks: N` 并准备飞书提醒行

每个指标产出（**注意双语**）：
{
  id, value, value_display,
  value_display_en (仅当 value_display 是中文文本，比如"升温"/"加速中"，需要英文翻译；纯数字单位如 "+22%" 不需要),
  status, as_of, source_url,
  threshold_text (中文版, 例如 ">35 红 / 25-35 黄 / <25 绿"),
  threshold_text_en (英文版, 例如 ">35 red / 25-35 yellow / <25 green"),
  note (中文 1-2 句解读),
  note_en (英文 1-2 句解读，自然像英文新闻不要逐字对译),
  stale: false（仅当本期真正拿到新原始数据点时才是 false）
}

抓不到时（prefetch 与备源链全部失败）：
- 沿用 latest.json 上周值（包括 _en 字段），stale=true；**`as_of` 必须保留上期的真实 as_of，绝对禁止写成本期日期**；note 改为"沿用 {上期 as_of} 值（数据源暂不可用）"，note_en 改为 "Carrying value as of {上期 as_of} (source unavailable)"
- **红线：`as_of`=本期日期 ⟺ note 里给得出本期新抓的原始数据点，两者必须同真同假**——历史教训：被封期间 as_of 每周照写新日期、stale 照写 false，导致停更 5 周在看板上完全不可见
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

verdict_desc 和 verdict_desc_en 都要写；须引用相似度最高的历史时点，并点名当前与 2000-02 向量的主要差异指标。

### 5. WoW 变化

对比 latest.json 每个指标上周 status：
- status_upgrade: green→yellow / yellow→red / green→red
- status_downgrade: red→yellow / yellow→green / red→green
- value_change: status 没变但数值变化 >10%（仅数值型）

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
- 确认 debt_ledger.json 与 raw_history.json 已按第 2 步更新（它们随快照一起 commit）

### 7. 写飞书 payload 到 outbox 文件（**写文件，不要 curl 飞书**）

飞书消息只发中文（用户是中文阅读者）。构造完整 Feishu payload（msg_type="post" rich text），写入文件 `feishu_outbox/{as_of_date}.json`（不存在则创建，已存在则覆盖）：

{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {
        "title": "📊 AI 泡沫监测 · Issue #{issue_number 三位数} · {as_of_date}",
        "content": [
          [{"tag":"text","text":"🔴 风险温度（红灯比例）{red_pct}% （阈值 60%）"}],
          [{"tag":"text","text":"📊 加权风险分 {weighted_risk_score}%"}],
          [{"tag":"text","text":"🔴 {red_count} 红 / 🟠 {yellow_count} 黄 / 🟢 {green_count} 绿"}],
          [{"tag":"text","text":"🧭 两轴: 泡沫成熟度 {stage_score}（{stage_label}）· 破裂临近度 {trigger_score}（{trigger_label}）"}],
          [{"tag":"text","text":"🕰 历史相似度: 最像 {similarity[0].period} {similarity[0].label_zh}（{similarity[0].match_pct}%）"}],
          [{"tag":"text","text":"📈 本周边际: {momentum.deteriorated} 恶化 / {momentum.improved} 好转（净 {momentum.net}）"}],
          (若有 suspect_static 指标，对每个加一行):
          [{"tag":"text","text":"⚠ 疑似静态: {name_zh} 连续 {static_weeks} 期原始值未变/未获取 = {value_display}，请人工核查"}],
          (若 prefetch 存在 status 非 ok 的源，对每个加一行):
          [{"tag":"text","text":"⚠ prefetch 失败: {源名} — {error 摘要}"}],
          (若 debt_ledger 本周有新 deal):
          [{"tag":"text","text":"💰 本周新增 AI 债务 deal: {borrower $XB, ...} · YTD 台账累计 ${Y}B"}],
          [{"tag":"text","text":""}],
          [{"tag":"text","text":"📌 判读: {verdict_label}"}],
          [{"tag":"text","text":"{verdict_desc}"}],
          [{"tag":"text","text":""}],
          [{"tag":"text","text":"▲ 本周变化"}],
          [{"tag":"text","text":"────────────────"}],
          (对每条 wow_changes 最多 5 条):
          [{"tag":"text","text":"  {icon} {note}"}]  // status_upgrade=🔴, status_downgrade=🟢, value_change=📈/📉
          (如 wow_changes 为空):
          [{"tag":"text","text":"本周状态无变化"}],
          [{"tag":"text","text":""}],
          [{"tag":"text","text":"🔴 当前红灯指标"}],
          [{"tag":"text","text":"────────────────"}],
          (对每个 status=red 指标):
          [{"tag":"text","text":"  • {name_zh}: {value_display}"}],
          [{"tag":"text","text":"    {note}"}],
          [{"tag":"text","text":""}],
          [{"tag":"text","text":"🔗 中文 Dashboard: https://aibubble-cn.github.io"}],
          [{"tag":"text","text":"🔗 English: https://bubblewatch.github.io"}]
        ]
      }
    }
  }
}

stale > 5 时（错误情形）：outbox 文件改为：
{ "msg_type": "text", "content": { "text": "⚠️ AI Bubble Monitor 周报失败 · {as_of_date}\n\n{stale 数} 个指标取数失败，超阈值。" } }
写完 outbox 后，不写 docs/ 下的快照，直接跳到第 8 步 commit+push（只提交 outbox），然后结束。

### 8. 写快照文件并 git 提交推送

如果不是错误情形，先写两个快照文件（直接覆盖，手动重跑也覆盖即可，不需要 sha）：
a) `docs/data/snapshots/{as_of_date}.json` ← 本期完整快照
b) `docs/data/latest.json` ← 覆盖为本期内容

两个 dashboard（aibubble-cn 和 bubblewatch）从这份 latest.json 自动拉数据，不需要单独更新它们。

然后一次性提交并推送（outbox + 两个快照一起）：
```
git add -A
git commit -m "Issue #{N} · {as_of_date}"
git push origin HEAD:main
```
确认 `git push` 退出码为 0。**如果 push 失败，把完整的 git 报错原样写进运行总结（不要吞错误），然后停止——不要尝试别的写入方式。**

### 9. 输出运行总结

routine 最后输出：
- Issue 编号 + 日期
- 红黄绿计数 + 红灯比例 + 两轴分数 + 判读（中英）
- 相似度 top1、WoW 变化数、suspect_static 数、本周新增债务 deal 数
- stale 指标数
- git push 结果（成功的 commit SHA，或失败的完整报错）
- Outbox 文件路径（飞书消息将由 GitHub Actions 转发）

## 注意事项

- 不要在日志里打印任何敏感信息或 webhook URL
- **绝对不要直接 curl https://open.feishu.cn/...** —— sandbox 出站被拦，会 403
- 写仓库一律用 git（add/commit/push origin HEAD:main），不要用 GitHub Contents API，不要用 token
- 阈值取 INDICATORS.md，不要自改
- 指标 id 严格按 INDICATORS.md 定义的清单执行，不增不减、不要假设固定数量（加减指标只会改 INDICATORS.md，本 prompt 不用动）
- 双语字段必须都有；中英文不要逐字对译，分别写得自然
- insider_sell_buy / token_volume_mom / top5_weight / hy_oas 先读 `docs/data/prefetch/latest.json`（各源含现成的 summary/data，as_of 用源的 as_of）；multpl.com 找页面顶部数字。openinsider 与 FRED CSV 均已失效，不要再抓
```

---

## 跑测试（可选）

不想等周日的话，去 https://claude.ai/code/routines 找到 "AI Bubble Monitor Weekly" 手动触发一次。会真实推一条飞书 + 生成新一期 Issue。跑完检查：
1. 飞书群收到周报（含两轴、相似度、动量行）
2. 仓库 `docs/data/latest.json` 有新 commit、`total_indicators` 与 INDICATORS.md 一致（当前 25）、summary 含 stage/trigger/momentum/similarity
3. `debt_ledger.json` 有本周追加（或"无新 deal"note）、`raw_history.json` 各指标多一期
4. 三个看板硬刷新后正常（两轴仪表、相似度 chips、指标卡 as_of 日期）
5. **prefetch 生效检查**：insider_sell_buy / token_volume_mom / hy_oas / top5_weight 的 `as_of` 应等于 prefetch 各源的 `as_of`（而非机械等于运行日）；insider 的 note 应含真实卖/买美元总额、token 的 note 应含 30 日绝对量。**若这些指标 as_of 仍机械=运行日，说明线上 prompt 没同步**
