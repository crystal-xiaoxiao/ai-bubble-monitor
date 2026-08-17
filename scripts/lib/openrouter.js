// token_volume：OpenRouter 官方数据 API（rankings 页同源），滚动 30 日总量 vs 前 30 日算 MoM
'use strict';

const { fetchRetry } = require('./util');

const LOOKBACK_DAYS = 70; // 两个 30 日窗 + 数据末端滞后余量

function iso(d) { return d.toISOString().slice(0, 10); }
const toT = (n) => Math.round(n / 1e12 * 10) / 10; // 换算成 T（万亿 tokens），1 位小数

// daysNeeded 可调：backfill 用它拉更长历史
async function fetchDailyTotals(env, daysBack = LOOKBACK_DAYS) {
  const key = env.OPENROUTER_API_KEY;
  if (!key) throw new Error('OPENROUTER_API_KEY 未设置');
  const end = new Date();
  const start = new Date(end.getTime() - daysBack * 864e5);
  const url = `https://openrouter.ai/api/v1/datasets/rankings-daily?start_date=${iso(start)}&end_date=${iso(end)}&period=day`;
  const res = await fetchRetry(url, { headers: { Authorization: `Bearer ${key}` } });
  const json = await res.json();
  const rows = json.data || [];
  const daily = new Map(); // date -> 全平台日总量（top50 各行 + other 汇总行求和）
  for (const row of rows) {
    const n = Number(row.total_tokens);
    if (!isFinite(n)) continue;
    daily.set(row.date, (daily.get(row.date) || 0) + n);
  }
  return [...daily.entries()].sort((a, b) => a[0] < b[0] ? -1 : 1); // [date, tokens] 升序
}

async function fetchTokenVolume(env) {
  const days = await fetchDailyTotals(env);
  if (days.length < 60) {
    return {
      status: 'partial',
      as_of: days.length ? days[days.length - 1][0] : null,
      summary: `OpenRouter API 仅返回 ${days.length} 个有数日（不足两个 30 日窗），无法算 MoM`,
      data: { days_covered: days.length },
      source: 'https://openrouter.ai/api/v1/datasets/rankings-daily',
      error: `insufficient days: ${days.length} < 60`,
    };
  }
  const last30 = days.slice(-30);
  const prev30 = days.slice(-60, -30);
  const sum = (arr) => arr.reduce((s, [, n]) => s + n, 0);
  const last30Tokens = sum(last30);
  const prev30Tokens = sum(prev30);
  const momPct = Math.round((last30Tokens / prev30Tokens - 1) * 1000) / 10;
  const lastDate = days[days.length - 1][0];
  return {
    status: 'ok',
    as_of: lastDate,
    summary: `OpenRouter 官方 API：近 30 日 ${toT(last30Tokens)}T tokens，前 30 日 ${toT(prev30Tokens)}T，` +
      `MoM ${momPct >= 0 ? '+' : ''}${momPct}%（全平台 top50+other 口径，数据截至 ${lastDate}）`,
    data: {
      last30_tokens: last30Tokens, prev30_tokens: prev30Tokens,
      last30_tokens_t: toT(last30Tokens), prev30_tokens_t: toT(prev30Tokens),
      mom_pct: momPct, last_data_date: lastDate, days_covered: days.length,
      daily_tail: last30.slice(-7).map(([date, n]) => ({ date, tokens_t: toT(n) })),
    },
    source: 'https://openrouter.ai/api/v1/datasets/rankings-daily',
    error: null,
  };
}

module.exports = { fetchTokenVolume, fetchDailyTotals };
