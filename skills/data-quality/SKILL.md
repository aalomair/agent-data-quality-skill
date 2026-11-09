---
name: data-quality
description: Profile local datasets (CSV, TSV, XLSX, JSON, JSONL, text, SQLite, Parquet) and check YAML data-quality rules read-only.
license: MIT
compatibility: Requires Python 3.10–3.14 plus the dependencies in scripts/requirements.txt (XLSX needs openpyxl; Parquet needs optional pyarrow). Reads local files and one local SQLite table; no network access. CI-tested on Linux with Python 3.10–3.14.
metadata:
  author: Abdullatif Alomair
  version: "0.5.0"
---

# Data Quality Skill

Profile a local dataset and check it against a small YAML rule set. Python (`scripts/dq.py`) does all reading, counting, and checking deterministically; you (the host agent) interpret the objective, decide which rules are justified, and write a concise human-facing report. Source data is permanently read-only: the helper makes no model or network calls and never alters the inspected data.

## Data privacy

Your job is to keep the data on the user's machine. The helper reads the source locally; you, the model, should only ever see what `dq.py` prints. This is a hard rule, not a preference:

- **Never read, print, sample, or open the source data yourself.** No `cat`, `head`, `less`, spreadsheet viewers, ad-hoc pandas or SQL queries, or file-reading tools on the source. Every fact you use about the data comes from `dq.py` output.
- **What reaches you is the engine's summary:** column names, counts, missing rates, inferred types, string lengths, numeric min/max/mean, rule results, and row positions. With `--discover` it also includes masked shapes (`ORD-9999`) and the category labels of low-cardinality text columns. Numeric min/max/mean and category labels are real values from the data; treat them like any other data in your report.
- **`--strict-privacy`** removes numeric min/max/mean and category labels from the output and refuses raw examples. Use it when the user says the data is sensitive, or asks for the most private run.
- **`--examples` prints raw values.** Use it only after the user explicitly agrees, and say which columns it will expose.
- **When a rule needs knowledge you don't have** (the allowed values of a category, the exact format of an ID, a business limit), get it from the user, a source document, or a schema. If none is available, list the check under "Supported but not assessed" with that reason. Do not look at the data to fill the gap.
- The skill cannot technically stop a host agent with file access from reading the source. If the user needs that guarantee, point them to the host's own permission settings, so that only `dq.py` can read the data folder.

Portability note: this bundle follows the portable Agent Skills layout (`SKILL.md` + `scripts/` + `references/`). Hermes has been tested end-to-end with this skill. Codex and Claude Code are format-compatible, but this repository has not harness-tested them.

## When to Use

- The user asks for a data-quality profile, validation, or "is this file clean?" check on a local dataset.
- You need deterministic counts (missing values, duplicates, rule violations) to cite in a report.
- The user supplies or requests explicit acceptance rules: required, max_null_pct, unique, type, min, max, allowed, regex, max_duplicate_rows, dataset-level `unique_together` groups, or a narrow dataset-level `conditional_required` rule.

Don't use for: cleansing, repairing, or altering source data (permanently out of scope by design); comparing editions (no baselines/drift detection); semantic or factual validation of text; or non-SQLite databases (export to a supported file first).

## Getting and installing this skill

- Download the bundle: `https://github.com/aalomair/agent-data-quality-skill/releases/latest/download/data-quality-skill.zip` (or pin a version with `.../releases/download/v0.5.0/data-quality-skill.zip`). The zip unpacks to a single `data-quality/` directory.
- Place that directory in the host's skills directory, or keep it anywhere and resolve `scripts/dq.py` relative to it. Nothing needs to be installed from this repository itself; only the runtime dependencies below.
- Git alternative: shallow-clone the repository and copy `skills/data-quality/` out of it.

## Prerequisites

The skill never installs packages. You (the host agent) or the user decide whether to install these and where — an existing environment or a fresh virtual environment — following the host's and user's policy.

- Python 3.10–3.14.
- `pandas>=2.2,<4` — required on every run.
- `PyYAML>=6.0,<7` — required on every run (import name `yaml`).
- `openpyxl>=3.1,<4` — only for `.xlsx` sources.
- `pyarrow>=15` — optional, only for `.parquet` sources.

`scripts/requirements.txt` is the authoritative range list and mirrors the list above. Check availability before a run:

```bash
python -c "import pandas, yaml"
```

Example install, into the environment you or the user choose:

```bash
python -m pip install -r <skill-directory>/scripts/requirements.txt
python -m pip install 'pyarrow>=15'   # optional, Parquet only
```

Without `pandas` or `yaml`, the helper still prints one valid JSON error document with `errors[0].code == "missing_dependency"` and exits 2; stdout never carries a traceback. No configuration, credentials, or network access are involved.

Preflight before the first run, using the same interpreter you will run `dq.py` with:

```bash
python --version
python -c "import pandas, yaml; print('pandas', pandas.__version__, '| PyYAML', yaml.__version__)"
python <skill-directory>/scripts/dq.py --help
```

If installation is not possible in this environment (no pip, no network, a read-only or managed interpreter), stop and tell the user exactly which dependency is missing, which interpreter you checked, and the command that failed with its error. Offer the install command for them to run. Never produce data-quality results without a successful engine run.

## How to Run

One command — resolve `scripts/dq.py` relative to this skill's directory, never a fixed checkout:

```bash
python <skill-directory>/scripts/dq.py SOURCE [--rules rules.yml] [--sheet NAME] [--table NAME] [--encoding NAME] [--examples N]
```

- Always profiles; applies rules only when `--rules` is supplied.
- JSON goes to stdout, diagnostics to stderr. There is no output-file flag: to save a report, redirect to a NEW path (e.g. `> report.json`) and never onto the source or rules file.
- Exit codes: 0 = inspected / no failed rules; 1 = rule violations; 2 = input, configuration, or execution error (errors take precedence).

### Programmatic use (no installation)

Put `<skill-directory>/scripts` on `sys.path` and import the helper; `dq.run()` returns exactly the JSON payload the CLI prints and never raises:

```python
import sys
sys.path.insert(0, "<skill-directory>/scripts")
import dq

payload = dq.run("data.csv", "rules.yml", examples=2)
payload["overall"]["exit_code"]   # 0, 1, or 2
payload["errors"]                 # [] or [{"code": ..., "message": ...}]
```

The signature mirrors the CLI: `dq.run(source, rules=None, *, sheet=None, table=None, encoding=None, examples=0, discover=False, strict_privacy=False, mask_examples=False)`. The CLI remains the primary contract; `run()` is the same payload as a dict, including error payloads.

## Quick Reference

| Task | Command |
|---|---|
| Profile a CSV | `python scripts/dq.py data.csv` |
| Check a rule set | `python scripts/dq.py data.csv --rules rules.yml` |
| One worksheet | `python scripts/dq.py book.xlsx --sheet Data` |
| SQLite table | `python scripts/dq.py db.sqlite --table items` |
| Other text encoding | `python scripts/dq.py data.csv --encoding cp1256` |
| Bounded examples | append `--examples 3` (capped at 5 per check) |
| Propose candidate rules | `python scripts/dq.py data.csv --discover` |
| Most private output | add `--strict-privacy` (and `--mask-examples` with `--examples`) |

## Bundle scope and limits

- Supported local formats are CSV/TSV, XLSX, JSON/JSONL, TXT/Markdown, SQLite tables, and optional Parquet (with `pyarrow`).
- One sheet or table is inspected per run. Empty or duplicate headers, wider records, and malformed sources are rejected rather than repaired or silently truncated.
- Sources above 50 MiB or 200,000 rows are rejected; the helper never samples or reports a partial source as complete.
- UTF-8 with optional BOM is the default encoding; alternate encodings are explicit and strict. The helper makes no network or model calls.
- `dataset.unique_together` takes a non-empty YAML list of groups; each group has at least two known, distinct columns and is evaluated as a deterministic composite uniqueness check.
- `dataset.conditional_required` takes a non-empty list of exact `when`/`then_required` entries; a matching non-null scalar trigger evaluates whether the required target column is nonmissing.

Rule semantics and evidence rules are in `references/RULES.md`. This copied bundle is self-contained.

## Procedure

1. **Inspect/profile first.** Run `scripts/dq.py SOURCE --discover` (or without `--discover` for a quick profile), then read the profile, warnings, selected sheet/table, row/column counts, limits, and the candidate list. Do not choose rules before this pass.
2. **Understand the objective and context.** Read the user's question, available schema/column names, and any domain or reference context. Identify what decision the checks are meant to support.
3. **Establish rule provenance before writing YAML.** Use three levels:
   - **Explicit constraint (confirmed):** directly required by the user, contract, standard, schema, policy, SLA, or authoritative source.
   - **Source-informed candidate:** strongly suggested by official metadata, but not explicitly established as a requirement. A documented field or value vocabulary does not by itself make a field mandatory or a rule authoritative.
   - **Inferred candidate:** suggested by the LLM from profiling, observed patterns, context, or likely semantics.
   Only explicit constraints should automatically produce confirmed DQ findings.
4. **Keep confirmed and candidate rule sets separate when the distinction affects interpretation.** Run explicit/confirmed constraints independently from source-informed and inferred candidates when needed. Do not add provenance fields or new syntax to the YAML rules in this phase; provenance belongs in the host report.
5. **State candidate uncertainty.** For every source-informed or inferred candidate, record its provenance, rationale, evidence/source, and uncertainty. Never present a candidate as an established business requirement.
6. **Generate the smallest useful YAML rule set.** Include only the checks needed for the objective. When the user asks for a comprehensive or full assessment, build the coverage inventory in **Comprehensive assessments** below first, then write rules from it. For compound-key constraints, use `dataset.unique_together` with explicit groups of at least two known columns. For a narrow cross-field obligation, use `dataset.conditional_required` with one exact scalar trigger and one different required column. Do not silently add broad rules, and do not treat an unconfirmed candidate as an established acceptance rule.
7. **Run the deterministic engine.** Execute `scripts/dq.py SOURCE --rules RULES.yml` and use its JSON output. The source remains read-only and the engine, not the LLM, performs all rule evaluation, dimension aggregation, and scoring.
8. **Treat engine results as authoritative.** Preserve the engine's `checks`, `dimensions`, and scores exactly. Use the LLM only to interpret, explain, prioritize findings, state limitations, and suggest next checks or actions.
9. **Interpret dimension results as rule-conformance.** A dimension percentage measures the conformance of the supplied rule applications, not intrinsic dataset cleanliness. Include coverage context in human-facing summaries: the number of checks, the number of distinct columns or scopes, and the total evaluated rule applications. A dataset can contain missing values and still have 100% completeness rule-conformance when the supplied rules allow that missingness.
10. **Never alter the source.** Cleansing, cleaning, repair, and data alteration are permanently out of scope; suggested fixes are explanations only.

## Discover, review, verify

`--discover` makes the engine propose candidate rules from patterns in the data, so you review a fixed list instead of inventing rules. The same file always produces the same candidates, whichever model runs the skill. Use it for every comprehensive request, and whenever you have no rules from the user.

1. **Discover.** `python scripts/dq.py SOURCE --discover > discovery.json`. Each candidate has a `rule`, a `value`, a `detector`, `evidence` (counts and masked shapes, never raw rows), and `expected` (the violations it would report). All candidates are `inferred`.
2. **Review every candidate.** Accept, reject, or edit each one, with a one-line reason. Typical reasons to reject: an `allowed` list that dropped a rare but legitimate value, a `regex` that is only a coincidence of formats, a `unique_together` pair that is unique by chance. Typical edits: add values the user confirms to an `allowed` list, loosen a regex. A candidate becomes **confirmed** only when the user or a source states the rule.
3. **Add what discovery cannot know.** The engine never proposes `min` or `max`: a bound read from the data's own range always passes. Bounds and any other business limits come from the user, a source, or your own judgement labelled as an inferred candidate.
4. **Verify.** Write the accepted rules to a new YAML file (`discovery.rules` is a ready starting point), run `--rules`, and report from that run. Candidates are never scores or findings; only the verify run is.
5. **Report the review.** Add a short **Candidates reviewed** table to the report: rule, column, decision (accepted, edited, rejected), reason.

Under `--strict-privacy`, candidates whose rule would contain a data value (`allowed` lists, `conditional_required` triggers) are withheld. Ask the user for those values, or list the checks under "Supported but not assessed".

## Comprehensive assessments

Benchmarks showed that the biggest source of missed issues is not the engine but which rules the agent chooses: different agents given the same file and the same "comprehensive" request picked very different subsets of the available checks, and more checks did not mean better coverage. When the user asks for a comprehensive, full, or thorough assessment, work through this before writing YAML:

1. **Start from `--discover`.** Its candidates cover most rule families automatically. Then walk every rule family against every column for what is left. For each column, decide whether each family applies: `required`, `max_null_pct`, `unique`, `type`, `min`, `max`, `allowed`, `regex`. For the dataset, decide on `max_duplicate_rows`, `unique_together`, and `conditional_required`. Record each as **assessed**, **not applicable**, or **supported but not assessed** with a one-line reason. Keep this inventory in your working notes; it feeds the report's "Supported but not assessed" section.
2. **Get category values and formats from discovery, the user, or a source, never from reading the data.** Discovery lists category labels for low-cardinality text columns and masked shapes for the rest. If those are withheld or not enough, the list must come from the user, a data dictionary, a schema, or a source document (see **Data privacy**).
3. **Separate the three kinds of uniqueness.** A single-column ID (`unique`), a compound key such as invoice + line number (`unique_together`), and whole-row copies (`max_duplicate_rows`) catch different problems. Consider all three.
4. **Separate always-required fields from state-dependent ones.** Many blanks are legitimate: no closing date on an open ticket, no refund reference on a payment that was never refunded. Use `required` only where every row needs a value; use `conditional_required` when a status or flag makes a field mandatory (for example a closed ticket needs a closing date, a refunded payment needs a refund reference). Never count optional blanks as defects.
5. **Write regexes that fit every legitimate subpopulation.** An ID or code format usually comes from the user or a source. Before anchoring it, ask whether valid values span several years, prefixes, regions, or channels (for example invoice numbers issued under two different year prefixes). A pattern built from the newest or most common variant alone flags thousands of valid rows. If a regex flags a large share of a column, treat that as a sign the pattern is wrong before calling it a data problem.
6. **Pair `type` with plausible bounds on numeric columns.** Quantities, prices, percentages, fees and ratings usually have a natural floor and a sensible ceiling. When the ceiling is not stated by the user or a source, it is an inferred candidate and must be labelled as one.
7. **Do not over-reach.** Comprehensive does not mean every field is required, every rare value is invalid, or `NA` is missing. Each rule still needs a provenance level, and declining a check with a stated reason is better than guessing.

The available rules cannot check calendar validity of date-shaped strings (such as `2025-02-30`), arithmetic between columns (such as a total that should equal price times quantity), date ordering, or references between tables. If you notice such issues, report them as observations outside the engine's checks; do not present them as engine results.

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
   - When `--discover` was used, add a short **Candidates reviewed** table: rule, column, decision (accepted, edited, rejected), reason.
5. **Supported but not assessed**
   - List plausible, high-value checks the engine supports that you did not run, each with its reason: no authority to call it a requirement, unclear semantics, or an execution constraint.
   - Reporting a gap is better than guessing. For comprehensive assessments this section comes from the coverage inventory.
6. **Limitations**
   - State relevant checks that were not validated, such as accuracy, semantics, or freshness.
   - Keep profile observations (such as the total count of missing cells) separate from failed-rule findings. Neither a missing-cell total nor a rule-conformance score is a rate of defective rows.
7. **Suggested next checks/actions**
   - Give read-only recommendations only.
   - Do not recommend or perform cleansing, repair, or source modification.

## Results for reports and dashboards

The JSON is the evidence. `references/OUTPUT.md` documents every field, status, detail shape and error code. When the user asks for a written report, spreadsheet, or dashboard:

- Save the JSON to a new file first (`> report.json`); never write to the source or rules file.
- Build the output from that saved JSON, never from recomputed numbers.
- Show the three dimension rule-conformance scores, each with `evaluated`, `violations` and coverage context. Show no global score, and display `null` as **not assessed**.
- Keep confirmed findings and candidate findings separate.
- Do not run `--examples` without the user's consent, and do not put example values into a shareable artifact without it.
- Write the dashboard outside the source data location unless the user asks otherwise.

This skill ships no dashboard generator, HTML renderer, or charting dependency: the host agent builds the dashboard from the saved JSON.

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
- Keep the counts apart: **rule violations** (per check, from the engine), **distinct affected rows**, **duplicate extras**, and **dimension rule-conformance**. One bad value can fail several rules (a value like `one` in a numeric column fails both `type` and `min`), and duplicated rows repeat the same bad values, so violations cannot be summed into a number of defects or divided by a defect count. `row_refs` show at most 10 rows per check, so they illustrate a finding but never prove a complete list of affected rows.
- Whitespace-only cells count as missing in the engine. Use the same meaning in your own commentary.

## Verification

- The helper printed valid JSON on stdout and the exit code matched the report's `overall.exit_code`.
- Every executed check carries rule, fixed dimension, scope/column, evaluated count, violation count, and bounded `row_refs`.
- `unique_together` checks are classified as uniqueness, identify their configured group deterministically, count all repeated-key members, and contribute to the uniqueness aggregate.
- `conditional_required` checks are classified as completeness, use exact scalar trigger equality, count only triggered rows as evaluated, and contribute to the completeness aggregate.
- The report includes deterministic completeness, uniqueness, and validity aggregates; unevaluated checks are excluded and empty dimensions have a `null` score.
- Human-facing dimension labels use rule-conformance terminology and include evaluated/violations plus coverage context when practical.
- Reports warn that percentages from materially different rule sets are not directly comparable.
- Human-facing findings distinguish explicit/confirmed constraints from source-informed and inferred candidates; each candidate states rationale, evidence/source, and uncertainty.
- For comprehensive requests, every rule family was considered for every column, and the report lists supported checks that were not assessed, with reasons.
- Source bytes are unchanged after the run (SQLite is opened with `mode=ro`; a write attempt fails).
