# agent-data-quality-skill

**v0.1.0** — a small, portable [Agent Skill](https://agentskills.io/specification) for deterministic, **read-only** data-quality profiling and rule checking.

The host LLM (Hermes, Claude Code, Codex, or any Agent Skills–compatible host) interprets the objective and writes the report; Python (`skills/data-quality/scripts/dq.py`) reads the local data and computes every metric and check. Source data is permanently read-only: the helper makes **no model calls, no network access, and no writes** to inspected sources.

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

Other databases (PostgreSQL/MySQL/SQL Server): export to a supported file first — v0.1 ships no connectors and implies none.

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

Exactly eight column rules — `required`, `max_null_pct`, `unique`, `type`, `min`, `max`, `allowed`, `regex` — and one dataset rule, `max_duplicate_rows`. Counting semantics (missing values, missing percentages, duplicate groups, numeric parsing, type matching, exact scalar matching), evidence limits, and read-only guarantees are specified in `skills/data-quality/references/RULES.md` — read it before writing rules.

## Output contract

One compact JSON document on stdout with `schema_version`, `source`, `selection`, `profile`, `checks`, `dimensions`, `warnings`, `errors`, `overall`. Every check carries its rule, fixed `dimension` (`completeness`, `uniqueness`, or `validity`), scope/column, `evaluated` count, `violations` count, `status` (`passed` / `failed` / `not_evaluated`), and up to 10 run-local `row_refs`. Example values are opt-in (`--examples N`, ≤5 per check, ≤100 characters each) and are **not anonymized**. Strict JSON: no NaN/Infinity tokens.

`dimensions` always contains `completeness`, `uniqueness`, and `validity`. Each aggregates only evaluated checks in that dimension: `score = (sum(evaluated) - sum(violations)) / sum(evaluated) * 100`; `score` is rounded to 2 decimals after calculation and is `null` when no checks are evaluated. There is no overall or global DQ score.

## Limits

- Sources above **50 MiB** or **200,000 rows** are rejected (exit 2) — never sampled, truncated, or reported as if complete. Reads are bounded per format where possible; there is no streaming framework and no promised hard memory ceiling.
- One sheet or one table per run. Duplicate or empty headers are rejected, not renamed. A record with more fields than the header is rejected (exit 2) — data is never truncated, shifted, or silently dropped.
- Text encoding: strict UTF-8 with BOM acceptance by default; `--encoding NAME` adds other encodings strictly — no lossy replacement or auto-detection.

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

## Verification status (as of 2026-09-20)

Environment: Linux, Python 3.14.4, pandas 3.0.6, openpyxl 3.1.5, PyYAML 6.0.3, pyarrow 25.0.1, pytest 9.1.1.

- **Local Part 2 checkpoint run (`686af68`)** — **107 passed, 3 skipped**.
- **GitHub Actions on commit `686af68`** — **110 passed**.
- **Copied-folder test** — `skills/data-quality/` was copied to an unrelated directory, installed into a clean venv **from `requirements.txt` only**, and run from an unrelated working directory: profile+rules run produced the expected exit 1 and matching check summary; the Parquet path returned the specific `missing_dependency` error because pyarrow was absent (as designed). No repository-root dependency.
- **Hermes Agent harness (this machine; isolated scratch `HERMES_HOME`, never a live profile)** — the bundle was copied into a scratch home's skills directory and driven with `hermes -z … --skills data-quality`: the harness preloaded the skill by name, the agent resolved and ran the installed `scripts/dq.py` itself, and reported exit 1 with the expected per-check lines (3 passed / 3 failed / 0 not_evaluated). Latest run: against the final revision after the record-width fix (`dq.py` sha256 prefix `e55118ac`); the earlier build runs produced the same report, and `hermes skills list` in that scratch home registers `data-quality` as enabled. Nothing was installed into a live profile's skills directory. Note: Hermes one-shot mode (`-z`) does not inject a skills index — pass `--skills data-quality`, or install into the host's skills directory for regular sessions.
- **Format compatibility vs tested harnesses** — the bundle follows the portable Agent Skills layout (`SKILL.md` + `scripts/` + `references/`), which does not imply other hosts were exercised. Codex, Claude Code, and all other hosts are **untested** by this repository.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -r skills/data-quality/scripts/requirements.txt pytest pyarrow
python -m pytest tests/ -q
```

If `python -m venv` produces an environment without pip (some distro builds omit `ensurepip`), create it with `uv venv` and install with `uv pip install` — the dependency set is identical.

CI (`.github/workflows/ci.yml`) runs the same suite in one job on Python 3.14; the latest recorded GitHub Actions result is listed above. The same dependency set and test command were reproduced locally in a fresh venv.

## Roadmap (deferred by design)

v0.1.0 stops at the scope described above. The following are deliberately **not** implemented, and no extension infrastructure is being designed for them now:

- **Baseline comparison** — no stored profiles, no comparison against a previous edition of a dataset.
- **Drift / distribution-change detection** — no change detection between runs.
- **IQR / statistical anomaly detection** — outliers are not flagged; only the rules the user supplies are checked.
- **SQLAlchemy or any live non-SQLite database access** — PostgreSQL, MySQL, and SQL Server go through an export to a supported file first.
- **Remediation / repair** — the skill never modifies source data; findings and suggested fixes are explanations only.

The source-data boundary is permanent: cleansing, repair, and data alteration are out of scope by design.

No extension roadmap is promised for those boundaries; future work, if any, remains read-only profiling and rule checking.

## License

MIT — see [LICENSE](LICENSE).
