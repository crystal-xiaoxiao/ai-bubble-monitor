'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

// Run the real inline page renderer. Optional paths let the same contract suite
// verify both independently deployed language mirrors before publication.
const pages = process.argv.slice(2);
if (!pages.length) pages.push(path.join(__dirname, '../docs/index.html'));

function pageRenderer(page) {
  const html = fs.readFileSync(page, 'utf8');
  const script = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
    .map(match => match[1]).find(value => value.includes('function render(data, credit)'));
  assert.ok(script, 'the inline page renderer must exist');
  const root = { innerHTML: '' };
  const context = {
    document: { getElementById: id => id === 'root' ? root : null },
    // Suppress only asynchronous network loading; call render itself below.
    fetch: () => new Promise(() => {}),
  };
  vm.createContext(context);
  vm.runInContext(script, context, { filename: page });
  return {
    currentLabel: /<html lang="en">/.test(html) ? 'Latest filing' : '最新披露',
    legacyLabel: /<html lang="en">/.test(html) ? 'CARRIED' : '沿用',
    render(indicator) {
      const fixture = {
        as_of_date: '2026-10-19', issue_number: 29, history_seed: [],
        summary: {
          red_pct: 0, red_count: 0, yellow_count: 0, green_count: 1,
          weighted_risk_score: 0, total_indicators: 1,
          verdict_label: '观察期', verdict_label_en: 'Observation',
          verdict_desc: 'Test observation', verdict_desc_en: 'Test observation',
        },
        indicators: [{
          id: 'test', category: 'valuation', name_en: 'TEST', name_zh: '测试',
          value: 10, value_display: '10', value_display_en: '10', status: 'green',
          note: 'Test note', note_en: 'Test note', threshold_text: 'Test threshold',
          threshold_text_en: 'Test threshold', source_name: 'Test source',
          as_of: '2026-09-30', stale: false, ...indicator,
        }],
      };
      context.render(fixture, null);
      const card = root.innerHTML.match(/<article class="indicator[^>]*>[\s\S]*?<\/article>/);
      assert.ok(card, 'the real renderer must output an indicator card');
      return card[0];
    },
  };
}

for (const page of pages) {
  const renderer = pageRenderer(page);
  const name = path.basename(path.dirname(page));
  test(`${name}: new observations omit freshness tags even when older than the issue`, () => {
    const card = renderer.render({ freshness: 'new', stale: true });
    assert.match(card, /^<article class="indicator">/);
    assert.doesNotMatch(card, /(?:current|carry)-tag/);
  });
  test(`${name}: current observations show the latest filing tag, never STALE`, () => {
    const card = renderer.render({ freshness: 'current', stale: true });
    assert.match(card, /^<article class="indicator">/);
    assert.ok(card.includes(`<span class="current-tag">${renderer.currentLabel}</span>`));
    assert.doesNotMatch(card, /class="carry-tag"/);
  });
  test(`${name}: explicit stale state activates STALE styling even if the old flag is false`, () => {
    const card = renderer.render({ freshness: 'stale', stale: false });
    assert.match(card, /^<article class="indicator stale">/);
    assert.doesNotMatch(card, /(?:current|carry)-tag/);
  });
  test(`${name}: old stale snapshots retain STALE styling`, () => {
    const card = renderer.render({ stale: true });
    assert.match(card, /^<article class="indicator stale">/);
    assert.doesNotMatch(card, /(?:current|carry)-tag/);
  });
  test(`${name}: old observations retain the date-based carry tag`, () => {
    const card = renderer.render({ stale: false });
    assert.match(card, /^<article class="indicator">/);
    assert.ok(card.includes(`<span class="carry-tag">${renderer.legacyLabel}</span>`));
    assert.doesNotMatch(card, /class="current-tag"/);
  });
  test(`${name}: old same-day observations have no carry tag`, () => {
    const card = renderer.render({ as_of: '2026-10-19' });
    assert.doesNotMatch(card, /(?:current|carry)-tag/);
  });
  test(`${name}: an unknown freshness value preserves the legacy fallback`, () => {
    const card = renderer.render({ freshness: 'unexpected', stale: false });
    assert.ok(card.includes(`<span class="carry-tag">${renderer.legacyLabel}</span>`));
  });
}
