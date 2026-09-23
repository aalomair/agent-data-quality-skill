"""Small regression tests for the defect-injection benchmark harness."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = REPO_ROOT / "benchmark" / "run.py"


def _load_benchmark():
    spec = importlib.util.spec_from_file_location(
        "benchmark_run_under_test", BENCHMARK_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_run_under_test"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def benchmark():
    assert BENCHMARK_PATH.is_file()
    return _load_benchmark()


def test_erpnext_uses_actual_injection_counts_and_adjusted_duplicates(
    tmp_path, benchmark, capsys
):
    rows: list[list[str]] = []
    for pair in range(5):
        rows.extend(
            [
                [f"req-{pair}-a", str(pair), "EA"],
                [f"req-{pair}-b", str(pair), "EA"],
            ]
        )
    for pair in range(5):
        rows.extend(
            [
                [f"num-{pair}", str(pair), "EA"],
                [f"num-{pair}", str(pair + 100), "EA"],
            ]
        )
    for pair in range(2):
        rows.extend(
            [
                [f"cat-{pair}", "200", "EA"],
                [f"cat-{pair}", "200", "BOX"],
            ]
        )

    source = tmp_path / "erpnext.csv"
    benchmark.write_csv(source, ["name", "qty", "uom"], rows)

    assert benchmark.run_erpnext(source, verbose=False) is True
    output = capsys.readouterr().out

    # 10 required + 10 max-null + 10 type + 10 min + 4 allowed;
    # 12 mutation-created duplicate extras are an intentional overlap.
    assert "Expected detections: 56" in output
    assert "Detected: 56" in output
    assert "Unexpected: 0" in output
    assert "Source unchanged: PASS" in output


def test_benchmark_validates_cli_exit_status_and_errors(benchmark):
    payload = {
        "checks": [],
        "errors": [{"code": "unexpected"}],
        "overall": {"status": "passed", "exit_code": 2},
    }

    problems = benchmark.validate_cli_result(
        0,
        payload,
        "diagnostic",
        expected_exit_code=1,
        expected_status="failed",
    )

    assert any("CLI exit code" in problem for problem in problems)
    assert any("payload overall.exit_code" in problem for problem in problems)
    assert any("payload status" in problem for problem in problems)
    assert any("payload errors" in problem for problem in problems)
