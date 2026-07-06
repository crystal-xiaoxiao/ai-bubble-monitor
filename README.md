# AI Bubble Monitor

监测美股 AI 泡沫风险的 24 个领先指标，每周一早 7 点（北京时间）自动飞书推送。

**Dashboard**: https://crystal-xiaoxiao.github.io/ai-bubble-monitor/

## 工作原理

```
                ┌─────────────────────────────────────┐
                │  Claude Scheduled Routine            │
                │  (每周一 北京 07:00 / Sun 23:00 UTC) │
                └──────────────────┬──────────────────┘
                                   │
        ┌──────────────────────────┴──────────────────────────┐
        │                                                       │
        ▼                                                       ▼
  读 INDICATORS.md                                       读上周 snapshot
  + web_search/WebFetch 抓                              （用于 WoW 对比）
  24 个指标当前值
        │                                                       │
        └──────────────────────────┬──────────────────────────┘
                                   ▼
                          ┌──────────────────┐
                          │ 评分 + 生成 JSON │
                          └────────┬─────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
       飞书推送（周报）   commit 到 docs/data/   GH Pages 自动重建
```

**关键设计**：
- 没有服务器、没有 Anthropic API key；唯一的 GitHub Actions 是 `feishu-relay.yml`（把 routine 写入 `feishu_outbox/` 的 payload 转发到飞书 webhook 后删除——routine 沙箱 egress 直连飞书会被拦）
- Claude routine 在订阅内运行，零额外费用
- 这个仓库当文件柜 + 数据台账：存指标定义、历史快照、债务台账、原始值台账，托管 dashboard

## 文件结构

```
ai-bubble-monitor/
├── README.md                  # 这个文件
├── INDICATORS.md              # 24 个指标的定义/阈值/聚合规则/历史校准表（routine 读这个）
├── ROUTINE_PROMPT.md          # 线上 routine prompt 的版本化副本 + 运维说明
├── .github/workflows/
│   └── feishu-relay.yml       # 飞书转发 relay（监听 feishu_outbox/ push）
├── feishu_outbox/             # routine 写、relay 发完即删（平时为空）
└── docs/                      # GitHub Pages 源目录
    ├── index.html             # Dashboard
    └── data/
        ├── latest.json        # 最新一期（三个 dashboard 都读这个）
        ├── debt_ledger.json   # AI 债务交易台账（debt_capex_ratio 周度增量源）
        ├── raw_history.json   # 原始值台账（反锚定：环比一律从这里算）
        └── snapshots/
            └── YYYY-MM-DD.json  # 历史快照
```

## 改指标怎么办

直接改 `INDICATORS.md`，下次 routine 跑就生效。**指标 ID 不要改**（会破坏历史比对）。
阈值改了的话在 commit message 里写明原因。

## 改样式怎么办

直接改 `docs/index.html` 里的 CSS。GH Pages 几分钟内重建。

## 看历史

每周的 snapshot 都在 `docs/data/snapshots/`。直接打开 JSON 看，或者改 dashboard 加个时间选择器。

## 阈值校准来源

| 阈值 | 历史锚点 |
|---|---|
| 内部人卖买比 23x = 红 | 2000 dot-com 顶部前一个月 |
| NVDA 客户投资/收入 24% = 末期 | Lucent 1999 vendor financing 24% |
| CAPE > 35 = 红 | 1999-2000 峰值 44.19 |
| 前 5 大权重 > 25% = 红 | 2000 峰值 ~18% |
| HY OAS > 500 bps = 红 | 2000/2008/2020 风险事件阈值 |
| 50 日均线上方比例 < 40% 红 | 指数新高时背离的经典阈值 |

## Issue 历史

完整历史见 `docs/data/snapshots/`（最早 #4 · 2026-05-10）。2026-07-06 起框架升级为两轴判读（stage/trigger）+ 历史相似度 + 周度债务台账，详见 INDICATORS.md。
