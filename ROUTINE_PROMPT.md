# Routine Prompt — 喂给 `/schedule`

下面那个代码块就是你要塞给 Claude `/schedule` 的完整 prompt。**先填两个占位符**：

1. `<<FEISHU_WEBHOOK_URL>>` → 替换成你的飞书机器人 webhook 完整 URL
2. `<<GITHUB_PAT>>` → 替换成你刚生成的 fine-grained PAT（教程见下方）

填好之后，直接 `/schedule "0 23 * * 0"` 然后把整段 prompt 粘进去。Cron `0 23 * * 0` = 每周日 UTC 23:00 = 周一北京 07:00。

---

## 设置流程（10 分钟）

### Step 1 — 开飞书机器人（3 分钟）

1. 在飞书创建一个"AI 泡沫监测"群（或在已有群里）
2. 群设置 → 群机器人 → 添加机器人 → "自定义机器人"
3. 名字填 "AI Bubble Watch"，复制 webhook URL（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx`）

### Step 2 — 创建 GitHub Fine-Grained PAT（5 分钟）

我建议生成一个**只能写这一个仓库**的 token，安全最小化。

1. 打开 https://github.com/settings/personal-access-tokens/new
2. **Token name**: `ai-bubble-monitor-routine`
3. **Expiration**: 1 year（或你想要的）
4. **Repository access** → "Only select repositories" → 选 `crystal-xiaoxiao/ai-bubble-monitor`
5. **Permissions** → Repository permissions → **Contents: Read and write**（其他都不要）
6. 点 Generate token → **复制下来**（只会显示一次！）

### Step 3 — 粘 prompt 到 `/schedule`（2 分钟）

在 Claude Code 对话框输入：

```
/schedule "0 23 * * 0"
```

回车后把下面整段 prompt 粘贴进去（**记得替换占位符**）。

---

## Routine Prompt（完整内容）

```
你是 AI Bubble Monitor 周报 routine。每次运行一遍完整的数据采集 → 评分 → 飞书推送 → 提交快照到 GitHub。

仓库: crystal-xiaoxiao/ai-bubble-monitor
飞书 webhook: <<FEISHU_WEBHOOK_URL>>
GitHub Token: <<GITHUB_PAT>>

## 步骤

### 1. 读配置和上周数据

- 用 WebFetch 读 https://raw.githubusercontent.com/crystal-xiaoxiao/ai-bubble-monitor/main/INDICATORS.md
  → 这里有 23 个指标定义、阈值、direction 规则、聚合判读规则、JSON schema
- 用 WebFetch 读 https://raw.githubusercontent.com/crystal-xiaoxiao/ai-bubble-monitor/main/docs/data/latest.json
  → 上周快照，用于 WoW 对比和 fallback

记下上一期的 issue_number，新一期 = 上期 + 1。
新一期 as_of_date = 今天日期 (YYYY-MM-DD)。

### 2. 抓 23 个指标当前值

按 INDICATORS.md 里每个指标的 source，并行尽量抓取（一次跑可同时发起多个 web_search / WebFetch）。

抓数策略：
- **稳定 URL（multpl, slickcharts, FRED CSV, openinsider）**: 用 WebFetch
- **定性指标（capex 指引、CEO 表态、IPO pipeline 等）**: 用 web_search

每个指标返回结构：
{
  "id": "...",
  "value": <数字或字符串>,
  "value_display": "供 dashboard 显示的字符串",
  "as_of": "YYYY-MM-DD",
  "source_url": "实际抓到数据的 URL",
  "note": "1-2 句话的当前值含义解读",
  "stale": false
}

抓不到怎么办：
- 沿用 latest.json 里上周的 value / status，把 stale 设为 true，note 改为"沿用上周值（数据源暂不可用）"
- 累计 stale 超过 5 个 → 中止，跳到第 7 步发错误提醒

### 3. 评分

按 INDICATORS.md 里的 direction 规则给每个指标打 status (red / yellow / green)。
对 qualitative 指标，由 web_search 结果直接判断 status，写在 note 里说明依据。

### 4. 算聚合

red_count, yellow_count, green_count
red_pct = red_count / 23 * 100  (保留 1 位小数)
weighted_risk_score = (red_count + yellow_count * 0.5) / 23 * 100  (保留 1 位小数)

verdict_label / verdict_desc 按 INDICATORS.md 的判读阈值表选取。

### 5. 算 WoW 变化

对比 latest.json 里每个指标上周的 status：
- status_upgrade: green→yellow / yellow→red / green→red
- status_downgrade: red→yellow / yellow→green / red→green
- value_change: status 没变但数值变化 >10%（仅对数值型指标）

每个变化生成一个对象：
{ "indicator_id": "...", "type": "...", "from": "...", "to": "...", "note": "一句话说明" }

只保留**最重要的 5 条**（红灯转换优先，再到接近阈值的黄→红）。

### 6. 拼装新快照 JSON

按 INDICATORS.md 里的 schema 拼好。注意：
- 沿用 history_seed 字段：从 latest.json 取出 history_seed 数组，append 一条 {week, red_pct, risk_score}（week 为 MM-DD），保留最近 10 条
- 完整 23 个指标都在 indicators 数组里
- 即使值没变也要写完整记录，不能省略

校验：
- indicators 数组长度必须 = 23
- summary.red_count + yellow_count + green_count = 23
- summary.red_pct 和 indicators 里的 red 数量一致

### 7. 推送飞书

用 curl POST 到 <<FEISHU_WEBHOOK_URL>>，msg_type 用 "post"（rich text）。

消息结构（北京时间）：

标题: 📊 AI 泡沫监测 · Issue #{issue_number 三位数} · {as_of_date}

正文 content（每行一个 [{tag:"text",text:"..."}] 数组）：
- "🔴 红灯比例 {red_pct}% （阈值 60%）"
- "📊 加权风险分 {weighted_risk_score}%"
- "🔴 {red_count} 红 / 🟠 {yellow_count} 黄 / 🟢 {green_count} 绿"
- "" (空行)
- "📌 判读: {verdict_label}"
- "{verdict_desc}"
- "" (空行)
- "▲ 本周变化"
- "────────────────"
- 对每条 wow_changes (最多 5 条):
  - "  [icon] {note}"  其中 status_upgrade 用 "🔴", status_downgrade 用 "🟢", value_change 用 "📈/📉"
- 如果 wow_changes 为空，写 "本周状态无变化"
- "" (空行)
- "🔴 当前红灯指标"
- "────────────────"
- 对每个 status=red 的指标:
  - "  • {name_zh}: {value_display}"
  - "    {note}"
- "" (空行)
- "🔗 完整 Dashboard: https://crystal-xiaoxiao.github.io/ai-bubble-monitor/"

如果 stale 数量 > 5（中止情形）：
- 改发 msg_type=text 的简短错误：
  "⚠️ AI Bubble Monitor 周报失败 · {as_of_date}\n\n{stale 数量} 个指标取数失败，超过阈值。请检查数据源或登录 routine 查看日志。"
- 不提交快照，直接结束 routine

### 8. 提交快照到 GitHub

用 curl + GitHub Contents API 写两个文件（PAT 在 Authorization header）：

a) `docs/data/snapshots/{as_of_date}.json` — 新建
   PUT https://api.github.com/repos/crystal-xiaoxiao/ai-bubble-monitor/contents/docs/data/snapshots/{as_of_date}.json
   body: { "message": "Issue #{N} · {as_of_date}", "content": <base64>, "branch": "main" }

b) `docs/data/latest.json` — 覆盖
   先 GET 拿到当前文件的 sha，然后 PUT 时带上 sha 字段
   PUT https://api.github.com/repos/crystal-xiaoxiao/ai-bubble-monitor/contents/docs/data/latest.json
   body: { "message": "Update latest to #{N}", "content": <base64>, "sha": "<old_sha>", "branch": "main" }

### 9. 输出运行总结

routine 最后输出（给用户看）：
- Issue 编号 + 日期
- 红黄绿计数 + 红灯比例 + 判读
- WoW 变化数
- stale 指标数
- GitHub commit URL
- 飞书是否成功

## 注意事项

- 不要在日志或输出里完整打印 webhook URL 和 GITHUB_PAT
- 数值阈值取 INDICATORS.md 里的，不要自己改
- 指标 id 严格按 INDICATORS.md 里的 23 个，不增不减
- 抓 multpl.com 时找页面顶部数字，slickcharts 找前 5 行权重相加
- 抓 FRED 用 https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2，取最后一行非空值
- 抓 openinsider 时聚合 NVDA/AVGO/AMD/MSFT/GOOGL/META/AMZN/ORCL/TSM/MU/ARM/PLTR 这 12 个 ticker 的 30 天美元卖买比
```

---

## 跑测试

填好 webhook 和 PAT、用 `/schedule` 创建 routine 之后：

1. 在 routine 列表里手动触发一次（不用等周一）
2. 检查飞书是不是收到消息
3. 检查 https://crystal-xiaoxiao.github.io/ai-bubble-monitor/ 是不是更新到 Issue #002
4. 都 OK 就让它自己每周一跑

如果飞书消息没收到 / GH 没更新 → 看 routine 运行日志，把错误贴回来给 Claude 看就行。
