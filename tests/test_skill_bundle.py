"""Skill-bundle contracts: dependencies, error contract, OUTPUT.md, copies, versions.

These tests keep the documentation and the engine from drifting: the
dependency ranges a reader installs, the documented JSON fields, the error
behaviour of a dependency-free interpreter, the standalone copy of the skill,
and the published version must all match the code and CI configuration.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "data-quality"
DQ_PATH = SKILL_DIR / "scripts" / "dq.py"
REQUIREMENTS = SKILL_DIR / "scripts" / "requirements.txt"
SKILL_MD = SKILL_DIR / "SKILL.md"
OUTPUT_MD = SKILL_DIR / "references" / "OUTPUT.md"
RULES_MD = SKILL_DIR / "references" / "RULES.md"
README = REPO_ROOT / "README.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

SAMPLE_CSV = (
    "id,status,amount,code\n"
    "1,Closed,10.5,AB-1\n"
    "2,Open,,CD-2\n"
    "2,Open,7,CD-2\n"
    "4,Pending,3,ZZ\n"
)

FULL_RULES = """\
dataset:
  max_duplicate_rows: 0
  unique_together:
    - [id, status]
  conditional_required:
    - when:
        column: status
        equals: Closed
      then_required: amount
columns:
  id:
    required: true
    unique: true
    type: integer
  status:
    required: true
    allowed: [Open, Closed, Pending]
  amount:
    max_null_pct: 20
    min: 0
    max: 100
  code:
    regex: "[A-Z]{2}-[0-9]"
"""


def _load_module():
    spec = importlib.util.spec_from_file_location("dq_bundle_under_test", DQ_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["dq_bundle_under_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dq():
    return _load_module()


@pytest.fixture()
def sample(tmp_path):
    data = tmp_path / "sample.csv"
    rules = tmp_path / "rules.yml"
    data.write_text(SAMPLE_CSV, encoding="utf-8")
    rules.write_text(FULL_RULES, encoding="utf-8")
    return data, rules


# ---------------------------------------------------------------------------
# Dependency documentation
# ---------------------------------------------------------------------------


def _requirement_ranges() -> list[tuple[str, str, bool]]:
    """(name, range, optional) for every dependency pin in requirements.txt."""
    parsed = []
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        optional = line.startswith("#")
        candidate = line.lstrip("# ").strip()
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_.-]*)>=[^#\s]+(?:,[^#\s]+)*", candidate)
        if match:
            parsed.append((match.group(1), candidate, optional))
    return parsed


def test_requirements_file_lists_every_runtime_dependency():
    ranges = {name: (value, optional) for name, value, optional in _requirement_ranges()}
    assert set(ranges) == {"pandas", "openpyxl", "PyYAML", "pyarrow"}
    assert ranges["pandas"] == ("pandas>=2.2,<4", False)
    assert ranges["PyYAML"] == ("PyYAML>=6.0,<7", False)
    assert ranges["openpyxl"] == ("openpyxl>=3.1,<4", False)
    assert ranges["pyarrow"] == ("pyarrow>=15", True)


def test_dependency_ranges_are_documented_identically():
    skill = SKILL_MD.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    for _name, requirement, optional in _requirement_ranges():
        assert f"`{requirement}`" in skill, f"SKILL.md must document {requirement}"
        assert f"`{requirement}`" in readme, f"README.md must document {requirement}"
        if optional:
            assert "optional" in skill.lower() and "optional" in readme.lower()


def test_both_docs_say_the_skill_never_installs_packages_and_who_decides():
    for path in (SKILL_MD, README):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "never install" in lowered or "installs nothing" in lowered, path.name
        assert "decide" in lowered, path.name
        assert "python -c \"import pandas, yaml\"" in text, path.name
        assert "pip install -r" in text, path.name


def test_missing_dependency_behaviour_is_documented():
    for path in (SKILL_MD, README):
        text = path.read_text(encoding="utf-8")
        assert "missing_dependency" in text, path.name
        assert "exit" in text.lower() and "2" in text, path.name


# ---------------------------------------------------------------------------
# Missing dependencies: the JSON contract survives a bare interpreter
# ---------------------------------------------------------------------------

_BLOCKER = """
import runpy
import sys

BLOCKED = {blocked!r}


class Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError("blocked for test: " + fullname)
        return None


sys.meta_path.insert(0, Blocker())
sys.argv = ["dq.py", {source!r}]
runpy.run_path({dq_path!r}, run_name="__main__")
"""


def _run_blocked(source: Path, blocked: set[str]) -> subprocess.CompletedProcess:
    code = _BLOCKER.format(blocked=blocked, source=str(source), dq_path=str(DQ_PATH))
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=source.parent,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize(
    "blocked,expected_names",
    [
        ({"pandas", "yaml"}, "pandas, yaml"),
        ({"pandas"}, "pandas"),
        ({"yaml"}, "yaml"),
    ],
)
def test_missing_dependency_emits_json_error_and_exit_2(tmp_path, blocked, expected_names):
    data = tmp_path / "data.csv"
    data.write_text(SAMPLE_CSV, encoding="utf-8")

    result = _run_blocked(data, blocked)

    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["errors"][0]["code"] == "missing_dependency"
    message = payload["errors"][0]["message"]
    assert expected_names in message
    assert "requirements.txt" in message
    assert payload["overall"]["status"] == "error"
    assert payload["overall"]["exit_code"] == 2
    assert payload["source"] is None and payload["selection"] is None
    assert payload["profile"] is None
    assert payload["schema_version"] == "1.0"
    assert "Traceback" not in result.stdout
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "[missing_dependency]" in stderr_lines[0]


# ---------------------------------------------------------------------------
# run() parity with the CLI
# ---------------------------------------------------------------------------


def _run_cli(source: Path, rules: Path | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(DQ_PATH), str(source)]
    if rules is not None:
        args += ["--rules", str(rules)]
    return subprocess.run(
        args, cwd=source.parent, capture_output=True, text=True, timeout=120, check=False
    )


@pytest.mark.parametrize(
    "case",
    ["passing", "violations", "input_error", "rules_error"],
)
def test_run_matches_cli_payload(dq, tmp_path, case):
    data = tmp_path / "data.csv"
    rules = tmp_path / "rules.yml"

    if case == "passing":
        data.write_text("id,name\n1,a\n2,b\n", encoding="utf-8")
        rules.write_text("columns:\n  id:\n    required: true\n", encoding="utf-8")
    elif case == "violations":
        data.write_text(SAMPLE_CSV, encoding="utf-8")
        rules.write_text(FULL_RULES, encoding="utf-8")
    elif case == "input_error":
        data.write_text(SAMPLE_CSV, encoding="utf-8")
        rules = None
        missing = tmp_path / "missing.csv"
        cli = _run_cli(missing)
        payload = dq.run(str(missing))
        assert payload == json.loads(cli.stdout)
        assert payload["errors"][0]["code"] == "source_not_found"
        assert payload["overall"]["exit_code"] == 2
        assert cli.returncode == 2
        return
    else:  # rules_error
        data.write_text(SAMPLE_CSV, encoding="utf-8")
        rules.write_text("columns:\n  id:\n    unknown_rule: true\n", encoding="utf-8")

    before = {p: p.read_bytes() for p in (data, rules) if p is not None}
    cli = _run_cli(data, rules)
    payload = dq.run(str(data), None if rules is None else str(rules))

    assert payload == json.loads(cli.stdout)
    assert payload["overall"]["exit_code"] == cli.returncode
    for path, content in before.items():
        assert path.read_bytes() == content, f"{path.name} was modified"


def test_run_never_raises_on_unexpected_arguments(dq, tmp_path):
    # A directory source is a structured error, not an exception.
    payload = dq.run(str(tmp_path))
    assert payload["errors"][0]["code"] == "invalid_source"
    assert payload["overall"]["exit_code"] == 2


# ---------------------------------------------------------------------------
# OUTPUT.md matches the real payload
# ---------------------------------------------------------------------------


def _field_index() -> dict[str, list[str]]:
    text = OUTPUT_MD.read_text(encoding="utf-8")
    section = text.split("## Field index (machine-checked)", 1)[1]
    block = section.split("```text", 1)[1].split("```", 1)[0]
    index = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        key, values = line.split(":", 1)
        index[key.strip()] = [value.strip() for value in values.split(",")]
    return index


def _text_payload(dq, tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("alpha\n\nbeta\nbeta\n", encoding="utf-8")
    return dq.run(str(text))


def _xlsx_payload(dq, tmp_path):
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Data"
    sheet.append(["value", "other"])
    sheet.append([1, "=A2+1"])
    sheet.append([2, "merged"])
    sheet.merge_cells("B2:B3")
    path = tmp_path / "book.xlsx"
    book.save(path)
    return dq.run(str(path), sheet="Data")


def _payloads(dq, tmp_path) -> dict[str, dict]:
    data = tmp_path / "sample.csv"
    rules = tmp_path / "rules.yml"
    data.write_text(SAMPLE_CSV, encoding="utf-8")
    rules.write_text(FULL_RULES, encoding="utf-8")
    empty = tmp_path / "empty.csv"
    empty.write_text("id,name\n", encoding="utf-8")
    empty_rules = tmp_path / "empty.yml"
    empty_rules.write_text("columns:\n  id:\n    required: true\n", encoding="utf-8")
    passing_rules = tmp_path / "passing.yml"
    passing_rules.write_text("columns:\n  id:\n    required: true\n", encoding="utf-8")
    return {
        "full": dq.run(str(data), str(rules), examples=2),
        "text": _text_payload(dq, tmp_path),
        "xlsx": _xlsx_payload(dq, tmp_path),
        "empty": dq.run(str(empty), str(empty_rules)),
        "passing": dq.run(str(data), str(passing_rules)),
        "error": dq.run(str(tmp_path / "nope.csv")),
    }


def test_output_reference_documents_the_real_payload(dq, tmp_path):
    index = _field_index()
    payloads = _payloads(dq, tmp_path)
    full = payloads["full"]

    assert set(index["top_level"]) == set(full)
    assert set(index["source"]) == set(full["source"])
    assert set(index["selection"]) == set(full["selection"])
    assert set(index["selection_rules"]) == set(full["selection"]["rules"])

    profile = full["profile"]
    assert set(index["column_profile"]) == set(profile["column_profiles"][0])
    assert set(index["numeric"]) == set(
        next(p for p in profile["column_profiles"] if p["numeric"])["numeric"]
    )
    assert set(index["string_length"]) == set(
        next(p for p in profile["column_profiles"] if p["string_length"])["string_length"]
    )

    text_profile = payloads["text"]["profile"]["text"]
    assert set(index["text_profile"]) == set(text_profile)
    assert set(index["text_control"]) == set(text_profile["unusual_control_characters"])

    check_keys = set()
    for payload in payloads.values():
        for check in payload["checks"]:
            check_keys.update(check)
    assert set(index["check"]) == check_keys

    assert set(index["dimension"]) == set(full["dimensions"]["completeness"])
    assert set(index["overall"]) == set(full["overall"])
    for payload in payloads.values():
        if payload["errors"]:
            assert set(index["error"]) == set(payload["errors"][0])
        for warning in payload["warnings"]:
            assert set(index["warning"]) == set(warning)


def test_output_reference_statuses_exit_codes_and_error_codes_match(dq, tmp_path):
    index = _field_index()
    payloads = _payloads(dq, tmp_path)

    observed_check_statuses = {
        check["status"] for payload in payloads.values() for check in payload["checks"]
    }
    observed_overall_statuses = {payload["overall"]["status"] for payload in payloads.values()}
    assert observed_check_statuses == set(index["check_status"])
    assert observed_overall_statuses == set(index["overall_status"])

    observed_exit_codes = {payload["overall"]["exit_code"] for payload in payloads.values()}
    assert observed_exit_codes == {int(code) for code in index["exit_codes"]}

    source = ast.parse(DQ_PATH.read_text(encoding="utf-8"))
    codes = set()
    for node in ast.walk(source):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        if name in {"DqError", "error_payload"} and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                codes.add(first.value)
    assert codes == set(index["error_codes"])
    assert payloads["error"]["errors"][0]["code"] in codes


def test_skill_md_carries_the_dashboard_and_results_rules():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "references/OUTPUT.md" in text
    for phrase in (
        "new file",
        "saved JSON",
        "global score",
        "not assessed",
        "confirmed",
        "candidate",
        "consent",
        "outside the source data location",
        "Comprehensive assessments",
        "Supported but not assessed",
        "every rule family",
        "outside the engine's checks",
        "Data privacy",
        "Never read, print, sample, or open the source data yourself",
    ):
        assert phrase.lower() in text.lower(), phrase


# ---------------------------------------------------------------------------
# Standalone copy and version consistency
# ---------------------------------------------------------------------------


def test_standalone_copy_produces_identical_output(tmp_path):
    copy_root = tmp_path / "copy"
    copy_skill = copy_root / "data-quality"
    shutil.copytree(
        SKILL_DIR,
        copy_skill,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    assert not (copy_skill / "scripts" / "__pycache__").exists()

    repo_run = tmp_path / "repo-run"
    copy_run = tmp_path / "copy-run"
    for run_dir in (repo_run, copy_run):
        run_dir.mkdir()
        (run_dir / "data.csv").write_text(SAMPLE_CSV, encoding="utf-8")
        (run_dir / "rules.yml").write_text(FULL_RULES, encoding="utf-8")

    def invoke(dq_path: Path, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(dq_path), "data.csv", "--rules", "rules.yml", "--examples", "2"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    repo = invoke(SKILL_DIR / "scripts" / "dq.py", repo_run)
    copied = invoke(copy_skill / "scripts" / "dq.py", copy_run)

    assert repo.returncode == copied.returncode == 1
    assert repo.stdout == copied.stdout
    assert repo.stderr == copied.stderr
    assert set(p.relative_to(copy_skill).as_posix() for p in copy_skill.rglob("*") if p.is_file()) == {
        "LICENSE",
        "SKILL.md",
        "scripts/dq.py",
        "scripts/requirements.txt",
        "references/RULES.md",
        "references/OUTPUT.md",
    }


def _versions() -> dict[str, str]:
    skill_frontmatter = SKILL_MD.read_text(encoding="utf-8").split("---", 2)[1]
    metadata = yaml.safe_load(skill_frontmatter)["metadata"]
    source = DQ_PATH.read_text(encoding="utf-8")
    changelog = CHANGELOG.read_text(encoding="utf-8")
    rules = RULES_MD.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    return {
        "SKILL.md": str(metadata["version"]),
        "dq.py": re.search(r'^__version__ = "([^"]+)"', source, re.M).group(1),
        "RULES.md": re.search(r"^# Rule semantics \(v([0-9.]+)\)", rules, re.M).group(1),
        "CHANGELOG.md": re.search(r"^## \[([0-9.]+)\]", changelog, re.M).group(1),
        "README.md": re.search(r"\*\*Version ([0-9.]+)\*\*", readme).group(1),
    }


def test_version_is_consistent_everywhere():
    versions = _versions()
    assert set(versions.values()) == {"0.5.0"}, versions


def test_no_document_calls_the_version_unreleased_or_is_pip_installable():
    for path in (README, SKILL_MD, RULES_MD, OUTPUT_MD, CHANGELOG):
        text = path.read_text(encoding="utf-8").lower()
        assert "unreleased" not in text, path.name
        assert "pip install agent-data-quality" not in text, path.name
        assert "pip install agent_data_quality" not in text, path.name
        assert "pypi.org" not in text, path.name


def test_skill_frontmatter_is_valid_and_claims_the_ci_python_range(dq, tmp_path):
    frontmatter = yaml.safe_load(SKILL_MD.read_text(encoding="utf-8").split("---", 2)[1])
    assert frontmatter["name"] == "data-quality"
    assert frontmatter["description"].strip()
    assert frontmatter["license"] == "MIT"
    assert frontmatter["metadata"]["version"] == dq.__version__

    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    matrix = workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]
    versions = sorted(matrix, key=lambda value: tuple(int(p) for p in value.split(".")))
    expected = f"Python {versions[0]}–{versions[-1]}"
    assert expected in frontmatter["compatibility"]
    assert expected in README.read_text(encoding="utf-8")
    assert versions == ["3.10", "3.11", "3.12", "3.13", "3.14"]
