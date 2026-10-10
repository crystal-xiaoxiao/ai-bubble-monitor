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
          "docs/data/prefetch/latest.json"]


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
    return {p: digest((root / p).read_bytes()) for p in INPUTS}


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
            for field in ["Axis", "Direction"]:
                m = re.search(r"\*\*" + field + r"\*\*:\s*([a-z_]+)", line)
                if m:
                    current[field.lower()] = m[1]
            m = re.search(r"\*\*Thresholds\*\*:\s*red=([-\d.]+),\s*yellow=([-\d.]+)", line)
            if m:
                current["thresholds"] = [float(m[1]), float(m[2])]
    for key, spec in result.items():
        need(spec.get("axis") in ("stage", "trigger") and "direction" in spec, f"Incomplete definition: {key}")
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
    delta = [v - old[k] for k, v in score.items() if k in old]
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


def validate_indicators(root, bundle, context, at):
    specs, calibration = definitions(root)
    config = read(root / "automation/task.json")
    previous = read(root / "docs/data/latest.json")
    old = {i["id"]: i for i in previous["indicators"]}
    indicators = copy.deepcopy(bundle["indicators"])
    need(len(indicators) == len(specs) and {i["id"] for i in indicators} == set(specs), "Indicator ID mismatch")
    need(set(bundle["evidence"]) == set(specs), "Evidence IDs must match indicators")
    history = read(root / "docs/data/raw_history.json")
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
        if item["stale"]:
            need(source is None, f"{key}: usable prefetch must be consumed")
            need(ev.get("kind") == "carry" and ev.get("attempted_urls"), f"{key}: document failed source chain")
            need(key in old, f"{key}: no prior value to carry")
            for field in ["value", "value_display", "value_display_en", "status", "as_of"]:
                need(item.get(field) == old[key].get(field), f"{key}: stale carry changed {field}")
            raw = copy.deepcopy(ev["raw"])
            raw["fetch_failed"] = True
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
        records = history.get(key, []) + [{"date": item["as_of"], "run_date": context["as_of_date"], "cycle": context["cycle"], "raw": raw, "value": item["value"], "stale": item["stale"]}]
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


def validate_debt(root, bundle, context, indicators):
    old = read(root / "docs/data/debt_ledger.json")
    new = bundle["debt_ledger"]
    ev = bundle["debt_review"]
    item = next(i for i in indicators if i["id"] == "debt_capex_ratio")
    if item["stale"]:
        need(new == old, "Stale debt data cannot change ledger")
        return []
    need(ev.get("searched_urls") and ev.get("weekly_search_note"), "Weekly debt search evidence required, including no-deal weeks")
    due = (date.fromisoformat(context["as_of_date"]) - date.fromisoformat(old["last_full_recon"])).days >= 28
    if due:
        need(ev.get("full_reconciliation") is True and ev.get("reconciliation_note"), "28-day full debt reconciliation due")
        need(new["last_full_recon"] == context["as_of_date"], "Full reconciliation date mismatch")
    elif not ev.get("full_reconciliation"):
        need(new["last_full_recon"] == old["last_full_recon"], "Cannot advance unreconciled date")
    need(numeric(new.get("capex_denominator_usd_b")) and new["capex_denominator_usd_b"] > 0, "Invalid capex denominator")
    need(numeric(new["ms_anchor"].get("numerator_usd_b")), "Missing full-scope numerator")
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


def notification(snapshot, added, root, config, at):
    s = snapshot["summary"]
    lines = [f"风险温度：红灯 {s['red_pct']}%（强预警参考线 60%）｜加权风险 {s['weighted_risk_score']}",
             f"🔴 {s['red_count']} 🟡 {s['yellow_count']} 🟢 {s['green_count']}",
             f"两轴：{s['stage_label']} {s['stage_score']} × {s['trigger_label']} {s['trigger_score']}",
             f"历史相似度：{s['similarity'][0]['period']} {s['similarity'][0]['match_pct']}%",
             f"动量：恶化 {s['momentum']['deteriorated']} / 改善 {s['momentum']['improved']} / 净值 {s['momentum']['net']}"]
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
    indicators, history, previous, specs, calibration = validate_indicators(root, bundle, context, at)
    stale = [i["id"] for i in indicators if i["stale"]]
    run = {"schema_version": 1, "cycle": context["cycle"], "attempt": context["attempt"], "prepared_at": context["prepared_at"],
           "base_commit": context["base_commit"], "inputs": context["inputs"], "bundle_sha256": digest(encoded(bundle)),
           "stale_ids": stale, "evidence": bundle["evidence"], "delivery": "queued_only; inspect Feishu Relay result"}
    files = {}
    if len(stale) > config["max_stale"]:
        run.update(status="failed_data", published_issue=None)
        message = f"⚠️ AI Bubble Monitor 周报失败 · {context['as_of_date']}\n\n{len(stale)} 个指标取数失败，超过 stale >{config['max_stale']} 阈值；未更新网页、快照及台账。\n" + "\n".join(f"{k}: {bundle['evidence'][k]['rationale']}" for k in stale)
        payload = {"msg_type": "text", "content": {"text": message}}
    else:
        summary, reasons = aggregate(indicators, previous, specs, calibration)
        validate_narrative(bundle, summary, reasons, previous)
        added = validate_debt(root, bundle, context, indicators)
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
        payload = notification(snapshot, added, root, config, at)
        if added:
            total = sum(d["amount_usd_b"] for d in bundle["debt_ledger"]["deals"])
            payload["content"]["post"]["zh_cn"]["content"].insert(5, [{"tag": "text", "text": f"YTD 台账下限：${total:.3f}B；并非全量融资"}])
        run.update(status="validated_release", issue_number=snapshot["issue_number"], as_of_date=snapshot["as_of_date"],
                   latest_sha256=digest(encoded(snapshot)), verdict_reasons=reasons)
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
        result, reasons = aggregate(read(args.bundle)["indicators"], read(root / "docs/data/latest.json"), specs, calibration)
        output = {"summary": result, "verdict_reasons": reasons}
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
