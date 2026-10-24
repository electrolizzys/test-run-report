#!/usr/bin/env python3
import json
import re
import sys

REQUIRED = ["Headline", "Totals", "Failures by cause", "Skipped tests", "Flaky tests",
            "Risks and next steps", "Failing tests"]
RECOMMENDATIONS = ("GO WITH RISKS", "NO-GO", "INCONCLUSIVE", "GO")
TOTAL_ROWS = {
    "Total": "total", "Passed": "passed", "Failed": "failed", "Skipped": "skipped",
    "Flaky (passed on retry)": "flaky", "Config failures": "config_failures",
    "Pass rate (executed)": "executed_pass_rate",
}


def sections(text):
    parts = re.split(r"^##\s+(.+?)\s*$", text, flags=re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def num(cell):
    m = re.search(r"-?\d+(?:\.\d+)?", cell)
    return float(m.group()) if m else None


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    report_path, data_path = sys.argv[1], sys.argv[2]
    text = open(report_path, encoding="utf-8").read()
    data = json.load(open(data_path, encoding="utf-8"))
    s = data["summary"]
    problems = []

    left = sorted(set(re.findall(r"\{\{[^}]+\}\}", text)))
    if left:
        problems.append("unfilled template fields: " + ", ".join(left))

    rec = re.search(r"^\*\*Recommendation:\*\*\s*(.+)$", text, flags=re.M)
    if not rec:
        problems.append("missing '**Recommendation:** ...' line")
    elif not any(rec.group(1).strip().upper().startswith(r) for r in RECOMMENDATIONS):
        problems.append(f"recommendation must start with one of {RECOMMENDATIONS}")
    dec = re.search(r"^\*\*Decided by:\*\*\s*(\S.*)$", text, flags=re.M)
    if not dec:
        problems.append("missing '**Decided by:** <name>' — the recommendation is a human decision")

    secs = sections(text)
    for name in REQUIRED:
        if not any(k.startswith(name) for k in secs):
            problems.append(f"missing section '## {name}'")
    if "comparison" in data and not any(k.startswith("Compared with previous run") for k in secs):
        problems.append("data has a previous-run comparison but the report has no '## Compared with previous run'")

    totals = next((v for k, v in secs.items() if k.startswith("Totals")), "")
    for label, key in TOTAL_ROWS.items():
        row = re.search(r"^\|\s*" + re.escape(label) + r"\s*\|\s*([^|]+)\|", totals, flags=re.M)
        if not row:
            problems.append(f"Totals table is missing the '{label}' row")
            continue
        got, want = num(row.group(1)), s[key]
        if got is None or abs(got - float(want)) > 0.05:
            problems.append(f"Totals '{label}' says {row.group(1).strip()} but the data says {want}")

    for f in data["failures"]:
        if f["id"] not in text and f["method"] not in text:
            problems.append(f"failing test not mentioned in the report: {f['id']}")
    for fl in data.get("flaky", []):
        if fl["id"].split("#")[-1] not in text:
            problems.append(f"flaky test not mentioned in the report: {fl['id']}")

    if problems:
        for p in problems:
            print(f"{report_path}: {p}")
        sys.exit(1)
    print(f"{report_path}: OK — numbers match {data_path}, every failure is accounted for")


if __name__ == "__main__":
    main()
