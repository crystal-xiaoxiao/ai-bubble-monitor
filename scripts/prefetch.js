#!/usr/bin/env node
// prefetch：GitHub Actions 每周日 21:00 UTC 机械抓取 4 个 egress 受限数据源，
// 写 docs/data/prefetch/latest.json 供周日 23:00 UTC 的 routine 优先取用。
// 用法：node scripts/prefetch.js [--dry-run]
// env：SEC_USER_AGENT / OPENROUTER_API_KEY / FRED_API_KEY
'use strict';

const fs = require('fs');
const path = require('path');
const { fetchInsiderSellBuy } = require('./lib/sec_form4');
const { fetchTokenVolume } = require('./lib/openrouter');
const { fetchTop5Weight } = require('./lib/slickcharts');
const { fetchHyOas } = require('./lib/fred');

const OUT = path.join(__dirname, '..', 'docs', 'data', 'prefetch', 'latest.json');

async function wrap(name, fn) {
  try {
    const r = await fn(process.env);
    console.log(`[${name}] ${r.status}: ${r.summary}${r.error ? ` | error: ${r.error}` : ''}`);
    return [name, r];
  } catch (e) {
    console.log(`[${name}] error: ${e.message}`);
    return [name, { status: 'error', as_of: null, summary: `抓取失败：${e.message}`, data: null, source: null, error: e.message }];
  }
}

async function main() {
  const dryRun = process.argv.includes('--dry-run');
  const entries = await Promise.all([
    wrap('insider_sell_buy', fetchInsiderSellBuy),
    wrap('token_volume', fetchTokenVolume),
    wrap('top5_weight', fetchTop5Weight),
    wrap('hy_oas', fetchHyOas),
  ]);

  const out = {
    _meta: {
      purpose: 'GitHub Actions 每周日 21:00 UTC 机械抓取的原始数据，供 routine 优先取用。' +
        'routine 判定规则：_meta.fetched_at 距今 <3 天 且 对应 sources.*.status=="ok" 才可用；' +
        '否则该指标按 INDICATORS.md 的备源链处理。partial = 数据可用但有缺口，须结合 error 字段人工判读。',
      schema_version: 1,
      fetched_at: new Date().toISOString(),
      workflow_run: process.env.GITHUB_RUN_ID
        ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`
        : 'local',
    },
    sources: Object.fromEntries(entries),
  };

  const json = JSON.stringify(out, null, 2) + '\n';
  if (dryRun) {
    console.log(json);
  } else {
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    fs.writeFileSync(OUT, json);
    console.log(`written: ${OUT}`);
  }

  // GitHub Actions 摘要
  if (process.env.GITHUB_STEP_SUMMARY) {
    const lines = ['## Prefetch 结果', '', '| 源 | 状态 | 摘要 |', '|---|---|---|'];
    for (const [name, r] of entries) lines.push(`| ${name} | ${r.status} | ${(r.summary || '').replace(/\|/g, '/')} |`);
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, lines.join('\n') + '\n');
  }

  // 退出码恒为 0：数据落盘优先，状态检查交给 workflow 的后续 step（commit 之后再红叉提醒）
}

main().catch((e) => { console.error(e); process.exit(1); });
