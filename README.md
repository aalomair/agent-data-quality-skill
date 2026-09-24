# agent-data-quality-skill

**v0.2.1** — a small, portable [Agent Skill](https://agentskills.io/specification) for deterministic, **read-only** data-quality profiling and rule checking.

The host LLM (Hermes, Claude Code, Codex, or any Agent Skills–compatible host) interprets the objective and writes the report; Python (`skills/data-quality/scripts/dq.py`) reads the local data and computes every metric and check. Source data is permanently read-only: the helper makes **no model calls, no network access, and no writes** to inspected sources. Hermes has been tested end-to-end with this skill; Codex and Claude Code are format-compatible, but are not harness-tested in this repository.

## Repository layout

```text
README.md
LICENSE                        MIT
.github/workflows/ci.yml       one CI test job
skills/data-quality/           the portable skill bundle
  SKILL.md                     skill instructions + frontmatter
  scripts/dq.py                the single CLI helper
  scripts/requirements.txt     runtime dependencies
  references/RULES.md          rule semantics, evidence rules, read-only guarantees
tests/test_dq.py               pytest suite (CLI-level + unit tests)
benchmark/run.py               defect-injection benchmark (UCI Adult + ERPNext)
benchmark/public/              UCI Adult fixture + benchmark rules
benchmark/private/             local-only datasets (gitignored)
```

## Supported inputs

| Source | Extensions | Notes |
|---|---|---|
| CSV / TSV | `.csv`, `.tsv` | one header row; duplicate/empty headers rejected; blank lines preserved as all-empty records; short rows padded as missing; records **wider** than the header are rejected, never truncated or shifted |
| Excel | `.xlsx` | `--sheet NAME` or the first worksheet (named explicitly in the report); formulas never executed (presence reported, cached values may be missing/stale); merged-cell warnings; a sheet whose data rows are wider than the header row is rejected (the extra column has no header name) |
| JSON | `.json` | array of flat records; scalar values only — nested structures rejected |
| JSONL / NDJSON | `.jsonl`, `.ndjson` | one flat record per nonblank line |
| Text / Markdown | `.txt`, `.md`, `.markdown` | each line is a record in a `text` column; blank lines preserved; extra statistics (blank lines, duplicate lines, length range, unusual control characters) |
| SQLite | `.sqlite`, `.sqlite3`, `.db` | one `--table NAME`; opened with URI `mode=ro`; views unsupported; exact table-name validation and identifier quoting |
| Parquet | `.parquet`, `.pq` | flat scalar tables; requires optional `pyarrow`; nested fields rejected |

Other databases (PostgreSQL/MySQL/SQL Server): export to a supported file first — the current scope ships no connectors and implies none.

## Install

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -r skills/data-quality/scripts/requirements.txt
python -m pip install 'pyarrow>=15'   # optional, Parquet only

python -m pip install pytest          # development only
```

Installing into a host: copy `skills/data-quality/` into that host's skills directory (for a Hermes profile: `<hermes-home>/skills/`) or point the host at the directory per its own docs. The bundle is self-contained — it never depends on this repository's root.

## Quick start (verified examples)

```bash
printf 'id,name,age\n00123,Ahmed,30\n00456,,25\n00789,NA,abc\n00012,Sara,\n' > customers.csv
cat > rules.yml <<'YAML'
dataset:
  max_duplicate_rows: 0
columns:
  id:
    required: true
    unique: true
  name:
    required: true
  age:
    min: 0
    max: 120
YAML
```

**1. Profile only** (exit 0 — status `inspected`, no rules applied). Real output, compacted here for width:

```json
{"schema_version":"1.0","source":{"path":"customers.csv","format":"csv","size_bytes":62},
 "selection":{"kind":"table","sheet":null,...,"encoding":"utf-8-sig","rules":{"path":null,"supplied":false}},
 "profile":{"rows":4,"columns":3,"column_names":["id","name","age"],
   "column_profiles":[
     {"name":"id","missing":0,"missing_percent":0.0,"nonmissing":4,"distinct_nonmissing":4,
      "observed_types":{"string":4},"numeric":{"count":4,"min":12,"max":789,"mean":345.0},
      "string_length":{"min":5,"max":5}},
     {"name":"name","missing":1,"missing_percent":25.0,...,"numeric":null,"string_length":{"min":2,"max":5}},
     {"name":"age","missing":1,...,"numeric":{"count":2,"min":25,"max":30,"mean":27.5}}],
   "duplicate_rows":0,"text":null},
 "checks":[],"dimensions":{"completeness":{"score":null,"evaluated":0,"violations":0},"uniqueness":{"score":null,"evaluated":0,"violations":0},"validity":{"score":null,"evaluated":0,"violations":0}},"warnings":[],"errors":[],
 "overall":{"status":"inspected","exit_code":0,"rules_applied":false,...}}
```

Note the profile's numeric view parses `"00123"` as 123 without rewriting the preserved string, and literal `NA` counts as a value, not as missing.

**2. Apply rules** (exit 1 — violations; failing checks, verbatim from the real output):

```bash
python skills/data-quality/scripts/dq.py customers.csv --rules rules.yml
```

```json
{"rule":"required","dimension":"completeness","scope":"column","column":"name","evaluated":4,"violations":1,
 "status":"failed","row_refs":[2],"row_refs_truncated":false}
{"rule":"min","dimension":"validity","scope":"column","column":"age","evaluated":3,"violations":1,
 "status":"failed","row_refs":[3],"row_refs_truncated":false,"details":{"bound":0}}
{"rule":"max","dimension":"validity","scope":"column","column":"age","evaluated":3,"violations":1,
 "status":"failed","row_refs":[3],"row_refs_truncated":false,"details":{"bound":120}}
```
overall: `{"status":"failed","exit_code":1,"rules_applied":true,"checks_passed":3,"checks_failed":3,"checks_not_evaluated":0}`

**3. SQLite table:**

```bash
python skills/data-quality/scripts/dq.py shop.sqlite --table orders
```

Save a report by redirecting stdout to a **new** path only — never onto the source or rules file:

```bash
python skills/data-quality/scripts/dq.py customers.csv --rules rules.yml > report.json
```

Exit codes: `0` = inspected / no failed rules · `1` = rule violations · `2` = input, configuration, or execution error (errors take precedence). A no-rules run reports `inspected`, never `passed`.

## Rules

Exactly eight column rules — `required`, `max_null_pct`, `unique`, `type`, `min`, `max`, `allowed`, `regex` — and two dataset rules: `max_duplicate_rows` and `unique_together`. A compound-key rule is written as a non-empty list of groups, for example `dataset: {unique_together: [[country_code, year]]}`; each group must contain at least two known, distinct columns. Counting semantics (missing values, missing percentages, duplicate groups, numeric parsing, type matching, exact scalar matching), evidence limits, and read-only guarantees are specified in `skills/data-quality/references/RULES.md` — read it before writing rules.

## Rule provenance in agent reports

The YAML rule syntax intentionally has no provenance fields. Provenance is a host-agent reporting concept, so the deterministic engine and JSON contract remain unchanged. Classify each rule before writing it:

- **Explicit constraint (confirmed):** directly required by the user, contract, standard, schema, policy, SLA, or authoritative source.
- **Source-informed candidate:** strongly suggested by official metadata, but not explicitly established as a requirement. A documented field or value vocabulary does not by itself make a field mandatory.
- **Inferred candidate:** suggested by the LLM from profiling, observed patterns, context, or likely semantics.

Only failed explicit/confirmed constraints belong under **Confirmed findings**. Failures from source-informed and inferred candidates belong under **Candidate findings** and must include their provenance, rationale, evidence/source, uncertainty, and deterministic result. Official metadata alone must not promote a candidate to a confirmed business requirement. When the distinction affects interpretation, run confirmed constraints separately from candidate rules.

## Output contract

One compact JSON document on stdout with `schema_version`, `source`, `selection`, `profile`, `checks`, `dimensions`, `warnings`, `errors`, `overall`. Every check carries its rule, fixed `dimension` (`completeness`, `uniqueness`, or `validity`), scope/column, `evaluated` count, `violations` count, `status` (`passed` / `failed` / `not_evaluated`), and up to 10 run-local `row_refs`. A `unique_together` check leaves `column` as `null` and identifies its configured group with deterministic `columns` and `details.columns` lists. Example values are opt-in (`--examples N`, ≤5 per check, ≤100 characters total including any `…` marker) and are **not anonymized**. Strict JSON: no NaN/Infinity tokens.

`dimensions` always contains `completeness`, `uniqueness`, and `validity`. Each aggregates only evaluated checks in that dimension: `score = (sum(evaluated) - sum(violations)) / sum(evaluated) * 100`; `score` is rounded to 2 decimals after calculation and is `null` when no checks are evaluated. These are **rule-conformance percentages**: they measure how the supplied rule applications performed, not intrinsic dataset cleanliness or the percentage of the dataset that is clean. There is no overall or global DQ score.

## Human-facing dimension reporting

When summarizing results, use **Completeness rule-conformance**, **Uniqueness rule-conformance**, and **Validity rule-conformance**. Include the exact score plus `evaluated` / `violations`, and include coverage context when practical: the number of checks, distinct columns or scopes, and total evaluated rule applications. Example:

```text
Validity rule-conformance: 99.98% — 5 checks · 4 columns · 99,101 rule applications
```

Coverage counts are derived from the emitted checks in the report layer; they do not change the JSON field names or score formula. **Dimension percentages produced from materially different rule sets are not directly comparable.** Do not rank a 100% result from two lenient checks against a 100% result from eight stricter checks as though they represented equivalent coverage.

For the default concise human-facing summary, follow `skills/data-quality/SKILL.md`; raw JSON is machine evidence and should be shown only when requested.

## v0.2.1 release notes

This release candidate hardens correctness and documentation without adding capabilities:

- `required: false` and `unique: false` now disable those checks entirely.
- CSV/TSV inputs reject NUL characters before parsing.
- Duplicate or empty column names are rejected consistently across supported readers.
- JSON and JSONL reject duplicate object keys.
- Malformed rule sections and null duplicate-row limits are rejected strictly.
- Numeric profile means use overflow-safe summation for finite large values.
- The ERPNext benchmark derives expectations from actual injections and validates CLI status, exit codes, and errors.
- Regex guidance documents catastrophic-backtracking risk and host-enforced execution timeouts.
- Documentation now corrects YAML identifier quoting, inline regex flags, example-length limits, bundle portability, harness status, and current-scope wording.

## Limits

- Sources above **50 MiB** or **200,000 rows** are rejected (exit 2) — never sampled, truncated, or reported as if complete. Reads are bounded per format where possible; there is no streaming framework and no promised hard memory ceiling.
- One sheet or one table per run. Duplicate or empty headers are rejected, not renamed. A record with more fields than the header is rejected (exit 2) — data is never truncated, shifted, or silently dropped.
- Text encoding: strict UTF-8 with BOM acceptance by default; `--encoding NAME` adds other encodings strictly — no lossy replacement or auto-detection.
- Python regular expressions can catastrophically backtrack on some patterns. Untrusted or automated runs should use a host-enforced execution timeout; the helper does not provide a regex timeout.

## Read-only boundaries

- Source data is permanently read-only. The helper never writes to the source. SQLite is opened via URI `mode=ro`; write attempts fail with `attempt to write a readonly database` (enforced by tests). All readers are verified to leave source bytes unchanged. Note: opening a WAL-mode database read-only may create SQLite's transient `-shm`/`-wal` sidecar files — the database file itself is never written.
- Cleansing, repair, and data alteration are out of scope by design; findings and suggested fixes are explanations only.
- No network access, no model calls, and no execution of data-derived strings. There is no output-file flag.
- `row_refs` are run-local record positions (1-based; physical line numbers for text sources; scan offsets for SQLite), not permanent row identifiers.

## What this does not assess

- Semantic or factual quality of text; freshness without an SLA; accuracy without reference data.
- Baselines, drift, distribution changes, or outlier detection — deferred by design.
- Cleansing, repair, or alteration of source data — permanently out of scope by design; findings and suggested fixes are explanations only.
- XLSX formulas are not evaluated; cached values may be missing or stale (a warning says so).
- No overall or global DQ score; exit 0 alone never proves dataset quality.
- Escaping adversarial cells as data does not make every host model immune to prompt injection.

## Verification status (as of 2026-09-24)

Environment: Linux, Python 3.14.4, pandas 3.0.6, openpyxl 3.1.5, PyYAML 6.0.3, pytest 9.1.1, pyarrow 25.0.1.

- **Local validation** — **140 passed**.
- **GitHub Actions on commit `d08feb2`** — **116 passed**.
- **Hermes end-to-end verification** — the tagged `v0.2.0` bundle was installed in a temporary `HERMES_HOME` and exercised; profiles-first behavior, rule provenance separation, deterministic scores, no global score, limitations, read-only next actions, and unchanged source all passed.
- **UCI Adult benchmark** — **60/60**, 0 unexpected, source unchanged.
- **ERPNext benchmark** — **60/60**, 0 unexpected, source unchanged.
- **Healthcare messy/clean pair** — profile → inferred candidate rules → deterministic checks/scores → human-report validation passed; external files were used transiently and are not committed.
- **FEBRL boundary validation** — exact-duplicate boundary passed; modified/linked records were not reported as exact duplicate rows; external files were used transiently and are not committed.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -r skills/data-quality/scripts/requirements.txt pytest pyarrow
python -m pytest tests/ -q
```

If `python -m venv` produces an environment without pip (some distro builds omit `ensurepip`), create it with `uv venv` and install with `uv pip install` — the dependency set is identical.

CI (`.github/workflows/ci.yml`) runs the same suite in one job on Python 3.14; the latest recorded GitHub Actions result is listed above. The same dependency set and test command were reproduced locally in a fresh venv.

## Roadmap (deferred by design)

The current scope stops at the capabilities described above. The following are deliberately **not** implemented, and no extension infrastructure is being designed for them now:

- **Baseline comparison** — no stored profiles, no comparison against a previous edition of a dataset.
- **Drift / distribution-change detection** — no change detection between runs.
- **IQR / statistical anomaly detection** — outliers are not flagged; only the rules the user supplies are checked.
- **SQLAlchemy or any live non-SQLite database access** — PostgreSQL, MySQL, and SQL Server go through an export to a supported file first.
- **Remediation / repair** — the skill never modifies source data; findings and suggested fixes are explanations only.

The source-data boundary is permanent: cleansing, repair, and data alteration are out of scope by design.

No extension roadmap is promised for those boundaries; future work, if any, remains read-only profiling and rule checking.

## License

MIT — see [LICENSE](LICENSE).
