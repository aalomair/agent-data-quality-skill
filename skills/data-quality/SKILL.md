---
name: data-quality
description: Profile local datasets (CSV, TSV, XLSX, JSON, JSONL, text, SQLite, Parquet) and check YAML data-quality rules read-only.
license: MIT
compatibility: Requires Python 3.10+ plus the dependencies in scripts/requirements.txt (Parquet needs optional pyarrow). Reads local files and one local SQLite table; no network access. Tested on Linux with Python 3.14.
metadata:
  author: Abdullatif Alomair
  version: "0.2.0"
---

# Data Quality Skill

Profile a local dataset and check it against a small YAML rule set. Python (`scripts/dq.py`) does all reading, counting, and checking deterministically; you (the host agent) interpret the objective, decide which rules are justified, and write a concise human-facing report. Source data is permanently read-only: the helper makes no model or network calls and never alters the inspected data.

Portability note: this bundle follows the portable Agent Skills layout (`SKILL.md` + `scripts/` + `references/`). Format compatibility does not mean every host has been tested — README.md lists the harnesses actually exercised.

## When to Use

- The user asks for a data-quality profile, validation, or "is this file clean?" check on a local dataset.
- You need deterministic counts (missing values, duplicates, rule violations) to cite in a report.
- The user supplies or requests explicit acceptance rules: required, max_null_pct, unique, type, min, max, allowed, regex, max_duplicate_rows.

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
| One SQLite table | `python scripts/dq.py db.sqlite --table items` |
| Other text encoding | `python scripts/dq.py data.csv --encoding cp1256` |
| Bounded examples | append `--examples 3` (capped at 5 per check) |

Rule semantics and evidence rules: `references/RULES.md`. Supported inputs, limits, and limitations: README.md in the repository root.

## Procedure

1. **Inspect/profile first.** Run `scripts/dq.py SOURCE` without `--rules`, then read the profile, warnings, selected sheet/table, row/column counts, and limits. Do not choose rules before this pass.
2. **Understand the objective and context.** Read the user's question, available schema/column names, and any domain or reference context. Identify what decision the checks are meant to support.
3. **Separate rule provenance.** Mark each rule as either **explicit/authoritative** (supplied by the user or an authoritative reference) or an **inferred candidate** (suggested by the LLM from the objective, profile, or context).
4. **State uncertainty.** Never present an inferred candidate as an established fact. Label its assumption, rationale, and uncertainty; keep it separate from authoritative findings and ask for confirmation when that distinction matters.
5. **Generate the smallest useful YAML rule set.** Include only the checks needed for the objective. Do not silently add broad rules, and do not treat an unconfirmed candidate as an established acceptance rule.
6. **Run the deterministic engine.** Execute `scripts/dq.py SOURCE --rules RULES.yml` and use its JSON output. The source remains read-only and the engine, not the LLM, performs all rule evaluation, dimension aggregation, and scoring.
7. **Treat engine results as authoritative.** Preserve the engine's `checks`, `dimensions`, and scores exactly. Use the LLM only to interpret, explain, prioritize findings, state limitations, and suggest next checks or actions.
8. **Interpret dimension scores correctly.** A dimension score measures rule applications, not unique bad rows or cells. One value can contribute to multiple checks when multiple rules apply, and each such rule application is counted in its corresponding check totals.
9. **Never alter the source.** Cleansing, cleaning, repair, and data alteration are permanently out of scope; suggested fixes are explanations only.

## Human-facing report

After the deterministic run, produce this concise report by default. Do not dump raw JSON unless the user asks for it.

1. **Scope & coverage**
   - State the source and selected sheet or table.
   - State rows and columns.
   - State what was assessed and what was not assessed.
2. **DQ dimension results**
   - Report `completeness`, `uniqueness`, and `validity` in that order.
   - Copy each deterministic score and its `evaluated` / `violations` counts exactly.
   - When a score is `null`, say **not assessed**; never substitute zero or invent a score.
   - Never present an overall or global score.
   - Score percentages measure rule applications, not the percentage of the dataset that is clean. Avoid wording such as “X% of the dataset is clean.”
3. **Confirmed findings**
   - Include failed authoritative or confirmed rules only.
   - For each, state the rule, column or scope, violations, evaluated count, and bounded row evidence.
   - Prioritize material findings in the presentation without changing engine results or counts.
4. **Candidate findings / assumptions**
   - Keep inferred LLM rules and hypotheses in a separate section.
   - Label assumptions and uncertainty; never present candidates as confirmed business requirements.
5. **Limitations**
   - State relevant checks that were not validated, such as accuracy, semantics, or freshness.
6. **Suggested next checks/actions**
   - Give read-only recommendations only.
   - Do not recommend or perform cleansing, repair, or source modification.

## Pitfalls

- `--examples` output contains raw source values and is not anonymized or automatically safe to share.
- Row references are run-local record positions (1-based; text sources use physical line numbers; JSONL skips blank lines so its positions count records), not permanent row IDs.
- Exit 0 never proves dataset quality: rules may be absent, or checks may be `not_evaluated` (empty data or no eligible values).
- XLSX formulas are never executed; their cached values may be missing or stale, and the report warns when formulas are present.
- Sources beyond the documented limits (50 MiB / 200,000 rows) are rejected, never sampled or truncated.
- Passing supplied rules does not establish factual accuracy or overall fitness: state what was not assessed (semantic text quality, freshness without an SLA, accuracy without reference data). The report has fixed per-dimension scores but no overall or global DQ score. Cleansing, repair, and alteration of source data are permanently out of scope; suggested fixes are explanations only — this skill never alters data.
- The helper escaping adversarial cells as data does not prove every host model is immune to prompt injection.

## Verification

- The helper printed valid JSON on stdout and the exit code matched the report's `overall.exit_code`.
- Every executed check carries rule, fixed dimension, scope/column, evaluated count, violation count, and bounded `row_refs`.
- The report includes deterministic completeness, uniqueness, and validity aggregates; unevaluated checks are excluded and empty dimensions have a `null` score.
- Source bytes are unchanged after the run (SQLite is opened with `mode=ro`; a write attempt fails).
