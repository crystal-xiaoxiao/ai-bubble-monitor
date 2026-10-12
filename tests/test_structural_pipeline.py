"""Structural-contract regression tests use synthetic state and never publish."""
import copy
from datetime import datetime, timedelta, timezone
from unittest import TestCase

import test_pipeline as legacy

p = legacy.p


class StructuralPipelineTests(TestCase):
    def setUp(self):
        legacy.PipelineTests.setUp(self)
        self.at = datetime(2026, 10, 18, 23, 10, tzinfo=timezone.utc)
        (self.root / 'docs/data/nvda_commitments.json').write_bytes(p.encoded(self.nvda_fixture()))
        self.context = p.prepare(self.root, self.at)

    def nvda_fixture(self):
        entries = []
        for key, instrument, amount, status, parent in [
                ('equity', 'equity', 30, 'signed', None),
                ('guarantee', 'financing_guarantee', 105, 'signed', None),
                ('aggregate', 'financing_guarantee', 3.5, 'signed', None),
                ('detail', 'financing_guarantee', .86034, 'signed', 'aggregate'),
                ('part-signed', 'convertible', 2, 'conditional', None),
                ('unsigned-ceiling', 'loan', 0, 'conditional', None)]:
            entry = {'id': key, 'customer': key, 'instrument': instrument,
                     'announcement_date': '2026-09-15', 'signed_amount_usd_bn': amount,
                     'amount_usd_bn': max(amount, 100) if status == 'conditional' else amount,
                     'status': status, 'source_date': '2026-09-15',
                     'source_url': 'https://example.test/synthetic',
                     'accessed_at': '2026-10-12T10:00:00Z', 'notes': 'Synthetic signed contract test only'}
            if parent:
                entry['included_in'] = parent
            entries.append(entry)
        quarters = [{'fiscal_period': str(index), 'period_end': end, 'revenue_usd_bn': 25,
                     'source_url': 'https://example.test/synthetic', 'source_date': '2026-08-26'}
                    for index, end in enumerate(['2025-10-26', '2026-01-25', '2026-04-26', '2026-07-26'])]
        return {'schema_version': 1, 'basis': 'signed_customer_financing_including_guarantees',
                'coverage': {'complete': True, 'unresolved_ids': []}, 'entries': entries,
                'exclusions': [], 'ltm_revenue': {'as_of': '2026-07-26', 'quarters': quarters, 'revenue_usd_bn': 100},
                'total_signed_usd_bn': 140.5, 'ratio_pct': 140.5}

    def bundle(self, stale_count=0):
        b = legacy.PipelineTests.bundle(self, stale_count)
        items = {i['id']: i for i in b['indicators']}
        item = items['enterprise_deploy']
        item.update(value=44, value_display='44%', status='green', as_of='2026-09-24', stale=False,
                    note='口径切换为 KPMG 重要劳动力采纳率，44%较23%增加21pt。',
                    note_en='Basis switch to KPMG significant workforce adoption: 44% versus 23%, up21pt.')
        b['evidence'][item['id']].update(kind='web', raw={
            'basis': 'kpmg_significant_workforce_adoption', 'current_pct': 44, 'previous_pct': 23,
            'current_quarter': '2026-Q3', 'previous_quarter': '2026-Q2', 'change_pp': 21,
            'publication_date': '2026-09-24'})
        item = items['dc_abs_spread']
        item.update(status='green', as_of=self.context['as_of_date'], stale=False,
                    note='口径切换为90天信用事件扫描，本期未见确认事件。',
                    note_en='Basis switch to a90-day credit-event scan; no confirmed events observed.')
        b['evidence'][item['id']].update(kind='web', raw={
            'basis': 'dc_abs_project_finance_credit_status',
            'window': {'start': (self.at.date()-timedelta(days=90)).isoformat(), 'end': self.context['as_of_date']},
            'queries': ['Synthetic 90-day scan'], 'sources_checked': ['https://example.test/synthetic'], 'events': []})
        item = items['nvda_invest_revenue']
        item.update(value=140.5, value_display='140.5%', status='red', as_of='2026-09-15', stale=False,
                    note='本期重建已签约分子，与旧43–45%口径不可比。',
                    note_en='Rebuild signed financing numerator; not comparable with the old43–45% basis.')
        b['evidence'][item['id']].update(kind='web', raw={'ledger_check': 'Synthetic opened-source ledger check only'})
        item = items['arr_2nd_deriv']
        item.update(value='减速', value_display='减速·披露序列', value_display_en='Slowing disclosed series',
                    status='red', as_of='2026-07-31', stale=False,
                    note='口径切换为同口径披露点估算；Anthropic披露序列减速，OpenAI历史net端点不足，未计入。',
                    note_en='Basis switch to a disclosed-series estimate; Anthropic slows; OpenAI lacks historical net anchors and is excluded.')
        b['evidence'][item['id']].update(kind='web', raw={'ledger_check': 'Synthetic opened-source ledger check only'})
        b['debt_review']['reconciliation_sources'] = [
            {'scope': scope, 'url': 'https://example.test/synthetic', 'checked_at': p.iso(self.at), 'raw_reading': 'Synthetic full reconciliation only'}
            for scope in ['financing_anchor', 'capex_denominator', 'deal_reconciliation']]
        b['verdict_desc'] = '**一句话**：风险温度偏高。\n\n**历史**：1999-06、2000-02、2021-11、2007-10有差异。\n\n**反向证据**：基本面仍有支撑。\n\n**判读**：估值资金面共振，两轴及边际风险需关注。'
        b['verdict_desc_en'] = '**Bottom line**: Risk remains elevated.\n\n**History**: 1999-06,2000-02,2021-11 and2007-10 differ.\n\n**Counterevidence**: Fundamentals offer support.\n\n**Verdict**: Category resonance applies; monitor two-axis signals and marginal momentum.'
        return b

    def test_quarterly_trend_boundaries_including_decimal_percentages(self):
        for current, previous, expected in [(26,23,'green'), (20,23,'yellow'), (19.99,23,'red'),
                                            (25.99,23,'yellow'), (66.1,63.1,'green'), (63.1,66.1,'yellow')]:
            raw = {'basis':'kpmg_significant_workforce_adoption','current_pct':current,'previous_pct':previous,
                   'current_quarter':'2026-Q3','previous_quarter':'2026-Q2','change_pp':round(current-previous,10)}
            self.assertEqual(p.enterprise_status(raw,current),expected)
        raw['previous_quarter']='2026-Q1'
        with self.assertRaisesRegex(p.GateError,'adjacent quarters'):
            p.enterprise_status(raw,current)

    def test_pipeline_derives_freshness_and_does_not_rewrite_old_snapshots(self):
        b = self.bundle()
        for item in b['indicators']:
            item['freshness'] = 'stale'  # Input labels are not authoritative.
        before = (self.root/'docs/data/latest.json').read_bytes()
        files = p.build(self.root,b,self.context,self.at)
        self.assertTrue(all(i['freshness']=='new' for i in files['docs/data/latest.json']['indicators']))
        self.assertEqual((self.root/'docs/data/latest.json').read_bytes(),before)
        self.assertNotIn('docs/data/snapshots/2026-10-12.json',files)
        self.assertEqual(files['runs/2026-10-18.json']['freshness_counts'],{'new':25,'current':0,'stale':0})

    def test_dc_events_types_and_50bp_boundary(self):
        for kind in ['default','force_majeure','downgrade','issuance_withdrawal','forced_repricing']:
            self.assertEqual(p.dc_credit_status({'events':[{'event_type':kind,'confirmed':True}]}),'red')
        for kind in ['issuance_delay','terms_tightening']:
            self.assertEqual(p.dc_credit_status({'events':[{'event_type':kind,'confirmed':True}]}),'yellow')
        self.assertEqual(p.dc_credit_status({'events':[]}),'green')
        for bp, expected in [(49.99,'green'),(50,'red')]:
            self.assertEqual(p.dc_credit_status({'events':[{'event_type':'spread_widening','confirmed':True,'spread_change_bps':bp}]}),expected)
        self.assertEqual(p.dc_credit_status({'events':[{'event_type':'default','confirmed':False}]}),'green')
        b = self.bundle()
        b['evidence']['dc_abs_spread']['raw']['window']['start']='2026-10-01'
        with self.assertRaisesRegex(p.GateError,'90-day scan'):
            p.build(self.root,b,self.context,self.at)

    def test_signed_guarantees_partial_conditional_and_aggregate_detail_no_double_count(self):
        totals = p.nvda_totals(self.nvda_fixture(),self.context['as_of_date'])
        self.assertEqual(totals['numerator_signed_usd_bn'],140.5)
        self.assertEqual(totals['metric_as_of'],'2026-09-15')
        ledger = self.nvda_fixture()
        ledger['entries'][3]['signed_amount_usd_bn']=4
        ledger['entries'][3]['amount_usd_bn']=4
        with self.assertRaisesRegex(p.GateError,'details exceed'):
            p.nvda_totals(ledger,self.context['as_of_date'])

    def test_unknown_signed_amount_cannot_establish_green_from_lower_bound(self):
        ledger = self.nvda_fixture()
        ledger['entries'] = [ledger['entries'][4],copy.deepcopy(ledger['entries'][0])]
        ledger['entries'][1]['signed_amount_usd_bn']=None
        ledger['coverage']={'complete':False,'unresolved_ids':['equity']}
        ledger.update(total_signed_usd_bn=2,ratio_pct=2)
        item={'value':2,'as_of':'2026-09-15','note':'已核实下限','note_en':'Verified lower bound'}
        with self.assertRaisesRegex(p.GateError,'below red'):
            p.structural_status('nvda_invest_revenue',item,{}, {'nvda_commitments':ledger},self.context)

    def test_arr_same_basis_qualifiers_lag_and_unspecified_exclusion(self):
        ledger = p.read(self.root/'docs/data/arr_ledger.json')
        result = p.arr_calculations(ledger,self.context['as_of_date'])
        a = result['companies']['Anthropic']
        self.assertEqual(a['anchor_lag_days'],[24,31])
        self.assertAlmostEqual(a['acceleration_pp'],-116.666667,places=5)
        self.assertTrue(a['reported_point_estimate'])
        self.assertIn('OpenAI',result['excluded_companies'])
        for point in ledger['observations']:
            if point['id']=='anthropic-2025-12-31-gross':
                point['as_of']='2025-12-30'
        self.assertNotIn('Anthropic',p.arr_calculations(ledger,self.context['as_of_date'])['companies'])
        ledger = p.read(self.root/'docs/data/arr_ledger.json')
        ledger['observations'][0]['is_forecast']=True
        with self.assertRaisesRegex(p.GateError,'forecasts'):
            p.arr_calculations(ledger,self.context['as_of_date'])

    def test_basis_confirmation_cannot_be_removed_or_company_mismatched(self):
        b=self.bundle()
        ledger=p.read(self.root/'docs/data/arr_ledger.json')
        ledger['basis_confirmations']=[]
        b['arr_ledger']=ledger
        with self.assertRaisesRegex(p.GateError,'basis confirmation changed or removed'):
            p.ledger_candidate(self.root,b,'arr_ledger')
        ledger=p.read(self.root/'docs/data/arr_ledger.json')
        ledger['observations'][0]['basis_confirmation_id']='openai-net-cloud-sales-2026-10-09'
        with self.assertRaisesRegex(p.GateError,'mismatched accounting-basis'):
            p.arr_calculations(ledger,self.context['as_of_date'])

    def test_first_basis_switch_is_excluded_from_momentum_and_wow(self):
        b=self.bundle()
        files=p.build(self.root,b,self.context,self.at)
        items=files['docs/data/latest.json']['indicators']
        changed={i['id'] for i in items if i.get('basis_changed')}
        self.assertTrue(set(p.STRUCTURAL_CANONICAL)<=changed)
        self.assertEqual(files['docs/data/latest.json']['summary']['momentum']['net'],0)
        enterprise=next(i for i in items if i['id']=='enterprise_deploy')
        self.assertIn('≥+3pt',enterprise['threshold_text'])
        old=next(i for i in self.old['indicators'] if i['id']=='enterprise_deploy')
        b['wow_changes']=[{'indicator_id':'enterprise_deploy','type':'status_downgrade','from':old['status'],'to':'green','note':'测试','note_en':'Test'}]
        with self.assertRaisesRegex(p.GateError,'basis switch is incomparable'):
            p.build(self.root,b,self.context,self.at)

    def test_arr_company_and_accounting_basis_signature_change_is_incomparable(self):
        prior = copy.deepcopy(self.old)
        prior_item = next(i for i in prior['indicators'] if i['id']=='arr_2nd_deriv')
        prior_item.update(basis='same_basis_disclosed_series_3m_vs_prior3m',basis_components={'OpenAI':'net'})
        (self.root/'docs/data/latest.json').write_bytes(p.encoded(prior))
        self.old=prior
        self.context=p.prepare(self.root,self.at)
        files=p.build(self.root,self.bundle(),self.context,self.at)
        item=next(i for i in files['docs/data/latest.json']['indicators'] if i['id']=='arr_2nd_deriv')
        self.assertTrue(item['basis_changed'])
        self.assertEqual(item['basis_components'],{'Anthropic':'gross'})
        self.assertTrue(files['docs/data/raw_history.json']['arr_2nd_deriv'][-1]['raw']['basis_switch'])

    def test_current_must_preserve_actual_quarter_inputs_not_only_display(self):
        b=self.bundle()
        files=p.build(self.root,b,self.context,self.at)
        for path in ['docs/data/latest.json','docs/data/raw_history.json','docs/data/debt_ledger.json']:
            (self.root/path).write_bytes(p.encoded(files[path]))
        self.old=p.read(self.root/'docs/data/latest.json')
        self.history=p.read(self.root/'docs/data/raw_history.json')
        self.at += timedelta(days=7)
        self.context=p.prepare(self.root,self.at)
        b=self.bundle()
        item=next(i for i in b['indicators'] if i['id']=='enterprise_deploy')
        prior=next(i for i in self.old['indicators'] if i['id']=='enterprise_deploy')
        item.update({k:prior[k] for k in ['value','value_display','status','as_of']})
        ev=b['evidence'][item['id']]
        ev['kind']='current'
        ev['raw'].update(latest_release_date='2026-09-24',next_expected='Not announced')
        ev['raw'].update(previous_pct=22,change_pp=22)  # Same44%, green, date and visible label.
        with self.assertRaisesRegex(p.GateError,'current changed canonical previous_pct'):
            p.build(self.root,b,self.context,self.at)

    def test_debt_reconciliation_mandatory_even_if_debt_carried_stale(self):
        b=self.bundle()
        b['debt_review']['full_reconciliation']=False
        b['debt_ledger']['last_full_recon']='2026-09-06'
        with self.assertRaisesRegex(p.GateError,'mandatory from 2026-10-18'):
            p.build(self.root,b,self.context,self.at)
        item=next(i for i in b['indicators'] if i['id']=='debt_capex_ratio')
        prior=next(i for i in self.old['indicators'] if i['id']=='debt_capex_ratio')
        for field in ['value','value_display','value_display_en','status','as_of']:
            if field in prior:
                item[field]=prior[field]
            else:
                item.pop(field,None)
        item['stale']=True
        b['evidence'][item['id']]['kind']='carry'
        with self.assertRaisesRegex(p.GateError,'mandatory from 2026-10-18'):
            p.build(self.root,b,self.context,self.at)
        self.at+=timedelta(days=7)
        self.context=p.prepare(self.root,self.at)
        b=self.bundle()
        b['debt_review']['full_reconciliation']=False
        b['debt_ledger']['last_full_recon']='2026-09-06'
        with self.assertRaisesRegex(p.GateError,'mandatory from 2026-10-18'):
            p.build(self.root,b,self.context,self.at)

    def test_debt_source_audit_requires_all_scopes_and_real_this_run_timestamp(self):
        b=self.bundle()
        b['debt_review']['reconciliation_sources'].pop()
        with self.assertRaisesRegex(p.GateError,'must audit annual financing'):
            p.build(self.root,b,self.context,self.at)
        b=self.bundle()
        b['debt_review']['reconciliation_sources'][0]['checked_at']=p.iso(self.at+timedelta(hours=2))
        with self.assertRaisesRegex(p.GateError,'not checked in this run'):
            p.build(self.root,b,self.context,self.at)
        # Completing the one-time deadline does not waive audit evidence for
        # a later claimed full reconciliation.
        old=p.read(self.root/'docs/data/debt_ledger.json')
        old['last_full_recon']='2026-10-18'
        (self.root/'docs/data/debt_ledger.json').write_bytes(p.encoded(old))
        self.at+=timedelta(days=7)
        self.context=p.prepare(self.root,self.at)
        b=self.bundle()
        b['debt_review'].pop('reconciliation_sources')
        with self.assertRaisesRegex(p.GateError,'this-run source audit'):
            p.build(self.root,b,self.context,self.at)

    def test_append_only_ledger_is_written_only_to_success_manifest(self):
        b=self.bundle()
        ledger=p.read(self.root/'docs/data/arr_ledger.json')
        point=copy.deepcopy(ledger['observations'][-1])
        point.update(id='openai-2026-10-01-net-synthetic',as_of='2026-10-01',source_date='2026-10-01',amount_usd_bn=51)
        ledger['observations'].append(point)
        b['arr_ledger']=ledger
        files=p.build(self.root,b,self.context,self.at)
        self.assertEqual(files['docs/data/arr_ledger.json'],ledger)
        self.assertNotIn('docs/data/nvda_commitments.json',files)
        b=self.bundle(6)
        b['arr_ledger']=ledger
        files=p.build(self.root,b,self.context,self.at)
        self.assertEqual(set(files),{'feishu_outbox/2026-10-18.json','runs/2026-10-18.json'})
        b=self.bundle()
        ledger['observations'][0]['amount_usd_bn']=10
        b['arr_ledger']=ledger
        with self.assertRaisesRegex(p.GateError,'historical record changed'):
            p.ledger_candidate(self.root,b,'arr_ledger')

    def test_stale_arr_cannot_persist_new_forecast_inside_otherwise_valid_release(self):
        b=self.bundle()
        ledger=p.read(self.root/'docs/data/arr_ledger.json')
        point=copy.deepcopy(ledger['observations'][-1])
        point.update(id='forecast-synthetic',as_of='2026-10-01',source_date='2026-10-01',is_forecast=True)
        ledger['observations'].append(point)
        b['arr_ledger']=ledger
        item=next(i for i in b['indicators'] if i['id']=='arr_2nd_deriv')
        prior=next(i for i in self.old['indicators'] if i['id']=='arr_2nd_deriv')
        for field in ['value','value_display','value_display_en','status','as_of']:
            if field in prior:
                item[field]=prior[field]
            else:
                item.pop(field,None)
        item['stale']=True
        b['evidence'][item['id']]['kind']='carry'
        with self.assertRaisesRegex(p.GateError,'forecasts cannot enter actual ARR ledger'):
            p.build(self.root,b,self.context,self.at)
