#!/usr/bin/env python3
"""Portable, stdlib-only quality gates and release assembly. Never calls a model or sends messages."""
import argparse
import copy
import hashlib
import json
import math
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
POINTS = {"green": 0, "yellow": 1, "red": 2}
VERDICTS = [("观察期", "Observation"), ("中度警戒", "Moderate Caution"),
            ("高风险预警", "High Risk Alert"), ("系统性顶部信号", "Systemic Top Signal")]
CATEGORIES = {"Valuation": ("valuation", "估值"), "Capital": ("capital", "资金面"),
              "Market Structure": ("market_structure", "市场结构"), "Credit": ("credit", "信用"),
              "Fundamentals": ("fundamentals", "基本面"), "Macro & Sentiment": ("macro", "宏观与情绪")}
PERIODS = [("1999-06", "互联网泡沫顶前 9 个月", "9 months before dot-com top"),
           ("2000-02", "互联网泡沫顶前 1 个月", "1 month before dot-com top"),
           ("2007-10", "金融危机股市顶", "GFC equity top"),
           ("2021-11", "成长股/SPAC 顶", "Growth/SPAC top")]
INPUTS = ["INDICATORS.md", "ROUTINE_PROMPT.md", "automation/task.json", "scripts/pipeline.py",
          "docs/data/latest.json", "docs/data/debt_ledger.json", "docs/data/raw_history.json",
          "docs/data/prefetch/latest.json", "docs/data/nvda_commitments.json", "docs/data/arr_ledger.json"]
LEDGERS = {"nvda_commitments": ("docs/data/nvda_commitments.json", "entries"),
           "arr_ledger": ("docs/data/arr_ledger.json", "observations")}


class GateError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise GateError(message)


def read(path):
    return json.loads(Path(path).read_text())


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def timestamp(text):
    result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    need(result.tzinfo is not None, "Timestamp must include timezone")
    return result.astimezone(UTC)


def now():
    return datetime.now(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def head(root):
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def fingerprints(root):
    return {p: digest((root / p).read_bytes()) if (root / p).exists() else None for p in INPUTS}


def structural_active(config, cycle):
    return cycle >= config["structural_contracts"]["effective_cycle"]


def valid_url(value):
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def source_record(record, as_of, label):
    need(valid_url(record.get("source_url")), f"{label}: source URL required")
    need(record.get("source_date") and record["source_date"] <= as_of, f"{label}: valid nonfuture source date required")
    date.fromisoformat(record["source_date"])
    need(record.get("accessed_at"), f"{label}: actual source access timestamp required")
    need(timestamp(record["accessed_at"]).date() <= date.fromisoformat(as_of), f"{label}: future access timestamp")


def ledger_candidate(root, bundle, key):
    path, records_key = LEDGERS[key]
    need((root / path).exists(), f"Missing persistent ledger: {path}")
    old = read(root / path)
    new = copy.deepcopy(bundle.get(key, old))
    need(new.get("schema_version") == 1 and isinstance(new.get(records_key), list), f"{key}: invalid ledger structure")
    records = new[records_key]
    need(all(isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"] for r in records), f"{key}: stable record IDs required")
    need(len({r["id"] for r in records}) == len(records), f"{key}: duplicate record ID")
    by_id = {r["id"]: r for r in records}
    for record in old[records_key]:
        need(by_id.get(record["id"]) == record, f"{key}: historical record changed or removed; append a sourced superseding record")
    if key == "arr_ledger":
        confirmations = {r.get("id"): r for r in new.get("basis_confirmations", [])}
        need(len(confirmations) == len(new.get("basis_confirmations", [])), "ARR: duplicate basis confirmation ID")
        for confirmation in old.get("basis_confirmations", []):
            need(confirmations.get(confirmation["id"]) == confirmation, "ARR: historical basis confirmation changed or removed")
    for field in ("excluded_reports", "exclusions"):
        need(all(record in new.get(field, []) for record in old.get(field, [])), f"{key}: historical exclusion audit removed")
    return new


def active_records(records, label):
    ids = {r["id"] for r in records}
    superseded = set()
    links = {}
    for record in records:
        prior = record.get("supersedes", [])
        prior = [prior] if isinstance(prior, str) else prior
        need(isinstance(prior, list) and all(p in ids and p != record["id"] for p in prior), f"{label}: invalid supersedes reference")
        need(not (superseded & set(prior)), f"{label}: one record superseded more than once")
        superseded.update(prior)
        links[record["id"]] = prior
    def visit(key, trail):
        need(key not in trail, f"{label}: cyclic supersedes references")
        for prior in links[key]:
            visit(prior, trail | {key})
    for key in links:
        visit(key, set())
    return [r for r in records if r["id"] not in superseded]


def nvda_totals(ledger, as_of):
    need(ledger.get("basis") == "signed_customer_financing_including_guarantees", "NVDA: signed financing basis required")
    coverage = ledger.get("coverage")
    need(isinstance(coverage, dict) and isinstance(coverage.get("complete"), bool), "NVDA: coverage disclosure required")
    active = active_records(ledger["entries"], "NVDA")
    total, unresolved = 0.0, []
    for entry in ledger["entries"]:
        label = f"NVDA {entry['id']}"
        source_record(entry, as_of, label)
        need(entry.get("customer") and entry.get("notes"), f"{label}: customer and signed/draw conditions required")
        need(entry.get("instrument") in ("equity", "loan", "convertible", "financing_guarantee"), f"{label}: unsupported financing instrument")
        need(entry.get("status") in ("signed", "conditional", "drawn"), f"{label}: invalid signing status")
        date.fromisoformat(entry["announcement_date"])
        need(entry["announcement_date"] <= as_of, f"{label}: future announcement")
        signed, ceiling = entry.get("signed_amount_usd_bn"), entry.get("amount_usd_bn")
        need(signed is None or numeric(signed) and signed >= 0, f"{label}: invalid signed amount")
        need(ceiling is None or numeric(ceiling) and ceiling >= 0, f"{label}: invalid announced ceiling")
        need(signed is None or ceiling is None or signed <= ceiling + 0.000001, f"{label}: signed amount exceeds announced ceiling")
        if entry in active and not entry.get("included_in"):
            if signed is None and entry["status"] in ("signed", "drawn"):
                unresolved.append(entry["id"])
            elif signed is not None:
                total += signed
    active_by_id = {e["id"]: e for e in active}
    for parent in active:
        children = [e for e in active if e.get("included_in") == parent["id"]]
        if children:
            need(not parent.get("included_in") and numeric(parent.get("signed_amount_usd_bn")), "NVDA: included detail requires one active signed aggregate")
            need(all(e["instrument"] == parent["instrument"] and numeric(e.get("signed_amount_usd_bn")) for e in children), "NVDA: included detail must match aggregate instrument and known signed amounts")
            need(sum(e["signed_amount_usd_bn"] for e in children) <= parent["signed_amount_usd_bn"] + 0.000001, "NVDA: included details exceed signed aggregate")
    need(all(not e.get("included_in") or e["included_in"] in active_by_id and e["included_in"] != e["id"] for e in active), "NVDA: missing/self included aggregate reference")
    need(not coverage["complete"] or not unresolved, "NVDA: undisclosed signed amounts cannot claim complete coverage")
    declared_unresolved = coverage.get("unresolved_ids", [])
    need(isinstance(declared_unresolved, list) and set(unresolved) <= set(declared_unresolved), "NVDA: missing unresolved signing disclosure")
    ltm = ledger.get("ltm_revenue", {})
    quarters = ltm.get("quarters")
    need(isinstance(quarters, list) and len(quarters) == 4, "NVDA: exactly four actual revenue quarters required")
    need(len({q.get("fiscal_period") for q in quarters}) == 4, "NVDA: duplicate fiscal quarter")
    ends = []
    for quarter in quarters:
        need(valid_url(quarter.get("source_url")) and quarter.get("source_date") <= as_of, "NVDA: quarter filing source required")
        date.fromisoformat(quarter["source_date"])
        end = date.fromisoformat(quarter["period_end"])
        need(end.isoformat() <= as_of and numeric(quarter.get("revenue_usd_bn")) and quarter["revenue_usd_bn"] > 0, "NVDA: invalid actual quarterly revenue")
        ends.append(end)
    ends.sort()
    need(all(75 <= (b - a).days <= 110 for a, b in zip(ends, ends[1:])), "NVDA: LTM quarters must be consecutive")
    need(ltm.get("as_of") == ends[-1].isoformat(), "NVDA: LTM as_of must be latest quarter end")
    revenue = sum(q["revenue_usd_bn"] for q in quarters)
    need(numeric(ltm.get("revenue_usd_bn")) and abs(ltm["revenue_usd_bn"] - revenue) < 0.011, "NVDA: LTM revenue sum mismatch")
    need(numeric(ledger.get("total_signed_usd_bn")) and abs(ledger["total_signed_usd_bn"] - total) < 0.011, "NVDA: signed numerator sum mismatch")
    ratio = total / revenue * 100
    need(numeric(ledger.get("ratio_pct")) and abs(ledger["ratio_pct"] - ratio) <= 0.011, "NVDA: signed/LTM ratio mismatch")
    signing_dates = []
    for entry in active:
        if entry["status"] in ("signed", "drawn") or (entry.get("signed_amount_usd_bn") or 0) > 0:
            observed = entry.get("drawn_date") if entry["status"] == "drawn" else None
            observed = observed or entry.get("signed_date") or entry["announcement_date"]
            date.fromisoformat(observed)
            need(observed <= as_of, "NVDA: future signing/draw date")
            signing_dates.append(observed)
    return {"numerator_signed_usd_bn": round(total, 6), "ltm_revenue_usd_bn": round(revenue, 6),
            "ratio_pct": round(ratio, 6), "coverage_complete": coverage["complete"], "unresolved_ids": unresolved,
            "metric_as_of": max([ltm["as_of"]] + signing_dates)}


def subtract_months(value, months):
    """Calendar cutoffs; observations retain their real dates, never interpolated."""
    import calendar
    year, month = divmod(value.year * 12 + value.month - 1 - months, 12)
    month += 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def arr_calculations(ledger, as_of):
    points = active_records(ledger["observations"], "ARR")
    confirmations = {r["id"]: r for r in ledger.get("basis_confirmations", [])}
    need(len(confirmations) == len(ledger.get("basis_confirmations", [])), "ARR: duplicate basis confirmation ID")
    for confirmation in confirmations.values():
        source_record(confirmation, as_of, "ARR basis confirmation")
        need(confirmation.get("company") in ("OpenAI", "Anthropic") and confirmation.get("basis") in ("gross", "net"), "ARR: invalid sourced basis confirmation")
        need(confirmation.get("reading") and confirmation.get("application"), "ARR: retrospective basis confirmation reading/application required")
    for point in ledger["observations"]:
        label = f"ARR {point['id']}"
        source_record(point, as_of, label)
        need(point.get("company") in ("OpenAI", "Anthropic"), f"{label}: unsupported company")
        need(point.get("basis") in ("gross", "net", "unspecified"), f"{label}: accounting basis required")
        need(point.get("as_of_precision") in ("day", "month_end", "month", "early_month", "week"), f"{label}: date precision required")
        need(point.get("reported_qualifier") in ("exact", "about", "more_than", "nearly"), f"{label}: reported qualifier required")
        need(point.get("source_type") in ("company", "mainstream_media"), f"{label}: company or mainstream media source required")
        need(point.get("raw_reading") and point.get("notes"), f"{label}: actual reading and basis notes required")
        need(point.get("is_forecast") is False, f"{label}: forecasts cannot enter actual ARR ledger")
        need(numeric(point.get("amount_usd_bn")) and point["amount_usd_bn"] > 0, f"{label}: actual run-rate required")
        date.fromisoformat(point["as_of"])
        need(point["as_of"] <= point["source_date"] <= as_of, f"{label}: future/forecast observation date")
        if point.get("basis_confirmation_id"):
            confirmation = confirmations.get(point["basis_confirmation_id"])
            need(confirmation and confirmation["company"] == point["company"] and confirmation["basis"] == point["basis"], f"{label}: missing or mismatched accounting-basis confirmation")
        if "observed_interval" in point:
            interval = point["observed_interval"]
            need(isinstance(interval, dict) and interval.get("start") and interval.get("end"), f"{label}: invalid reported observation interval")
            start, end = (date.fromisoformat(interval[k]) for k in ("start", "end"))
            need(start <= end and end.isoformat() == point["as_of"], f"{label}: retain conservative upper bound of uncertain date")
    unique = [(p["company"], p["as_of"], p["basis"]) for p in points]
    need(len(set(unique)) == len(unique), "ARR: duplicate company/date/basis point")
    results, excluded = {}, {}
    for company in ("OpenAI", "Anthropic"):
        candidates = []
        for basis in ("gross", "net"):
            series = sorted((p for p in points if p["company"] == company and p["basis"] == basis), key=lambda p: p["as_of"])
            if not series:
                continue
            latest = series[-1]
            end = date.fromisoformat(latest["as_of"])
            cutoff3, cutoff6 = subtract_months(end, 3), subtract_months(end, 6)
            anchors = [next((p for p in reversed(series) if p["as_of"] <= cutoff.isoformat()), None) for cutoff in (cutoff3, cutoff6)]
            if any(p is None for p in anchors):
                continue
            previous, earlier = anchors
            lags = [(cutoff3 - date.fromisoformat(previous["as_of"])).days, (cutoff6 - date.fromisoformat(earlier["as_of"])).days]
            if any(lag > 31 for lag in lags) or (date.fromisoformat(as_of) - end).days > 120:
                continue
            need(earlier["as_of"] < previous["as_of"] < latest["as_of"], "ARR: distinct actual anchors required")
            recent = (latest["amount_usd_bn"] / previous["amount_usd_bn"] - 1) * 100
            prior = (previous["amount_usd_bn"] / earlier["amount_usd_bn"] - 1) * 100
            candidates.append({"basis": basis, "latest": latest, "previous": previous, "earlier": earlier,
                               "cutoff_3m": cutoff3.isoformat(), "cutoff_6m": cutoff6.isoformat(),
                               "anchor_lag_days": lags,
                               "recent_growth_pct": round(recent, 6), "prior_growth_pct": round(prior, 6),
                               "acceleration_pp": round(recent - prior, 6),
                               "reported_point_estimate": any(p["reported_qualifier"] != "exact" for p in (latest, previous, earlier))})
        if candidates:
            results[company] = max(candidates, key=lambda c: c["latest"]["as_of"])
        else:
            excluded[company] = "Fewer than three dated actual observations in one confirmed gross/net basis at the calendar cutoffs"
    return {"companies": results, "excluded_companies": excluded}


def enterprise_status(raw, value):
    need(raw.get("basis") == "kpmg_significant_workforce_adoption", "enterprise_deploy: KPMG significant workforce adoption basis required")
    current, previous = raw.get("current_pct"), raw.get("previous_pct")
    need(all(numeric(v) and 0 <= v <= 100 for v in (current, previous)), "enterprise_deploy: actual current/prior percentage required")
    quarters = []
    for key in ("current_quarter", "previous_quarter"):
        match = re.fullmatch(r"(\d{4})-Q([1-4])", str(raw.get(key)))
        need(match is not None, "enterprise_deploy: actual quarter metadata required")
        quarters.append(int(match[1]) * 4 + int(match[2]))
    need(quarters[0] - quarters[1] == 1, "enterprise_deploy: compare adjacent quarters")
    change = round(current - previous, 10)
    need(numeric(raw.get("change_pp")) and abs(raw["change_pp"] - change) < 0.001, "enterprise_deploy: quarterly change mismatch")
    need(numeric(value) and abs(value - current) < 0.001, "enterprise_deploy: level must be reported KPMG percentage")
    return "green" if change >= 3 else "red" if change < -3 else "yellow"


def dc_credit_status(raw):
    red = {"default", "force_majeure", "downgrade", "issuance_withdrawal", "forced_repricing"}
    yellow = {"issuance_delay", "terms_tightening"}
    states = []
    for event in raw["events"]:
        kind = event.get("event_type")
        need(kind in red | yellow | {"spread_widening", "smooth_issuance"}, "dc_abs_spread: classified credit event required")
        need(isinstance(event.get("confirmed"), bool), "dc_abs_spread: confirmation status required")
        if kind == "spread_widening":
            need(numeric(event.get("spread_change_bps")), "dc_abs_spread: reported spread change in bps required")
        if not event["confirmed"]:
            continue
        states.append("red" if kind in red or kind == "spread_widening" and event["spread_change_bps"] >= 50 else "yellow" if kind in yellow else "green")
    return "red" if "red" in states else "yellow" if "yellow" in states else "green"


def structural_status(key, item, raw, ledgers, context):
    """Derive the new contracts from source readings and persistent ledgers."""
    def computed(name, value):
        need(name not in raw or raw[name] == value, f"{key}: supplied {name} disagrees with authoritative ledger")
        raw[name] = value
    if key == "enterprise_deploy":
        publication = raw.get("publication_date")
        need(isinstance(publication, str) and publication <= context["as_of_date"], "enterprise_deploy: actual publication date required")
        date.fromisoformat(publication)
        need(item["as_of"] == publication, "enterprise_deploy: as_of must be actual KPMG publication date")
        if "latest_release_date" in raw:
            need(raw["latest_release_date"] == publication, "enterprise_deploy: current release date contradicts actual publication")
        status = enterprise_status(raw, item["value"])
        year, quarter = (int(v) for v in raw["current_quarter"].replace("Q", "").split("-"))
        checked_date = date.fromisoformat(context["as_of_date"])
        need(year * 4 + quarter <= checked_date.year * 4 + (checked_date.month - 1) // 3 + 1, "enterprise_deploy: future survey quarter")
        return status
    if key == "dc_abs_spread":
        need(raw.get("basis") == "dc_abs_project_finance_credit_status", "dc_abs_spread: ABS/project-finance credit basis required")
        start, end = (date.fromisoformat(raw["window"][k]) for k in ("start", "end"))
        need((end - start).days == 90, "dc_abs_spread: complete 90-day scan window required")
        return dc_credit_status(raw)
    if key == "nvda_invest_revenue":
        ledger = ledgers["nvda_commitments"]
        totals = nvda_totals(ledger, context["as_of_date"])
        computed("basis", ledger["basis"])
        computed("numerator_signed_usd_bn", totals["numerator_signed_usd_bn"])
        computed("ltm_revenue_usd_bn", totals["ltm_revenue_usd_bn"])
        computed("nvda_coverage", {"complete": totals["coverage_complete"], "unresolved_ids": totals["unresolved_ids"]})
        computed("nvda_active_commitments", [{k: e.get(k) for k in ("id", "instrument", "status", "signed_amount_usd_bn", "included_in")} for e in sorted(active_records(ledger["entries"], "NVDA"), key=lambda e: e["id"])])
        computed("ltm_period_end", ledger["ltm_revenue"]["as_of"])
        need(numeric(item["value"]) and abs(item["value"] - totals["ratio_pct"]) <= 0.51, "nvda_invest_revenue: value disagrees with signed commitments/LTM")
        need(item["as_of"] == totals["metric_as_of"], "nvda_invest_revenue: as_of must be latest actual signing/draw or revenue-quarter date")
        if not totals["coverage_complete"]:
            need("下限" in item["note"] and "lower bound" in item["note_en"].lower(), "NVDA: incomplete coverage requires bilingual lower-bound disclosure")
            need(totals["ratio_pct"] >= 30, "NVDA: incomplete lower bound below red cannot establish an exact green/yellow status; mark stale")
        return "red" if totals["ratio_pct"] >= 30 else "yellow" if totals["ratio_pct"] >= 15 else "green"
    if key == "arr_2nd_deriv":
        calculations = arr_calculations(ledgers["arr_ledger"], context["as_of_date"])
        need(calculations["companies"], "arr_2nd_deriv: no same-basis comparable three-anchor disclosed series; mark stale")
        computed("basis", "same_basis_disclosed_series_3m_vs_prior3m")
        computed("arr_calculations", calculations)
        computed("arr_basis_signature", {company: c["basis"] for company, c in calculations["companies"].items()})
        computed("arr_anchor_ids", {company: [c[p]["id"] for p in ("latest", "previous", "earlier")] for company, c in calculations["companies"].items()})
        need(item["as_of"] == max(c["latest"]["as_of"] for c in calculations["companies"].values()), "arr_2nd_deriv: as_of must be latest actual calculated-series observation date")
        for company in calculations["excluded_companies"]:
            need(company.lower() in item["note"].lower() and company.lower() in item["note_en"].lower(), "ARR: excluded company must be named in both notes")
        if any(any(c["anchor_lag_days"]) for c in calculations["companies"].values()):
            need(any(term in item["note"] for term in ("披露序列", "披露点")) and any(term in item["note_en"].lower() for term in ("disclosed-series", "reported observations")), "ARR: nonzero anchor lag requires disclosed-series qualification")
        if any(c["reported_point_estimate"] for c in calculations["companies"].values()):
            need(any(term in item["note"] for term in ("估算", "约", "披露点")) and any(term in item["note_en"].lower() for term in ("estimate", "approx", "reported observations")), "ARR: approximate source readings require point-estimate qualification")
        directions = [c["acceleration_pp"] for c in calculations["companies"].values()]
        return "green" if all(d > 0 for d in directions) else "red" if all(d < 0 for d in directions) else "yellow"
    return None


STRUCTURAL_CANONICAL = {
    "enterprise_deploy": ("basis", "current_pct", "previous_pct", "current_quarter", "previous_quarter", "change_pp", "publication_date"),
    "nvda_invest_revenue": ("basis", "numerator_signed_usd_bn", "ltm_revenue_usd_bn", "nvda_active_commitments", "ltm_period_end"),
    "arr_2nd_deriv": ("basis", "arr_anchor_ids", "arr_basis_signature"),
    "dc_abs_spread": ("basis",),
}
STRUCTURAL_LABELS = {
    "enterprise_deploy": ("企业显著员工 AI 采用率", "KPMG significant workforce adoption",
                          "较上季 ≥+3pt 绿 / −3pt ≤变化<+3pt 黄 / 下降>3pt 红",
                          "QoQ change ≥+3pt green / −3pt ≤ change <+3pt yellow / decline >3pt red"),
    "dc_abs_spread": ("数据中心 ABS/项目融资信用状态", "Data-center ABS/project-finance credit status",
                      "90 天内确认信用事件或利差走阔≥50bp 红 / 延期、条款收紧等压力 黄 / 发行顺畅、无事件 绿",
                      "90d confirmed credit event or spread widening ≥50bp red / delays or tighter terms yellow / smooth issuance and no events green"),
}


def definitions(root):
    text = (root / "INDICATORS.md").read_text()
    result, category, current = {}, None, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = None
            category = next((v for k, v in CATEGORIES.items() if k in line), None)
        m = re.match(r"### `([a-z0-9_]+)`", line)
        if m:
            need(category is not None, "Unrecognized indicator category")
            current = {"category": category[0], "category_zh": category[1]}
            need(m[1] not in result, "Duplicate indicator definition")
            result[m[1]] = current
        if current is not None:
            for field in ["Axis", "Direction", "Cadence"]:
                m = re.search(r"\*\*" + field + r"\*\*:\s*([a-z_]+)", line)
                if m:
                    current[field.lower()] = m[1]
            m = re.search(r"\*\*Thresholds\*\*:\s*red=([-\d.]+),\s*yellow=([-\d.]+)", line)
            if m:
                current["thresholds"] = [float(m[1]), float(m[2])]
            m = re.search(r"\*\*Max age\*\*:\s*(\d+)\s*days", line)
            if m:
                current["max_age_days"] = int(m[1])
    for key, spec in result.items():
        need(spec.get("axis") in ("stage", "trigger") and "direction" in spec, f"Incomplete definition: {key}")
        need(spec.get("cadence") in ("live", "periodic", "scan"), f"Missing or invalid cadence: {key}")
        if spec["cadence"] == "periodic":
            limit = 200 if key == "enterprise_deploy" else 120
            spec.setdefault("max_age_days", limit)
            need(0 < spec["max_age_days"] <= limit, f"{key}: periodic age limit exceeds contract")
    need(result, "No indicators parsed")
    historical = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) == 5:
            m = re.match(r"([a-z0-9_]+)", cells[0])
            if m and m[1] in result and all(c in ("R", "Y", "G", "—") for c in cells[1:]):
                historical[m[1]] = cells[1:]
    need(set(historical) == set(result), "Historical calibration IDs must match definitions")
    return result, historical


def scheduled_cycle(at):
    sunday = (at - timedelta(days=(at.weekday() + 1) % 7)).replace(hour=23, minute=0, second=0, microsecond=0)
    if at < sunday:
        sunday -= timedelta(days=7)
    return sunday.date().isoformat()


def prefetch_source(root, config, key, at):
    mapping = config["prefetch"].get(key)
    if not mapping:
        return None
    cache = read(root / "docs/data/prefetch/latest.json")
    try:
        age = (at - timestamp(cache["_meta"]["fetched_at"])).total_seconds()
        source = cache["sources"][mapping["source"]]
        if 0 <= age < config["prefetch_max_age_hours"] * 3600 and source.get("status") == "ok":
            need(isinstance(source.get("data"), dict), f"Malformed prefetch: {key}")
            return source
    except (KeyError, TypeError, ValueError):
        return None
    return None


def prepare(root, at, cycle=None, retry_failed=False):
    cycle = cycle or scheduled_cycle(at)
    need(date.fromisoformat(cycle).weekday() == 6, "Cycle must be the scheduled UTC Sunday date")
    need(cycle <= at.date().isoformat(), "Future cycle cannot be run")
    config = read(root / "automation/task.json")
    latest = read(root / "docs/data/latest.json")
    run_path = root / f"runs/{cycle}.json"
    previous = read(run_path) if run_path.exists() else None
    if latest["as_of_date"] >= cycle or (previous and (previous["status"] == "validated_release" or not retry_failed)):
        return {"ready": False, "reason": "cycle_already_processed", "cycle": cycle}
    pending = list((root / "feishu_outbox").glob("*.json"))
    need(not pending, "Pending notification: inspect relay before creating another release")
    return {"schema_version": 1, "ready": True, "cycle": cycle, "prepared_at": iso(at),
            "as_of_date": at.date().isoformat(), "base_commit": head(root), "inputs": fingerprints(root),
            "attempt": (previous.get("attempt", 0) if previous else 0) + 1,
            "prefetch_usable": {k: bool(prefetch_source(root, config, k, at)) for k in config["prefetch"]}}


def check_context(root, context):
    need(context.get("ready") is True, "Context is not ready")
    need(context["inputs"] == fingerprints(root), "Inputs changed; prepare again against current main")
    need(context["base_commit"] == head(root), "Branch head changed; prepare again")
    cycle = context["cycle"]
    latest = read(root / "docs/data/latest.json")
    need(latest["as_of_date"] < cycle, "Cycle has already been published")
    path = root / f"runs/{cycle}.json"
    if path.exists():
        previous = read(path)
        need(previous["status"] != "validated_release" and context["attempt"] == previous["attempt"] + 1,
             "Duplicate or superseded attempt")
    need(not list((root / "feishu_outbox").glob("*.json")), "Pending outbox must be resolved first")


def base_level(red_pct):
    return 3 if red_pct >= 60 else 2 if red_pct >= 40 else 1 if red_pct >= 25 else 0


def aggregate(indicators, previous, specs, calibration):
    need(len(indicators) == len(specs) and {i["id"] for i in indicators} == set(specs), "Indicator ID mismatch")
    score = {i["id"]: POINTS[i["status"]] for i in indicators}
    n = len(score)
    counts = {color: sum(i["status"] == color for i in indicators) for color in POINTS}
    result = {"total_indicators": n, **{f"{c}_count": v for c, v in counts.items()},
              "red_pct": round(counts["red"] / n * 100, 1),
              "weighted_risk_score": round(sum(score.values()) / n * 50, 1)}
    for axis in ["stage", "trigger"]:
        values = [score[k] for k, v in specs.items() if v["axis"] == axis]
        need(values, f"Empty axis: {axis}")
        result[f"{axis}_score"] = round(sum(values) / len(values) * 50, 1)
    stage, trigger = result["stage_score"], result["trigger_score"]
    s = 0 if stage < 30 else 1 if stage < 50 else 2 if stage < 70 else 3
    t = 0 if trigger < 25 else 1 if trigger < 45 else 2 if trigger < 65 else 3
    result["stage_label"], result["stage_label_en"] = [("早期 Displacement", "Displacement"), ("扩张 Boom", "Boom"), ("亢奋 Euphoria", "Euphoria"), ("极端 Mania", "Mania")][s]
    result["trigger_label"], result["trigger_label_en"] = [("引线未燃", "Fuse Unlit"), ("零星火花", "Sparks"), ("引线点燃", "Fuse Lit"), ("破裂进行中", "Unwinding")][t]
    result["category_scores"] = {}
    for cat in dict.fromkeys(v["category"] for v in specs.values()):
        vals = [score[k] for k, v in specs.items() if v["category"] == cat]
        result["category_scores"][cat] = round(sum(vals) / len(vals) * 50, 1)
    old = {i["id"]: POINTS[i["status"]] for i in previous["indicators"]}
    incomparable = {i["id"] for i in indicators if i.get("basis_changed")}
    delta = [v - old[k] for k, v in score.items() if k in old and k not in incomparable]
    deteriorated, improved = sum(max(x, 0) for x in delta), sum(max(-x, 0) for x in delta)
    result["momentum"] = {"deteriorated": deteriorated, "improved": improved, "net": deteriorated - improved}
    similarity = []
    for j, (period, zh, en) in enumerate(PERIODS):
        matches = [1 - abs(score[k] - {"G": 0, "Y": 1, "R": 2}[v[j]]) / 2 for k, v in calibration.items() if v[j] != "—"]
        similarity.append({"period": period, "label_zh": zh, "label_en": en, "match_pct": round(sum(matches) / len(matches) * 100, 1)})
    result["similarity"] = sorted(similarity, key=lambda x: -x["match_pct"])
    level, reasons = base_level(result["red_pct"]), []
    red_in = lambda cat: sum(score[k] == 2 for k, v in specs.items() if v["category"] == cat)
    if red_in("valuation") >= 2 and red_in("capital") >= 3:
        level = max(level, 2)
        reasons.append("category_resonance")
    if stage >= 60 and trigger >= 50:
        level = max(level, 3 if trigger >= 65 else 2)
        reasons.append("two_axis")
    old_summary = previous["summary"]
    previous_level = next((j for j, labels in enumerate(VERDICTS) if old_summary["verdict_label"] == labels[0]), None)
    need(previous_level is not None, "Unknown previous verdict")
    if level < previous_level and not (base_level(result["red_pct"]) < previous_level and base_level(old_summary["red_pct"]) < previous_level):
        level = previous_level
        reasons.append("downgrade_hysteresis")
    result["verdict_label"], result["verdict_label_en"] = VERDICTS[level]
    return result, reasons


def core_values(raw, aliases):
    result = []
    for group in aliases:
        value = next((raw[k] for k in group if k in raw and numeric(raw[k])), None)
        if value is None:
            return None
        result.append(value)
    return result


def static_weeks(records, aliases):
    def missing(record):
        return record.get("stale", False) or record["raw"].get("fetch_failed", False) or core_values(record["raw"], aliases) is None
    def streak(predicate):
        count = 0
        for record in reversed(records):
            if not predicate(record):
                break
            count += 1
        return count
    last = core_values(records[-1]["raw"], aliases)
    unchanged = streak(lambda r: core_values(r["raw"], aliases) == last) if last is not None else 0
    return max(unchanged, streak(missing), streak(lambda r: r["raw"].get("estimated", False)))


def validate_scan(key, item, evidence, context):
    """A recorded, successful search is an observation; an empty event list is valid."""
    raw = evidence["raw"]
    failed = any(raw.get(k) for k in ("fetch_failed", "source_failed", "tool_failed", "search_failed"))
    unavailable = any(raw.get(k) is False for k in ("search_available", "tool_available", "scan_complete"))
    need(not failed and not unavailable, f"{key}: failed/incomplete scan must be stale")
    window = raw.get("window")
    need(isinstance(window, dict) and window.get("start") and window.get("end"), f"{key}: scan window start/end required")
    start, end = (date.fromisoformat(window[k]) for k in ("start", "end"))
    need(start <= end and window["end"] == item["as_of"] == context["as_of_date"], f"{key}: scan window/date mismatch")
    queries = raw.get("queries")
    need(isinstance(queries, list) and queries and all(isinstance(q, str) and q.strip() for q in queries), f"{key}: recorded scan queries required")
    checked = raw.get("sources_checked")
    need(isinstance(checked, list) and checked, f"{key}: scan sources_checked required")
    for entry in checked:
        url = entry.get("url") if isinstance(entry, dict) else entry
        need(isinstance(url, str) and url.startswith(("https://", "http://")) and url in evidence["urls"], f"{key}: checked scan source must be an opened URL")
        if isinstance(entry, dict):
            need(entry.get("status") == "ok", f"{key}: failed/incomplete scan source must be stale")
    events = raw.get("events")
    need(isinstance(events, list), f"{key}: scan events list required (may be empty)")
    for event in events:
        need(isinstance(event, dict) and isinstance(event.get("what"), str) and event["what"].strip(), f"{key}: scan event description required")
        event_date = date.fromisoformat(event["date"])
        need(start <= event_date <= end, f"{key}: scan event outside search window")
        need(isinstance(event.get("url"), str) and event["url"].startswith(("https://", "http://")) and event["url"] in evidence["urls"], f"{key}: opened scan event URL required")


def freshness_counts(indicators, evidence):
    counts = {"new": 0, "current": 0, "stale": 0}
    for item in indicators:
        state = "stale" if item["stale"] else "current" if evidence[item["id"]]["kind"] == "current" else "new"
        need(item.get("freshness", state) == state, f"{item['id']}: freshness contradicts validated evidence")
        counts[state] += 1
    return counts


def debt_reconciliation_age(root, context, ledger=None):
    ledger = ledger if ledger is not None else read(root / "docs/data/debt_ledger.json")
    interval = read(root / "automation/task.json")["debt_reconciliation"]["interval_days"]
    need(isinstance(interval, int) and not isinstance(interval, bool) and interval > 0, "Invalid debt reconciliation interval")
    age = (date.fromisoformat(context["as_of_date"]) - date.fromisoformat(ledger["last_full_recon"])).days
    need(age >= 0, "Future debt reconciliation date")
    return age, interval


def debt_reconciliation_warning(root, context, ledger=None):
    ledger = ledger if ledger is not None else read(root / "docs/data/debt_ledger.json")
    age, interval = debt_reconciliation_age(root, context, ledger)
    if age >= interval:
        return {"debt_reconciliation_overdue_days": age - interval,
                "message": f"⚠ 债务完整对账逾期 {age - interval} 天（上次 {ledger['last_full_recon']}）；周度增量扫描不替代完整对账"}
    return None


def apply_debt_reconciliation_policy(root, bundle, context):
    """Carry an unreconciled due ratio before scoring and the aggregate stale gate."""
    result = copy.deepcopy(bundle)
    config = read(root / "automation/task.json")
    effective = config["debt_reconciliation"]["stale_if_due_unreconciled_from_cycle"]
    old_ledger = read(root / "docs/data/debt_ledger.json")
    age, interval = debt_reconciliation_age(root, context, old_ledger)
    review = result.get("debt_review", {})
    if context["cycle"] < effective or age < interval or review.get("full_reconciliation") is True:
        return result
    candidate = result.get("debt_ledger", old_ledger)
    need(candidate.get("last_full_recon") == old_ledger["last_full_recon"], "Cannot advance unreconciled date")
    key = "debt_capex_ratio"
    prior = next(i for i in read(root / "docs/data/latest.json")["indicators"] if i["id"] == key)
    item = next(i for i in result["indicators"] if i["id"] == key)
    ev = result["evidence"][key]
    supplied_raw = copy.deepcopy(ev.get("raw", {}))
    already_carried = ev.get("kind") == "carry" and supplied_raw.get("reconciliation_incomplete") is True
    history = read(root / "docs/data/raw_history.json").get(key, [])
    raw = supplied_raw if already_carried else copy.deepcopy(history[-1]["raw"] if history else {})
    if not already_carried:
        raw["attempted_observations"] = supplied_raw
    pending = copy.deepcopy(raw.get("pending_debt_updates", {}))
    changed = pending.get("changed_deals", [])
    for deal in candidate.get("deals", []):
        if deal not in old_ledger["deals"] and deal not in changed:
            changed.append(copy.deepcopy(deal))
    if changed:
        pending["changed_deals"] = changed
    for field in ("ms_anchor", "capex_denominator_usd_b"):
        if field in candidate and candidate[field] != old_ledger.get(field):
            pending["proposed_" + field] = copy.deepcopy(candidate[field])
    if pending:
        raw["pending_debt_updates"] = pending
    for field in ("value", "value_display", "value_display_en", "status", "as_of", "basis"):
        if field in prior:
            item[field] = copy.deepcopy(prior[field])
        else:
            item.pop(field, None)
    overdue = age - interval
    reason = review.get("reconciliation_failure_note") or review.get("reconciliation_note") or "完整对账尚未完成 / full reconciliation not completed"
    raw.update(reconciliation_incomplete=True, last_full_recon=old_ledger["last_full_recon"],
               reconciliation_age_days=age, reconciliation_overdue_days=overdue,
               reconciliation_failure_note=reason)
    raw["fetch_failed"] = bool(supplied_raw.get("fetch_failed"))
    item.update(stale=True, freshness="stale",
                note=f"完整债务对账逾期 {overdue} 天仍未完成；沿用 {prior['as_of']} 的已发布值，本期周度线索保留待对账。",
                note_en=f"Full debt reconciliation remains incomplete, {overdue} days overdue; carrying the published value as of {prior['as_of']}. This week's leads remain pending reconciliation.")
    ev.update(kind="carry", raw=raw, rationale=f"Full debt reconciliation incomplete ({overdue} days overdue): {reason}")
    result["debt_ledger"] = copy.deepcopy(old_ledger)
    if isinstance(result.get("wow_changes"), list):
        suppressed = [c for c in result["wow_changes"] if isinstance(c, dict) and c.get("indicator_id") == key]
        if suppressed:
            raw["suppressed_wow_changes"] = suppressed
        result["wow_changes"] = [c for c in result["wow_changes"] if c not in suppressed]
    return result


def validate_indicators(root, bundle, context, at):
    specs, calibration = definitions(root)
    config = read(root / "automation/task.json")
    previous = read(root / "docs/data/latest.json")
    old = {i["id"]: i for i in previous["indicators"]}
    indicators = copy.deepcopy(bundle["indicators"])
    need(len(indicators) == len(specs) and {i["id"] for i in indicators} == set(specs), "Indicator ID mismatch")
    need(set(bundle["evidence"]) == set(specs), "Evidence IDs must match indicators")
    history = read(root / "docs/data/raw_history.json")
    active = structural_active(config, context["cycle"])
    ledgers = {k: ledger_candidate(root, bundle, k) for k in LEDGERS} if active else {}
    for item in indicators:
        key = item["id"]
        spec, ev = specs[key], bundle["evidence"][key]
        for field in ["name_en", "name_zh", "value_display", "threshold_text", "threshold_text_en", "note", "note_en", "source_name", "source_url"]:
            need(isinstance(item.get(field), str) and item[field].strip(), f"{key}: missing {field}")
        need(isinstance(item.get("stale"), bool) and item.get("status") in POINTS, f"{key}: invalid stale/status")
        need(isinstance(item.get("value"), str) or numeric(item.get("value")), f"{key}: invalid value")
        need("unit" in item, f"{key}: unit missing")
        date.fromisoformat(item["as_of"])
        need(item["as_of"] <= context["as_of_date"], f"{key}: future data date")
        need(item["source_url"].startswith(("https://", "http://")), f"{key}: source URL required")
        if re.search(r"[\u4e00-\u9fff]", item["value_display"]):
            need(item.get("value_display_en"), f"{key}: translated display required")
        item.update({k: spec[k] for k in ["axis", "category", "category_zh"]})
        source = prefetch_source(root, config, key, at)
        checked = timestamp(ev["checked_at"])
        need(timestamp(context["prepared_at"]) - timedelta(minutes=5) <= checked <= at + timedelta(minutes=5), f"{key}: evidence was not checked in this run")
        need(ev.get("rationale") and ev.get("raw") is not None, f"{key}: evidence rationale/raw missing")
        if ev.get("kind") == "current":
            need(not item["stale"], f"{key}: current must have stale=false")
        if item["stale"]:
            need(source is None, f"{key}: usable prefetch must be consumed")
            reconciliation_carry = False
            if key == "debt_capex_ratio" and ev.get("raw", {}).get("reconciliation_incomplete") is True:
                age, interval = debt_reconciliation_age(root, context)
                effective = config["debt_reconciliation"]["stale_if_due_unreconciled_from_cycle"]
                reconciliation_carry = context["cycle"] >= effective and age >= interval and bundle.get("debt_review", {}).get("full_reconciliation") is not True
            need(ev.get("kind") == "carry" and (ev.get("attempted_urls") or reconciliation_carry), f"{key}: document failed source chain or incomplete debt reconciliation")
            need(key in old, f"{key}: no prior value to carry")
            for field in ["value", "value_display", "value_display_en", "status", "as_of"]:
                need(item.get(field) == old[key].get(field), f"{key}: stale carry changed {field}")
            raw = copy.deepcopy(ev["raw"])
            if not reconciliation_carry:
                raw["fetch_failed"] = True
        elif ev.get("kind") == "current":
            need(spec["cadence"] == "periodic", f"{key}: current is allowed only for periodic indicators")
            need(source is None, f"{key}: valid prefetch has priority")
            need(ev.get("urls") and all(isinstance(u, str) and u.startswith(("https://", "http://")) for u in ev["urls"]), f"{key}: current requires opened source URLs")
            need(isinstance(ev["raw"], dict) and not ev["raw"].get("fetch_failed"), f"{key}: current requires a successful disclosure check")
            need(not any(ev["raw"].get(k) for k in ("source_failed", "tool_failed", "search_failed")), f"{key}: failed source check must be stale")
            release_date = ev["raw"].get("latest_release_date")
            need(isinstance(release_date, str), f"{key}: current latest_release_date required")
            date.fromisoformat(release_date)
            need(release_date <= context["as_of_date"], f"{key}: future latest_release_date")
            need(isinstance(ev["raw"].get("next_expected"), str) and ev["raw"]["next_expected"].strip(), f"{key}: current next_expected disclosure metadata required")
            need(key in old, f"{key}: no prior observation for current")
            for field in ["value", "value_display", "value_display_en", "status", "as_of"]:
                need(item.get(field) == old[key].get(field), f"{key}: current changed {field}")
            age = (date.fromisoformat(context["as_of_date"]) - date.fromisoformat(item["as_of"])).days
            need(age <= spec["max_age_days"], f"{key}: current observation exceeds {spec['max_age_days']}-day maximum age; mark stale")
            raw = copy.deepcopy(ev["raw"])
        elif source is not None:
            need(ev.get("kind") == "prefetch", f"{key}: valid prefetch has priority")
            need(item["as_of"] == source["as_of"], f"{key}: prefetch observation date mismatch")
            raw = copy.deepcopy(source["data"])
            expected = raw[config["prefetch"][key]["value_key"]]
            if key == "insider_sell_buy" and raw.get("zero_buy"):
                expected = min(expected, 99) if numeric(expected) else 99
                need("近零" in item["value_display"], "Zero-buy display must explain near-zero purchases")
            need(numeric(expected) and numeric(item["value"]) and abs(item["value"] - expected) < 0.011, f"{key}: prefetch value mismatch")
        else:
            need(ev.get("kind") == "web" and ev.get("urls") and all(u.startswith(("https://", "http://")) for u in ev["urls"]), f"{key}: opened source URLs required")
            need(isinstance(ev["raw"], dict) and ev["raw"] and not ev["raw"].get("fetch_failed"), f"{key}: new raw observations required")
            raw = copy.deepcopy(ev["raw"])
            if spec["cadence"] == "scan":
                validate_scan(key, item, ev, context)
        item["freshness"] = "stale" if item["stale"] else "current" if ev["kind"] == "current" else "new"
        item.pop("basis_changed", None)
        if active and not item["stale"] and raw.get("basis") is not None:
            item["basis"] = copy.deepcopy(raw["basis"])
            prior_basis = history.get(key, [{}])[-1].get("raw", {}).get("basis")
            if prior_basis is not None and prior_basis != raw["basis"]:
                item["basis_changed"] = True
        if active and key in STRUCTURAL_CANONICAL and not item["stale"]:
            expected_status = structural_status(key, item, raw, ledgers, context)
            need(item["status"] == expected_status, f"{key}: status contradicts deterministic structural contract")
            item["basis"] = raw["basis"]
            item["basis_changed"] = old[key].get("basis") != item["basis"]
            if key == "arr_2nd_deriv":
                item["basis_components"] = copy.deepcopy(raw["arr_basis_signature"])
                item["basis_changed"] = item["basis_changed"] or old[key].get("basis_components") != item["basis_components"]
            if ev["kind"] == "current":
                need(not item["basis_changed"], f"{key}: basis switch is a new observation, cannot be current")
                prior_raw = history.get(key, [{}])[-1].get("raw", {})
                for field in STRUCTURAL_CANONICAL[key]:
                    need(field in prior_raw and raw[field] == prior_raw[field], f"{key}: current changed canonical {field}")
            if item["basis_changed"]:
                need("口径" in item["note"] and any(t in item["note"] for t in ("切换", "重建", "不可比")), f"{key}: first observation requires Chinese basis-switch note")
                need(any(t in item["note_en"].lower() for t in ("basis switch", "incomparable", "not comparable", "rebuild")), f"{key}: first observation requires English basis-switch note")
                if key == "nvda_invest_revenue":
                    need(all(t in item["note"] and t in item["note_en"] for t in ("43", "45")), "NVDA: first rebuilt numerator must disclose old 43–45% is incomparable")
            if key in STRUCTURAL_LABELS:
                item["name_zh"], item["name_en"], item["threshold_text"], item["threshold_text_en"] = STRUCTURAL_LABELS[key]
        if active:
            raw["basis_switch"] = bool(item.get("basis_changed"))
        if "thresholds" in spec and not item["stale"]:
            need(numeric(item["value"]), f"{key}: numeric value required")
            red, yellow = spec["thresholds"]
            v = item["value"]
            if spec["direction"] == "high_bad":
                status = "red" if v >= red else "yellow" if v >= yellow else "green"
            elif spec["direction"] == "low_bad":
                status = "red" if v <= red else "yellow" if v <= yellow else "green"
            else:
                raise GateError(f"{key}: unsupported numeric direction")
            need(item["status"] == status, f"{key}: status contradicts threshold")
        calculation = ev.get("calculation")
        if calculation and not item["stale"]:
            x, y = calculation["current"], calculation["previous"]
            need(numeric(x) and numeric(y) and y != 0, f"{key}: invalid calculation")
            op = calculation["operator"]
            need(op in ["change_pct", "ratio_pct", "ratio"], f"{key}: unknown calculation")
            expected = (x / y - 1) * 100 if op == "change_pct" else x / y * (100 if op == "ratio_pct" else 1)
            need(numeric(item["value"]) and abs(item["value"] - expected) <= 0.51, f"{key}: derived value mismatch")
        records = history.get(key, []) + [{"date": item["as_of"], "run_date": context["as_of_date"], "cycle": context["cycle"], "raw": raw, "value": item["value"], "stale": item["stale"], "freshness": item["freshness"]}]
        if key in config["static_core_keys"]:
            aliases = config["static_core_keys"][key]
            need(item["stale"] or core_values(raw, aliases) is not None, f"{key}: missing static-check core fields; document raw alias in task.json")
            weeks = static_weeks(records, aliases)
            item.pop("suspect_static", None)
            item.pop("static_weeks", None)
            if weeks >= 3:
                item.update(suspect_static=True, static_weeks=weeks)
        history[key] = records[-config["raw_history_limit"]:]
    return indicators, history, previous, specs, calibration


def validate_narrative(bundle, summary, reasons, previous):
    parts = []
    for key, prefix in [("verdict_desc", "**一句话**"), ("verdict_desc_en", "**Bottom line**")]:
        text = bundle.get(key, "")
        paragraphs = text.split("\n\n")
        need(4 <= len(paragraphs) <= 6 and all(p.strip().startswith("**") for p in paragraphs), f"{key}: need 4–6 headed paragraphs")
        need(paragraphs[0].startswith(prefix), f"{key}: TLDR heading missing")
        first = paragraphs[0].replace("**", "")
        need(len(first) <= 90 if key == "verdict_desc" else len(first.split()) <= 54, f"{key}: TLDR too long")
        need(not re.search(r"(?m)^\s*(?:#|[-*+]\s|\d+\.\s|\|)", text), f"{key}: unsupported markdown")
        need(summary["similarity"][0]["period"] in text and "2000-02" in text, f"{key}: historical comparison missing")
        parts.append(paragraphs)
    need(len(parts[0]) == len(parts[1]), "Bilingual paragraph structure differs")
    zh, en = bundle["verdict_desc"], bundle["verdict_desc_en"].lower()
    need("反向" in zh and ("counter" in en or "offset" in en), "Counterevidence paragraph required")
    if "category_resonance" in reasons:
        need("共振" in parts[0][-1] and "resonance" in parts[1][-1].lower(), "Explain category resonance in closing paragraph")
    if "two_axis" in reasons:
        need("两轴" in parts[0][-1] and ("two-axis" in parts[1][-1].lower() or "two axes" in parts[1][-1].lower()), "Explain two-axis rule in closing paragraph")
    if abs(summary["momentum"]["net"]) >= 4:
        need("边际" in zh and ("momentum" in en or "marginal" in en), "Explain significant momentum")
    if summary["total_indicators"] != previous["summary"]["total_indicators"]:
        need("分母" in zh and "denominator" in en, "Explain changed denominator")


def validate_debt(root, bundle, context, indicators, at=None):
    old = read(root / "docs/data/debt_ledger.json")
    new = bundle["debt_ledger"]
    ev = bundle["debt_review"]
    item = next(i for i in indicators if i["id"] == "debt_capex_ratio")
    config = read(root / "automation/task.json")
    if structural_active(config, context["cycle"]) and ev.get("full_reconciliation"):
        need(not item["stale"], "Completed debt reconciliation cannot carry stale")
        audits = ev.get("reconciliation_sources")
        need(isinstance(audits, list) and audits, "Debt full reconciliation requires this-run source audit")
        scopes = set()
        for audit in audits:
            need(isinstance(audit, dict) and audit.get("scope") in ("financing_anchor", "capex_denominator", "deal_reconciliation"), "Debt reconciliation audit scope required")
            need(valid_url(audit.get("url")) and audit["url"] in ev.get("searched_urls", []), "Debt reconciliation audit must reference an opened searched URL")
            need(isinstance(audit.get("raw_reading"), str) and audit["raw_reading"].strip(), "Debt reconciliation audit actual reading required")
            checked = timestamp(audit["checked_at"])
            prepared = timestamp(context["prepared_at"])
            need(prepared - timedelta(minutes=5) <= checked <= (at or now()) + timedelta(minutes=5), "Debt reconciliation audit was not checked in this run")
            scopes.add(audit["scope"])
        need(scopes == {"financing_anchor", "capex_denominator", "deal_reconciliation"}, "Debt reconciliation must audit annual financing, all-in capex denominator and historical deals")
    if item["stale"]:
        need(new == old, "Stale debt data cannot change ledger")
        return []
    need(ev.get("searched_urls") and ev.get("weekly_search_note"), "Weekly debt search evidence required, including no-deal weeks")
    if ev.get("full_reconciliation"):
        need(ev.get("reconciliation_note"), "Full debt reconciliation evidence required")
        need(new["last_full_recon"] == context["as_of_date"], "Full reconciliation date mismatch")
    else:
        need(new["last_full_recon"] == old["last_full_recon"], "Cannot advance unreconciled date")
    need(numeric(new.get("capex_denominator_usd_b")) and new["capex_denominator_usd_b"] > 0, "Invalid capex denominator")
    need(numeric(new["ms_anchor"].get("numerator_usd_b")) and new["ms_anchor"]["numerator_usd_b"] > 0, "Missing full-scope numerator")
    need(new["ms_anchor"].get("source"), "Full-scope anchor source required")
    date.fromisoformat(new["ms_anchor"]["as_of"])
    need(new["ms_anchor"]["as_of"] <= context["as_of_date"], "Future full-scope anchor")
    need(abs(item["value"] - new["ms_anchor"]["numerator_usd_b"] / new["capex_denominator_usd_b"] * 100) <= 0.51, "Debt ratio inconsistent with all-in anchor")
    corrections = ev.get("corrections", [])
    for deal in old["deals"]:
        matches = [d for d in new["deals"] if d["borrower"] == deal["borrower"] and d["date"] == deal["date"]]
        need(deal in matches or any(c.get("borrower") == deal["borrower"] and c.get("date") == deal["date"] and c.get("reason") and c.get("source_url") for c in corrections), "Historical debt deal changed without correction evidence")
    added = []
    for index, deal in enumerate(new["deals"]):
        need(numeric(deal.get("amount_usd_b")) and deal["amount_usd_b"] > 0 and deal.get("source_url"), "Invalid debt deal")
        date.fromisoformat(deal["date"])
        need(deal["date"] <= context["as_of_date"], "Future debt deal")
        if not any(d["borrower"] == deal["borrower"] and d["date"] == deal["date"] for d in old["deals"]):
            added.append(deal)
            for other_index, other in enumerate(new["deals"]):
                if other_index == index:
                    continue
                days = abs((date.fromisoformat(deal["date"]) - date.fromisoformat(other["date"])).days)
                close_amount = abs(deal["amount_usd_b"] - other["amount_usd_b"]) <= max(0.05, other["amount_usd_b"] * 0.05)
                need(not (deal["borrower"].casefold() == other["borrower"].casefold() and days <= 7 and close_amount), "Possible duplicate debt deal; reconcile before publication")
    return added


def validate_wow(changes, indicators, previous, added):
    need(isinstance(changes, list) and len(changes) <= 5, "At most 5 WoW changes")
    old, new = ({i["id"]: i for i in values} for values in [previous["indicators"], indicators])
    for change in changes:
        key = change["indicator_id"]
        need(key in old and key in new and change.get("note") and change.get("note_en"), "Invalid or untranslated WoW change")
        a, b = old[key], new[key]
        need(not b.get("basis_changed"), f"{key}: first basis switch is incomparable and cannot be a WoW change")
        kind = change["type"]
        delta = POINTS[b["status"]] - POINTS[a["status"]]
        if kind in ("status_upgrade", "status_downgrade"):
            need(delta > 0 if kind == "status_upgrade" else delta < 0, "WoW status direction mismatch")
            need(change["from"] == a["status"] and change["to"] == b["status"], "WoW status endpoints mismatch")
        else:
            need(kind == "value_change", "Unknown WoW change type")
            large_debt = key == "debt_capex_ratio" and any(d["amount_usd_b"] >= 10 for d in added)
            need(large_debt or (delta == 0 and numeric(a["value"]) and numeric(b["value"]) and a["value"] != 0 and abs(b["value"] / a["value"] - 1) > 0.1), "WoW value change must exceed 10%")
            need(change["from"] == a["value"] and change["to"] == b["value"], "WoW value endpoints mismatch")
    if any(d["amount_usd_b"] >= 10 for d in added):
        need(any(c["indicator_id"] == "debt_capex_ratio" for c in changes), "New >=$10B debt deal must be a WoW change")


def notification(snapshot, added, root, config, at, counts, warning):
    s = snapshot["summary"]
    lines = [f"风险温度：红灯 {s['red_pct']}%（强预警参考线 60%）｜加权风险 {s['weighted_risk_score']}",
             f"🔴 {s['red_count']} 🟡 {s['yellow_count']} 🟢 {s['green_count']}",
             f"两轴：{s['stage_label']} {s['stage_score']} × {s['trigger_label']} {s['trigger_score']}",
             f"历史相似度：{s['similarity'][0]['period']} {s['similarity'][0]['match_pct']}%",
             f"动量：恶化 {s['momentum']['deteriorated']} / 改善 {s['momentum']['improved']} / 净值 {s['momentum']['net']}",
             f"新鲜度：new {counts['new']} / current {counts['current']} / stale {counts['stale']}（current 为本期核实仍最新，保留真实披露日）"]
    if warning:
        lines.append(warning["message"])
    for item in snapshot["indicators"]:
        if item.get("suspect_static"):
            lines.append(f"⚠ 疑似静态：{item['name_zh']} 连续 {item['static_weeks']} 期原始值未变/未获取 = {item['value_display']}，请人工核查")
    for key in config["prefetch"]:
        if not prefetch_source(root, config, key, at):
            lines.append(f"⚠ prefetch {key} 不可用或已过期；本期按备源/沿用标记处理")
    if added:
        lines.append("本周新债务：" + "；".join(f"{d['borrower']} ${d['amount_usd_b']}B" for d in added))
    lines.extend([s["verdict_label"], s["verdict_desc"].replace("**", "")])
    lines.extend(f"WoW：{c['note']}" for c in snapshot["wow_changes"])
    lines.extend(f"🔴 {i['name_zh']} {i['value_display']} — {i['note']}" for i in snapshot["indicators"] if i["status"] == "red")
    lines.extend(["中文：https://aibubble-cn.github.io", "English: https://bubblewatch.github.io", config["dashboard"]])
    return {"msg_type": "post", "content": {"post": {"zh_cn": {
        "title": f"📊 AI 泡沫监测 · Issue #{snapshot['issue_number']:03d} · {snapshot['as_of_date']}",
        "content": [[{"tag": "text", "text": line}] for line in lines]}}}}


def build(root, bundle, context, at):
    check_context(root, context)
    need(bundle.get("schema_version") == 1 and bundle.get("cycle") == context["cycle"], "Bundle version/cycle mismatch")
    need(timestamp(context["prepared_at"]) <= at + timedelta(minutes=5), "Future context")
    need(at - timestamp(context["prepared_at"]) < timedelta(hours=24), "Context expired; refresh evidence and prepare again")
    config = read(root / "automation/task.json")
    input_bundle_sha256 = digest(encoded(bundle))
    bundle = apply_debt_reconciliation_policy(root, bundle, context)
    indicators, history, previous, specs, calibration = validate_indicators(root, bundle, context, at)
    stale = [i["id"] for i in indicators if i["stale"]]
    counts = freshness_counts(indicators, bundle["evidence"])
    warning = debt_reconciliation_warning(root, context)
    run = {"schema_version": 1, "cycle": context["cycle"], "attempt": context["attempt"], "prepared_at": context["prepared_at"],
           "base_commit": context["base_commit"], "inputs": context["inputs"], "bundle_sha256": input_bundle_sha256,
           "stale_ids": stale, "freshness_counts": counts, "evidence": bundle["evidence"], "delivery": "queued_only; inspect Feishu Relay result"}
    if digest(encoded(bundle)) != input_bundle_sha256:
        run["normalized_bundle_sha256"] = digest(encoded(bundle))
    files = {}
    if len(stale) > config["max_stale"]:
        run.update(status="failed_data", published_issue=None)
        message = f"⚠️ AI Bubble Monitor 周报失败 · {context['as_of_date']}\n\n{len(stale)} 个指标取数失败，超过 stale >{config['max_stale']} 阈值；未更新网页、快照及台账。\n新鲜度：new {counts['new']} / current {counts['current']} / stale {counts['stale']}（current 保留真实披露日）\n"
        if warning:
            message += warning["message"] + "\n"
        message += "\n".join(f"{k}: {bundle['evidence'][k]['rationale']}" for k in stale)
        payload = {"msg_type": "text", "content": {"text": message}}
    else:
        summary, reasons = aggregate(indicators, previous, specs, calibration)
        validate_narrative(bundle, summary, reasons, previous)
        added = validate_debt(root, bundle, context, indicators, at)
        warning = debt_reconciliation_warning(root, context, bundle["debt_ledger"])
        validate_wow(bundle["wow_changes"], indicators, previous, added)
        summary.update({k: bundle[k] for k in ["verdict_desc", "verdict_desc_en"]})
        history_seed = (previous.get("history_seed", []) + [{"week": context["as_of_date"][5:], "red_pct": summary["red_pct"], "risk_score": summary["weighted_risk_score"]}])[-config["history_seed_limit"]:]
        snapshot = {"issue_number": previous["issue_number"] + 1, "as_of_date": context["as_of_date"],
                    "generated_at": context["prepared_at"], "summary": summary, "wow_changes": bundle["wow_changes"],
                    "history_seed": history_seed, "indicators": indicators}
        snapshot_path = f"docs/data/snapshots/{context['as_of_date']}.json"
        need(not (root / snapshot_path).exists(), "Refuse to overwrite a historical snapshot")
        files.update({"docs/data/latest.json": snapshot, snapshot_path: snapshot,
                      "docs/data/debt_ledger.json": bundle["debt_ledger"], "docs/data/raw_history.json": history})
        if structural_active(config, context["cycle"]):
            ledger_values = {key: ledger_candidate(root, bundle, key) for key in LEDGERS}
            nvda_totals(ledger_values["nvda_commitments"], context["as_of_date"])
            arr_calculations(ledger_values["arr_ledger"], context["as_of_date"])
            run["ledger_sha256"] = {key: digest(encoded(value)) for key, value in ledger_values.items()}
            for key, value in ledger_values.items():
                path = LEDGERS[key][0]
                if value != read(root / path):
                    files[path] = value
        payload = notification(snapshot, added, root, config, at, counts, warning)
        if added:
            total = sum(d["amount_usd_b"] for d in bundle["debt_ledger"]["deals"])
            payload["content"]["post"]["zh_cn"]["content"].insert(5, [{"tag": "text", "text": f"YTD 台账下限：${total:.3f}B；并非全量融资"}])
        run.update(status="validated_release", issue_number=snapshot["issue_number"], as_of_date=snapshot["as_of_date"],
                   latest_sha256=digest(encoded(snapshot)), verdict_reasons=reasons)
    if warning:
        run["warnings"] = [warning["message"]]
        run["debt_reconciliation_overdue_days"] = warning["debt_reconciliation_overdue_days"]
    files[f"feishu_outbox/{context['as_of_date']}.json"] = payload
    files[f"runs/{context['cycle']}.json"] = run
    return files


def check_site(root, expected_path):
    config = read(root / "automation/task.json")
    expected = read(expected_path)
    req = urllib.request.Request(config["data_url"] + "?verify=" + digest(encoded(expected))[:16], headers={"Cache-Control": "no-cache", "User-Agent": "AI-Bubble-Release-Check"})
    with urllib.request.urlopen(req, timeout=30) as response:
        actual = json.load(response)
    need(actual == expected, "Published data differs from expected complete snapshot")
    with urllib.request.urlopen(config["dashboard"], timeout=30) as response:
        html = response.read().decode()
    need("data/latest.json" in html, "Dashboard does not reference expected data")
    return {"site_verified": True, "issue": actual["issue_number"], "as_of_date": actual["as_of_date"], "sha256": digest(encoded(actual))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("prepare")
    p.add_argument("--cycle")
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--out", type=Path, default=Path(".run/context.json"))
    p = subs.add_parser("score")
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--context", type=Path, default=Path(".run/context.json"))
    for command in ["build", "check"]:
        p = subs.add_parser(command)
        p.add_argument("--bundle", type=Path, required=True)
        p.add_argument("--context", type=Path, default=Path(".run/context.json"))
        p.add_argument("--release", type=Path, default=Path(".run/release"))
    p = subs.add_parser("check-site")
    p.add_argument("--expected", type=Path, default=Path("docs/data/latest.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "prepare":
        output = prepare(root, now(), args.cycle, args.retry_failed)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(encoded(output))
    elif args.command == "score":
        specs, calibration = definitions(root)
        bundle = read(args.bundle)
        config = read(root / "automation/task.json")
        policy_active = bundle["cycle"] >= config["debt_reconciliation"]["stale_if_due_unreconciled_from_cycle"]
        need(args.context.exists() or not policy_active, "Prepared context required for debt policy; run prepare first")
        context = read(args.context) if args.context.exists() else {"cycle": bundle["cycle"], "as_of_date": now().date().isoformat()}
        need(context["cycle"] == bundle["cycle"], "Score context/bundle cycle mismatch")
        bundle = apply_debt_reconciliation_policy(root, bundle, context)
        indicators = copy.deepcopy(bundle["indicators"])
        previous = read(root / "docs/data/latest.json")
        if structural_active(config, bundle["cycle"]):
            ledgers = {key: ledger_candidate(root, bundle, key) for key in LEDGERS}
            old = {i["id"]: i for i in previous["indicators"]}
            history = read(root / "docs/data/raw_history.json")
            for item in indicators:
                item.pop("basis_changed", None)
                if item["stale"]:
                    continue
                raw = copy.deepcopy(bundle["evidence"][item["id"]]["raw"])
                prior_basis = history.get(item["id"], [{}])[-1].get("raw", {}).get("basis")
                if raw.get("basis") is not None and prior_basis is not None and raw["basis"] != prior_basis:
                    item["basis_changed"] = True
                if item["id"] in STRUCTURAL_CANONICAL:
                    item["status"] = structural_status(item["id"], item, raw, ledgers, context)
                    item["basis_changed"] = old[item["id"]].get("basis") != raw["basis"]
                    if item["id"] == "arr_2nd_deriv":
                        item["basis_changed"] = item["basis_changed"] or old[item["id"]].get("basis_components") != raw["arr_basis_signature"]
        result, reasons = aggregate(indicators, previous, specs, calibration)
        for item in indicators:
            item["freshness"] = "stale" if item["stale"] else "current" if bundle["evidence"][item["id"]]["kind"] == "current" else "new"
        output = {"summary": result, "verdict_reasons": reasons,
                  "indicator_statuses": {i["id"]: i["status"] for i in indicators},
                  "indicator_freshness": {i["id"]: i["freshness"] for i in indicators},
                  "freshness_counts": freshness_counts(indicators, bundle["evidence"])}
    elif args.command in ["build", "check"]:
        context, bundle = read(args.context), read(args.bundle)
        files = build(root, bundle, context, now())
        manifest = {"base_commit": context["base_commit"], "cycle": context["cycle"], "files": {p: digest(encoded(v)) for p, v in files.items()}}
        if args.command == "build":
            need(not args.release.exists() or not any(args.release.iterdir()), "Release directory must be empty; choose a new path for a corrected attempt")
            for path, value in {**files, "manifest.json": manifest}.items():
                dest = args.release / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(encoded(value))
        else:
            need(read(args.release / "manifest.json") == manifest, "Release manifest mismatch")
            actual_paths = {str(p.relative_to(args.release)) for p in args.release.rglob("*") if p.is_file()}
            need(actual_paths == set(files) | {"manifest.json"}, "Unexpected release files")
            for path, value in files.items():
                need((args.release / path).read_bytes() == encoded(value), f"Release altered after validation: {path}")
        output = manifest
    else:
        output = check_site(root, args.expected)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (GateError, KeyError, ValueError, TypeError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
