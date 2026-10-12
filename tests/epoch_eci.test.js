'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { execFileSync } = require('node:child_process');
const { parseEciCsv, computeFrontierEci, readEciArchive, fetchFrontierEci, CSV_MEMBER } = require('../scripts/lib/epoch_eci');
const { preserveFailedSourceData } = require('../scripts/prefetch');

const HEADER = 'Model,eci,eci_ci_low,eci_ci_high,date,Organization';
const csv = (lines) => `${HEADER}\n${lines.join('\n')}\n`;
const record = (model, score, date) => `${model},${score},${score - 1},${score + 1},${date},Lab`;
const HISTORY = csv([
  record('Base', 100, '2025-10-01'),
  record('Prior', 110, '2025-12-01'),
  record('Ninety', 120, '2026-04-20'),
  record('July', 125, '2026-07-20'),
  record('September', 128, '2026-09-01'),
  record('Later weaker', 119, '2026-10-05'),
  record('Future', 999, '2026-11-01'),
]);

test('ECI rolling maxima use release dates, ignore weaker later/future models, and expose two 90-day windows', () => {
  // Deliberately reverse CSV rows: calculation must not depend on upstream row order.
  const data = computeFrontierEci(parseEciCsv(HISTORY).reverse(), '2026-10-12');
  assert.equal(data.current_sota.model, 'September');
  assert.equal(data.sota_90d_ago.model, 'Ninety');
  assert.equal(data.sota_180d_ago.model, 'Prior');
  assert.equal(data.sota_365d_ago.model, 'Base');
  assert.equal(data.gain_90d, 8);
  assert.equal(data.gain_previous_90d, 10);
  assert.equal(data.gain_1y, 28);
  assert.equal(data.avg_quarterly_gain_1y, 7);
  assert.equal(data.gain_90d_to_quarterly_1y_ratio, 1.142857);
  assert.deepEqual(data.frontier_entrants_90d.map((r) => r.model), ['July', 'September']);
  assert.equal(data.future_models_excluded, 1);
  assert.equal(data.latest_model_date, '2026-10-05');
});

test('same-day entrants are deterministic and tied unchanged scores do not count as frontier progress', () => {
  const text = csv([
    record('Base', 100, '2025-01-01'),
    record('Low same day', 101, '2026-08-01'),
    record('Z tie', 110, '2026-08-01'),
    record('A tie', 110, '2026-08-01'),
    record('No gain', 110, '2026-09-01'),
  ]);
  const data = computeFrontierEci(parseEciCsv(text), '2026-10-12');
  assert.deepEqual(data.frontier_entrants_90d.map((r) => r.model), ['A tie', 'Z tie']);
  assert.equal(data.current_sota.model, 'A tie');
});

test('cutoff boundaries include baseline day; 90-day entrants are later than that day', () => {
  const text = csv([record('Before', 100, '2025-01-01'), record('At boundary', 110, '2026-07-14'), record('After', 120, '2026-07-15')]);
  const data = computeFrontierEci(parseEciCsv(text), '2026-10-12');
  assert.equal(data.baseline_cutoffs['90d'], '2026-07-14');
  assert.equal(data.sota_90d_ago.model, 'At boundary');
  assert.deepEqual(data.frontier_entrants_90d.map((r) => r.model), ['After']);
});

test('CSV accepts BOM/CRLF, quoted commas, escaped quotes and multiline organization', () => {
  const rows = parseEciCsv(`\uFEFF${HEADER}\r\n"A, \"\"quoted\"\"",100,99,101,2026-01-01,"Lab\nTeam"\r\n`);
  assert.equal(rows[0].model, 'A, "quoted"');
  assert.equal(rows[0].organization, 'Lab\nTeam');
});

test('official historical rows may omit CI and organization; missing metadata remains null without discarding ECI', () => {
  const rows = parseEciCsv(csv(['Historical,150,,,2025-08-07,', record('Later', 155, '2026-09-01')]));
  assert.equal(rows[0].eci, 150);
  assert.equal(rows[0].eci_ci_low, null);
  assert.equal(rows[0].eci_ci_high, null);
  assert.equal(rows[0].organization, null);
  const data = computeFrontierEci(rows, '2026-10-12');
  assert.equal(data.sota_365d_ago.eci, 150);
  assert.equal(data.models_missing_confidence_intervals, 1);
  assert.equal(data.models_missing_organization, 1);
});

test('malformed numeric/date/schema values fail instead of silently producing a lower frontier', () => {
  for (const text of [
    csv(['Broken,NaN,99,101,2026-01-01,Lab']),
    csv(['Broken,,99,101,2026-01-01,Lab']),
    csv(['Broken,100,99,Infinity,2026-01-01,Lab']),
    csv(['Broken,100,101,102,2026-01-01,Lab']),
    csv(['Broken,100,99,101,2026-02-30,Lab']),
    csv(['Broken,100,99,101,2026-13-01,Lab']),
    csv(['Broken,100,99,101,not-a-date,Lab']),
    csv(['Broken,100,99,101,2026-01-01']),
    csv(['"Broken,100,99,101,2026-01-01,Lab']),
    'Model,eci,date,Organization\nX,100,2026-01-01,Lab\n',
  ]) assert.throws(() => parseEciCsv(text), /ECI/);
  assert.throws(() => computeFrontierEci(parseEciCsv(HISTORY), '2026-02-30'), /invalid date/);
  assert.throws(() => computeFrontierEci(parseEciCsv(HISTORY), '2020-01-01'), /no model/);
});

test('limited history yields partial with null baselines; a flat year has no infinite ratio', async () => {
  const data = computeFrontierEci(parseEciCsv(csv([record('Only recent', 100, '2026-09-01')])), '2026-10-12');
  assert.equal(data.sota_90d_ago, null);
  assert.equal(data.sota_365d_ago, null);
  assert.equal(data.gain_90d, null);
  const fetched = await fetchFrontierEci({}, {
    now: new Date('2026-10-12T01:00:00Z'),
    fetcher: async () => ({ arrayBuffer: async () => Buffer.from('unused') }),
    extract: async () => csv([record('Only recent', 100, '2026-09-01')]),
  });
  assert.equal(fetched.status, 'partial');
  assert.match(fetched.error, /insufficient history/);
  assert.equal(fetched.as_of, '2026-09-01');
  const flat = computeFrontierEci(parseEciCsv(csv([record('Flat', 100, '2025-01-01')])), '2026-10-12');
  assert.equal(flat.gain_90d, 0);
  assert.equal(flat.gain_previous_90d, 0);
  assert.equal(flat.avg_quarterly_gain_1y, 0);
  assert.equal(flat.gain_90d_to_quarterly_1y_ratio, null);
});

function archive(member, contents) {
  return execFileSync('python3', ['-c',
    'import io,sys,zipfile; b=io.BytesIO(); z=zipfile.ZipFile(b,"w"); z.writestr(sys.argv[1],sys.argv[2]); z.close(); sys.stdout.buffer.write(b.getvalue())',
    member, contents]);
}

test('actual unzip path reads only the official CSV member; corrupt or absent member fails', async () => {
  assert.equal(await readEciArchive(archive(CSV_MEMBER, HISTORY)), HISTORY);
  await assert.rejects(readEciArchive(Buffer.from('not a zip')), /invalid archive signature/);
  await assert.rejects(readEciArchive(archive('wrong.csv', HISTORY)), /extraction failed/);
  await assert.rejects(readEciArchive(archive(CSV_MEMBER, '')), /empty CSV member/);
});

test('fetch integration returns source/date/calculated data and propagates network or extraction errors', async () => {
  const got = await fetchFrontierEci({}, {
    now: new Date('2026-10-12T23:00:00Z'),
    fetcher: async (url) => {
      assert.equal(url, 'https://epoch.ai/data/benchmark_data.zip');
      return { arrayBuffer: async () => archive(CSV_MEMBER, HISTORY) };
    },
  });
  assert.equal(got.status, 'ok');
  assert.equal(got.as_of, '2026-09-01');
  assert.equal(got.data.gain_90d, 8);
  await assert.rejects(fetchFrontierEci({}, { fetcher: async () => { throw new Error('HTTP 503'); } }), /HTTP 503/);
  await assert.rejects(fetchFrontierEci({}, { fetcher: async () => ({ arrayBuffer: async () => Buffer.from('bad') }) }), /invalid archive signature/);
});

test('failed sources retain old data without freshness promotion, including repeated failures', () => {
  const oldData = { current_sota: { eci: 100, date: '2026-09-01' } };
  const previous = { _meta: { fetched_at: '2026-10-01T00:00:00Z' }, sources: { frontier_eci: { status: 'ok', data: oldData, as_of: '2026-09-01', source: 'official' } } };
  const error = { status: 'error', data: null, as_of: null, source: null, error: 'HTTP 503' };
  const [[name, retained]] = preserveFailedSourceData([['frontier_eci', error]], previous);
  assert.equal(name, 'frontier_eci');
  assert.equal(retained.status, 'error');
  assert.deepEqual(retained.data, oldData);
  assert.equal(retained.as_of, '2026-09-01');
  assert.equal(retained.retained_data_fetched_at, '2026-10-01T00:00:00Z');
  assert.equal(retained.error, 'HTTP 503');
  const retry = preserveFailedSourceData([['frontier_eci', error]], { _meta: { fetched_at: '2026-10-11T00:00:00Z' }, sources: { frontier_eci: retained } });
  assert.equal(retry[0][1].retained_data_fetched_at, '2026-10-01T00:00:00Z');
  const fresh = { status: 'ok', data: { eci: 120 }, as_of: '2026-10-12' };
  assert.deepEqual(preserveFailedSourceData([['frontier_eci', fresh]], previous)[0][1], fresh);
  assert.deepEqual(preserveFailedSourceData([['unknown', error]], previous)[0][1], error);
});
