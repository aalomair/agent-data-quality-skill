#!/usr/bin/env python3
"""Benchmark harness for the Data Quality Skill (v0.1.0).

The harness runs the shipped CLI (skills/data-quality/scripts/dq.py) on a real
dataset, injects four defect types into a *temporary copy*, and compares the
violations the skill reports with the defects that were injected. The skill is
never modified and the datasets are never written to.

Datasets:

* default           benchmark/public/adult.csv — UCI Adult (public fixture),
                    checked against the hand-written benchmark/public/rules.yml
* ``--erpnext PATH``  an ERPNext CSV export. Its rules are derived mechanically
                    from the file — the required, numeric, and categorical
                    columns are the first suitable columns in file order — because
                    the benchmark must not invent business rules. A defect type
                    is skipped when no suitable column exists.

The corrupted copy and any generated rules live in a temporary directory that is
removed on exit, so nothing is written next to the sources.

Run with an interpreter that has the skill's dependencies:

    .venv/bin/python benchmark/run.py
    .venv/bin/python benchmark/run.py --erpnext benchmark/private/erpnext-export.csv
    .venv/bin/python benchmark/run.py --verbose
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "data-quality" / "scripts" / "dq.py"

INJECT_PER_TYPE = 10
MISSING_VALUE = ""                     # empty cell: missing for the skill
INVALID_NUMBER = "not-a-number"        # non-missing, non-numeric
INVALID_CATEGORY = "not-a-category"    # non-missing, outside the allowed set

NUMBER_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\Z")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        records = list(csv.reader(handle))
    if not records:
        raise SystemExit(f"{path}: no header row")
    return records[0], records[1:]


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def is_missing(value: str) -> bool:
    """Missing by the skill's definition: empty or whitespace-only."""
    return value.strip() == ""


def parse_number(value: str) -> float | None:
    """Mirror of the skill's numeric view: trim, then full-string numeric match."""
    text = value.strip()
    return float(text) if NUMBER_RE.match(text) else None


def pick_positions(row_count: int, count: int, taken: set[int]) -> list[int]:
    """Deterministic, spread-out row positions that are not already used."""
    step = max(1, row_count // (count * 4))
    picked: list[int] = []
    position = 0
    while len(picked) < count and position < row_count:
        if position not in taken:
            picked.append(position)
            taken.add(position)
        position += step
    return picked


def strict_json(text: str) -> dict:
    def reject(constant):
        raise ValueError(f"non-standard JSON constant in output: {constant}")

    return json.loads(text, parse_constant=reject)


def run_skill(source: Path, rules: Path | None = None) -> tuple[int, dict | None, str]:
    command = [sys.executable, str(SKILL), str(source)]
    if rules is not None:
        command += ["--rules", str(rules)]
    proc = subprocess.run(command, capture_output=True, text=True)
    try:
        payload = strict_json(proc.stdout)
    except Exception:  # noqa: BLE001 - reported as a failed check below
        payload = None
    return proc.returncode, payload, proc.stderr.strip()


def detected_violations(payload: dict) -> dict[str, int]:
    """Failing checks as {rule:column-or-dataset -> violation count}."""
    detected: dict[str, int] = {}
    for check in payload["checks"]:
        key = f"{check['rule']}:{check.get('column') or 'dataset'}"
        detected[key] = check["violations"] if check["status"] == "failed" else 0
    return detected


def compare(expected: dict[str, int], payload: dict) -> tuple[int, int, int, list[str]]:
    detected = detected_violations(payload)
    injected = sum(expected.values())
    observed = sum(detected.values())
    unexpected = 0
    problems: list[str] = []
    for key, count in detected.items():
        want = expected.get(key, 0)
        if count > want:
            unexpected += count - want
            problems.append(f"{key}: {count} violation(s), expected {want}")
        elif count < want:
            problems.append(f"{key}: {count} violation(s) but {want} injected")
    for key, want in expected.items():
        if key not in detected:
            problems.append(f"{key}: check missing from the report (expected {want})")
    return injected, observed, unexpected, problems


def report(name: str, rows: int | None, injected: int, observed: int,
           unexpected: int, unchanged: bool) -> None:
    print(name)
    if rows is not None:
        print(f"Rows: {rows:,}")
    print(f"Injected: {injected}")
    print(f"Detected: {observed}")
    print(f"Unexpected: {unexpected}")
    print(f"Source unchanged: {'PASS' if unchanged else 'FAIL'}")


# --------------------------------------------------------------------------- #
# public benchmark — UCI Adult
# --------------------------------------------------------------------------- #
def run_public(verbose: bool) -> bool:
    source = REPO / "benchmark" / "public" / "adult.csv"
    rules = REPO / "benchmark" / "public" / "rules.yml"
    header, rows = read_csv(source)
    index = {name: position for position, name in enumerate(header)}
    before, listing = sha256(source), sorted(p.name for p in source.parent.iterdir())

    taken: set[int] = set()
    blank_age = pick_positions(len(rows), INJECT_PER_TYPE, taken)
    bad_age = pick_positions(len(rows), INJECT_PER_TYPE, taken)
    bad_workclass = pick_positions(len(rows), INJECT_PER_TYPE, taken)
    copied = pick_positions(len(rows), INJECT_PER_TYPE, taken)

    corrupted = [list(row) for row in rows]
    for position in blank_age:
        corrupted[position][index["age"]] = MISSING_VALUE
    for position in bad_age:
        corrupted[position][index["age"]] = INVALID_NUMBER
    for position in bad_workclass:
        corrupted[position][index["workclass"]] = INVALID_CATEGORY
    corrupted += [list(rows[position]) for position in copied]

    expected = {
        "required:age": INJECT_PER_TYPE,
        "min:age": INJECT_PER_TYPE,
        "allowed:workclass": INJECT_PER_TYPE,
        "max_duplicate_rows:dataset": INJECT_PER_TYPE,
    }

    with tempfile.TemporaryDirectory(prefix="dq-bench-public-") as tmp:
        corrupted_path = Path(tmp) / "adult-corrupted.csv"
        write_csv(corrupted_path, header, corrupted)
        code, payload, stderr = run_skill(corrupted_path, rules)

    unchanged = sha256(source) == before and \
        sorted(p.name for p in source.parent.iterdir()) == listing
    problems = ["no JSON report on stdout"] if payload is None else []
    if payload is not None and payload["overall"]["status"] not in {"failed", "passed"}:
        problems.append(f"unexpected report status {payload['overall']['status']!r}: {stderr}")
    injected = observed = unexpected = 0
    if payload is not None:
        injected, observed, unexpected, problems_checks = compare(expected, payload)
        problems += problems_checks
    report("UCI Adult", None, injected, observed, unexpected, unchanged)
    return finish(problems, unchanged, verbose, payload, expected)


# --------------------------------------------------------------------------- #
# ERPNext benchmark — mechanically derived rules
# --------------------------------------------------------------------------- #
def derive_rules(header: list[str], rows: list[list[str]]
                 ) -> tuple[dict, dict[str, object], list[str]]:
    """Pick the first suitable columns; never invent business rules."""
    columns = list(zip(*rows)) if rows else [[] for _ in header]
    skipped: list[str] = []
    rules: dict[str, object] = {"required": None, "numeric": None, "category": None}
    notes: dict[str, object] = {}

    for position, name in enumerate(header):
        values = list(columns[position])
        if any(is_missing(value) for value in values):
            continue
        rules["required"] = name
        notes["required_column"] = name
        break
    else:
        skipped.append("missing required values (no column without empty cells)")

    for position, name in enumerate(header):
        if name == rules["required"]:
            continue
        values = [value for value in columns[position] if not is_missing(value)]
        parsed = [parse_number(value) for value in values]
        if values and all(number is not None for number in parsed):
            numeric_values = [number for number in parsed if number is not None]
            rules["numeric"] = name
            rules["min"] = min(numeric_values)
            notes["numeric_column"] = name
            notes["min"] = min(numeric_values)
            break
    if rules["numeric"] is None:
        skipped.append("invalid numeric values (no fully numeric column)")

    for position, name in enumerate(header):
        if name in {rules["required"], rules["numeric"]}:
            continue
        values = [value for value in columns[position] if not is_missing(value)]
        if len(values) != len(columns[position]) or not values:
            continue
        if all(parse_number(value) is not None for value in values):
            continue
        distinct = sorted(set(values))
        if 2 <= len(distinct) <= 50:
            rules["category"] = name
            rules["allowed"] = distinct
            notes["category_column"] = name
            notes["allowed_values"] = len(distinct)
            break
    if rules["category"] is None:
        skipped.append("invalid categorical values (no low-cardinality text column)")

    notes["duplicate_allowance"] = len(rows) - len({tuple(row) for row in rows})
    return rules, notes, skipped


def rules_yaml(rules: dict) -> str:
    lines: list[str] = []
    if rules.get("max_duplicate_rows") is not None:
        lines += ["dataset:", f"  max_duplicate_rows: {rules['max_duplicate_rows']}"]
    lines.append("columns:")
    if rules["required"]:
        lines += [f"  {rules['required']}:", "    required: true"]
    if rules["numeric"]:
        lines += [f"  {rules['numeric']}:", f"    min: {rules['min']}"]
    if rules["category"]:
        lines += [f"  {rules['category']}:", "    allowed:"]
        lines += [f"      - {json.dumps(value)}" for value in rules["allowed"]]
    return "\n".join(lines) + "\n"


def run_erpnext(path: Path, verbose: bool) -> bool:
    header, rows = read_csv(path)
    before, listing = sha256(path), sorted(p.name for p in path.parent.iterdir())

    profile_code, profile_payload, profile_err = run_skill(path)
    if profile_payload is None:
        print("ERPNext")
        print(f"Rows: {len(rows):,}")
        print("Injected: 0")
        print("Detected: 0")
        print("Unexpected: 0")
        print("Source unchanged: FAIL")
        print(f"error: the skill produced no JSON report (exit {profile_code}): {profile_err}",
              file=sys.stderr)
        return False

    rules, notes, skipped = derive_rules(header, rows)
    expected: dict[str, int] = {}
    taken: set[int] = set()
    corrupted = [list(row) for row in rows]
    index = {name: position for position, name in enumerate(header)}

    if rules["required"]:
        target = index[rules["required"]]
        for position in pick_positions(len(rows), INJECT_PER_TYPE, taken):
            corrupted[position][target] = MISSING_VALUE
        expected[f"required:{rules['required']}"] = INJECT_PER_TYPE
    if rules["numeric"]:
        target = index[rules["numeric"]]
        for position in pick_positions(len(rows), INJECT_PER_TYPE, taken):
            corrupted[position][target] = INVALID_NUMBER
        expected[f"min:{rules['numeric']}"] = INJECT_PER_TYPE
    if rules["category"]:
        target = index[rules["category"]]
        for position in pick_positions(len(rows), INJECT_PER_TYPE, taken):
            corrupted[position][target] = INVALID_CATEGORY
        expected[f"allowed:{rules['category']}"] = INJECT_PER_TYPE

    copied = pick_positions(len(rows), INJECT_PER_TYPE, taken)
    corrupted += [list(rows[position]) for position in copied]
    rules["max_duplicate_rows"] = notes["duplicate_allowance"]
    expected["max_duplicate_rows:dataset"] = INJECT_PER_TYPE

    with tempfile.TemporaryDirectory(prefix="dq-bench-erpnext-") as tmp:
        corrupted_path = Path(tmp) / "erpnext-corrupted.csv"
        rules_path = Path(tmp) / "erpnext-rules.yml"
        write_csv(corrupted_path, header, corrupted)
        rules_path.write_text(rules_yaml(rules), encoding="utf-8")
        code, payload, stderr = run_skill(corrupted_path, rules_path)

    unchanged = sha256(path) == before and \
        sorted(p.name for p in path.parent.iterdir()) == listing
    problems = ["no JSON report on stdout"] if payload is None else []
    injected = observed = unexpected = 0
    if payload is not None:
        injected, observed, unexpected, problems = compare(expected, payload)

    report("ERPNext", len(rows), injected, observed, unexpected, unchanged)
    for item in skipped:
        print(f"Skipped: {item}")
    if verbose:
        print(f"  derived rules: required={rules['required']!r} "
              f"numeric={rules['numeric']!r} (min={rules.get('min')}) "
              f"categorical={rules['category']!r} "
              f"({notes.get('allowed_values')} allowed values, "
              f"duplicate allowance {notes['duplicate_allowance']})")
    return finish(problems, unchanged, verbose, payload, expected)


def finish(problems: list[str], unchanged: bool, verbose: bool,
           payload: dict | None, expected: dict[str, int]) -> bool:
    if verbose and payload is not None:
        for key, count in sorted(detected_violations(payload).items()):
            print(f"  {key}: {count} (expected {expected.get(key, 0)})")
    for problem in problems:
        print(f"  problem: {problem}", file=sys.stderr)
    if not unchanged:
        print("  problem: the source dataset changed", file=sys.stderr)
    return not problems and unchanged


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--erpnext", metavar="CSV",
                        help="ERPNext CSV export to benchmark (rules are derived "
                             "mechanically from the file)")
    parser.add_argument("--verbose", action="store_true",
                        help="also print per-check counts and derived rules")
    args = parser.parse_args(argv)

    if not SKILL.is_file():
        print(f"skill not found at {SKILL}", file=sys.stderr)
        return 2

    ok = True
    if args.erpnext:
        path = Path(args.erpnext).expanduser()
        if not path.is_file():
            print(f"ERPNext export not found: {path}", file=sys.stderr)
            return 2
        ok &= run_erpnext(path, args.verbose)
    else:
        ok &= run_public(args.verbose)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
