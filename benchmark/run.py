#!/usr/bin/env python3
"""Benchmark harness for the Data Quality Skill (v0.2.1).

The harness runs the shipped CLI (skills/data-quality/scripts/dq.py) on a real
dataset, injects four defect types into a *temporary copy*, and compares the
violations the skill reports with the defects that were injected. The type and
max-null-percentage checks intentionally observe the existing invalid-number
and missing-value injections; they do not add second mutation mechanisms. The
skill is never modified and the datasets are never written to.

Datasets:

* default           benchmark/public/adult.csv — UCI Adult (public fixture),
                    checked against the hand-written benchmark/public/rules.yml
* ``--erpnext PATH``  an ERPNext CSV export. Its rules are derived mechanically
                    from the file — the required, numeric, and categorical
                    columns are the first suitable columns in file order — because
                    the benchmark must not invent business rules. A defect type
                    is skipped when no suitable column exists.

The corrupted copy and any generated rules live in a temporary directory that is
removed on exit, so nothing is written next to the sources. ERPNext expected
counts use the positions actually injected; duplicate expectations use the final
exact-duplicate extras relative to the source's original duplicate allowance.

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
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "data-quality" / "scripts" / "dq.py"

INJECT_PER_TYPE = 10
MAX_EVIDENCE_REFS = 10
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


def duplicate_extras(rows: list[list[str]]) -> int:
    """Return exact duplicate rows beyond the first occurrence of each key."""
    return len(rows) - len({tuple(row) for row in rows})


def duplicate_violation_positions(rows: list[list[str]], allowance: int) -> list[int]:
    """Return 1-based duplicate positions beyond the configured allowance."""
    seen: set[tuple[str, ...]] = set()
    duplicates: list[int] = []
    for position, row in enumerate(rows, start=1):
        key = tuple(row)
        if key in seen:
            duplicates.append(position)
        else:
            seen.add(key)
    return duplicates[allowance:]


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


def validate_cli_result(
    code: int,
    payload: dict | None,
    stderr: str,
    *,
    expected_exit_code: int,
    expected_status: str,
) -> list[str]:
    """Validate the CLI result before comparing benchmark check counts."""
    problems: list[str] = []
    if payload is None:
        detail = f": {stderr}" if stderr else ""
        return [f"no JSON report on stdout (CLI exit code {code}{detail})"]
    if not isinstance(payload, dict):
        return [f"JSON report is not an object (CLI exit code {code})"]

    if code != expected_exit_code:
        problems.append(
            f"CLI exit code {code}, expected {expected_exit_code}"
        )
    overall = payload.get("overall")
    if not isinstance(overall, dict):
        problems.append("payload overall is missing or is not an object")
    else:
        if overall.get("exit_code") != code:
            problems.append(
                "payload overall.exit_code "
                f"{overall.get('exit_code')!r} does not match CLI exit code {code}"
            )
        if overall.get("status") != expected_status:
            problems.append(
                f"payload status {overall.get('status')!r}, "
                f"expected {expected_status!r}"
            )
    if payload.get("errors") != []:
        problems.append(f"payload errors are not empty: {payload.get('errors')!r}")
    if not isinstance(payload.get("checks"), list):
        problems.append("payload checks is missing or is not a list")
    return problems


def check_key(check: dict) -> str:
    return f"{check['rule']}:{check.get('column') or 'dataset'}"


def expected_check(
    dimension: str,
    evaluated: int,
    violating_positions: list[int],
) -> dict:
    return {
        "dimension": dimension,
        "evaluated": evaluated,
        "violations": len(violating_positions),
        "status": (
            "not_evaluated"
            if evaluated == 0
            else ("failed" if violating_positions else "passed")
        ),
        "row_refs": violating_positions[:MAX_EVIDENCE_REFS],
        "row_refs_truncated": len(violating_positions) > MAX_EVIDENCE_REFS,
    }


def expected_dimensions(expected_checks: dict[str, dict]) -> dict[str, dict[str, Any]]:
    dimensions: dict[str, dict[str, Any]] = {
        name: {"evaluated": 0, "violations": 0}
        for name in ("completeness", "uniqueness", "validity")
    }
    for expectation in expected_checks.values():
        if expectation["status"] == "not_evaluated":
            continue
        dimension = dimensions[expectation["dimension"]]
        dimension["evaluated"] += expectation["evaluated"]
        dimension["violations"] += expectation["violations"]
    for dimension in dimensions.values():
        evaluated = dimension["evaluated"]
        violations = dimension["violations"]
        dimension["score"] = (
            None
            if evaluated == 0
            else round((evaluated - violations) / evaluated * 100, 2)
        )
    return dimensions


def validate_check_results(
    payload: dict,
    expected: dict[str, dict],
) -> list[str]:
    """Validate deterministic check fields and dimension aggregation."""
    problems: list[str] = []
    actual_checks = payload.get("checks")
    if not isinstance(actual_checks, list):
        return ["payload checks is missing or is not a list"]

    actual_by_key: dict[str, dict] = {}
    for check in actual_checks:
        if not isinstance(check, dict):
            problems.append("a report check is not an object")
            continue
        try:
            key = check_key(check)
        except KeyError as exc:
            problems.append(f"report check is missing {exc.args[0]!r}")
            continue
        if key in actual_by_key:
            problems.append(f"duplicate check in report: {key}")
        actual_by_key[key] = check

    for key in sorted(set(expected) - set(actual_by_key)):
        problems.append(f"{key}: check missing from the report")
    for key in sorted(set(actual_by_key) - set(expected)):
        problems.append(f"{key}: unexpected check in the report")

    fields = (
        "dimension",
        "evaluated",
        "violations",
        "status",
        "row_refs",
        "row_refs_truncated",
    )
    for key, expectation in expected.items():
        actual = actual_by_key.get(key)
        if actual is None:
            continue
        for field in fields:
            if actual.get(field) != expectation[field]:
                problems.append(
                    f"{key}: {field} {actual.get(field)!r}, "
                    f"expected {expectation[field]!r}"
                )
        refs = actual.get("row_refs")
        if isinstance(refs, list) and len(refs) > MAX_EVIDENCE_REFS:
            problems.append(
                f"{key}: row_refs contains {len(refs)} entries; "
                f"maximum is {MAX_EVIDENCE_REFS}"
            )

    actual_dimensions = payload.get("dimensions")
    expected_dimension_values = expected_dimensions(expected)
    if actual_dimensions != expected_dimension_values:
        problems.append(
            f"dimensions {actual_dimensions!r}, expected {expected_dimension_values!r}"
        )
    return problems


def detected_violations(payload: dict) -> dict[str, int]:
    """Failing checks as {rule:column-or-dataset -> violation count}."""
    detected: dict[str, int] = {}
    for check in payload["checks"]:
        key = check_key(check)
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
    print(f"Expected detections: {injected}")
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
        "max_null_pct:age": INJECT_PER_TYPE,
        "type:age": INJECT_PER_TYPE,
        "min:age": INJECT_PER_TYPE,
        "allowed:workclass": INJECT_PER_TYPE,
        "max_duplicate_rows:dataset": INJECT_PER_TYPE,
    }
    duplicate_allowance = duplicate_extras(rows)
    age_present = [
        position + 1
        for position, row in enumerate(corrupted)
        if not is_missing(row[index["age"]])
    ]
    workclass_present = [
        position + 1
        for position, row in enumerate(corrupted)
        if not is_missing(row[index["workclass"]])
    ]
    blank_age_refs = [position + 1 for position in blank_age]
    bad_age_refs = [position + 1 for position in bad_age]
    bad_workclass_refs = [position + 1 for position in bad_workclass]
    duplicate_refs = duplicate_violation_positions(corrupted, duplicate_allowance)
    expected_checks = {
        "max_duplicate_rows:dataset": expected_check(
            "uniqueness", len(corrupted), duplicate_refs
        ),
        "required:age": expected_check(
            "completeness", len(corrupted), blank_age_refs
        ),
        "max_null_pct:age": expected_check(
            "completeness", len(corrupted), blank_age_refs
        ),
        "type:age": expected_check("validity", len(age_present), bad_age_refs),
        "min:age": expected_check("validity", len(age_present), bad_age_refs),
        "allowed:workclass": expected_check(
            "validity", len(workclass_present), bad_workclass_refs
        ),
    }

    with tempfile.TemporaryDirectory(prefix="dq-bench-public-") as tmp:
        corrupted_path = Path(tmp) / "adult-corrupted.csv"
        write_csv(corrupted_path, header, corrupted)
        code, payload, stderr = run_skill(corrupted_path, rules)

    unchanged = sha256(source) == before and \
        sorted(p.name for p in source.parent.iterdir()) == listing
    problems = validate_cli_result(
        code,
        payload,
        stderr,
        expected_exit_code=1,
        expected_status="failed",
    )
    injected = observed = unexpected = 0
    if payload is not None and isinstance(payload, dict) \
            and isinstance(payload.get("checks"), list):
        injected, observed, unexpected, problems_checks = compare(expected, payload)
        problems += problems_checks
        problems += validate_check_results(payload, expected_checks)
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
    rules: dict[str, object] = {
        "required": None,
        "numeric": None,
        "category": None,
        "type": None,
    }
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
            rules["type"] = "number"
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

    notes["duplicate_allowance"] = duplicate_extras(rows)
    return rules, notes, skipped


def rules_yaml(rules: dict) -> str:
    lines: list[str] = []
    if rules.get("max_duplicate_rows") is not None:
        lines += ["dataset:", f"  max_duplicate_rows: {rules['max_duplicate_rows']}"]
    lines.append("columns:")
    if rules["required"]:
        lines += [
            f"  {rules['required']}:",
            "    required: true",
            "    max_null_pct: 0",
        ]
    if rules["numeric"]:
        lines += [
            f"  {rules['numeric']}:",
            f"    type: {rules['type']}",
            f"    min: {rules['min']}",
        ]
    if rules["category"]:
        lines += [f"  {rules['category']}:", "    allowed:"]
        lines += [f"      - {json.dumps(value)}" for value in rules["allowed"]]
    return "\n".join(lines) + "\n"


def run_erpnext(path: Path, verbose: bool) -> bool:
    header, rows = read_csv(path)
    before, listing = sha256(path), sorted(p.name for p in path.parent.iterdir())

    profile_code, profile_payload, profile_err = run_skill(path)
    profile_problems = validate_cli_result(
        profile_code,
        profile_payload,
        profile_err,
        expected_exit_code=0,
        expected_status="inspected",
    )
    if profile_problems:
        unchanged = sha256(path) == before and \
            sorted(p.name for p in path.parent.iterdir()) == listing
        report("ERPNext", len(rows), 0, 0, 0, unchanged)
        for problem in profile_problems:
            print(f"  problem: profile {problem}", file=sys.stderr)
        if not unchanged:
            print("  problem: the source dataset changed", file=sys.stderr)
        return False

    rules, notes, skipped = derive_rules(header, rows)
    expected: dict[str, int] = {}
    taken: set[int] = set()
    corrupted = [list(row) for row in rows]
    index = {name: position for position, name in enumerate(header)}
    required_positions: list[int] = []
    numeric_positions: list[int] = []
    category_positions: list[int] = []

    if rules["required"]:
        target = index[rules["required"]]
        required_positions = pick_positions(len(rows), INJECT_PER_TYPE, taken)
        for position in required_positions:
            corrupted[position][target] = MISSING_VALUE
        expected[f"required:{rules['required']}"] = len(required_positions)
        expected[f"max_null_pct:{rules['required']}"] = len(required_positions)
    if rules["numeric"]:
        target = index[rules["numeric"]]
        numeric_positions = pick_positions(len(rows), INJECT_PER_TYPE, taken)
        for position in numeric_positions:
            corrupted[position][target] = INVALID_NUMBER
        expected[f"min:{rules['numeric']}"] = len(numeric_positions)
        expected[f"type:{rules['numeric']}"] = len(numeric_positions)
    if rules["category"]:
        target = index[rules["category"]]
        category_positions = pick_positions(len(rows), INJECT_PER_TYPE, taken)
        for position in category_positions:
            corrupted[position][target] = INVALID_CATEGORY
        expected[f"allowed:{rules['category']}"] = len(category_positions)

    duplicate_allowance = duplicate_extras(rows)
    copied = pick_positions(len(rows), INJECT_PER_TYPE, taken)
    corrupted += [list(rows[position]) for position in copied]
    rules["max_duplicate_rows"] = duplicate_allowance
    duplicate_refs = duplicate_violation_positions(corrupted, duplicate_allowance)
    expected["max_duplicate_rows:dataset"] = len(duplicate_refs)

    expected_checks = {
        "max_duplicate_rows:dataset": expected_check(
            "uniqueness", len(corrupted), duplicate_refs
        )
    }
    if rules["required"]:
        required_refs = [position + 1 for position in required_positions]
        expected_checks[f"required:{rules['required']}"] = expected_check(
            "completeness", len(corrupted), required_refs
        )
        expected_checks[f"max_null_pct:{rules['required']}"] = expected_check(
            "completeness", len(corrupted), required_refs
        )
    if rules["numeric"]:
        numeric_target = index[rules["numeric"]]
        numeric_evaluated = sum(
            not is_missing(row[numeric_target]) for row in corrupted
        )
        numeric_refs = [position + 1 for position in numeric_positions]
        expected_checks[f"type:{rules['numeric']}"] = expected_check(
            "validity", numeric_evaluated, numeric_refs
        )
        expected_checks[f"min:{rules['numeric']}"] = expected_check(
            "validity", numeric_evaluated, numeric_refs
        )
    if rules["category"]:
        category_target = index[rules["category"]]
        category_evaluated = sum(
            not is_missing(row[category_target]) for row in corrupted
        )
        category_refs = [position + 1 for position in category_positions]
        expected_checks[f"allowed:{rules['category']}"] = expected_check(
            "validity", category_evaluated, category_refs
        )

    with tempfile.TemporaryDirectory(prefix="dq-bench-erpnext-") as tmp:
        corrupted_path = Path(tmp) / "erpnext-corrupted.csv"
        rules_path = Path(tmp) / "erpnext-rules.yml"
        write_csv(corrupted_path, header, corrupted)
        rules_path.write_text(rules_yaml(rules), encoding="utf-8")
        code, payload, stderr = run_skill(corrupted_path, rules_path)

    unchanged = sha256(path) == before and \
        sorted(p.name for p in path.parent.iterdir()) == listing
    injected = sum(expected.values())
    expected_exit_code = 1 if injected else 0
    expected_status = "failed" if injected else (
        "passed" if rows else "inspected"
    )
    problems = validate_cli_result(
        code,
        payload,
        stderr,
        expected_exit_code=expected_exit_code,
        expected_status=expected_status,
    )
    observed = unexpected = 0
    if payload is not None and isinstance(payload, dict) \
            and isinstance(payload.get("checks"), list):
        _, observed, unexpected, problems_checks = compare(expected, payload)
        problems += problems_checks
        problems += validate_check_results(payload, expected_checks)

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
    if (
        verbose
        and isinstance(payload, dict)
        and isinstance(payload.get("checks"), list)
    ):
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
