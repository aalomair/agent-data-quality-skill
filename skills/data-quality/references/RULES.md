# Rule semantics (v0.1.0)

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

## Dimension scores

- The top-level `dimensions` object always contains `completeness`, `uniqueness`, and `validity`.
- Each dimension sums only checks whose status is not `not_evaluated`; its `evaluated` and `violations` fields are the corresponding sums.
- `score` = `(sum(evaluated) - sum(violations)) / sum(evaluated) * 100`, rounded to 2 decimals after calculation. A dimension with no evaluated checks has `score: null`.
- Dimension scores measure rule applications, not unique bad rows or cells; one value may contribute to multiple checks when multiple rules apply.
- There is no overall or global DQ score.

## `dataset.max_duplicate_rows`

- Duplicate rows = **extra exact rows beyond the first occurrence**: `rows − distinct row keys`.
- Row equality uses preserved values: strings exact and case-sensitive; numbers compare numerically (`1` equals `1.0`); booleans are distinct from numbers; all nulls share one canonical representation (`None`/`NaN` compare equal).
- `violations` = duplicate rows **beyond the allowance**: `max(0, duplicates − max_duplicate_rows)`. With `max_duplicate_rows: 0`, every duplicate row counts.
- `row_refs` lists the positions of the extra duplicate rows (bounded, see Evidence).

## Column rules

### `required`
Boolean. Violations are missing values; `evaluated` is the row count.

### `max_null_pct`
- The threshold must be a finite number from 0 through 100.
- Missing values use the definition above, including native nulls and empty or whitespace-only strings. Literal `NA`, `NULL`, and `na` remain values.
- The raw missing percentage is `missing rows / total rows * 100`; pass/fail compares this unrounded value with the threshold. The reported `actual_missing_percent` is rounded to 2 decimals like the profile's `missing_percent`.
- The check passes when the raw missing percentage is less than or equal to the threshold; otherwise it fails. `violations` counts the missing rows when the threshold is exceeded, and `row_refs` lists those missing-row positions (bounded, see Evidence).
- `details` always includes `threshold` and `actual_missing_percent`. For an empty dataset, the actual value is `null`, `evaluated` is 0, and the status is `not_evaluated` — never `passed`.

### `unique`
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
- A Python regular expression applied as a **full-string match** (`re.fullmatch`), case-sensitive, no flags.
- Missing values are excluded from evaluation; nonmissing **non-string** values fail.

## YAML notes

- YAML typing applies: quote values whose string form matters — `allowed: ['NA', 'no', '00123']`. Unquoted `yes`/`no`/`on`/`off` become booleans; unquoted `00123` becomes the integer `123`.
- Duplicate keys anywhere in the file are rejected. Unknown top-level keys, unknown dataset/column rules, unknown column names, invalid rule values, and invalid regex patterns are **explicit errors** (exit 2), never skipped.

## Evidence and limits

- `row_refs`: up to **10** run-local 1-based positions within the inspected records. For TXT/Markdown sources these are the physical line numbers; JSONL skips blank lines, so its positions count records rather than physical lines; SQLite positions are scan offsets, **not row IDs**.
- `examples`: opt-in via `--examples N` (default 0; a negative value is an error, values above 5 are capped at 5). Up to 5 distinct violating values per check, each truncated to 100 characters with an `…` marker. Missing-value violations carry no examples.
- Statuses: `passed`, `failed`, `not_evaluated`. Overall status: `error` (exit 2), `failed` (exit 1), `passed` (rules executed and at least one passed, none failed), `inspected` (no rules, or no check produced a passing verdict — e.g. empty data).
- Empty datasets: percentages are `null`; no check can pass; nothing about quality is implied.

## Read-only guarantees

- Sources are opened for reading only; SQLite connections use URI `mode=ro` and write attempts raise `attempt to write a readonly database` (covered by tests).
- Opening a WAL-mode database read-only may create SQLite's transient `-shm`/`-wal` sidecar files; the database file itself is never written.
- The helper never writes files; save reports by redirecting stdout to a NEW path — never onto the source or rules file.
