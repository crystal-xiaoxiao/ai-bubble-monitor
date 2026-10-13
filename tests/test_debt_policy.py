"""Debt policy regressions use isolated synthetic state; never publish or send."""
import contextlib
import copy
import io
import json
from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch

import test_structural_pipeline as structural

p = structural.p


class DebtPolicyTests(TestCase):
    # Reuse synthetic setup and data without inheriting the existing test cases.
    setUp = structural.StructuralPipelineTests.setUp
    nvda_fixture = structural.StructuralPipelineTests.nvda_fixture
    bundle = structural.StructuralPipelineTests.bundle

    def prior_debt(self):
        return next(i for i in self.old['indicators'] if i['id'] == 'debt_capex_ratio')

    def debt_item(self, bundle):
        return next(i for i in bundle['indicators'] if i['id'] == 'debt_capex_ratio')

    def incomplete_bundle(self, stale_count=0):
        bundle = self.bundle(stale_count)
        bundle['debt_review']['full_reconciliation'] = False
        bundle['debt_ledger'] = p.read(self.root / 'docs/data/debt_ledger.json')
        return bundle

    def set_reconciliation_age(self, days):
        ledger = p.read(self.root / 'docs/data/debt_ledger.json')
        ledger['last_full_recon'] = (self.at.date() - timedelta(days=days)).isoformat()
        (self.root / 'docs/data/debt_ledger.json').write_bytes(p.encoded(ledger))
        self.context = p.prepare(self.root, self.at)

    def notice_text(self, files):
        return json.dumps(files[f"feishu_outbox/{self.context['as_of_date']}.json"], ensure_ascii=False)

    def test_due_policy_carries_authoritative_state_and_preserves_pending_research(self):
        bundle = self.incomplete_bundle()
        old_ledger = copy.deepcopy(bundle['debt_ledger'])
        observation = {'financing_reading': 700, 'source_date': '2026-10-18'}
        bundle['evidence']['debt_capex_ratio']['raw'] = observation
        # Opened sources succeeded; incomplete full reconciliation is its own reason.
        bundle['evidence']['debt_capex_ratio']['attempted_urls'] = []
        new_deal = {'borrower': 'Synthetic unconfirmed reconciliation candidate',
                    'date': '2026-10-18', 'amount_usd_b': 1,
                    'source_url': 'https://example.test/synthetic-candidate'}
        bundle['debt_ledger']['deals'].append(new_deal)
        bundle['debt_ledger']['ms_anchor']['numerator_usd_b'] = 700
        bundle['debt_ledger']['capex_denominator_usd_b'] = 1000
        self.debt_item(bundle).update(value=70, value_display='70%', status='red',
                                      as_of=self.context['as_of_date'])
        bundle['wow_changes'] = [{'indicator_id': 'debt_capex_ratio', 'type': 'status_upgrade',
                                  'from': self.prior_debt()['status'], 'to': 'red',
                                  'note': '尚未完成对账的候选变化',
                                  'note_en': 'Candidate change pending reconciliation'}]
        untouched = copy.deepcopy(bundle)

        normalized = p.apply_debt_reconciliation_policy(self.root, bundle, self.context)
        self.assertEqual(bundle, untouched, 'Policy must not mutate the researcher input')
        item = self.debt_item(normalized)
        for field in ['value', 'value_display', 'value_display_en', 'status', 'as_of']:
            self.assertEqual(item.get(field), self.prior_debt().get(field), field)
        self.assertTrue(item['stale'])
        self.assertEqual(item['freshness'], 'stale')
        self.assertEqual(normalized['debt_ledger'], old_ledger)
        self.assertEqual(normalized['wow_changes'], [])
        evidence = normalized['evidence']['debt_capex_ratio']
        self.assertEqual(evidence['kind'], 'carry')
        self.assertEqual(evidence['raw']['attempted_observations'], observation)
        self.assertIn(new_deal, evidence['raw']['pending_debt_updates']['changed_deals'])
        self.assertIn('recon', evidence['rationale'].lower())

        files = p.build(self.root, bundle, self.context, self.at)
        self.assertEqual(files['docs/data/debt_ledger.json'], old_ledger)
        self.assertNotIn('本周新债务', self.notice_text(files))
        run = files[f"runs/{self.context['cycle']}.json"]
        self.assertIn(new_deal, run['evidence']['debt_capex_ratio']['raw']['pending_debt_updates']['changed_deals'])
        self.assertEqual(bundle, untouched)

    def test_age_28_is_due_and_warning_is_a_separate_notification_line(self):
        self.set_reconciliation_age(28)
        files = p.build(self.root, self.incomplete_bundle(), self.context, self.at)
        run = files[f"runs/{self.context['cycle']}.json"]
        self.assertEqual(run['status'], 'validated_release')
        self.assertEqual(run['debt_reconciliation_overdue_days'], 0)
        self.assertIn('debt_capex_ratio', run['stale_ids'])
        rows = files[f"feishu_outbox/{self.context['as_of_date']}.json"]['content']['post']['zh_cn']['content']
        warnings = [row for row in rows if any('债务完整对账逾期 0 天' in part.get('text', '') for part in row)]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0], [{'tag': 'text', 'text': run['warnings'][0]}])

    def test_policy_does_not_apply_before_october_18_cycle(self):
        self.at -= timedelta(days=7)
        self.context = p.prepare(self.root, self.at)
        bundle = self.incomplete_bundle()
        self.assertEqual(p.apply_debt_reconciliation_policy(self.root, bundle, self.context), bundle)
        files = p.build(self.root, bundle, self.context, self.at)
        run = files[f"runs/{self.context['cycle']}.json"]
        self.assertNotIn('debt_capex_ratio', run['stale_ids'])
        self.assertIn('债务完整对账逾期', self.notice_text(files))

    def test_not_due_weekly_increment_remains_fresh_and_is_not_discarded(self):
        self.set_reconciliation_age(27)
        bundle = self.incomplete_bundle()
        new_deal = {'borrower': 'Synthetic actual weekly debt', 'date': '2026-10-18',
                    'amount_usd_b': 1, 'source_url': 'https://example.test/synthetic-new'}
        bundle['debt_ledger']['deals'].append(new_deal)
        self.assertEqual(p.apply_debt_reconciliation_policy(self.root, bundle, self.context), bundle)
        files = p.build(self.root, bundle, self.context, self.at)
        self.assertIn(new_deal, files['docs/data/debt_ledger.json']['deals'])
        run = files[f"runs/{self.context['cycle']}.json"]
        self.assertNotIn('debt_capex_ratio', run['stale_ids'])
        self.assertNotIn('warnings', run)
        self.assertIn('本周新债务', self.notice_text(files))

    def test_due_policy_recurs_28_days_after_a_later_successful_reconciliation(self):
        ledger = p.read(self.root / 'docs/data/debt_ledger.json')
        ledger['last_full_recon'] = '2026-10-18'
        (self.root / 'docs/data/debt_ledger.json').write_bytes(p.encoded(ledger))
        self.at += timedelta(days=28)
        self.context = p.prepare(self.root, self.at)
        normalized = p.apply_debt_reconciliation_policy(self.root, self.incomplete_bundle(), self.context)
        self.assertEqual(self.context['cycle'], '2026-11-15')
        self.assertTrue(self.debt_item(normalized)['stale'])
        self.assertEqual(normalized['debt_ledger']['last_full_recon'], '2026-10-18')

    def test_due_debt_counts_in_five_success_six_failure_gate_without_state_writes(self):
        for other_stale, expected_status in [(4, 'validated_release'), (5, 'failed_data')]:
            with self.subTest(total_stale=other_stale + 1):
                before = p.fingerprints(self.root)
                files = p.build(self.root, self.incomplete_bundle(other_stale), self.context, self.at)
                run = files[f"runs/{self.context['cycle']}.json"]
                self.assertEqual(run['status'], expected_status)
                self.assertEqual(run['freshness_counts']['stale'], other_stale + 1)
                self.assertIn('debt_capex_ratio', run['stale_ids'])
                self.assertIn('债务完整对账逾期', self.notice_text(files))
                self.assertEqual(p.fingerprints(self.root), before)
                if expected_status == 'failed_data':
                    self.assertEqual(set(files), {f"runs/{self.context['cycle']}.json",
                                                  f"feishu_outbox/{self.context['as_of_date']}.json"})

    def test_completed_reconciliation_remains_fresh_but_requires_all_audit_scopes(self):
        bundle = self.bundle()
        normalized = p.apply_debt_reconciliation_policy(self.root, bundle, self.context)
        self.assertEqual(normalized, bundle)
        files = p.build(self.root, bundle, self.context, self.at)
        run = files[f"runs/{self.context['cycle']}.json"]
        self.assertNotIn('debt_capex_ratio', run['stale_ids'])
        self.assertNotIn('warnings', run)
        for missing in ['financing_anchor', 'capex_denominator', 'deal_reconciliation']:
            with self.subTest(missing_scope=missing):
                candidate = copy.deepcopy(bundle)
                candidate['debt_review']['reconciliation_sources'] = [
                    row for row in candidate['debt_review']['reconciliation_sources'] if row['scope'] != missing]
                with self.assertRaisesRegex(p.GateError, 'must audit annual financing'):
                    p.build(self.root, candidate, self.context, self.at)

    def test_incomplete_reconciliation_cannot_advance_its_authoritative_date(self):
        bundle = self.incomplete_bundle()
        bundle['debt_ledger']['last_full_recon'] = self.context['as_of_date']
        with self.assertRaisesRegex(p.GateError, 'Cannot advance unreconciled date'):
            p.build(self.root, bundle, self.context, self.at)

    def test_completed_reconciliation_cannot_be_claimed_for_a_stale_carried_indicator(self):
        bundle = self.bundle()
        bundle['debt_ledger'] = p.read(self.root / 'docs/data/debt_ledger.json')
        item = self.debt_item(bundle)
        for field in ['value', 'value_display', 'value_display_en', 'status', 'as_of']:
            if field in self.prior_debt():
                item[field] = self.prior_debt()[field]
            else:
                item.pop(field, None)
        item['stale'] = True
        bundle['evidence']['debt_capex_ratio']['kind'] = 'carry'
        with self.assertRaisesRegex(p.GateError, 'Completed debt reconciliation cannot carry stale'):
            p.build(self.root, bundle, self.context, self.at)
        item['stale'] = False
        bundle['evidence']['debt_capex_ratio']['kind'] = 'web'
        with self.assertRaisesRegex(p.GateError, 'Full reconciliation date mismatch'):
            p.validate_debt(self.root, bundle, self.context, bundle['indicators'], self.at)

    def test_source_failure_without_attempted_urls_still_fails_outside_debt_policy(self):
        bundle = self.incomplete_bundle()
        self.debt_item(bundle)['stale'] = False
        bundle['evidence']['debt_capex_ratio']['attempted_urls'] = []
        p.build(self.root, bundle, self.context, self.at)
        item = bundle['indicators'][0]
        item['stale'] = True
        evidence = bundle['evidence'][item['id']]
        evidence.update(kind='carry', attempted_urls=[])
        with self.assertRaisesRegex(p.GateError, 'document failed source chain'):
            p.build(self.root, bundle, self.context, self.at)

    def test_debt_reconciliation_raw_flag_cannot_bypass_source_chain_outside_policy(self):
        for before_effective in [False, True]:
            with self.subTest(before_effective=before_effective):
                if before_effective:
                    self.at -= timedelta(days=7)
                    self.set_reconciliation_age(35)
                else:
                    self.set_reconciliation_age(27)
                bundle = self.incomplete_bundle()
                item = self.debt_item(bundle)
                for field in ['value', 'value_display', 'value_display_en', 'status', 'as_of']:
                    if field in self.prior_debt():
                        item[field] = self.prior_debt()[field]
                    else:
                        item.pop(field, None)
                item['stale'] = True
                evidence = bundle['evidence']['debt_capex_ratio']
                evidence.update(kind='carry', attempted_urls=[])
                evidence['raw']['reconciliation_incomplete'] = True
                with self.assertRaisesRegex(p.GateError, 'document failed source chain'):
                    p.build(self.root, bundle, self.context, self.at)

    def test_score_uses_prepared_context_and_matches_build_debt_and_summary(self):
        bundle = self.incomplete_bundle()
        self.debt_item(bundle).update(value=70, value_display='70%', status='red',
                                      as_of=self.context['as_of_date'])
        directory = self.root / '.run'
        directory.mkdir(exist_ok=True)
        bundle_path = directory / 'bundle.json'
        context_path = directory / 'context.json'
        bundle_path.write_bytes(p.encoded(bundle))
        context_path.write_bytes(p.encoded(self.context))
        files = p.build(self.root, bundle, self.context, self.at)
        snapshot = files['docs/data/latest.json']
        for explicit in [False, True]:
            with self.subTest(explicit_context=explicit):
                argv = ['pipeline.py', '--root', str(self.root), 'score', '--bundle', str(bundle_path)]
                if explicit:
                    argv += ['--context', str(context_path)]
                output = io.StringIO()
                with contextlib.chdir(self.root), patch.object(p.sys, 'argv', argv), \
                        patch.object(p, 'now', return_value=self.at), contextlib.redirect_stdout(output):
                    p.main()
                result = json.loads(output.getvalue())
                self.assertEqual(result['indicator_statuses']['debt_capex_ratio'], self.prior_debt()['status'])
                self.assertEqual(result['indicator_freshness']['debt_capex_ratio'], 'stale')
                run = files[f"runs/{self.context['cycle']}.json"]
                self.assertEqual(result['freshness_counts'], run['freshness_counts'])
                carried = next(i for i in snapshot['indicators'] if i['id'] == 'debt_capex_ratio')
                self.assertEqual(carried['as_of'], self.prior_debt()['as_of'])
                for field, value in result['summary'].items():
                    self.assertEqual(value, snapshot['summary'][field], field)
