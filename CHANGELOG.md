# Changelog

All notable changes to this project are documented here. Versions are git tags and GitHub releases; this is not a Python package.

## [0.4.1] — 2026-11-09

Privacy fix. The engine, rules, and JSON output are unchanged.

- Removed the 0.4.0 instruction that had the agent read real values from low-cardinality columns. It sent raw data to the model.
- `SKILL.md` adds a **Data privacy** section: the agent never opens, prints or samples the source; everything it knows about the data comes from `dq.py` output; `--examples` needs the user's explicit consent; rules that need unknown values (category lists, ID formats, business limits) come from the user or a source, or are reported as not assessed.
- README adds **What the model sees**, listing exactly what reaches the model (including numeric min/max/mean) and the limits of an instruction-only guarantee.

## [0.4.0] — 2026-11-08

Better rule coverage for comprehensive assessments, based on benchmark runs across several agents. The engine, rules, and JSON output are unchanged.

- `SKILL.md` adds a comprehensive-assessment procedure: walk every rule family against every column, inspect low-cardinality values before writing `allowed`/`regex`, separate column, compound-key and whole-row uniqueness, separate always-required from state-dependent fields, and fit regexes to every legitimate subpopulation.
- The human-facing report gains a **Supported but not assessed** section listing plausible checks that were not run, with reasons.
- Reporting guidance separates rule violations, distinct affected rows, duplicate extras and rule-conformance scores, and keeps profile observations apart from failed-rule findings.
- Out-of-scope observations (calendar-impossible dates, cross-column arithmetic, date ordering, cross-table references) must be labelled as outside the engine's checks.
- Dependency preflight: check the interpreter and imports first; if installation is blocked, report exactly what is missing instead of producing results.

## [0.3.0] — 2026-11-07

Makes the skill easy for an agent to download and install on its own, and adds two dataset rules. The read-only design is unchanged.

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
