# Rule semantics (v0.2.1)

Reference for how `scripts/dq.py` evaluates data and rules. Every count is deterministic and computed from preserved values; source data is permanently read-only, and cleansing, repair, and alteration are out of scope by design.

## Missing values

- **Missing** = native null (None, NaN, SQL NULL) or an empty / whitespace-only string.
- Literal strings such as `NA`, `NULL`, `na` are ordinary values — never interpreted as missing.
- `missing_percent` uses all inspected rows as the denominator, rounded to 2 decimals; it is `null` for empty datasets.

## Rule application

- `required` evaluates **all rows**; each missing value is a violation.
- `max_null_pct` evaluates **all rows** to calculate the column's missing percentage.
- Every other column rule **excludes missing values** from evaluation. Combine with `required` when missing values must also fail.
- `evaluated` = number of eligible values for the rule; for `max_null_pct`, this is the total row count. **No eligible values → status `not_evaluated`**, never `passed`.
- Output order: dataset rule first, then columns in the rules file's order; within a column: required, max_null_pct, unique, type, min, max, allowed, regex.
- Each check carries a fixed dimension: `required` and `max_null_pct` are `completeness`; `unique` and `max_duplicate_rows` are `uniqueness`; `type`, `min`, `max`, `allowed`, and `regex` are `validity`.

## Dimension rule-conformance scores

- The top-level `dimensions` object always contains `completeness`, `uniqueness`, and `validity`.
- Each dimension sums only checks whose status is not `not_evaluated`; its `evaluated` and `violations` fields are the corresponding sums.
- `score` = `(sum(evaluated) - sum(violations)) / sum(evaluated) * 100`, rounded to 2 decimals after calculation. A dimension with no evaluated checks has `score: null`.
- These percentages measure **rule-conformance**: how the supplied rule applications performed. They are not intrinsic measurements of dataset cleanliness. A dataset may contain missing values and still have 100% completeness rule-conformance when the supplied rules allow that missingness.
- When presenting a dimension in a human-facing report, include coverage context when practical: the number of checks, distinct columns or scopes, and total evaluated rule applications. Derive those counts from the emitted checks; this does not add fields to the deterministic JSON contract.
- **Dimension percentages produced from materially different rule sets are not directly comparable.** A 100% result from two lenient checks must not be ranked against a 100% result from eight stricter checks as though they represented equivalent coverage.
- There is no overall or global DQ score.

## Rule provenance and human reports

The deterministic engine evaluates the YAML rules without provenance metadata; no provenance syntax is part of the rule file. The host-agent report classifies each rule at preparation time:

- **Explicit constraint (confirmed):** directly required by the user, contract, standard, schema, policy, SLA, or authoritative source.
- **Source-informed candidate:** strongly suggested by official metadata, but not explicitly established as a requirement. A documented field or value vocabulary does not by itself make a field mandatory.
- **Inferred candidate:** suggested by the LLM from profiling, observed patterns, context, or likely semantics.

Only failures of explicit/confirmed constraints belong under **Confirmed findings**. Failures from source-informed and inferred candidates belong under **Candidate findings** and must include provenance, rationale, evidence/source, uncertainty, and the deterministic result. Official metadata alone does not promote a candidate to a confirmed business requirement. When the distinction affects interpretation, run confirmed and candidate rule sets separately; preserve each engine result exactly.

## `dataset.max_duplicate_rows`

- Duplicate rows = **extra exact rows beyond the first occurrence**: `rows − distinct row keys`.
- Row equality uses preserved values: strings exact and case-sensitive; numbers compare numerically (`1` equals `1.0`); booleans are distinct from numbers; all nulls share one canonical representation (`None`/`NaN` compare equal).
- `details.duplicate_rows` (and `profile.duplicate_rows`) = the total number of duplicate extras, including rows within the allowance.
- `violations` = duplicate extras **beyond the allowance**: `max(0, duplicates − max_duplicate_rows)`. With `max_duplicate_rows: 0`, every duplicate row counts.
- `row_refs` lists only the positions of duplicate extras **beyond the allowance**, bounded by the evidence limit; allowed duplicate extras are excluded. `row_refs_truncated` applies only to those violating duplicate positions.

## Column rules

### `required`
Boolean. `true` evaluates all rows and reports missing values as violations; `false` disables this check entirely. Violations are missing values; `evaluated` is the row count.

### `max_null_pct`
- The threshold must be a finite number from 0 through 100.
- Missing values use the definition above, including native nulls and empty or whitespace-only strings. Literal `NA`, `NULL`, and `na` remain values.
- The raw missing percentage is `missing rows / total rows * 100`; pass/fail compares this unrounded value with the threshold. The reported `actual_missing_percent` is rounded to 2 decimals like the profile's `missing_percent`.
- The check passes when the raw missing percentage is less than or equal to the threshold; otherwise it fails. `violations` counts the missing rows when the threshold is exceeded, and `row_refs` lists those missing-row positions (bounded, see Evidence).
- `details` always includes `threshold` and `actual_missing_percent`. For an empty dataset, the actual value is `null`, `evaluated` is 0, and the status is `not_evaluated` — never `passed`.

### `unique`
- Boolean. `true` evaluates nonmissing values for repeated groups; `false` disables this check entirely.
- Violations count **every nonmissing value that sits in a repeated-value group**: `[a, a, b]` → 2 violations; `[a, a, a]` → 3.
- Value equality follows the same scalar rules as duplicate-row detection.

### `type`
- The expected type must be one of `integer`, `number`, `string`, or `boolean`.
- Missing values are excluded from evaluation.
- `integer` accepts native integers (but not booleans) and strings matching an optional sign followed by digits (`"123"` is valid; `"123.5"` is not).
- `number` accepts finite native integers/floats (but not booleans) and strings matching the numeric grammar used by `min`/`max` (`"123"`, `"123.5"`, and exponent forms are valid).
- `string` accepts strings, including numeric-looking strings. `boolean` accepts native booleans only; booleans are never numbers, and strings such as `"true"` are not converted.
- Date and datetime type checking is not supported yet; those values fail the four supported type rules unless they are missing.

### `min` / `max`
- Inclusive numeric bounds: a violation when `value < min` (or `value > max`).
- The numeric view parses integers and floats, and strings matching a canonical numeric form: optional sign, digits with optional decimal part, optional exponent (`42`, `-3.5`, `.5`, `5.`, `1e3`) — after trimming surrounding whitespace. Leading zeros parse fine (`00123` → 123); values themselves are never rewritten.
- A nonmissing value that cannot be parsed as a number **fails the check** — it is never coerced to missing and dropped.
- Rule bounds must be **finite** numbers; `.nan` / `.inf` in a rules file are invalid rule values (exit 2).
- A value that parses to a non-finite float (for example `1e999`) is not valid for min/max and fails the check.
- Booleans are excluded from numeric interpretation; a boolean value in a min/max column fails the check.
- No currency symbols, locale separators, or date parsing. `min` greater than `max` is a rules error.

### `allowed`
- A non-empty list of YAML scalars (strings, numbers, booleans).
- **Exact, case-sensitive matching, no implicit conversion**: string `"1"` never matches number `1`; boolean `true` never matches number `1`; numbers compare numerically across int/float (`1` matches `1.0`).
- A boolean cell matches only a boolean allowed value; allowed numbers must be finite.
- Missing values are excluded from evaluation.

### `regex`
- A Python regular expression applied as a **full-string match** (`re.fullmatch`), case-sensitive by default. Inline Python flags such as `(?i)` are supported.
- Missing values are excluded from evaluation; nonmissing **non-string** values fail.
- Python regular expressions can catastrophically backtrack on some patterns. Untrusted or automated runs should use a host-enforced execution timeout; the helper does not provide a regex timeout.

## YAML notes

- YAML typing applies: quote values whose string form matters — `allowed: ['NA', 'no', '00123']`. Unquoted `yes`/`no`/`on`/`off` become booleans, and unquoted numeric-looking identifiers such as `00123` may be reinterpreted as numbers; quote identifiers when their string form matters.
- Duplicate keys anywhere in the file are rejected. Unknown top-level keys, unknown dataset/column rules, unknown column names, invalid rule values, and invalid regex patterns are **explicit errors** (exit 2), never skipped.

## Evidence and limits

- `row_refs`: up to **10** run-local 1-based positions within the inspected records. For TXT/Markdown sources these are the physical line numbers; JSONL skips blank lines, so its positions count records rather than physical lines; SQLite positions are scan offsets, **not row IDs**.
- `examples`: opt-in via `--examples N` (default 0; a negative value is an error, values above 5 are capped at 5). Up to 5 distinct violating values per check, each limited to 100 characters total, including any trailing `…` marker. Missing-value violations carry no examples.
- Statuses: `passed`, `failed`, `not_evaluated`. Overall status: `error` (exit 2), `failed` (exit 1), `passed` (rules executed and at least one passed, none failed), `inspected` (no rules, or no check produced a passing verdict — e.g. empty data).
- Empty datasets: percentages are `null`; no check can pass; nothing about quality is implied.

## Read-only guarantees

- Sources are opened for reading only; SQLite connections use URI `mode=ro` and write attempts raise `attempt to write a readonly database` (covered by tests).
- Opening a WAL-mode database read-only may create SQLite's transient `-shm`/`-wal` sidecar files; the database file itself is never written.
- The helper never writes files; save reports by redirecting stdout to a NEW path — never onto the source or rules file.
