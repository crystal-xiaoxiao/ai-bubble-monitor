#!/usr/bin/env node
// 一次性脚本：用 OpenRouter 官方 API 的真实日度数据，给 raw_history.json 里
// token_volume_mom 被冻结期间（2026-06 起沿用估算）的各期追加 revised 真值字段。
// 原则（Crystal 2026-08-17 拍板）：注记式回填——原 raw/value 一律不动，只追加：
//   entry.revised_openrouter_30d_tokens_t  该期日期截止的滚动 30 日真实总量（T）
//   entry.revised_mom_pct                  真实 MoM（该 30 日窗 vs 前 30 日窗）
// 并在 _meta.corrections 里记一条修正说明。snapshots/ 与历史 latest.json 不动。
// 用法：OPENROUTER_API_KEY=... node scripts/backfill_token_history.js [--dry-run]
'use strict';

const fs = require('fs');
const path = require('path');
const { fetchDailyTotals } = require('./lib/openrouter');

const FILE = path.join(__dirname, '..', 'docs', 'data', 'raw_history.json');
const AFFECTED_FROM = '2026-06-01'; // 该日期起的 token 台账 entry 全部回填

const toT = (n) => Math.round(n / 1e12 * 10) / 10;

async function main() {
  const dryRun = process.argv.includes('--dry-run');
  const hist = JSON.parse(fs.readFileSync(FILE, 'utf8'));
  const entries = (hist.token_volume_mom || []).filter((e) => e.date >= AFFECTED_FROM);
  if (!entries.length) { console.log('没有需要回填的 entry'); return; }

  // 拉足够长的日度数据：最早 entry 往前 65 天（两个 30 日窗 + 余量）
  const earliest = entries[0].date;
  const daysBack = Math.ceil((Date.now() - new Date(earliest).getTime()) / 864e5) + 65;
  const days = await fetchDailyTotals(process.env, daysBack);
  const idx = new Map(days.map(([d, n], i) => [d, i]));
  const dates = days.map(([d]) => d);

  // 该期日期（含）之前最近的有数日作为窗口右端
  function windowSums(endDate) {
    let i = idx.has(endDate) ? idx.get(endDate) : dates.findLastIndex((d) => d <= endDate);
    if (i < 59) return null; // 不足两个 30 日窗
    const sum = (a, b) => days.slice(a, b).reduce((s, [, n]) => s + n, 0);
    return { last30: sum(i - 29, i + 1), prev30: sum(i - 59, i - 29) };
  }

  let touched = 0;
  for (const e of entries) {
    const w = windowSums(e.date);
    if (!w) { console.log(`${e.date}: API 数据不足，跳过`); continue; }
    e.revised_openrouter_30d_tokens_t = toT(w.last30);
    e.revised_mom_pct = Math.round((w.last30 / w.prev30 - 1) * 1000) / 10;
    console.log(`${e.date}: 台账原值 ${JSON.stringify(e.raw.openrouter_monthly_tokens_t ?? null)}T/月(估算) → 真实 30 日 ${e.revised_openrouter_30d_tokens_t}T，真实 MoM ${e.revised_mom_pct}%`);
    touched++;
  }

  hist._meta = hist._meta || {};
  hist._meta.corrections = hist._meta.corrections || [];
  hist._meta.corrections.push({
    date: new Date().toISOString().slice(0, 10),
    indicator: 'token_volume_mom',
    note: `2026-06 起因 openrouter.ai egress 403，各期 value/raw 为估算沿用；真实 30 日总量与真实 MoM 见各 entry 的 revised_* 字段（源 = OpenRouter 官方 datasets API rankings-daily，本次回填 ${touched} 期）。原字段按台账语义（记录当期实际输入）保留不动。`,
  });

  if (dryRun) { console.log('(dry-run，未写文件)'); return; }
  fs.writeFileSync(FILE, JSON.stringify(hist, null, 2) + '\n');
  console.log(`已写入 ${FILE}（回填 ${touched} 期）`);
}

main().catch((e) => { console.error(e); process.exit(1); });
