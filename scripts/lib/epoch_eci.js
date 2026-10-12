// Epoch Capabilities Index：官方 ZIP 中的 CSV，按模型日期重建滚动最高分。
// 不自动替研究者做 frontier_progress 的三层定性判读。
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');
const { promisify } = require('util');
const { fetchRetry } = require('./util');
const execFileAsync = promisify(execFile);

const SOURCE_URL = 'https://epoch.ai/data/benchmark_data.zip';
const CSV_MEMBER = 'epoch_capabilities_index/eci_scores.csv';
const DAY_MS = 86400000;
const REQUIRED = ['Model', 'eci', 'eci_ci_low', 'eci_ci_high', 'date', 'Organization'];

// RFC 4180: 引号中的逗号、换行及双引号必须保留，不能简单 split(',')。
function parseCsv(text) {
  text = text.replace(/^\uFEFF/, '');
  const rows = [];
  let row = [], field = '', quoted = false, closed = false;
  const endField = () => { row.push(field); field = ''; closed = false; };
  const endRow = () => { endField(); if (row.some((v) => v !== '')) rows.push(row); row = []; };
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else field += c;
    } else if (c === ',' || c === '\n' || c === '\r') {
      if (c === ',') endField();
      else { endRow(); if (c === '\r' && text[i + 1] === '\n') i++; }
    } else if (c === '"' && field === '' && !closed) quoted = true;
    else if (closed || c === '"') throw new Error('ECI CSV: malformed quoted field');
    else field += c;
  }
  if (quoted) throw new Error('ECI CSV: unterminated quoted field');
  if (field !== '' || row.length || closed) endRow();
  return rows;
}

function dateMillis(value, label) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error(`ECI ${label}: invalid date ${value}`);
  const ms = Date.parse(`${value}T00:00:00Z`);
  if (!Number.isFinite(ms) || new Date(ms).toISOString().slice(0, 10) !== value) {
    throw new Error(`ECI ${label}: invalid date ${value}`);
  }
  return ms;
}

function parseEciCsv(text) {
  const rows = parseCsv(text);
  if (rows.length < 2) throw new Error('ECI CSV: no model records');
  const header = rows.shift();
  if (new Set(header).size !== header.length) throw new Error('ECI CSV: duplicate columns');
  for (const name of REQUIRED) if (!header.includes(name)) throw new Error(`ECI CSV: missing column ${name}`);
  return rows.map((row, index) => {
    if (row.length !== header.length) throw new Error(`ECI CSV row ${index + 2}: unexpected field count`);
    const get = (name) => row[header.indexOf(name)].trim();
    const model = get('Model'), date = get('date'), organization = get('Organization') || null;
    if (!model) throw new Error(`ECI CSV row ${index + 2}: empty model`);
    dateMillis(date, `row ${index + 2}`);
    const values = ['eci', 'eci_ci_low', 'eci_ci_high'].map((name) => {
      const raw = get(name), number = Number(raw);
      // 官方历史 CSV 少数记录未提供 CI；保留 null，不把缺失当成 0 或舍弃有效 ECI。
      if (name !== 'eci' && raw === '') return null;
      if (!raw || !Number.isFinite(number)) throw new Error(`ECI CSV row ${index + 2}: invalid ${name}`);
      return number;
    });
    const [eci, eci_ci_low, eci_ci_high] = values;
    if ((eci_ci_low !== null && eci_ci_low > eci) || (eci_ci_high !== null && eci_ci_high < eci)) {
      throw new Error(`ECI CSV row ${index + 2}: inconsistent confidence interval`);
    }
    return { model, eci, eci_ci_low, eci_ci_high, date, organization };
  });
}

const round = (number) => Math.round((number + Number.EPSILON) * 1000000) / 1000000;

function computeFrontierEci(records, cutoffDate) {
  const cutoff = dateMillis(cutoffDate, 'cutoff');
  const dates = Object.fromEntries([90, 180, 365].map((days) => [days, new Date(cutoff - days * DAY_MS).toISOString().slice(0, 10)]));
  const eligible = records.filter((r) => r.date <= cutoffDate)
    .sort((a, b) => a.date.localeCompare(b.date) || b.eci - a.eci || a.model.localeCompare(b.model));
  if (!eligible.length) throw new Error('ECI CSV: no model released on or before cutoff');
  const bestAt = (date) => eligible.filter((r) => r.date <= date).reduce((best, r) => !best || r.eci > best.eci ? r : best, null);
  const current = bestAt(cutoffDate), ago90 = bestAt(dates[90]), ago180 = bestAt(dates[180]), ago365 = bestAt(dates[365]);
  // 同一天只纳入最高分，避免 CSV 行序使较弱模型误算为进入前沿；并列新最高均保留。
  const entrants = [];
  let frontier = -Infinity;
  for (let i = 0; i < eligible.length;) {
    let j = i + 1;
    while (j < eligible.length && eligible[j].date === eligible[i].date) j++;
    const dayBest = eligible[i].eci;
    if (dayBest > frontier && eligible[i].date > dates[90]) {
      entrants.push(...eligible.slice(i, j).filter((r) => r.eci === dayBest));
    }
    frontier = Math.max(frontier, dayBest);
    i = j;
  }
  const gain90 = ago90 ? round(current.eci - ago90.eci) : null;
  const gain1y = ago365 ? round(current.eci - ago365.eci) : null;
  const quarterly = gain1y === null ? null : round(gain1y / 4);
  return {
    basis: 'Epoch ECI rolling maximum by model release date; historical cutoffs reconstructed from the same download',
    cutoff_date: cutoffDate,
    baseline_cutoffs: { '90d': dates[90], '180d': dates[180], '365d': dates[365] },
    current_sota: current,
    sota_90d_ago: ago90,
    sota_180d_ago: ago180,
    sota_365d_ago: ago365,
    gain_90d: gain90,
    gain_previous_90d: ago90 && ago180 ? round(ago90.eci - ago180.eci) : null,
    gain_1y: gain1y,
    avg_quarterly_gain_1y: quarterly,
    gain_90d_to_quarterly_1y_ratio: quarterly > 0 ? round(gain90 / quarterly) : null,
    frontier_entrants_90d: entrants,
    models_covered: eligible.length,
    models_missing_confidence_intervals: eligible.filter((r) => r.eci_ci_low === null || r.eci_ci_high === null).length,
    models_missing_organization: eligible.filter((r) => r.organization === null).length,
    future_models_excluded: records.length - eligible.length,
    earliest_model_date: eligible[0].date,
    latest_model_date: eligible[eligible.length - 1].date,
  };
}

async function readEciArchive(bytes) {
  if (bytes.length > 50 * 1024 * 1024) throw new Error('ECI ZIP: archive exceeds 50 MiB limit');
  if (bytes.length < 4 || !bytes.subarray(0, 4).equals(Buffer.from([0x50, 0x4b, 0x03, 0x04]))) throw new Error('ECI ZIP: invalid archive signature');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'epoch-eci-'));
  try {
    const archive = path.join(dir, 'benchmark_data.zip');
    fs.writeFileSync(archive, bytes);
    // 输出指定成员而非解压目录，避免 ZIP 路径穿越；保留 unzip 的 CRC/格式错误。
    const { stdout } = await execFileAsync('unzip', ['-p', archive, CSV_MEMBER], { maxBuffer: 20 * 1024 * 1024, timeout: 30000 });
    if (!stdout.trim()) throw new Error('ECI ZIP: empty CSV member');
    return stdout;
  } catch (error) {
    throw new Error(`ECI ZIP extraction failed: ${(error.stderr || error.message).trim().slice(0, 500)}`);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

async function fetchFrontierEci(_env, { now = new Date(), fetcher = fetchRetry, extract = readEciArchive } = {}) {
  const cutoff = now.toISOString().slice(0, 10);
  const response = await fetcher(SOURCE_URL);
  const csv = await extract(Buffer.from(await response.arrayBuffer()));
  const data = computeFrontierEci(parseEciCsv(csv), cutoff);
  const missing = [data.sota_90d_ago, data.sota_180d_ago, data.sota_365d_ago].some((v) => v === null);
  return {
    status: missing ? 'partial' : 'ok',
    as_of: data.current_sota.date,
    summary: `Epoch ECI SOTA ${data.current_sota.model} ${data.current_sota.eci}（${data.current_sota.date}）；` +
      `90 天增幅 ${data.gain_90d ?? '历史不足'}；过去一年季均增幅 ${data.avg_quarterly_gain_1y ?? '历史不足'}`,
    data,
    source: SOURCE_URL,
    error: missing ? 'insufficient history for one or more 90/180/365-day baselines; do not extrapolate' : null,
  };
}

module.exports = { SOURCE_URL, CSV_MEMBER, parseCsv, parseEciCsv, computeFrontierEci, readEciArchive, fetchFrontierEci };
