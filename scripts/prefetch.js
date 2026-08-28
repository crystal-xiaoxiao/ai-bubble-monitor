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
const { fetchHyOas, fetchFredSeries } = require('./lib/fred');

const OUT = path.join(__dirname, '..', 'docs', 'data', 'prefetch', 'latest.json');
const CREDIT_OUT = path.join(__dirname, '..', 'docs', 'data', 'credit_spread_history.json');
// credit spread 趋势图数据：HY=高收益整体 / CCC=neocloud 所在评级尾部 / IG=hyperscaler 发债基准
const CREDIT_SERIES = { hy: 'BAMLH0A0HYM2', ccc: 'BAMLH0A3HYC', ig: 'BAMLC0A0CM' };
const CREDIT_WINDOW_DAYS = 366;

// 每周全量重拉 1 年日度序列，幂等覆盖写；任一序列失败则整体跳过、保留上一份文件
async function writeCreditHistory(dryRun) {
  try {
    const start = new Date(Date.now() - CREDIT_WINDOW_DAYS * 86400e3).toISOString().slice(0, 10);
    const series = {};
    for (const [key, id] of Object.entries(CREDIT_SERIES)) {
      series[key] = await fetchFredSeries(process.env, id, start);
    }
    const out = {
      _meta: {
        purpose: '前端 credit spread 趋势图专用（三站小倍数图）。仅展示，不参与红黄绿判读。',
        schema_version: 1,
        fetched_at: new Date().toISOString(),
        source: 'FRED API',
        window_days: CREDIT_WINDOW_DAYS,
        cadence: 'daily',
        series_ids: CREDIT_SERIES,
      },
      series,
    };
    const counts = Object.entries(series).map(([k, v]) => `${k}=${v.length}点(末${v[v.length - 1].date}:${v[v.length - 1].bps}bp)`).join(' ');
    if (dryRun) {
      console.log(`[credit_history] ok (dry-run 不落盘): ${counts}`);
    } else {
      fs.writeFileSync(CREDIT_OUT, JSON.stringify(out, null, 1) + '\n');
      console.log(`[credit_history] ok: ${counts} → ${CREDIT_OUT}`);
    }
    return `ok: ${counts}`;
  } catch (e) {
    console.log(`[credit_history] error（保留旧文件不覆盖）: ${e.message}`);
    return `error: ${e.message}`;
  }
}

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

  // credit spread 历史序列：独立产物，不进 sources 契约（routine 不消费它）
  const creditResult = await writeCreditHistory(dryRun);

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
    lines.push(`| credit_history | ${creditResult.startsWith('ok') ? 'ok' : 'error'} | ${creditResult.replace(/\|/g, '/')} |`);
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, lines.join('\n') + '\n');
  }

  // 退出码恒为 0：数据落盘优先，状态检查交给 workflow 的后续 step（commit 之后再红叉提醒）
}

main().catch((e) => { console.error(e); process.exit(1); });
