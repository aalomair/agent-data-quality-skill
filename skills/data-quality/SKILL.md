---
name: data-quality
description: Profile local datasets (CSV, TSV, XLSX, JSON, JSONL, text, SQLite, Parquet) and check YAML data-quality rules read-only.
license: MIT
compatibility: Requires Python 3.10+ plus the dependencies in scripts/requirements.txt (Parquet needs optional pyarrow). Reads local files and one local SQLite table; no network access. Tested on Linux with Python 3.14.
metadata:
  author: Abdullatif Alomair
  version: "0.2.1"
---

# Data Quality Skill

Profile a local dataset and check it against a small YAML rule set. Python (`scripts/dq.py`) does all reading, counting, and checking deterministically; you (the host agent) interpret the objective, decide which rules are justified, and write a concise human-facing report. Source data is permanently read-only: the helper makes no model or network calls and never alters the inspected data.

Portability note: this bundle follows the portable Agent Skills layout (`SKILL.md` + `scripts/` + `references/`). Hermes has been tested end-to-end with this skill. Codex and Claude Code are format-compatible, but this repository has not harness-tested them.

## When to Use

- The user asks for a data-quality profile, validation, or "is this file clean?" check on a local dataset.
- You need deterministic counts (missing values, duplicates, rule violations) to cite in a report.
- The user supplies or requests explicit acceptance rules: required, max_null_pct, unique, type, min, max, allowed, regex, max_duplicate_rows, dataset-level `unique_together` groups, or a narrow dataset-level `conditional_required` rule.

Don't use for: cleansing, repairing, or altering source data (permanently out of scope by design); comparing editions (no baselines/drift detection); semantic or factual validation of text; or non-SQLite databases (export to a supported file first).

## Prerequisites

- Python 3.10+ and the skill's runtime dependencies, resolved relative to this skill directory:
  `python -m pip install -r scripts/requirements.txt`
- Optional: `python -m pip install 'pyarrow>=15'` only if Parquet sources are needed.
- No configuration, credentials, or network access.

## How to Run

One command — resolve `scripts/dq.py` relative to this skill's directory, never a fixed checkout:

```bash
python <skill-directory>/scripts/dq.py SOURCE [--rules rules.yml] [--sheet NAME] [--table NAME] [--encoding NAME] [--examples N]
```

- Always profiles; applies rules only when `--rules` is supplied.
- JSON goes to stdout, diagnostics to stderr. There is no output-file flag: to save a report, redirect to a NEW path (e.g. `> report.json`) and never onto the source or rules file.
- Exit codes: 0 = inspected / no failed rules; 1 = rule violations; 2 = input, configuration, or execution error (errors take precedence).

## Quick Reference

| Task | Command |
|---|---|
| Profile a CSV | `python scripts/dq.py data.csv` |
| Check a rule set | `python scripts/dq.py data.csv --rules rules.yml` |
| One worksheet | `python scripts/dq.py book.xlsx --sheet Data` |
| SQLite table | `python scripts/dq.py db.sqlite --table items` |
| Other text encoding | `python scripts/dq.py data.csv --encoding cp1256` |
| Bounded examples | append `--examples 3` (capped at 5 per check) |

## Bundle scope and limits

- Supported local formats are CSV/TSV, XLSX, JSON/JSONL, TXT/Markdown, SQLite tables, and optional Parquet (with `pyarrow`).
- One sheet or table is inspected per run. Empty or duplicate headers, wider records, and malformed sources are rejected rather than repaired or silently truncated.
- Sources above 50 MiB or 200,000 rows are rejected; the helper never samples or reports a partial source as complete.
- UTF-8 with optional BOM is the default encoding; alternate encodings are explicit and strict. The helper makes no network or model calls.
- `dataset.unique_together` takes a non-empty YAML list of groups; each group has at least two known, distinct columns and is evaluated as a deterministic composite uniqueness check.
- `dataset.conditional_required` takes a non-empty list of exact `when`/`then_required` entries; a matching non-null scalar trigger evaluates whether the required target column is nonmissing.

Rule semantics and evidence rules are in `references/RULES.md`. This copied bundle is self-contained.

## Procedure

1. **Inspect/profile first.** Run `scripts/dq.py SOURCE` without `--rules`, then read the profile, warnings, selected sheet/table, row/column counts, and limits. Do not choose rules before this pass.
2. **Understand the objective and context.** Read the user's question, available schema/column names, and any domain or reference context. Identify what decision the checks are meant to support.
3. **Establish rule provenance before writing YAML.** Use three levels:
   - **Explicit constraint (confirmed):** directly required by the user, contract, standard, schema, policy, SLA, or authoritative source.
   - **Source-informed candidate:** strongly suggested by official metadata, but not explicitly established as a requirement. A documented field or value vocabulary does not by itself make a field mandatory or a rule authoritative.
   - **Inferred candidate:** suggested by the LLM from profiling, observed patterns, context, or likely semantics.
   Only explicit constraints should automatically produce confirmed DQ findings.
4. **Keep confirmed and candidate rule sets separate when the distinction affects interpretation.** Run explicit/confirmed constraints independently from source-informed and inferred candidates when needed. Do not add provenance fields or new syntax to the YAML rules in this phase; provenance belongs in the host report.
5. **State candidate uncertainty.** For every source-informed or inferred candidate, record its provenance, rationale, evidence/source, and uncertainty. Never present a candidate as an established business requirement.
6. **Generate the smallest useful YAML rule set.** Include only the checks needed for the objective. For compound-key constraints, use `dataset.unique_together` with explicit groups of at least two known columns. For a narrow cross-field obligation, use `dataset.conditional_required` with one exact scalar trigger and one different required column. Do not silently add broad rules, and do not treat an unconfirmed candidate as an established acceptance rule.
7. **Run the deterministic engine.** Execute `scripts/dq.py SOURCE --rules RULES.yml` and use its JSON output. The source remains read-only and the engine, not the LLM, performs all rule evaluation, dimension aggregation, and scoring.
8. **Treat engine results as authoritative.** Preserve the engine's `checks`, `dimensions`, and scores exactly. Use the LLM only to interpret, explain, prioritize findings, state limitations, and suggest next checks or actions.
9. **Interpret dimension results as rule-conformance.** A dimension percentage measures the conformance of the supplied rule applications, not intrinsic dataset cleanliness. Include coverage context in human-facing summaries: the number of checks, the number of distinct columns or scopes, and the total evaluated rule applications. A dataset can contain missing values and still have 100% completeness rule-conformance when the supplied rules allow that missingness.
10. **Never alter the source.** Cleansing, cleaning, repair, and data alteration are permanently out of scope; suggested fixes are explanations only.

## Human-facing report

After the deterministic run, produce this concise report by default. Do not dump raw JSON unless the user asks for it.

1. **Scope & coverage**
   - State the source and selected sheet or table.
   - State rows and columns.
   - State what was assessed and what was not assessed.
2. **Dimension rule-conformance results**
   - Report **Completeness rule-conformance**, **Uniqueness rule-conformance**, and **Validity rule-conformance** in that order.
   - Copy each deterministic score and its `evaluated` / `violations` counts exactly.
   - Preserve the engine formula `score = (evaluated - violations) / evaluated * 100`; do not add weights, grades, labels, or a global score.
   - Include coverage context when practical: the number of checks, distinct columns or scopes, and total evaluated rule applications. For example: `Validity rule-conformance: 99.98% — 5 checks · 4 columns · 99,101 rule applications`.
   - Coverage counts are derived from the emitted checks in the report layer; do not add fields to or alter the deterministic JSON contract.
   - A rule-conformance percentage measures the supplied rule applications, not the percentage of the dataset that is clean. Avoid wording such as “X% of the dataset is clean.”
   - **Dimension percentages produced from materially different rule sets are not directly comparable.** Do not rank a 100% result from two lenient checks against a 100% result from eight stricter checks as though they represented equivalent coverage.
   - When a score is `null`, say **not assessed**; never substitute zero or invent a score.
   - Never present an overall or global score.
3. **Confirmed findings**
   - Include failed explicit/confirmed constraints only.
   - For each, state the rule, column or scope, violations, evaluated count, and bounded row evidence.
   - Do not promote a source-informed or inferred candidate to a confirmed finding merely because it came from official metadata or appears plausible.
   - Prioritize material findings in the presentation without changing engine results or counts.
4. **Candidate findings**
   - Keep failures from **source-informed candidates** and **inferred candidates** separate from confirmed findings.
   - For each candidate, state its provenance level, rule, column or scope, deterministic result, rationale, evidence/source, uncertainty, and bounded row evidence where available.
   - Candidate findings are hypotheses for review, not confirmed business requirements.
5. **Limitations**
   - State relevant checks that were not validated, such as accuracy, semantics, or freshness.
6. **Suggested next checks/actions**
   - Give read-only recommendations only.
   - Do not recommend or perform cleansing, repair, or source modification.

## Pitfalls

- An official data dictionary, API schema, or documented vocabulary can support a **source-informed candidate** without establishing a mandatory constraint. Do not call every metadata-derived rule authoritative.
- `--examples` output contains raw source values and is not anonymized or automatically safe to share.
- Row references are run-local record positions (1-based; text sources use physical line numbers; JSONL skips blank lines so its positions count records), not permanent row IDs.
- `unique_together` evaluates every row, including rows with missing components; missing components share one canonical key, and every member of a repeated composite-key group is a violation. Its check identifies the group in `columns` and `details.columns` while leaving `column` as `null`.
- `conditional_required` evaluates only rows whose trigger exactly matches its non-null scalar `equals` value; a missing target is a violation, and no-trigger entries are `not_evaluated`. Its check identifies the trigger and target in `columns` and `details` while leaving `column` as `null`; it does not support operators, compound predicates, coercion, expressions, or code.
- Exit 0 never proves dataset quality: rules may be absent, or checks may be `not_evaluated` (empty data or no eligible values).
- XLSX formulas are never executed; their cached values may be missing or stale, and the report warns when formulas are present.
- Sources beyond the documented limits (50 MiB / 200,000 rows) are rejected, never sampled or truncated.
- Python regular expressions can catastrophically backtrack on some patterns. For untrusted or automated runs, require a host-enforced execution timeout; this helper does not provide a regex timeout.
- Passing supplied rules does not establish factual accuracy or overall fitness: state what was not assessed (semantic text quality, freshness without an SLA, accuracy without reference data). The report has fixed per-dimension rule-conformance scores but no overall or global DQ score. Cleansing, repair, and alteration of source data are permanently out of scope; suggested fixes are explanations only — this skill never alters data.
- The helper escaping adversarial cells as data does not prove every host model is immune to prompt injection.

## Verification

- The helper printed valid JSON on stdout and the exit code matched the report's `overall.exit_code`.
- Every executed check carries rule, fixed dimension, scope/column, evaluated count, violation count, and bounded `row_refs`.
- `unique_together` checks are classified as uniqueness, identify their configured group deterministically, count all repeated-key members, and contribute to the uniqueness aggregate.
- `conditional_required` checks are classified as completeness, use exact scalar trigger equality, count only triggered rows as evaluated, and contribute to the completeness aggregate.
- The report includes deterministic completeness, uniqueness, and validity aggregates; unevaluated checks are excluded and empty dimensions have a `null` score.
- Human-facing dimension labels use rule-conformance terminology and include evaluated/violations plus coverage context when practical.
- Reports warn that percentages from materially different rule sets are not directly comparable.
- Human-facing findings distinguish explicit/confirmed constraints from source-informed and inferred candidates; each candidate states rationale, evidence/source, and uncertainty.
- Source bytes are unchanged after the run (SQLite is opened with `mode=ro`; a write attempt fails).
