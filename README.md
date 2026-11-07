# agent-data-quality-skill

Deterministic, **read-only** data-quality evidence for AI agents. This repository ships one portable [Agent Skill](https://agentskills.io/specification) that an agent can download, drop into its skills directory, and run with the Python it already has: profile a local dataset and check it against a small YAML rule set, with every number computed by Python rather than by the model.

**Version 0.3.0** · [Releases](https://github.com/aalomair/agent-data-quality-skill/releases) · [Changelog](CHANGELOG.md) · MIT

The host LLM (Hermes, Claude Code, Codex, or any Agent Skills–compatible host) interprets the objective, chooses the rules, and writes the report. Python (`skills/data-quality/scripts/dq.py`) reads the local data and computes every metric and check. The helper makes **no model calls, no network access, and no writes** to inspected sources. Hermes is the only host harness-tested end to end in this repository; Codex and Claude Code follow the same open skill format but have not been harness-tested here.

## Install for agents

### 1. Download the bundle

```bash
curl -fsSL -o data-quality-skill.zip \
  https://github.com/aalomair/agent-data-quality-skill/releases/latest/download/data-quality-skill.zip

# pinned to this version instead of latest:
# https://github.com/aalomair/agent-data-quality-skill/releases/download/v0.3.0/data-quality-skill.zip
```

```bash
unzip -q data-quality-skill.zip     # creates ./data-quality/
```

The zip unpacks to a single top-level `data-quality/` directory — that directory is the skill. Keep it intact, including its `LICENSE`. Each release also attaches a `SHA256SUMS` file, which verifies the downloaded zip:

```bash
curl -fsSL -O https://github.com/aalomair/agent-data-quality-skill/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS
```

### 2. Put it in the host's skills directory

| Host | Location |
|---|---|
| Hermes | `<hermes-home>/skills/data-quality/` (the only harness-tested host here) |
| Claude Code | `~/.claude/skills/data-quality/` (personal) or `.claude/skills/data-quality/` (project) — per the [Claude Code skills docs](https://code.claude.com/docs/en/skills#where-skills-live) |
| Codex | `$HOME/.agents/skills/data-quality/` (user) or `.agents/skills/data-quality/` (repository) — per the [Codex skills docs](https://developers.openai.com/codex/skills) |
| Any other Agent Skills host | that host's skills directory, per its docs |

Alternatively, keep the directory anywhere and resolve `scripts/dq.py` relative to it; nothing requires the repository checkout.

### 3. Install the dependencies yourself, if you decide to

The skill **never installs packages**. The installing agent or the user decides whether and where to install these — an existing environment or a fresh virtual environment — following the host's and the user's policy.

- Python 3.10–3.14.
- `pandas>=2.2,<4` — required on every run.
- `PyYAML>=6.0,<7` — required on every run (import name `yaml`).
- `openpyxl>=3.1,<4` — only for `.xlsx` sources.
- `pyarrow>=15` — optional, only for `.parquet` sources.

These ranges are mirrored from `skills/data-quality/scripts/requirements.txt`, which is authoritative; a test keeps the docs in sync with it. Check what is already available:

```bash
python -c "import pandas, yaml"
```

Example install, into the environment you choose:

```bash
python -m venv .venv && . .venv/bin/activate             # optional; use an existing env instead if you prefer
python -m pip install -r <skill-directory>/scripts/requirements.txt
python -m pip install 'pyarrow>=15'                      # optional, Parquet only
```

If `pandas` or `yaml` is missing, the helper still prints one valid JSON error document with `errors[0].code == "missing_dependency"` and exits 2; no traceback reaches stdout. The message names the missing module and the requirements install command. Missing `openpyxl` or `pyarrow` behaves the same way for those source formats.

### 4. Verify the install

```bash
python <skill-directory>/scripts/dq.py --help
python <skill-directory>/scripts/dq.py <some.csv>
```

### Git alternative

For an agent that prefers git over release downloads:

```bash
git clone --depth 1 https://github.com/aalomair/agent-data-quality-skill.git
cp -R agent-data-quality-skill/skills/data-quality <host-skills-directory>/data-quality
```

## Quick start — the agent flow

The typical request is: *"download the data-quality skill, use it on this dataset, and put the results in a dashboard."* The skill's job is the deterministic evidence; the host agent builds the dashboard from the saved JSON.

**1. Create a sample dataset and a rules file** (or use the user's own file):

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

**2. Profile first, and save the JSON to a new file** — never onto the source or rules file:

```bash
python <skill-directory>/scripts/dq.py customers.csv > profile.json
```

Exit 0, status `inspected`, no rules applied:

```json
{"schema_version":"1.0","source":{"path":"customers.csv","format":"csv","size_bytes":62},
 "selection":{"kind":"table",...,"encoding":"utf-8-sig","rules":{"path":null,"supplied":false}},
 "profile":{"rows":4,"columns":3,"column_names":["id","name","age"],
   "column_profiles":[
     {"name":"id","missing":0,"missing_percent":0.0,"nonmissing":4,"distinct_nonmissing":4,
      "observed_types":{"string":4},"numeric":{"count":4,"min":12,"max":789,"mean":345.0},
      "string_length":{"min":5,"max":5}},
     {"name":"name","missing":1,"missing_percent":25.0,...,"numeric":null,"string_length":{"min":2,"max":5}},
     {"name":"age","missing":1,...,"numeric":{"count":2,"min":25,"max":30,"mean":27.5}}],
   "duplicate_rows":0,"text":null},
 "checks":[],"dimensions":{"completeness":{"score":null,...},...},"warnings":[],"errors":[],
 "overall":{"status":"inspected","exit_code":0,"rules_applied":false,...}}
```

The profile's numeric view parses `"00123"` as 123 without rewriting the preserved string, and literal `NA` counts as a value, not as missing. (`...` marks fields elided here for width; the real document is complete and compact.)

**3. Apply the rules and save the result** (exit 1 — violations):

```bash
python <skill-directory>/scripts/dq.py customers.csv --rules rules.yml > report.json
```

Failing checks, verbatim from the real output:

```json
{"rule":"required","dimension":"completeness","scope":"column","column":"name","evaluated":4,"violations":1,
 "status":"failed","row_refs":[2],"row_refs_truncated":false}
{"rule":"min","dimension":"validity","scope":"column","column":"age","evaluated":3,"violations":1,
 "status":"failed","row_refs":[3],"row_refs_truncated":false,"details":{"bound":0}}
{"rule":"max","dimension":"validity","scope":"column","column":"age","evaluated":3,"violations":1,
 "status":"failed","row_refs":[3],"row_refs_truncated":false,"details":{"bound":120}}
```

`overall`: `{"status":"failed","exit_code":1,"rules_applied":true,"checks_passed":3,"checks_failed":3,"checks_not_evaluated":0}`

**4. Build the report or dashboard from `report.json`.** `references/OUTPUT.md` documents every field, status, `details` shape, warning and error code. `SKILL.md` gives the human-facing report format and the dashboard rules; in short: use the saved JSON (never recomputed numbers), show the three dimension rule-conformance scores with `evaluated`/`violations`, show no global score, render `null` as "not assessed", and treat `--examples` values as raw and shareable only with consent. The skill ships no dashboard generator — the host agent builds it.

**Other sources and options:**

```bash
python <skill-directory>/scripts/dq.py shop.sqlite --table orders
python <skill-directory>/scripts/dq.py book.xlsx --sheet Data
python <skill-directory>/scripts/dq.py data.csv --encoding cp1256
python <skill-directory>/scripts/dq.py data.csv --rules rules.yml --examples 3
```

Exit codes: `0` = inspected / no failed rules · `1` = rule violations · `2` = input, configuration, dependency, or execution error (errors take precedence). A no-rules run reports `inspected`, never `passed`.

### Programmatic use

`dq.run()` returns exactly the CLI payload and never raises, so an agent can inspect results in-process:

```python
import sys
sys.path.insert(0, "<skill-directory>/scripts")
import dq

payload = dq.run("customers.csv", "rules.yml")
payload["overall"]["exit_code"]  # 0, 1, or 2
```

The signature mirrors the CLI: `dq.run(source, rules=None, *, sheet=None, table=None, encoding=None, examples=0)`. The CLI JSON remains the primary contract.

## Repository layout

```text
README.md                      this file
CHANGELOG.md                   release notes
LICENSE                        MIT
.github/workflows/ci.yml       tests on Python 3.10–3.14 + full-history secret scan
skills/data-quality/           the portable skill bundle (the download payload)
  SKILL.md                     skill instructions + frontmatter
  LICENSE                      MIT notice retained in copy-only installs
  scripts/dq.py                the single CLI helper and dq.run()
  scripts/requirements.txt     runtime dependency ranges
  references/RULES.md          rule semantics, evidence rules, read-only guarantees
  references/OUTPUT.md         JSON field reference for reports and dashboards
tests/test_dq.py               pytest suite (CLI-level + unit tests)
tests/test_publication.py      packaging, licensing and release-safety tests
tests/test_skill_bundle.py     dependency-doc sync, OUTPUT.md contract, copy parity, versions
benchmark/run.py               defect-injection benchmark (UCI Adult + ERPNext)
benchmark/public/              UCI Adult fixture (CC BY 4.0), notice + rules
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

## Rules

Exactly eight column rules — `required`, `max_null_pct`, `unique`, `type`, `min`, `max`, `allowed`, `regex` — and three dataset rules: `max_duplicate_rows`, `unique_together`, and the narrow cross-field `conditional_required`. Compound keys use a non-empty list of groups, and conditional requirements use one exact scalar trigger and one different required column:

```yaml
dataset:
  conditional_required:
    - when:
        column: status
        equals: Closed
      then_required: closed_date
```

Counting semantics (missing values, missing percentages, duplicate groups, numeric parsing, type matching, exact scalar matching), evidence limits, and read-only guarantees are specified in `skills/data-quality/references/RULES.md` — read it before writing rules.

## Rule provenance in agent reports

The YAML rule syntax intentionally has no provenance fields. Provenance is a host-agent reporting concept, so the deterministic engine and JSON contract remain unchanged. Classify each rule before writing it:

- **Explicit constraint (confirmed):** directly required by the user, contract, standard, schema, policy, SLA, or authoritative source.
- **Source-informed candidate:** strongly suggested by official metadata, but not explicitly established as a requirement. A documented field or value vocabulary does not by itself make a field mandatory.
- **Inferred candidate:** suggested by the LLM from profiling, observed patterns, context, or likely semantics.

Only failed explicit/confirmed constraints belong under **Confirmed findings**. Failures from source-informed and inferred candidates belong under **Candidate findings** and must include their provenance, rationale, evidence/source, uncertainty, and deterministic result. Official metadata alone must not promote a candidate to a confirmed business requirement. When the distinction affects interpretation, run confirmed constraints separately from candidate rules.

## Output contract

One compact JSON document on stdout with `schema_version`, `source`, `selection`, `profile`, `checks`, `dimensions`, `warnings`, `errors`, `overall`. Every check carries its rule, fixed `dimension` (`completeness`, `uniqueness`, or `validity`), scope/column, `evaluated` count, `violations` count, `status` (`passed` / `failed` / `not_evaluated`), and up to 10 run-local `row_refs`. `unique_together` and `conditional_required` checks leave `column` as `null` and identify their columns in `columns` and `details`. Example values are opt-in (`--examples N`, ≤5 per check, ≤100 characters total including any `…` marker) and are **not anonymized**. Strict JSON: no NaN/Infinity tokens.

`dimensions` always contains `completeness`, `uniqueness`, and `validity`. Each aggregates only evaluated checks in that dimension: `score = (sum(evaluated) - sum(violations)) / sum(evaluated) * 100`; `score` is rounded to 2 decimals after calculation and is `null` when no checks are evaluated. These are **rule-conformance percentages**: they measure how the supplied rule applications performed, not intrinsic dataset cleanliness or the percentage of the dataset that is clean. There is no overall or global DQ score.

The full field-by-field reference — top-level keys, per-column profile fields, every check field and `details` shape, statuses, warnings, error codes and exit codes — is [`skills/data-quality/references/OUTPUT.md`](skills/data-quality/references/OUTPUT.md). A test checks that reference against the engine.

## Human-facing dimension reporting

When summarizing results, use **Completeness rule-conformance**, **Uniqueness rule-conformance**, and **Validity rule-conformance**. Include the exact score plus `evaluated` / `violations`, and include coverage context when practical: the number of checks, distinct columns or scopes, and total evaluated rule applications. Example:

```text
Validity rule-conformance: 99.98% — 5 checks · 4 columns · 99,101 rule applications
```

Coverage counts are derived from the emitted checks in the report layer; they do not change the JSON field names or score formula. **Dimension percentages produced from materially different rule sets are not directly comparable.** Do not rank a 100% result from two lenient checks against a 100% result from eight stricter checks as though they represented equivalent coverage.

For the default concise human-facing summary and the dashboard rules, follow [`skills/data-quality/SKILL.md`](skills/data-quality/SKILL.md); raw JSON is machine evidence and should be shown only when requested.

## Versioning and releases

Versions are git tags and GitHub releases; the repository is not a Python package and is not published to PyPI. Release assets are built from `git archive` of the tag, so they contain exactly the tracked `skills/data-quality/` tree.

Release history and per-version notes: [CHANGELOG.md](CHANGELOG.md). The latest release: [github.com/aalomair/agent-data-quality-skill/releases/latest](https://github.com/aalomair/agent-data-quality-skill/releases/latest).

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

## Verification status

Local environment for the dated run below: Linux, Python 3.14.4, pandas 3.0.6, openpyxl 3.1.5, PyYAML 6.0.3, pytest 9.1.1, pyarrow 25.0.1.

- **Local suite (2026-11-07)** — `210 passed` on Python 3.14, `210 passed` in a clean Python 3.11 virtual environment, and `210 passed` in a clean Python 3.10 virtual environment.
- **UCI Adult benchmark (2026-11-07)** — **60/60** expected rule-violation detections, 0 unexpected, source unchanged. These are injected/overlapping rule checks, not 60 independent naturally occurring defects; see the [benchmark notice](benchmark/public/README.md).
- **CI** — [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs the full suite on Python 3.10, 3.11, 3.12, 3.13 and 3.14, plus a checksum-verified full-history Gitleaks scan, on every push. The exact commit and run for a release are recorded in the release notes/report; a run verifies only the commit it ran on.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -r skills/data-quality/scripts/requirements.txt pytest pyarrow
python -m pytest tests/ -q
```

If `python -m venv` produces an environment without pip (some distro builds omit `ensurepip`), create it with `uv venv` and install with `uv pip install` — the dependency set is identical.

CI (`.github/workflows/ci.yml`) runs the same suite across Python 3.10–3.14 and a separate full-history Gitleaks scan. Jobs use read-only repository permissions, checkout without persisted credentials, and immutable action SHAs; the scanner binary is version-pinned and SHA-256-verified before execution. Runtime dependency ranges remain flexible rather than fully locked.

Keep credentials in ignored `.env`/`.env.*` files, and put generated reports in the ignored `reports/` directory. Only sanitized placeholders belong in a tracked `.env.example`. Ignore rules do not remove already tracked secrets; inspect staged files and run the secret scan before pushing.

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

Project code and documentation are MIT-licensed — see [LICENSE](LICENSE). The portable skill includes the same [MIT notice](skills/data-quality/LICENSE) so directory-only installs retain it.

The third-party `benchmark/public/adult.csv` dataset is **CC BY 4.0**, not MIT. See [dataset attribution, license links, transformations, and checksums](benchmark/public/README.md). The benchmark rules and program remain MIT-licensed.
