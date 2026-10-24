#!/usr/bin/env python3
"""Summarize a test run (TestNG XML, Allure results or JUnit XML) into numbers a report can be written from.

Usage:
    python3 summarize_run.py <results-dir-or-file> [...] [--previous <dir-or-file> ...]
                             [--known known-issues.txt] [--top 5] [--out run-summary.json]

Reads, in order of preference (only the first format found is used, so tests are not counted twice):
    testng-results.xml   TestNG native report (config failures, retries, skipped dependents)
    allure-results/      Allure raw results: *-result.json (+ *-container.json for failed setup methods)
    TEST-*.xml           JUnit-format XML (Surefire/Failsafe)

Writes JSON with:
    summary      totals, pass rates, duration, start/finish time
    by_class     per test class: total / passed / failed / skipped
    failures     every failed test and config failure, with signature and known-issue match
    groups       failures grouped by root-cause signature
    skipped      skipped tests and the config failure that caused them (if any)
    flaky        tests that failed and then passed on retry
    slowest      the N slowest tests
    comparison   (with --previous) new failures, fixed, still failing, new/removed tests, rate delta

Only the Python standard library is used.
"""
import argparse
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict

FRAMEWORK_PREFIXES = (
    "java.", "javax.", "jdk.", "sun.", "org.testng.", "org.junit.", "org.assertj.", "org.opentest4j.",
    "io.restassured.", "org.apache.", "com.fasterxml.", "org.hamcrest.", "com.microsoft.playwright.",
    "org.openqa.", "io.qameta.", "org.springframework.", "org.h2.", "groovy.", "kotlin.",
)
FRAME_RE = re.compile(r"^\s*at\s+([\w$.]+)\.([\w$<>]+)\(([^)]*)\)")


# ----------------------------------------------------------------------------- helpers
def first_line(msg):
    if not msg:
        return ""
    pw = re.search(r"message='([^'\n]*)", msg)          # Playwright "Error { message='...'"
    return (pw.group(1) if pw else msg.strip().splitlines()[0])[:240]


def normalize(msg):
    m = first_line(msg)
    m = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", m, flags=re.I)
    m = re.sub(r"\d+", "<n>", m)
    return m[:160]


def project_frame(trace):
    for line in (trace or "").splitlines():
        m = FRAME_RE.match(line)
        if m and not m.group(1).startswith(FRAMEWORK_PREFIXES) and ".invoker." not in m.group(1):
            return f"{m.group(1).split('.')[-1]}.{m.group(2)}"
    return None


def record(cls, method, status, duration, exc=None, msg="", trace="", kind=None):
    pf = project_frame(trace)
    exc_short = (exc or "").split(".")[-1]
    return OrderedDict(
        id=f"{cls}#{method}", **{"class": cls}, method=method, status=status,
        kind=kind or status, duration_s=duration, exception=exc, message=first_line(msg),
        project_frame=pf,
        signature=f"{exc_short or 'Unknown'} @ {pf or '?'} :: {normalize(msg)}" if status != "PASS" or kind == "flaky" else None,
    )


# ----------------------------------------------------------------------------- parsers
def parse_testng(path):
    """Return (tests, config_failures, meta). tests: list of records (final attempt per test)."""
    root = ET.parse(path).getroot()
    attempts, configs = OrderedDict(), []
    meta = {"suites": [], "started": None, "finished": None, "duration_s": 0.0}
    for suite in root.iter("suite"):
        meta["suites"].append(suite.get("name"))
        meta["duration_s"] += int(suite.get("duration-ms", "0") or 0) / 1000
        for key, attr in (("started", "started-at"), ("finished", "finished-at")):
            v = suite.get(attr)
            if v and (meta[key] is None or (v < meta[key] if key == "started" else v > meta[key])):
                meta[key] = v
    for cls_el in root.iter("class"):
        cls = cls_el.get("name", "?")
        for tm in cls_el.findall("test-method"):
            if tm.get("is-config") == "true":
                if tm.get("status") == "FAIL":
                    configs.append((cls, tm))
                continue
            params = "|".join((v.text or "").strip() for v in tm.iter("value"))
            attempts.setdefault((cls, tm.get("name", "?"), params), []).append(tm)

    def exc(tm):
        e = tm.find("exception")
        if e is None:
            return None, "", ""
        return e.get("class"), e.findtext("message") or "", e.findtext("full-stacktrace") or ""

    def dur(tm):
        return round(int(tm.get("duration-ms", "0") or 0) / 1000, 3)

    tests, config_failures = [], []
    for cls, tm in configs:
        e, m, t = exc(tm)
        r = record(cls, tm.get("name", "?"), "FAIL", dur(tm), e, m, t, kind="config-failure")
        r["skipped_dependents"] = []
        config_failures.append(r)
    for (cls, name, params), tms in attempts.items():
        tms = sorted(tms, key=lambda x: x.get("started-at", ""))
        final = tms[-1]
        method = name + (f"[{params}]" if params else "")
        status = final.get("status", "SKIP")
        total_dur = round(sum(dur(t) for t in tms), 3)
        earlier = [t for t in tms[:-1] if t.find("exception") is not None]
        if status == "PASS" and earlier:
            e, m, t = exc(earlier[-1])
            r = record(cls, method, "PASS", total_dur, e, m, t, kind="flaky")
            r["attempts"] = len(tms)
        elif status == "FAIL":
            e, m, t = exc(final)
            r = record(cls, method, "FAIL", total_dur, e, m, t)
            if len(tms) > 1:
                r["attempts"] = len(tms)
        else:
            r = record(cls, method, status, total_dur)
            if status == "SKIP":
                owner = next((c for c in config_failures if c["class"] == cls), None) \
                    or (config_failures[0] if config_failures else None)
                if owner:
                    owner["skipped_dependents"].append(r["id"])
                    r["skipped_because"] = owner["id"]
        tests.append(r)
    return tests, config_failures, meta


def parse_junit(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    tests, meta = [], {"suites": [], "started": None, "finished": None, "duration_s": 0.0}
    for s in suites:
        meta["suites"].append(s.get("name"))
        meta["duration_s"] += float(s.get("time", "0") or 0)
        ts = s.get("timestamp")
        if ts and (meta["started"] is None or ts < meta["started"]):
            meta["started"] = ts
        for tc in s.findall("testcase"):
            cls, name = tc.get("classname", "?"), tc.get("name", "?")
            d = float(tc.get("time", "0") or 0)
            hard = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
            flaky = tc.find("flakyFailure") if tc.find("flakyFailure") is not None else tc.find("flakyError")
            if tc.find("skipped") is not None:
                tests.append(record(cls, name, "SKIP", d))
            elif hard is not None:
                tests.append(record(cls, name, "FAIL", d, hard.get("type"),
                                    hard.get("message") or (hard.text or ""), hard.text or ""))
            elif flaky is not None:
                tests.append(record(cls, name, "PASS", d, flaky.get("type"), flaky.get("message") or "",
                                    flaky.findtext("stackTrace") or flaky.text or "", kind="flaky"))
            else:
                tests.append(record(cls, name, "PASS", d))
    return tests, [], meta



def parse_allure_dir(files, containers):
    """Allure raw results. Retries share a historyId; failed befores in containers are config failures."""
    by_uuid, attempts = {}, OrderedDict()
    meta = {"suites": [], "started": None, "finished": None, "duration_s": 0.0}
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"WARN: cannot parse {f}: {e}", file=sys.stderr)
            continue
        labels = {l.get("name"): l.get("value") for l in d.get("labels", [])}
        cls = labels.get("testClass") or (d.get("fullName", "?").rsplit(".", 1)[0])
        name = labels.get("testMethod") or d.get("name", "?")
        d["_cls"], d["_name"] = cls, name
        by_uuid[d.get("uuid")] = d
        attempts.setdefault(d.get("historyId") or f"{cls}#{name}", []).append(d)
        suite = labels.get("suite") or labels.get("parentSuite")
        if suite and suite not in meta["suites"]:
            meta["suites"].append(suite)
        for k, v in (("started", d.get("start")), ("finished", d.get("stop"))):
            if v and (meta[k] is None or (v < meta[k] if k == "started" else v > meta[k])):
                meta[k] = v

    def dur(d):
        return round(((d.get("stop") or 0) - (d.get("start") or 0)) / 1000, 3)

    def det(d):
        sd = d.get("statusDetails") or {}
        msg, trace = sd.get("message") or "", sd.get("trace") or ""
        head = (trace or msg).strip().splitlines()[0] if (trace or msg).strip() else ""
        exc = head.split(":")[0].strip() if re.match(r"^[\w.$]+(Exception|Error)\b", head) else None
        return exc, msg, trace

    status_map = {"passed": "PASS", "failed": "FAIL", "broken": "FAIL", "skipped": "SKIP"}
    config_failures = []
    for cf in containers:
        try:
            c = json.load(open(cf, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for b in c.get("befores", []):
            if b.get("status") in ("failed", "broken"):
                children = [by_uuid[u] for u in c.get("children", []) if u in by_uuid]
                cls = children[0]["_cls"] if children else c.get("name", "?")
                exc, msg, trace = det(b)
                r = record(cls, b.get("name", "setup"), "FAIL", dur(b), exc, msg, trace, kind="config-failure")
                r["skipped_dependents"] = [f"{x['_cls']}#{x['_name']}" for x in children
                                           if x.get("status") == "skipped"]
                config_failures.append(r)

    tests = []
    for key, ds in attempts.items():
        ds = sorted(ds, key=lambda x: x.get("stop") or 0)
        final = ds[-1]
        status = status_map.get(final.get("status"), "SKIP")
        cls, name = final["_cls"], final["_name"]
        total = round(sum(dur(x) for x in ds), 3)
        earlier = [x for x in ds[:-1] if x.get("status") in ("failed", "broken")]
        flaky_flag = (final.get("statusDetails") or {}).get("flaky")
        if status == "PASS" and (earlier or flaky_flag):
            src = earlier[-1] if earlier else final
            r = record(cls, name, "PASS", total, *det(src), kind="flaky")
            r["attempts"] = len(ds)
        elif status == "FAIL":
            r = record(cls, name, "FAIL", total, *det(final))
            if len(ds) > 1:
                r["attempts"] = len(ds)
        else:
            r = record(cls, name, status, total)
            if status == "SKIP":
                owner = next((c for c in config_failures if r["id"] in c["skipped_dependents"]), None)
                if owner:
                    r["skipped_because"] = owner["id"]
        tests.append(r)
    if meta["started"] and meta["finished"]:
        meta["duration_s"] = (meta["finished"] - meta["started"]) / 1000
        from datetime import datetime, timezone
        meta["started"], meta["finished"] = [datetime.fromtimestamp(v / 1000, timezone.utc).isoformat(timespec="seconds")
                                             for v in (meta["started"], meta["finished"])]
    return tests, config_failures, meta

def load(paths):
    testng, junit, allure, containers = [], [], [], []
    for p in paths:
        if os.path.isdir(p):
            testng += glob.glob(os.path.join(p, "**", "testng-results.xml"), recursive=True)
            allure += glob.glob(os.path.join(p, "**", "*-result.json"), recursive=True)
            containers += glob.glob(os.path.join(p, "**", "*-container.json"), recursive=True)
            junit += glob.glob(os.path.join(p, "**", "TEST-*.xml"), recursive=True)
        elif os.path.basename(p) == "testng-results.xml":
            testng.append(p)
        elif p.endswith(".xml"):
            junit.append(p)
    if not testng and allure:
        t, c, m = parse_allure_dir(sorted(set(allure)), sorted(set(containers)))
        m.update(format="allure", files=[os.path.dirname(allure[0])])
        return t, c, m
    files = sorted(set(testng)) or sorted(set(junit))
    if not files:
        return None
    tests, configs = [], []
    meta = {"suites": [], "started": None, "finished": None, "duration_s": 0.0,
            "format": "testng" if testng else "junit", "files": files}
    for f in files:
        try:
            t, c, m = (parse_testng if testng else parse_junit)(f)
        except ET.ParseError as e:
            print(f"WARN: cannot parse {f}: {e}", file=sys.stderr)
            continue
        tests += t
        configs += c
        meta["suites"] += m["suites"]
        meta["duration_s"] += m["duration_s"]
        for k in ("started", "finished"):
            if m[k] and (meta[k] is None or (m[k] < meta[k] if k == "started" else m[k] > meta[k])):
                meta[k] = m[k]
    return tests, configs, meta


def load_known(path):
    """known-issues.txt: '<test id or text in signature> | <ticket> | <note>' per line, # for comments."""
    known = []
    if not path:
        return known
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            known.append({"match": parts[0], "ticket": parts[1] if len(parts) > 1 else "",
                          "note": parts[2] if len(parts) > 2 else ""})
    return known


# ----------------------------------------------------------------------------- summary
def summarize(tests, configs, meta, known, top):
    total = len(tests)
    passed = sum(t["status"] == "PASS" for t in tests)
    failed = sum(t["status"] == "FAIL" for t in tests)
    skipped = sum(t["status"] == "SKIP" for t in tests)
    flaky = [t for t in tests if t["kind"] == "flaky"]
    executed = total - skipped
    summary = OrderedDict(
        suites=meta["suites"], format=meta["format"], started=meta["started"], finished=meta["finished"],
        duration_s=round(meta["duration_s"], 1), total=total, passed=passed, failed=failed,
        skipped=skipped, flaky=len(flaky), config_failures=len(configs),
        pass_rate=round(100 * passed / total, 1) if total else 0.0,
        executed_pass_rate=round(100 * passed / executed, 1) if executed else 0.0,
    )

    by_class = OrderedDict()
    for t in tests:
        c = by_class.setdefault(t["class"], OrderedDict(**{"class": t["class"]}, total=0, passed=0, failed=0, skipped=0))
        c["total"] += 1
        c[{"PASS": "passed", "FAIL": "failed"}.get(t["status"], "skipped")] += 1

    failures = configs + [t for t in tests if t["status"] == "FAIL"]
    for f in failures + flaky:
        hit = next((k for k in known if k["match"] == f["id"] or k["match"] in (f["signature"] or "")), None)
        f["known_issue"] = {"ticket": hit["ticket"], "note": hit["note"]} if hit else None

    groups = OrderedDict()
    for f in failures:
        g = groups.setdefault(f["signature"], OrderedDict(
            signature=f["signature"], tests=[], count=0, exception=f["exception"],
            project_frame=f["project_frame"], sample_message=f["message"], config_failure=False,
            skipped_dependents=0, known_issue=f["known_issue"]))
        g["tests"].append(f["id"])
        g["count"] += 1
        if f["kind"] == "config-failure":
            g["config_failure"] = True
            g["skipped_dependents"] += len(f.get("skipped_dependents", []))
    groups = sorted(groups.values(), key=lambda g: -(g["count"] + g["skipped_dependents"]))

    skipped_list = [OrderedDict(id=t["id"], because=t.get("skipped_because")) for t in tests if t["status"] == "SKIP"]
    slowest = sorted(tests, key=lambda t: -t["duration_s"])[:top]
    return OrderedDict(
        summary=summary, by_class=list(by_class.values()), failures=failures, groups=groups,
        skipped=skipped_list,
        flaky=[OrderedDict(id=t["id"], attempts=t.get("attempts"), message=t["message"],
                           known_issue=t["known_issue"]) for t in flaky],
        slowest=[OrderedDict(id=t["id"], duration_s=t["duration_s"], status=t["status"]) for t in slowest],
    )


def compare(cur_tests, prev_tests, cur_summary, prev_summary):
    cur = {t["id"]: t["status"] for t in cur_tests}
    prev = {t["id"]: t["status"] for t in prev_tests}
    both = cur.keys() & prev.keys()
    return OrderedDict(
        new_failures=sorted(i for i in both if cur[i] == "FAIL" and prev[i] != "FAIL"),
        fixed=sorted(i for i in both if prev[i] == "FAIL" and cur[i] == "PASS"),
        still_failing=sorted(i for i in both if cur[i] == "FAIL" and prev[i] == "FAIL"),
        newly_skipped=sorted(i for i in both if cur[i] == "SKIP" and prev[i] != "SKIP"),
        new_tests=sorted(cur.keys() - prev.keys()),
        removed_tests=sorted(prev.keys() - cur.keys()),
        previous_total=prev_summary["total"],
        previous_executed_pass_rate=prev_summary["executed_pass_rate"],
        executed_pass_rate_delta=round(cur_summary["executed_pass_rate"] - prev_summary["executed_pass_rate"], 1),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--previous", nargs="+", help="results of the previous run, for comparison")
    ap.add_argument("--known", help="known-issues.txt")
    ap.add_argument("--top", type=int, default=5, help="how many slowest tests to list")
    ap.add_argument("--out", help="write JSON here (default: stdout)")
    a = ap.parse_args()

    cur = load(a.paths)
    if cur is None:
        print("ERROR: no testng-results.xml, Allure *-result.json or TEST-*.xml found in: " + ", ".join(a.paths), file=sys.stderr)
        sys.exit(2)
    known = load_known(a.known)
    result = summarize(*cur, known, a.top)
    if a.previous:
        prev = load(a.previous)
        if prev is None:
            print("WARN: --previous given but no results found there; skipping comparison", file=sys.stderr)
        else:
            prev_summary = summarize(*prev, [], a.top)["summary"]
            result["comparison"] = compare(cur[0], prev[0], result["summary"], prev_summary)

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if not a.out:
        print(text)
        return
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)
    s = result["summary"]
    print(f"{', '.join(filter(None, s['suites']))}: {s['total']} tests - {s['passed']} passed, {s['failed']} failed, "
          f"{s['skipped']} skipped, {s['flaky']} flaky, {s['config_failures']} config failure(s). "
          f"Executed pass rate {s['executed_pass_rate']}%, duration {s['duration_s']}s.")
    for i, g in enumerate(result["groups"], 1):
        extra = f" (+{g['skipped_dependents']} skipped)" if g["skipped_dependents"] else ""
        k = f" [KNOWN {g['known_issue']['ticket']}]" if g["known_issue"] else ""
        print(f"  {i}. {g['count']} test(s){extra}{k}  {g['signature']}")
    if "comparison" in result:
        c = result["comparison"]
        print(f"vs previous: {len(c['new_failures'])} new failure(s), {len(c['fixed'])} fixed, "
              f"{len(c['still_failing'])} still failing, {len(c['newly_skipped'])} newly skipped, "
              f"pass rate {c['executed_pass_rate_delta']:+} pts.")
    print(f"Full details: {a.out}")


if __name__ == "__main__":
    main()
