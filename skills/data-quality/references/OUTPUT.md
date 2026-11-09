# Output reference — the JSON report

`scripts/dq.py` prints exactly one compact JSON document on stdout (diagnostics go to stderr). This page is the field-by-field reference for that document as the engine actually emits it, so a host agent can build a report, spreadsheet, or dashboard from the saved JSON without guessing or recomputing numbers.

Save the report to a **new** file (`> report.json`); never onto the source or rules file. The schema version is `"1.0"`, including error reports.

## Top level

| Key | Type | Meaning |
|---|---|---|
| `schema_version` | string | Always `"1.0"` for this version. |
| `source` | object or `null` | The inspected file (see below). `null` in error reports. |
| `selection` | object or `null` | Which sheet/table/encoding/rules were used. `null` in error reports. |
| `profile` | object or `null` | Column profile (see below). `null` in error reports. |
| `checks` | array | One object per executed rule check; empty when no rules were supplied or on error. |
| `dimensions` | object | Always has `completeness`, `uniqueness`, `validity`. |
| `warnings` | array | Warning objects, sorted by `code` then `message`. |
| `errors` | array | Empty on success; one `{code, message}` object in an error report. |
| `overall` | object | Run status, exit code and check tallies. |

### `source`

| Field | Type | Meaning |
|---|---|---|
| `path` | string | The source path as given on the command line (pathlib normalisation applies, e.g. `./data.csv` becomes `data.csv`). |
| `format` | string | One of `csv`, `tsv`, `xlsx`, `json`, `jsonl`, `text`, `sqlite`, `parquet`. |
| `size_bytes` | integer | File size at read time, before any parsing. |

### `selection`

| Field | Type | Meaning |
|---|---|---|
| `kind` | string | `"table"` for tabular sources, `"text"` for TXT/Markdown. |
| `sheet` | string or `null` | Worksheet name for `.xlsx`; `null` otherwise. |
| `sheet_selection` | string or `null` | `"explicit"` when `--sheet` chose it, `"first"` when the first worksheet was used, `null` for non-XLSX. |
| `sheets_available` | array of strings or `null` | All worksheet names for `.xlsx`; `null` otherwise. |
| `table` | string or `null` | SQLite table name; `null` otherwise. |
| `encoding` | string or `null` | Effective text encoding (`"utf-8-sig"` by default for CSV/TSV/JSON/JSONL/text); `null` for XLSX, SQLite and Parquet. |
| `rules.path` | string or `null` | Rules path as given (pathlib normalisation applies), or `null`. |
| `rules.supplied` | boolean | Whether `--rules` was given. A false value means no check was evaluated, not that the data passed. |

### `profile`

| Field | Type | Meaning |
|---|---|---|
| `rows` | integer | Data records inspected (header excluded). |
| `columns` | integer | Number of columns. |
| `column_names` | array of strings | Column names in file order. |
| `column_profiles` | array | One object per column, in file order. |
| `duplicate_rows` | integer | Records whose full row key repeats an earlier record (count of extras, not groups). |
| `text` | object or `null` | Text/Markdown statistics for `kind: "text"`; `null` for tabular sources. |

Each entry of `column_profiles`:

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Column name. |
| `missing` | integer | Count of missing values (blank, native null, `NaN`/`NA`-style null tokens per the reader). |
| `missing_percent` | number or `null` | `missing / rows * 100`, rounded to 2 decimals; `null` when `rows` is 0. |
| `nonmissing` | integer | Count of present values. |
| `distinct_nonmissing` | integer | Distinct present values under the engine's value key. |
| `observed_types` | object | Counts keyed by observed kind; only non-zero keys appear, from `string`, `integer`, `number`, `boolean`, `datetime`, `other`. Values stay strings in text formats, so `numeric` may parse while `observed_types` reports `string`. |
| `numeric` | object or `null` | `{count, min, max, mean}` over finite parsed numbers; `mean` rounded to 6 decimals; `null` when no finite numbers were parsed. Non-finite values are excluded and warned about. |
| `string_length` | object or `null` | `{min, max}` character lengths over present string values; `null` when no strings are present. |

`profile.text` (only for `.txt`, `.md`, `.markdown`):

| Field | Type | Meaning |
|---|---|---|
| `blank_lines` | integer | Blank or whitespace-only lines. |
| `duplicate_line_rows` | integer | Non-blank lines whose text repeats an earlier line (count of extras). |
| `line_length` | object or `null` | `{min, max}` over non-blank lines; `null` when no non-blank lines. |
| `unusual_control_characters.occurrences` | integer | Control characters other than tab. |
| `unusual_control_characters.lines` | integer | Lines containing at least one such character. |

## `checks[]`

One object per executed rule. Fields present on every check:

| Field | Type | Meaning |
|---|---|---|
| `rule` | string | `required`, `max_null_pct`, `unique`, `type`, `min`, `max`, `allowed`, `regex`, `max_duplicate_rows`, `unique_together`, or `conditional_required`. |
| `dimension` | string | Fixed by rule: `completeness`, `uniqueness`, or `validity`. |
| `scope` | string | `"column"` for column rules, `"dataset"` for dataset rules. |
| `column` | string or `null` | Column name for column rules; `null` for dataset rules (and for `unique_together` / `conditional_required`, which name columns in `columns`). |
| `evaluated` | integer | Values or rows the rule actually evaluated. |
| `violations` | integer | Failing values or rows. |
| `status` | string | `"passed"`, `"failed"`, or `"not_evaluated"`. |
| `row_refs` | array of integers | Up to 10 run-local record positions (1-based) of violations; empty when none. |
| `row_refs_truncated` | boolean | `true` when more than 10 violating rows exist, so `row_refs` shows only the first 10. |

Conditionally present:

| Field | Type | Meaning |
|---|---|---|
| `columns` | array of strings | Present only on `unique_together` (the configured group, in configured order) and `conditional_required` (`[when_column, required_column]`). |
| `details` | object | Rule-specific evidence; shape per rule below. |
| `examples` | array | Only when `--examples N` was requested, `N > 0`, the check failed, and the rule is not `required` or `max_null_pct`. Up to `N` (max 5) distinct violating values, each truncated to 100 characters with `…`. Values are raw source values and are **not anonymized**. |

`evaluated` semantics per rule:

| Rule | `evaluated` counts |
|---|---|
| `required` | all rows |
| `max_null_pct` | all rows (violation when the missing share exceeds the threshold) |
| `unique` | present (non-missing) values |
| `type`, `min`, `max`, `allowed`, `regex` | present values |
| `max_duplicate_rows` | all rows |
| `unique_together` | all rows |
| `conditional_required` | rows whose trigger matched |

`status` is `not_evaluated` when `evaluated` is 0 (empty data, no eligible values, or no triggered rows). A check can fail with `evaluated > 0` and `violations > 0` only.

### `details` shapes

| Rule | `details` |
|---|---|
| `max_duplicate_rows` | `{"duplicate_rows": <total duplicate extras>, "max_allowed": <configured limit>}` |
| `unique_together` | `{"columns": [<group columns>]}` |
| `conditional_required` | `{"when": {"column": <name>, "equals": <scalar>}, "required_column": <name>, "triggered_rows": <count>}` |
| `max_null_pct` | `{"threshold": <percent>, "actual_missing_percent": <number or null>}` |
| `type` | `{"expected_type": "integer" \| "number" \| "string" \| "boolean"}` |
| `min`, `max` | `{"bound": <number>}` |
| `allowed` | `{"allowed_count": <count>}` |
| `regex` | `{"pattern": <pattern string>}` |
| `required`, `unique` | no `details` key |

## `dimensions`

Always exactly three keys, in this order: `completeness`, `uniqueness`, `validity`. Each is:

| Field | Type | Meaning |
|---|---|---|
| `score` | number or `null` | `(evaluated - violations) / evaluated * 100`, rounded to 2 decimals; `null` when `evaluated` is 0. |
| `evaluated` | integer | Sum of `evaluated` over checks in this dimension whose status is not `not_evaluated`. |
| `violations` | integer | Sum of `violations` over the same checks. |

These are **rule-conformance percentages** for the supplied rules, not dataset cleanliness, and there is **no global score**.

## `warnings[]`

Each object has `code` and `message`. Codes:

| Code | Raised when |
|---|---|
| `merged_cells` | The XLSX worksheet contains merged ranges (not expanded). |
| `formula_cells` | The XLSX worksheet contains formulas (never executed; cached values may be stale). |
| `nonfinite_values` | A column contains `NaN`/`Infinity` numbers excluded from the numeric summary. |

Warnings never change the exit code.

## `errors[]`

Empty on success. In an error report there is one object, `{code, message}`, and `source`, `selection` and `profile` are `null`, `checks` is empty, and every dimension is `{"score": null, "evaluated": 0, "violations": 0}`. Error codes:

| Code | Meaning |
|---|---|
| `usage` | Command-line arguments invalid or missing. |
| `invalid_option` | A valid option with an unusable value (e.g. negative `--examples`, unknown encoding). |
| `incompatible_option` | An option that does not apply to the source format (e.g. `--sheet` on CSV). |
| `source_not_found` | Source path does not exist. |
| `invalid_source` | Source exists but is not a regular file. |
| `unsupported_source` | Unsupported or missing file extension. |
| `unsupported_format` | Recognised format with no reader in this version. |
| `size_limit` | Source exceeds 50 MiB. |
| `row_limit` | Source exceeds 200,000 rows. |
| `decode_error` | Text or rules file cannot be decoded with the chosen encoding. |
| `malformed_source` | Structurally invalid source (bad header, wider record, broken JSON, unreadable workbook/database). |
| `not_found` | Requested worksheet does not exist. |
| `rules_not_found` | Rules path does not exist or is not a readable file. |
| `invalid_rules` | Rules file is not valid YAML, is empty, or violates the rule schema. |
| `missing_dependency` | `pandas` or `yaml` cannot be imported (or optional `openpyxl`/`pyarrow` for that format); install `scripts/requirements.txt`. |
| `internal_error` | Unexpected engine failure, or a report that could not be serialised. |

## `overall`

| Field | Type | Meaning |
|---|---|---|
| `status` | string | `"failed"` if any check failed; else `"passed"` if any check passed; else `"inspected"` (no rules, or all checks `not_evaluated`). Error reports use `"error"`. |
| `exit_code` | integer | CLI exit code: `0`, `1`, or `2` (see below). |
| `rules_applied` | boolean | Whether a rules file was used. |
| `checks_passed` | integer | Count of checks with `status == "passed"`. |
| `checks_failed` | integer | Count of checks with `status == "failed"`. |
| `checks_not_evaluated` | integer | Count of checks with `status == "not_evaluated"`. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Inspected, or no rule failed. A no-rules run reports `inspected`, never `passed`. |
| 1 | At least one rule violation. |
| 2 | Input, configuration, dependency, or execution error; the JSON document carries the reason. Errors take precedence. |

## Optional sections (v0.5.0)

These appear **only** when the matching flag is passed. Without the flags, the report is byte-identical to v0.4.1.

### `options`

Present when `--discover`, `--strict-privacy` or `--mask-examples` is used: `{"discover": bool, "strict_privacy": bool, "mask_examples": bool}`.

### `--strict-privacy` effects

- Every `profile.column_profiles[].numeric` keeps `count` but sets `min`, `max` and `mean` to `null`.
- `--examples` without `--mask-examples` is refused with `invalid_option` (exit 2).
- In `discovery`, category labels are replaced by shapes, and candidates whose rule would contain a data value (`allowed`, `conditional_required`) are `withheld`: `value` is `null`.

### `--mask-examples`

Each check's `examples` list holds masked shapes instead of raw values, deduplicated after masking. Masking: ASCII upper-case letters → `A`, lower-case → `a`, digits → `9`, other letters → `L`, whitespace → space; punctuation and symbols are kept.

### `discovery`

Present with `--discover`. Discovery proposes rules; it never applies them, so `checks` stays empty unless `--rules` is also given.

- `settings`: every threshold used, as fixed numbers.
- `strict_privacy`: whether labels were withheld.
- `search`: how many column pairs and state columns were eligible and how many were examined. Both searches stop at a fixed cell budget, in a fixed order.
- `columns[]`: per column, `name`, `nonmissing`, `parse` (`integer`, `number`, `not_numeric` counts), `values` (low-cardinality text columns only: `value` or, under strict privacy, `shape`, plus `count` and `kept`; otherwise `null`), `shapes` (masked shapes seen at least 3 times, top 20, each with `count`), and `shapes_not_listed` (`shapes`, `values`).
- `candidates[]`: `id` (`c1`…), `rule`, `scope`, `column` (column rules) or `columns` (dataset rules), `value` (the YAML value for that rule, or `null` when withheld), `withheld`, `provenance` (always `inferred`), `detector`, `evidence` (detector-specific counts), and `expected` (`evaluated`, `violations`: what that one rule would report if run now).
- `rules`: a rules document built from every non-withheld candidate, in the normal YAML structure. Save it, edit it, then run it with `--rules`.

Detectors: `whole_row_duplicates` → `max_duplicate_rows: 0`; `near_unique_pair` → `unique_together`; `state_dependent_field` → `conditional_required`; `mostly_filled` → `required`; `near_unique` → `unique`; `parse_rate` → `type`; `low_cardinality` → `allowed` (values below the rare floor are left out, so they would be flagged); `dominant_shape` → `regex`. `min` and `max` are never proposed.

## Field index (machine-checked)

The lists below are parsed by the test suite, so they cannot drift from the engine.

```text
top_level: schema_version, source, selection, profile, checks, dimensions, warnings, errors, overall
source: path, format, size_bytes
selection: kind, sheet, sheet_selection, sheets_available, table, encoding, rules
selection_rules: path, supplied
column_profile: name, missing, missing_percent, nonmissing, distinct_nonmissing, observed_types, numeric, string_length
numeric: count, min, max, mean
string_length: min, max
text_profile: blank_lines, duplicate_line_rows, line_length, unusual_control_characters
text_control: occurrences, lines
check: rule, dimension, scope, column, columns, evaluated, violations, status, row_refs, row_refs_truncated, details, examples
dimension: score, evaluated, violations
warning: code, message
error: code, message
overall: status, exit_code, rules_applied, checks_passed, checks_failed, checks_not_evaluated
check_status: passed, failed, not_evaluated
overall_status: inspected, passed, failed, error
error_codes: usage, invalid_option, incompatible_option, source_not_found, invalid_source, unsupported_source, unsupported_format, size_limit, row_limit, decode_error, malformed_source, not_found, rules_not_found, invalid_rules, missing_dependency, internal_error
exit_codes: 0, 1, 2
optional_top_level: options, discovery
options: discover, strict_privacy, mask_examples
discovery: settings, strict_privacy, search, columns, candidates, rules
discovery_search: pairs_eligible, pairs_evaluated, state_columns_eligible, state_columns_evaluated
discovery_column: name, nonmissing, parse, values, shapes, shapes_not_listed
candidate: id, rule, scope, column, columns, value, withheld, provenance, detector, evidence, expected
```
