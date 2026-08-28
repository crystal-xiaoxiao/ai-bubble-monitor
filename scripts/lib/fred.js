// hy_oas：FRED 官方 API，BAMLH0A0HYM2（ICE BofA US High Yield OAS）
// 注意：FRED 值是百分数（如 2.71），×100 换算 bps；as_of = 观测日（比运行日早 1-2 个交易日，是真实日期）
'use strict';

const { fetchRetry } = require('./util');

async function fetchHyOas(env) {
  const key = env.FRED_API_KEY;
  if (!key) throw new Error('FRED_API_KEY 未设置');
  const url = 'https://api.stlouisfed.org/fred/series/observations?series_id=BAMLH0A0HYM2' +
    `&api_key=${key}&file_type=json&sort_order=desc&limit=10`;
  const res = await fetchRetry(url);
  const json = await res.json();
  const obs = (json.observations || []).filter((o) => o.value !== '.');
  if (!obs.length) throw new Error('FRED 返回 0 条有效观测');
  const latest = obs[0];
  const bps = Math.round(parseFloat(latest.value) * 100);
  return {
    status: 'ok',
    as_of: latest.date,
    summary: `FRED BAMLH0A0HYM2 = ${bps} bps（观测日 ${latest.date}）`,
    data: {
      oas_bps: bps,
      obs_date: latest.date,
      recent: obs.slice(0, 5).map((o) => ({ date: o.date, bps: Math.round(parseFloat(o.value) * 100) })),
    },
    source: 'FRED API BAMLH0A0HYM2',
    error: null,
  };
}

// 通用序列抓取：observation_start 起的完整历史（升序），供 credit_spread_history.json 用
async function fetchFredSeries(env, seriesId, observationStart) {
  const key = env.FRED_API_KEY;
  if (!key) throw new Error('FRED_API_KEY 未设置');
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}` +
    `&api_key=${key}&file_type=json&sort_order=asc&observation_start=${observationStart}`;
  const res = await fetchRetry(url);
  const json = await res.json();
  const points = (json.observations || [])
    .filter((o) => o.value !== '.')
    .map((o) => ({ date: o.date, bps: Math.round(parseFloat(o.value) * 100) }));
  if (!points.length) throw new Error(`FRED ${seriesId} 返回 0 条有效观测`);
  return points;
}

module.exports = { fetchHyOas, fetchFredSeries };
