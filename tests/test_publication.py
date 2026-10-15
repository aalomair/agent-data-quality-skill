"""Keep public licensing, portable notices, and publication safeguards intact."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_portable_bundle_carries_the_complete_mit_notice():
    assert (ROOT / "skills/data-quality/LICENSE").read_bytes() == (
        ROOT / "LICENSE"
    ).read_bytes()


def test_public_dataset_has_its_own_attribution_and_unchanged_fixture():
    notice = (ROOT / "benchmark/public/README.md").read_text()
    for required in (
        "Barry Becker", "Ronny Kohavi", "CC BY 4.0",
        "https://doi.org/10.24432/C5XW20",
        "https://creativecommons.org/licenses/by/4.0/",
        "adult.data", "header", "whitespace",
    ):
        assert required in notice
    digest = hashlib.sha256((ROOT / "benchmark/public/adult.csv").read_bytes()).hexdigest()
    assert digest == "6d8898ef78f064108f1a565b6e09580bb7274d4b94d819e8e19c3ea3ad291209"
    assert digest in notice
    readme = (ROOT / "README.md").read_text()
    assert "benchmark/public/README.md" in readme
    assert "CC BY 4.0" in readme


@pytest.mark.parametrize(
    "path,ignored",
    [
        (".env", True),
        (".env.local", True),
        ("nested/.env", True),
        ("nested/.env.production", True),
        (".env.example", False),
        ("nested/.env.example", False),
        ("reports/private.json", True),
        ("benchmark/private/export.csv", True),
        ("benchmark/public/adult.csv", False),
        ("skills/data-quality/LICENSE", False),
    ],
)
def test_gitignore_keeps_private_outputs_out_and_public_files_in(path, ignored):
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    assert (result.returncode == 0) is ignored


def test_ci_has_read_only_permissions_pinned_actions_and_full_history_scan():
    workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert workflow["permissions"] == {"contents": "read"}
    assert "push" in workflow["on"] and "pull_request" in workflow["on"]
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"
    scan = workflow["jobs"]["secrets"]
    checkout = next(s for s in scan["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == "0"
    script = next(s["run"] for s in scan["steps"] if s.get("name") == "Scan complete Git history")
    assert "sha256sum --check" in script
    assert "--all --full-history" in script
    assert "--redact" in script
    assert "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb" in script


def test_development_version_is_not_presented_as_a_published_release():
    readme = (ROOT / "README.md").read_text()
    assert "**v0.3.0 (unreleased)**" in readme
    assert "releases/tag/v0.2.1" in readme
    assert "## v0.3.0 changes (unreleased)" in readme
