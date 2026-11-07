# Changelog

All notable changes to this project are documented here. Versions are git tags and GitHub releases; this is not a Python package.

## [0.3.0] — 2026-11-07

Agent-ready distribution and two engine additions, without changing the read-only architecture.

Distribution and agent experience:

- GitHub release assets `data-quality-skill.zip` (built with `git archive`, top-level `data-quality/`) and `SHA256SUMS`; the unversioned asset URL `releases/latest/download/data-quality-skill.zip` stays stable across releases.
- README "Install for agents": download, checksum verification, host skill locations (Hermes harness-tested; Claude Code and Codex paths sourced from their docs), and a git alternative.
- Dependency disclosure in `SKILL.md` and the README: Python 3.10–3.14, `pandas>=2.2,<4`, `PyYAML>=6.0,<7`, `openpyxl>=3.1,<4` for XLSX, optional `pyarrow>=15` for Parquet. The skill never installs packages; the installing agent or user decides.
- Missing `pandas` or `yaml` now produces the documented JSON error contract — code `missing_dependency`, exit 2, one stderr diagnostic line — instead of an import traceback.
- `dq.run(source, rules=None, *, sheet=None, table=None, encoding=None, examples=0)` returns exactly the CLI payload and never raises; `main()` uses it, so the two cannot drift.
- `references/OUTPUT.md`: field-by-field reference for the JSON payload, with dashboard/report guidance in `SKILL.md` (saved JSON as the only number source, no global score, `null` = not assessed, confirmed vs candidate findings, raw examples require consent).
- CI matrix extended to Python 3.10, 3.11, 3.12, 3.13 and 3.14; documented compatibility now names only CI-proven versions.
- `CHANGELOG.md` added; version consistency across `SKILL.md`, `dq.__version__`, `RULES.md`, this file and the README is enforced by tests.

Engine and rule coverage:

- `dataset.unique_together` supports one or more composite groups, rejects logically duplicate groups regardless of column order, and preserves configured column order in emitted evidence.
- `dataset.conditional_required` adds exact scalar cross-field requirements; missing trigger values and semantically duplicate entries are rejected.
- Duplicate-row evidence lists only duplicate extras beyond `max_duplicate_rows`; total duplicate counts and violation semantics are unchanged.
- Allowlist matching remains strict, and oversized rules files are rejected before parsing at 1 MiB.
- The benchmark validates detailed checks, evidence, statuses, exit codes, structured errors, and source integrity.
- Publication safeguards preserve the standalone bundle's MIT notice, document the Adult dataset's separate CC BY 4.0 license, ignore local environment/report files, and run a checksum-verified full-history secret scan in CI.

## [0.2.1] — 2026-09-23

Correctness and validation hardening without new capabilities:

- `required: false` and `unique: false` now disable those checks entirely.
- CSV/TSV inputs reject NUL characters before parsing.
- Duplicate or empty column names are rejected consistently across supported readers.
- JSON and JSONL reject duplicate object keys.
- Malformed rule sections and null duplicate-row limits are rejected strictly.
- Numeric profile means use overflow-safe summation for finite large values.
- The ERPNext benchmark derives expectations from actual injections and validates CLI status, exit codes, and errors.
- Regex guidance documents catastrophic-backtracking risk and host-enforced execution timeouts.
- Documentation corrects YAML identifier quoting, inline regex flags, example-length limits, bundle portability, harness status, and current-scope wording.

## [0.2.0] — 2026-09-23

- Deterministic `type` and `max_null_pct` rules.
- Fixed completeness, uniqueness, and validity classification.
- Deterministic per-dimension scores with no global score.
- Explicit LLM workflow and human-facing report contract.
- Permanent read-only source-data boundary.

## [0.1.1] — 2026-09-20

Frozen v0.1 line: benchmark harness and documentation; the skill bundle is unchanged from v0.1.0.

## [0.1.0] — 2026-09-20

Portable, read-only data-quality Agent Skill: dataset profiling and YAML rule checks with structured JSON evidence.
