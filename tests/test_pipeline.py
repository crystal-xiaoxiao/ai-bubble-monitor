"""Boundary tests use synthetic bundles in isolated temporary copies; never publish or send."""
import copy
import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pipeline", REPO / "scripts/pipeline.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in p.INPUTS:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / name, dest)
        self.at = datetime(2026, 10, 11, 23, 10, tzinfo=timezone.utc)
        self.head = patch.object(p, "head", return_value="a" * 40)
        self.head.start()
        self.addCleanup(self.head.stop)
        self.context = p.prepare(self.root, self.at)
        self.old = p.read(self.root / "docs/data/latest.json")
        self.config = p.read(self.root / "automation/task.json")
        self.history = p.read(self.root / "docs/data/raw_history.json")

    def bundle(self, stale_count=0):
        data = {"schema_version": 1, "cycle": self.context["cycle"],
                "indicators": copy.deepcopy(self.old["indicators"]), "evidence": {}, "wow_changes": [],
                "debt_ledger": p.read(self.root / "docs/data/debt_ledger.json"),
                "debt_review": {"searched_urls": ["https://example.test/synthetic"], "weekly_search_note": "Synthetic test only",
                                "full_reconciliation": True, "reconciliation_note": "Synthetic test only"}}
        data["debt_ledger"]["last_full_recon"] = self.context["as_of_date"]
        specs, _ = p.definitions(self.root)
        for idx, item in enumerate(data["indicators"]):
            key = item["id"]
            raw = copy.deepcopy(self.history.get(key, [{"raw": {"synthetic_observation": "test only"}}])[-1]["raw"])
            raw.pop("fetch_failed", None)
            for group in self.config["static_core_keys"].get(key, []):
                if not any(k in raw and p.numeric(raw[k]) for k in group):
                    raw[group[0]] = item["value"] if p.numeric(item["value"]) else 3.25
            item["stale"] = idx < stale_count
            if not item["stale"] and specs[key]["cadence"] == "scan":
                item["as_of"] = self.context["as_of_date"]
                raw.update(window={"start": "2026-10-02", "end": self.context["as_of_date"]},
                           queries=[f"Synthetic {key} test scan"],
                           sources_checked=["https://example.test/synthetic"], events=[])
            data["evidence"][key] = {"kind": "carry" if item["stale"] else "web", "checked_at": p.iso(self.at),
                                     "raw": raw, "rationale": "Synthetic test observation",
                                     "urls": ["https://example.test/synthetic"], "attempted_urls": ["https://example.test/synthetic"]}
        data["verdict_desc"] = "**一句话**：风险温度偏高。\n\n**历史**：2000-02 最接近，本期信用有差异。\n\n**反向证据**：基本面仍有支撑。\n\n**判读**：估值和资金面共振，边际风险需关注。"
        data["verdict_desc_en"] = "**Bottom line**: Risk remains elevated.\n\n**History**: 2000-02 is the closest comparison, with credit differences.\n\n**Counterevidence**: Fundamentals offer support.\n\n**Verdict**: Category resonance applies; monitor marginal momentum."
        return data

    def test_existing_scores_reproduced_without_research(self):
        specs, calibration = p.definitions(self.root)
        summary, reasons = p.aggregate(self.old["indicators"], self.old, specs, calibration)
        for key in ["total_indicators", "red_count", "yellow_count", "green_count", "red_pct", "weighted_risk_score", "stage_score", "trigger_score", "category_scores", "similarity", "verdict_label"]:
            self.assertEqual(summary[key], self.old["summary"][key], key)
        self.assertIn("category_resonance", reasons)

    def test_six_stale_only_failure_outbox_and_run_record(self):
        before = p.fingerprints(self.root)
        files = p.build(self.root, self.bundle(6), self.context, self.at)
        self.assertEqual(set(files), {"feishu_outbox/2026-10-11.json", "runs/2026-10-11.json"})
        self.assertEqual(files["runs/2026-10-11.json"]["status"], "failed_data")
        self.assertEqual(p.fingerprints(self.root), before)

    def test_five_stale_pass_and_history_is_append_only(self):
        files = p.build(self.root, self.bundle(5), self.context, self.at)
        self.assertEqual(files["docs/data/latest.json"]["issue_number"], 28)
        self.assertEqual(files["docs/data/latest.json"], files["docs/data/snapshots/2026-10-11.json"])
        for key in self.config["static_core_keys"]:
            records = files["docs/data/raw_history.json"][key]
            self.assertEqual(records[:-1], self.history[key][-25:])

    def test_stale_cannot_advance_date(self):
        b = self.bundle(6)
        b["indicators"][0]["as_of"] = "2026-10-11"
        with self.assertRaisesRegex(p.GateError, "stale carry changed as_of"):
            p.build(self.root, b, self.context, self.at)

    def test_valid_prefetch_required_and_uses_observation_date(self):
        cache_path = self.root / "docs/data/prefetch/latest.json"
        cache = p.read(cache_path)
        cache["_meta"]["fetched_at"] = p.iso(self.at - timedelta(hours=1))
        for source in cache["sources"].values():
            source["as_of"] = "2026-10-10"
        cache["sources"]["hy_oas"]["as_of"] = "2026-10-08"
        cache["sources"]["hy_oas"]["data"]["oas_bps"] = 303
        cache_path.write_bytes(p.encoded(cache))
        self.context = p.prepare(self.root, self.at)
        b = self.bundle()
        with self.assertRaisesRegex(p.GateError, "valid prefetch has priority"):
            p.build(self.root, b, self.context, self.at)
        for item in b["indicators"]:
            key = item["id"]
            if key in self.config["prefetch"]:
                source = p.prefetch_source(self.root, self.config, key, self.at)
                b["evidence"][key]["kind"] = "prefetch"
                item["value"] = source["data"][self.config["prefetch"][key]["value_key"]]
                item["as_of"] = source["as_of"]
        files = p.build(self.root, b, self.context, self.at)
        hy = next(i for i in files["docs/data/latest.json"]["indicators"] if i["id"] == "hy_oas")
        self.assertEqual(hy["as_of"], "2026-10-08")
        self.assertEqual(hy["value"], 303)

    def test_prefetch_expiry_and_partial(self):
        path = self.root / "docs/data/prefetch/latest.json"
        cache = p.read(path)
        cache["_meta"]["fetched_at"] = p.iso(self.at - timedelta(hours=72))
        path.write_bytes(p.encoded(cache))
        self.assertIsNone(p.prefetch_source(self.root, self.config, "hy_oas", self.at))
        cache["_meta"]["fetched_at"] = p.iso(self.at)
        cache["sources"]["hy_oas"]["status"] = "partial"
        path.write_bytes(p.encoded(cache))
        self.assertIsNone(p.prefetch_source(self.root, self.config, "hy_oas", self.at))

    def test_static_checks_absolute_not_derived_values(self):
        records = [{"value": v, "raw": {"last30_tokens": 100}} for v in [35, 25, 5]]
        self.assertEqual(p.static_weeks(records, [["last30_tokens"]]), 3)
        records[-1]["raw"]["last30_tokens"] = 110
        self.assertEqual(p.static_weeks(records, [["last30_tokens"]]), 1)

    def test_missing_three_times_or_estimated_three_times(self):
        self.assertEqual(p.static_weeks([{"raw": {"fetch_failed": True}}] * 3, [["x"]]), 3)
        self.assertEqual(p.static_weeks([{"raw": {"x": i, "estimated": True}} for i in range(3)], [["x"]]), 3)

    def test_input_race_and_head_race_are_blocked(self):
        path = self.root / "docs/data/latest.json"
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(p.GateError, "Inputs changed"):
            p.build(self.root, self.bundle(), self.context, self.at)
        self.context = p.prepare(self.root, self.at)
        with patch.object(p, "head", return_value="b" * 40):
            with self.assertRaisesRegex(p.GateError, "Branch head changed"):
                p.build(self.root, self.bundle(), self.context, self.at)

    def test_duplicate_cycle_and_failure_retry(self):
        path = self.root / "runs/2026-10-11.json"
        path.parent.mkdir()
        path.write_bytes(p.encoded({"status": "failed_data", "attempt": 1}))
        self.assertFalse(p.prepare(self.root, self.at)["ready"])
        self.assertEqual(p.prepare(self.root, self.at, retry_failed=True)["attempt"], 2)
        path.write_bytes(p.encoded({"status": "validated_release", "attempt": 1}))
        self.assertFalse(p.prepare(self.root, self.at, retry_failed=True)["ready"])

    def test_pending_notification_blocks_new_release(self):
        path = self.root / "feishu_outbox/pending.json"
        path.parent.mkdir()
        path.write_text("{}")
        with self.assertRaisesRegex(p.GateError, "Pending notification"):
            p.prepare(self.root, self.at)

    def test_overdue_debt_reconciliation_is_warning_not_stale(self):
        b = self.bundle()
        b["debt_review"]["full_reconciliation"] = False
        b["debt_ledger"]["last_full_recon"] = "2026-09-06"
        files = p.build(self.root, b, self.context, self.at)
        run = files["runs/2026-10-11.json"]
        self.assertEqual(run["status"], "validated_release")
        self.assertEqual(run["debt_reconciliation_overdue_days"], 7)
        self.assertNotIn("debt_capex_ratio", run["stale_ids"])
        text = json.dumps(files["feishu_outbox/2026-10-11.json"], ensure_ascii=False)
        self.assertIn("债务完整对账逾期 7 天", text)

    def current(self, bundle, key):
        item = next(i for i in bundle["indicators"] if i["id"] == key)
        evidence = bundle["evidence"][key]
        evidence["kind"] = "current"
        evidence["raw"].update(latest_release_date=item["as_of"], next_expected="尚未公布 / not announced")
        return item, evidence

    def test_periodic_current_keeps_prior_fields_and_not_stale(self):
        b = self.bundle()
        prior = next(i for i in self.old["indicators"] if i["id"] == "hyperscaler_capex_yoy")
        self.current(b, prior["id"])
        files = p.build(self.root, b, self.context, self.at)
        actual = next(i for i in files["docs/data/latest.json"]["indicators"] if i["id"] == prior["id"])
        for field in ["value", "status", "as_of", "value_display", "value_display_en"]:
            self.assertEqual(actual.get(field), prior.get(field))
        self.assertFalse(actual["stale"])
        self.assertEqual(files["runs/2026-10-11.json"]["freshness_counts"], {"new": 24, "current": 1, "stale": 0})
        self.assertIn("new 24 / current 1 / stale 0", json.dumps(files["feishu_outbox/2026-10-11.json"], ensure_ascii=False))

    def test_current_cannot_change_prior_observation_or_display(self):
        for field, value in [("value", 79), ("status", "green"), ("as_of", "2026-10-11"),
                             ("value_display", "synthetic different"), ("value_display_en", "different")]:
            with self.subTest(field=field):
                b = self.bundle()
                item, _ = self.current(b, "hyperscaler_capex_yoy")
                item[field] = value
                with self.assertRaisesRegex(p.GateError, f"current changed {field}"):
                    p.build(self.root, b, self.context, self.at)

    def test_current_age_limits_include_boundary_and_survey_exception(self):
        for key, maximum in [("hyperscaler_capex_yoy", 120), ("enterprise_deploy", 200)]:
            for age in [maximum, maximum + 1]:
                with self.subTest(key=key, age=age):
                    prior = copy.deepcopy(self.old)
                    prior_item = next(i for i in prior["indicators"] if i["id"] == key)
                    prior_item["as_of"] = (self.at - timedelta(days=age)).date().isoformat()
                    (self.root / "docs/data/latest.json").write_bytes(p.encoded(prior))
                    self.context = p.prepare(self.root, self.at)
                    b = self.bundle()
                    item, ev = self.current(b, key)
                    item["as_of"] = prior_item["as_of"]
                    ev["raw"]["latest_release_date"] = prior_item["as_of"]
                    if age == maximum:
                        p.build(self.root, b, self.context, self.at)
                    else:
                        with self.assertRaisesRegex(p.GateError, "exceeds .*maximum age"):
                            p.build(self.root, b, self.context, self.at)

    def test_live_and_scan_do_not_allow_current(self):
        for key in ["cape", "accounting_events"]:
            b = self.bundle()
            self.current(b, key)
            with self.assertRaisesRegex(p.GateError, "current is allowed only for periodic"):
                p.build(self.root, b, self.context, self.at)

    def test_current_requires_opened_url_metadata_and_successful_check(self):
        for missing in ["urls", "latest_release_date", "next_expected"]:
            with self.subTest(missing=missing):
                b = self.bundle()
                _, ev = self.current(b, "hyperscaler_capex_yoy")
                if missing == "urls":
                    ev["urls"] = []
                else:
                    ev["raw"].pop(missing)
                with self.assertRaises(p.GateError):
                    p.build(self.root, b, self.context, self.at)
        b = self.bundle()
        item, ev = self.current(b, "hyperscaler_capex_yoy")
        item["stale"] = True
        with self.assertRaisesRegex(p.GateError, "current must have stale=false"):
            p.build(self.root, b, self.context, self.at)
        item["stale"] = False
        ev["raw"]["source_failed"] = True
        with self.assertRaisesRegex(p.GateError, "failed source check must be stale"):
            p.build(self.root, b, self.context, self.at)

    def test_scan_empty_events_can_be_fresh(self):
        b = self.bundle()
        ev = b["evidence"]["accounting_events"]
        self.assertEqual(ev["raw"]["events"], [])
        files = p.build(self.root, b, self.context, self.at)
        item = next(i for i in files["docs/data/latest.json"]["indicators"] if i["id"] == "accounting_events")
        self.assertFalse(item["stale"])
        self.assertEqual(item["as_of"], self.context["as_of_date"])

    def test_scan_needs_recorded_window_queries_sources_events(self):
        for field in ["window", "queries", "sources_checked", "events"]:
            with self.subTest(field=field):
                b = self.bundle()
                b["evidence"]["accounting_events"]["raw"].pop(field)
                with self.assertRaises(p.GateError):
                    p.build(self.root, b, self.context, self.at)

    def test_scan_failure_cannot_be_reported_as_empty_fresh_observation(self):
        for field in ["source_failed", "tool_failed", "fetch_failed", "search_failed"]:
            with self.subTest(field=field):
                b = self.bundle()
                b["evidence"]["accounting_events"]["raw"][field] = True
                with self.assertRaises(p.GateError):
                    p.build(self.root, b, self.context, self.at)
        b = self.bundle()
        b["evidence"]["accounting_events"]["raw"]["sources_checked"] = [{"url": "https://example.test/synthetic", "status": "error"}]
        with self.assertRaisesRegex(p.GateError, "failed/incomplete scan source must be stale"):
            p.build(self.root, b, self.context, self.at)

    def test_failure_outbox_counts_current_and_shows_debt_overdue(self):
        b = self.bundle(6)
        self.current(b, "cloud_rpo_growth")
        files = p.build(self.root, b, self.context, self.at)
        self.assertEqual(files["runs/2026-10-11.json"]["freshness_counts"], {"new": 18, "current": 1, "stale": 6})
        text = files["feishu_outbox/2026-10-11.json"]["content"]["text"]
        self.assertIn("new 18 / current 1 / stale 6", text)
        self.assertIn("债务完整对账逾期 7 天", text)

    def test_debt_weekly_search_and_all_in_numerator_still_required(self):
        for missing in ["searched_urls", "weekly_search_note"]:
            b = self.bundle()
            b["debt_review"].pop(missing)
            with self.assertRaisesRegex(p.GateError, "Weekly debt search evidence required"):
                p.build(self.root, b, self.context, self.at)
        b = self.bundle()
        b["debt_ledger"]["ms_anchor"]["numerator_usd_b"] = 100
        with self.assertRaisesRegex(p.GateError, "Debt ratio inconsistent with all-in anchor"):
            p.build(self.root, b, self.context, self.at)

    def test_unreconciled_debt_cannot_advance_reconciliation_date(self):
        b = self.bundle()
        b["debt_review"]["full_reconciliation"] = False
        with self.assertRaisesRegex(p.GateError, "Cannot advance unreconciled date"):
            p.build(self.root, b, self.context, self.at)

    def test_numeric_threshold_mismatch_is_blocked(self):
        b = self.bundle()
        b["indicators"][0]["status"] = "green"
        with self.assertRaisesRegex(p.GateError, "status contradicts threshold"):
            p.build(self.root, b, self.context, self.at)

    def test_schedule_is_sunday_utc_not_a_sliding_seven_day_gate(self):
        self.assertEqual(p.scheduled_cycle(datetime(2026, 10, 11, 22, 59, tzinfo=timezone.utc)), "2026-10-04")
        self.assertEqual(p.scheduled_cycle(datetime(2026, 10, 12, 1, tzinfo=timezone.utc)), "2026-10-11")

    def test_hysteresis_requires_two_lower_base_periods(self):
        specs, hist = p.definitions(self.root)
        indicators = copy.deepcopy(self.old["indicators"])
        for i in indicators:
            i["status"] = "green"
        old = copy.deepcopy(self.old)
        old["summary"].update(red_pct=40, verdict_label="高风险预警")
        summary, reasons = p.aggregate(indicators, old, specs, hist)
        self.assertEqual(summary["verdict_label"], "高风险预警")
        self.assertIn("downgrade_hysteresis", reasons)
        old["summary"]["red_pct"] = 20
        summary, _ = p.aggregate(indicators, old, specs, hist)
        self.assertEqual(summary["verdict_label"], "观察期")

    def test_cli_release_check_detects_tampering(self):
        context_path, bundle_path = self.root / "context.json", self.root / "bundle.json"
        context_path.write_bytes(p.encoded(self.context))
        bundle_path.write_bytes(p.encoded(self.bundle(5)))
        release = self.root / "release"
        base_args = ["pipeline.py", "--root", str(self.root)]
        flags = ["--context", str(context_path), "--bundle", str(bundle_path), "--release", str(release)]
        with patch.object(p, "now", return_value=self.at), contextlib.redirect_stdout(io.StringIO()):
            for command in ["build", "check"]:
                with patch("sys.argv", base_args + [command] + flags):
                    p.main()
            path = release / "docs/data/latest.json"
            snapshot = p.read(path)
            snapshot["issue_number"] = 999
            path.write_bytes(p.encoded(snapshot))
            with patch("sys.argv", base_args + ["check"] + flags):
                with self.assertRaisesRegex(p.GateError, "Release altered after validation"):
                    p.main()

    def test_duplicate_debt_detected_even_if_inserted_before_old_deal(self):
        b = self.bundle()
        duplicate = copy.deepcopy(b["debt_ledger"]["deals"][-1])
        duplicate["date"] = "2026-09-23"
        b["debt_ledger"]["deals"].insert(0, duplicate)
        with self.assertRaisesRegex(p.GateError, "Possible duplicate debt deal"):
            p.build(self.root, b, self.context, self.at)


if __name__ == "__main__":
    unittest.main()
