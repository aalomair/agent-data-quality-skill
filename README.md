# agent-data-quality-skill

An [Agent Skill](https://agentskills.io/specification) that lets an AI agent check the quality of a local dataset without guessing at the numbers.

**Version 0.4.0** · [Releases](https://github.com/aalomair/agent-data-quality-skill/releases) · [Changelog](CHANGELOG.md) · MIT

## Why this exists

Ask a language model how many rows in a file are missing an email address and it will often give you a confident number that it never actually counted. That is fine for a chat, and not fine for a data-quality report someone is going to act on.

This skill splits the work. The agent (Hermes, Claude Code, Codex, or any host that reads Agent Skills) does what models are good at: understanding what you're trying to check, proposing rules, and writing up the findings. A small Python script, `skills/data-quality/scripts/dq.py`, does the part that has to be exact: reading the file, profiling every column, and evaluating each rule. The script makes no model calls, opens no network connections, and never writes to the data it inspects.

I've tested it end to end with Hermes. Claude Code and Codex use the same skill format, but I haven't run them through the same harness yet.

## Install for agents

### 1. Download the bundle

```bash
curl -fsSL -o data-quality-skill.zip \
  https://github.com/aalomair/agent-data-quality-skill/releases/latest/download/data-quality-skill.zip

# or pin this exact version:
# https://github.com/aalomair/agent-data-quality-skill/releases/download/v0.4.0/data-quality-skill.zip
```

```bash
unzip -q data-quality-skill.zip     # creates ./data-quality/
```

The zip contains one folder, `data-quality/`, and that folder is the skill. Keep it intact, `LICENSE` included. Every release also ships a `SHA256SUMS` file so you can check the download:

```bash
curl -fsSL -O https://github.com/aalomair/agent-data-quality-skill/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS
```

### 2. Put it where your agent looks for skills

| Host | Location |
|---|---|
| Hermes | `<hermes-home>/skills/data-quality/` (the host I've tested) |
| Claude Code | `~/.claude/skills/data-quality/` (personal) or `.claude/skills/data-quality/` (project), per the [Claude Code skills docs](https://code.claude.com/docs/en/skills#where-skills-live) |
| Codex | `$HOME/.agents/skills/data-quality/` (user) or `.agents/skills/data-quality/` (repository), per the [Codex skills docs](https://developers.openai.com/codex/skills) |
| Anything else | wherever that host keeps skills |

You can also leave the folder anywhere and call `scripts/dq.py` relative to it. Nothing depends on having this repository checked out.

### 3. Dependencies (your call)

The skill will never install packages on its own. You, or the agent installing it, decide whether to install them and where, whether that's an existing environment or a fresh virtual environment.

- Python 3.10–3.14.
- `pandas>=2.2,<4`, needed on every run.
- `PyYAML>=6.0,<7`, needed on every run (imported as `yaml`).
- `openpyxl>=3.1,<4`, only for `.xlsx` files.
- `pyarrow>=15`, optional, only for `.parquet` files.

The source of truth for these ranges is `skills/data-quality/scripts/requirements.txt`, and a test fails if this list drifts from it. To see what you already have:

```bash
python -c "import pandas, yaml"
```

To install into whichever environment you picked:

```bash
python -m venv .venv && . .venv/bin/activate             # optional; an existing env works too
python -m pip install -r <skill-directory>/scripts/requirements.txt
python -m pip install 'pyarrow>=15'                      # optional, Parquet only
```

If `pandas` or `yaml` is missing, the script doesn't crash with a traceback. It prints a normal JSON report with `errors[0].code == "missing_dependency"`, names the missing module and the install command, and exits with code 2. A missing `openpyxl` or `pyarrow` is handled the same way for those formats.

### 4. Check it works

```bash
python --version
python -c "import pandas, yaml; print('pandas', pandas.__version__, '| PyYAML', yaml.__version__)"
python <skill-directory>/scripts/dq.py --help
python <skill-directory>/scripts/dq.py <some.csv>
```

Run these with the same interpreter the agent will use. If packages can't be installed in that environment, the agent should say which one is missing and stop, rather than produce results without the engine.

### Or use git

```bash
git clone --depth 1 https://github.com/aalomair/agent-data-quality-skill.git
cp -R agent-data-quality-skill/skills/data-quality <host-skills-directory>/data-quality
```

## A quick walkthrough

A typical request looks like: *"get the data-quality skill, run it on this file, and give me a dashboard."* The skill produces the evidence. Building the dashboard is the agent's job, using the JSON the skill saved.

**1. A small dataset and a rules file** (or use your own):

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

**2. Profile it first, and save the output to a new file.** Never redirect onto the source or the rules file.

```bash
python <skill-directory>/scripts/dq.py customers.csv > profile.json
```

This exits 0 with status `inspected`, since no rules were applied yet:

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

Two details worth noticing: `"00123"` is read as the number 123 for the numeric stats, but the original string is kept as is; and the literal text `NA` counts as a value, not as missing. (`...` just marks fields I cut for width. The real output is complete.)

**3. Apply the rules** (this exits 1 because some rules fail):

```bash
python <skill-directory>/scripts/dq.py customers.csv --rules rules.yml > report.json
```

The failing checks, copied from the actual output:

```json
{"rule":"required","dimension":"completeness","scope":"column","column":"name","evaluated":4,"violations":1,
 "status":"failed","row_refs":[2],"row_refs_truncated":false}
{"rule":"min","dimension":"validity","scope":"column","column":"age","evaluated":3,"violations":1,
 "status":"failed","row_refs":[3],"row_refs_truncated":false,"details":{"bound":0}}
{"rule":"max","dimension":"validity","scope":"column","column":"age","evaluated":3,"violations":1,
 "status":"failed","row_refs":[3],"row_refs_truncated":false,"details":{"bound":120}}
```

`overall`: `{"status":"failed","exit_code":1,"rules_applied":true,"checks_passed":3,"checks_failed":3,"checks_not_evaluated":0}`

**4. Build the report or dashboard from `report.json`.** Every field, status, warning and error code is documented in `references/OUTPUT.md`, and `SKILL.md` describes how the agent should present results. The short version: take numbers from the saved JSON rather than recalculating them, show the three dimension scores with their `evaluated` and `violations` counts, don't invent an overall score, show `null` as "not assessed", and treat `--examples` values as raw data you only share with the user's consent. There's no dashboard generator in the skill; the agent builds that.

**Other sources and options:**

```bash
python <skill-directory>/scripts/dq.py shop.sqlite --table orders
python <skill-directory>/scripts/dq.py book.xlsx --sheet Data
python <skill-directory>/scripts/dq.py data.csv --encoding cp1256
python <skill-directory>/scripts/dq.py data.csv --rules rules.yml --examples 3
```

Exit codes: `0` means inspected with no failed rules, `1` means at least one rule failed, and `2` means an input, configuration, dependency, or execution error (errors win over everything else). A run with no rules reports `inspected`, never `passed`.

### Calling it from Python

`dq.run()` returns the same payload the CLI prints and never raises, so an agent can use it in-process:

```python
import sys
sys.path.insert(0, "<skill-directory>/scripts")
import dq

payload = dq.run("customers.csv", "rules.yml")
payload["overall"]["exit_code"]  # 0, 1, or 2
```

The arguments match the CLI: `dq.run(source, rules=None, *, sheet=None, table=None, encoding=None, examples=0)`. The CLI's JSON is still the main contract.

## What's in the repo

```text
README.md                      this file
CHANGELOG.md                   release notes
LICENSE                        MIT
.github/workflows/ci.yml       tests on Python 3.10–3.14 + full-history secret scan
skills/data-quality/           the skill itself (this is what the release zip contains)
  SKILL.md                     instructions the agent reads
  LICENSE                      MIT notice, so copied installs keep it
  scripts/dq.py                the CLI and dq.run()
  scripts/requirements.txt     runtime dependency ranges
  references/RULES.md          exactly how each rule is evaluated
  references/OUTPUT.md         field-by-field guide to the JSON output
tests/test_dq.py               main pytest suite (CLI and unit tests)
tests/test_publication.py      packaging, licensing and release checks
tests/test_skill_bundle.py     doc/dependency sync, OUTPUT.md contract, copy parity, versions
benchmark/run.py               defect-injection benchmark (UCI Adult, plus ERPNext if you have an export)
benchmark/public/              UCI Adult data (CC BY 4.0), its notice, and rules
benchmark/private/             local-only datasets (gitignored)
```

## Supported inputs

| Source | Extensions | Notes |
|---|---|---|
| CSV / TSV | `.csv`, `.tsv` | One header row. Duplicate or empty headers are rejected. Blank lines are kept as empty records, short rows are padded as missing, and rows *wider* than the header are rejected rather than truncated or shifted. |
| Excel | `.xlsx` | `--sheet NAME`, or the first sheet (named in the report). Formulas are never run; their presence is reported and cached values may be missing or stale. Merged cells produce a warning. Data wider than the header row is rejected. |
| JSON | `.json` | An array of flat records with scalar values. Nested structures are rejected. |
| JSONL / NDJSON | `.jsonl`, `.ndjson` | One flat record per non-blank line. |
| Text / Markdown | `.txt`, `.md`, `.markdown` | Each line becomes a record in a `text` column. Blank lines are kept. Adds stats for blank lines, duplicate lines, line lengths, and unusual control characters. |
| SQLite | `.sqlite`, `.sqlite3`, `.db` | One `--table NAME`, opened read-only (`mode=ro`). Views aren't supported. Table names are validated exactly and quoted. |
| Parquet | `.parquet`, `.pq` | Flat tables only; needs the optional `pyarrow`. Nested fields are rejected. |

For PostgreSQL, MySQL or SQL Server, export the table to one of the formats above. There are no database connectors.

## Rules

There are eight column rules (`required`, `max_null_pct`, `unique`, `type`, `min`, `max`, `allowed`, `regex`) and three dataset rules: `max_duplicate_rows`, `unique_together` for compound keys, and `conditional_required` for simple "if this, then that must be filled" cases:

```yaml
dataset:
  conditional_required:
    - when:
        column: status
        equals: Closed
      then_required: closed_date
```

How missing values, percentages, duplicates, number parsing, type matching and exact matching are counted, plus evidence limits and the read-only guarantees, is all spelled out in `skills/data-quality/references/RULES.md`. Read it before writing rules.

## Where rules come from

A rule failing only means something if the rule was right in the first place. So when the agent writes a report, it labels each rule by where it came from. This lives in the report, not in the YAML, so the engine and its output format stay the same.

- **Explicit constraint (confirmed):** the user, a contract, a standard, a schema, a policy, an SLA, or another authoritative source actually requires it.
- **Source-informed candidate:** official metadata strongly suggests it, but nobody has said it's a requirement. A field being documented doesn't make it mandatory.
- **Inferred candidate:** the agent guessed it from the profile, patterns in the data, or what the columns probably mean.

Only failed confirmed constraints go under **Confirmed findings**. Failures from the other two go under **Candidate findings**, along with where the rule came from, why it was proposed, the evidence, how uncertain it is, and the result. Official metadata on its own doesn't promote a candidate to a confirmed requirement. When the difference matters, run the confirmed rules and the candidate rules separately.

## Output

The script prints one compact JSON document with `schema_version`, `source`, `selection`, `profile`, `checks`, `dimensions`, `warnings`, `errors` and `overall`. Each check records its rule, a fixed `dimension` (`completeness`, `uniqueness` or `validity`), its scope or column, how many values it `evaluated`, how many `violations` it found, a `status` (`passed`, `failed` or `not_evaluated`), and up to 10 `row_refs` pointing at offending rows. `unique_together` and `conditional_required` checks set `column` to `null` and list their columns in `columns` and `details`. Example values only appear if you ask for them (`--examples N`, at most 5 per check and 100 characters in total, counting any `…`), and they are **not anonymized**. The JSON is strict: no NaN or Infinity.

`dimensions` always has `completeness`, `uniqueness` and `validity`. Each one adds up only the checks that were actually evaluated: `score = (sum(evaluated) - sum(violations)) / sum(evaluated) * 100`, rounded to 2 decimals, or `null` if nothing in that dimension was evaluated.

It's important to read these correctly. They are **rule-conformance percentages**: how well the data did against the rules you gave it. They are not a measure of how clean the dataset is overall, and there is deliberately no single overall score.

The full reference is [`skills/data-quality/references/OUTPUT.md`](skills/data-quality/references/OUTPUT.md), and a test checks it against what the engine really emits.

## Presenting the scores

In a human-facing summary, call them **Completeness rule-conformance**, **Uniqueness rule-conformance** and **Validity rule-conformance**. Give the exact score with its `evaluated` and `violations` counts, and where you can, how much ground the rules covered (number of checks, columns or scopes, and rule applications):

```text
Validity rule-conformance: 99.98% — 5 checks · 4 columns · 99,101 rule applications
```

Those coverage numbers are worked out from the checks in the report; they don't change the JSON or the formula. **Scores from very different rule sets can't be compared directly.** 100% on two loose checks is not the same as 100% on eight strict ones.

[`skills/data-quality/SKILL.md`](skills/data-quality/SKILL.md) has the default report layout and the dashboard rules. Raw JSON is for machines; only show it if someone asks.

## Comprehensive assessments

Testing the skill across several agents on the same synthetic file showed that the engine wasn't the weak point. Rule choice was. Given the same request for a "comprehensive" check, one agent covered almost every planted issue category and another missed more than half by a rough count, mostly because it never wrote rules for some columns. Running more checks didn't help on its own either.

Since 0.4.0, `SKILL.md` asks the agent, for comprehensive requests, to walk every rule family against every column before writing YAML, to look at the real values of low-cardinality columns before writing `allowed` lists, and to keep three kinds of uniqueness and two kinds of missingness apart. Anything it chose not to check goes into a **Supported but not assessed** section of the report, with a reason. A visible gap is better than a silent one.

Keep the numbers apart when reading a report. **Rule violations** are counted per check, so one bad value can fail two rules and duplicated rows repeat the same violations. **Distinct affected rows**, **duplicate extras** and **dimension rule-conformance** are each something different again. None of them can be added together or divided by a count of real defects.

## Versions and releases

Versions are git tags and GitHub releases. This isn't a Python package and it isn't on PyPI. Release zips are built with `git archive` from the tag, so they contain exactly what's tracked under `skills/data-quality/`.

Release notes are in [CHANGELOG.md](CHANGELOG.md), and the newest release is always at [github.com/aalomair/agent-data-quality-skill/releases/latest](https://github.com/aalomair/agent-data-quality-skill/releases/latest).

## Limits

- Files over **50 MiB** or **200,000 rows** are rejected with exit code 2. They're never sampled or partially read and then reported as if complete. Reading is bounded per format where possible, but there's no streaming and no hard memory guarantee.
- One sheet or one table per run. Duplicate or empty headers are rejected, not renamed. A record with more fields than the header is rejected; data is never truncated, shifted or quietly dropped.
- Text defaults to strict UTF-8 (a BOM is fine). `--encoding NAME` lets you use another encoding, still strictly, with no lossy replacement and no auto-detection.
- Some regular expressions can backtrack catastrophically in Python. If you're running untrusted rules or running unattended, set a timeout in the host. The script doesn't have its own regex timeout.

## Read-only, always

- The script never writes to the source. SQLite is opened with `mode=ro`, so any write fails with `attempt to write a readonly database`, and the tests confirm every reader leaves the source bytes unchanged. One caveat: opening a WAL-mode SQLite database read-only can create SQLite's temporary `-shm`/`-wal` files next to it. The database file itself is untouched.
- Cleaning or fixing data is out of scope on purpose. Suggested fixes in a report are explanations, nothing more.
- No network, no model calls, and nothing from the data is ever executed. There's no option to write output to a file; you redirect stdout yourself.
- `row_refs` are positions within that run (1-based; physical line numbers for text files; scan order for SQLite), not permanent row IDs.

## What it doesn't tell you

- Whether text is semantically or factually correct, whether data is fresh (without an SLA to check against), or whether it's accurate (without reference data).
- Anything about baselines, drift, distribution changes or outliers.
- XLSX formula results; formulas aren't evaluated and cached values may be missing or stale (you'll get a warning).
- An overall quality score. Exit 0 on its own doesn't prove the data is good.
- Treating hostile cell contents as plain data helps, but it can't make every host model immune to prompt injection.

## Verification

The dated runs below used Linux, Python 3.14.4, pandas 3.0.6, openpyxl 3.1.5, PyYAML 6.0.3, pytest 9.1.1 and pyarrow 25.0.1.

- **Test suite (2026-11-07):** `210 passed` on Python 3.14, and again in clean Python 3.11 and 3.10 virtual environments.
- **UCI Adult benchmark (2026-11-07):** **60/60** expected rule violations detected, 0 unexpected, source file unchanged. These are injected defects counted per rule check, and some checks overlap, so this isn't 60 independent real-world defects. See the [benchmark notice](benchmark/public/README.md).
- **CI:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs the whole suite on Python 3.10, 3.11, 3.12, 3.13 and 3.14, plus a Gitleaks scan of the full git history, on every push. A CI run only vouches for the commit it ran on.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -r skills/data-quality/scripts/requirements.txt pytest pyarrow
python -m pytest tests/ -q
```

Some Linux distros ship Python without `ensurepip`, so `python -m venv` gives you an environment with no pip. If that happens, use `uv venv` and `uv pip install` instead; the dependencies are the same.

CI uses read-only repository permissions, doesn't persist checkout credentials, and pins actions to commit SHAs. The Gitleaks binary is pinned to a version and its SHA-256 is checked before it runs. Runtime dependencies use version ranges rather than a lock file.

Keep any credentials in `.env` or `.env.*` files and generated reports in `reports/`; both are gitignored. A tracked `.env.example` should only ever hold placeholders. Note that `.gitignore` won't remove a secret that's already been committed, so look at what you're staging and run the secret scan before you push.

## Not planned

These are left out on purpose, and I'm not building hooks for them:

- **Baseline comparison:** no saved profiles to compare a new version of a dataset against.
- **Drift detection:** nothing that tracks changes between runs.
- **Statistical outlier detection (IQR and similar):** only the rules you supply are checked.
- **Live database connections beyond SQLite** (SQLAlchemy, PostgreSQL, MySQL, SQL Server): export to a file first.
- **Fixing data:** the skill reads; it never modifies.

If the project grows, it will grow as read-only profiling and rule checking.

## License

The code and docs are MIT; see [LICENSE](LICENSE). The skill folder carries its own copy of the [MIT notice](skills/data-quality/LICENSE) so it survives being copied on its own.

`benchmark/public/adult.csv` is third-party data under **CC BY 4.0**, not MIT. Attribution, license links, the changes made to it, and checksums are in the [dataset notice](benchmark/public/README.md). The benchmark rules and script are MIT.
