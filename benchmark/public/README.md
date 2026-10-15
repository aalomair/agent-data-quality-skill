# Public benchmark data: Adult

## Attribution and license

`adult.csv` is derived from **Adult**, by **Barry Becker** and **Ronny Kohavi** (1996), distributed by the UCI Machine Learning Repository.

- Dataset page: https://archive.ics.uci.edu/dataset/2/adult
- Persistent source/DOI: https://doi.org/10.24432/C5XW20
- Official download: https://archive.ics.uci.edu/static/public/2/adult.zip
- Dataset license: **Creative Commons Attribution 4.0 International (CC BY 4.0)** — https://creativecommons.org/licenses/by/4.0/
- Full license terms: https://creativecommons.org/licenses/by/4.0/legalcode

The dataset retains CC BY 4.0; it is **not** relicensed under this repository's MIT code license. Retain this attribution, license link, and a description of any further changes when redistributing it. No endorsement by the dataset creators or UCI is implied.

## Changes from the official source

The fixture derives from the archive's `adult.data` training split:

- A header row was added (14 feature columns and the `class` target).
- Surrounding whitespace was trimmed from every field, and records were serialized as CSV.
- All 32,561 data records and their order are retained. Literal `?` markers are preserved, not converted to nulls.

On 2026-10-15, every committed data record was compared with the official `adult.data` after those transformations and matched exactly.

SHA-256 of the official downloaded ZIP:

```text
7537312dd56c2b98035880805ce99e68183a30ee468aa5329d6df0fbb3cc21bb
```

SHA-256 of this repository's `adult.csv`:

```text
6d8898ef78f064108f1a565b6e09580bb7274d4b94d819e8e19c3ea3ad291209
```

## Benchmark interpretation

The harness injects defects only into a temporary copy and verifies that source bytes are unchanged. Its 60 expected detections count rule-violation applications, including overlapping checks of the same injected defect; they are not 60 independent natural defects or a general accuracy estimate. `rules.yml` and the benchmark program are project code under MIT; the third-party license above applies to `adult.csv`.
