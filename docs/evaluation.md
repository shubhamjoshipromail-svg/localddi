# Evaluation of localddi 0.1.1

localddi lists many pairs from the ONC high-priority reference, but far fewer than DrugBank did in the archived NLM responses. It resolves most of the commonly dispensed names tested here. These are measurements of pair overlap and name resolution, not clinical correctness.

**Not for clinical use.** localddi is not a medical device and has not been clinically validated. Its data and name matching can be incomplete or wrong. **A response with no interactions does not mean a combination is safe.** Do not use it to make treatment decisions.

The code is MIT. The default DDInter 2.0 data is **CC BY-NC-SA 4.0, non-commercial use only**. It is downloaded by the operator, not bundled with this repository. Commercial use requires DDInter's permission or your own licensed data. Evaluation does not change those terms. See [data and licensing](data-and-licensing.md).

## Snapshot and method

The recorded results are in [evaluation-results.json](evaluation-results.json). They use localddi 0.1.1, RxNorm Current Prescribable Content release **2026-11-02**, and all **14 DDInter category files**. The import was on **15 November 2026 in America/Los_Angeles**; its JSON timestamp, `2026-11-16T05:56:24+00:00`, is the same date in local time.

[scripts/evaluate.py](../scripts/evaluate.py) compares the imported database with three public references. Each answers a different question:

| Reference | Question it can answer |
|---|---|
| Expanded ONC high-priority drug–drug interaction list | Which pairs in this high-priority reference are listed, and at what DDInter level? |
| Real NLM interaction responses preserved by the Internet Archive | How much of the pair content returned by the old API is present in this import? |
| CMS Medicare Part D Spending by Drug, ranked by 2024 claims | Can the resolver handle commonly dispensed generic and brand names as written in this file? |

For the pair comparisons, **testable** means the required names or RxCUIs are present in the current prescribable RxNorm subset. Untestable pairs are reported separately and excluded from the overlap percentages. They remain unavailable to this import. **Listed** means localddi returns or stores a reference pair; it does not mean the interaction has been independently confirmed.

### Import coverage

| Measure | Result |
|---|---:|
| DDInter rows read | 507,655 |
| Unique drug pairs | 234,981 |
| Interactions stored | 176,817 (75%) |
| Pairs dropped for an unmatched drug | 58,164 |
| DDInter drugs matched to an RxNorm ingredient | 1,598 of 1,971 (81%) |
| Match breakdown | 1,402 exact; 173 qualifier-stripped; 23 alias |
| Unmatched DDInter drugs | 373 |
| Stored major / moderate / minor / unknown rows | 28,339 / 101,194 / 6,832 / 40,452 |
| Database size | 33 MB |

All 14 DDInter ATC category files (**A B C D G H J L M N P R S V**) use the same five-column format: `DDInterID_A`, `Drug_A`, `DDInterID_B`, `Drug_B`, `Level`. Per file, **81–85% of drugs match RxNorm and 66–84% of pairs are kept**. These ranges describe individual files, not separate portions of the combined total; pairs repeat across files. Import now warns if any of the 14 is missing. The [licensing document](data-and-licensing.md#the-14-files) explains the six files not linked from DDInter's download page.

## ONC high-priority pairs

The reference is [Phansalkar et al., JAMIA 2012](https://pubmed.ncbi.nlm.nih.gov/22539083/), expanded to individual drugs by the University of Pittsburgh group in [public-PDDI-analysis](https://github.com/dbmi-pitt/public-PDDI-analysis/tree/master/PDDI-Datasets/ONC-High-Priority). This is the reference behind the `ONCHigh` list NLM served. The script reads the mapped file, removes duplicate unordered pairs, resolves each name, and queries the engine for each testable pair.

This reference gives a focused check against high-priority interactions. It does not cover every interaction a general-purpose database might contain.

| Measure | Result |
|---|---:|
| Distinct reference pairs | 1,150 |
| Untestable because a drug is absent from current prescribable RxNorm | 357 |
| Testable pairs | 793 |
| Listed at any DDInter level | 721 of 793 (90.9%) |
| Listed as major | 663 of 793 (83.6%) |
| Listed as moderate | 58 |
| Testable but not listed | 72 |
| Not listed, both drugs represented in the imported source | 42 |
| Not listed, a drug absent from the imported source | 30 |

The untestable drugs include astemizole, terfenadine and bepridil. Excluding them makes the denominator explicit; it does not restore their coverage.

Sulpiride appears in 30 unlisted pairs and cocaine in 29. These counts overlap: the cocaine–sulpiride pair is in both groups. The JSON contains the complete list of missing pairs. The high-priority reference and DDInter also differ in levels: 58 listed pairs are moderate rather than major. Pair presence alone does not establish agreement on alert priority.

## Archived NLM responses

The [capture manifest](../scripts/nlm_captures.tsv) identifies real NLM responses preserved by the Internet Archive. The script downloads the captures, parses their interaction pairs and deduplicates unordered pairs within each source. It checks whether each pair's RxCUIs exist in current prescribable RxNorm, then looks for that ingredient pair in the imported database.

This is a content comparison with responses the old API actually returned. It is separate from the [JSON structure compatibility tests](nlm-compatibility.md#what-was-checked-and-against-what).

| Capture measure | Result |
|---|---:|
| Captures examined | 52 |
| Captures containing interactions | 25 |

| Pair measure | DrugBank | ONCHigh |
|---|---:|---:|
| Distinct archived pairs | 7,122 | 6 |
| Untestable: RxCUI absent from current prescribable RxNorm | 4,072 | 1 |
| Testable pairs | 3,050 | 5 |
| Listed by localddi | 883 of 3,050 (29%) | 5 of 5 |
| Testable but not listed | 2,167 | 0 |
| Listed as major / moderate / minor / unknown | 33 / 218 / 36 / 596 | 5 / 0 / 0 / 0 |

**The 29% DrugBank overlap is a real limitation.** DDInter covers far fewer pairs than DrugBank did in these responses. Matching the old JSON structure does not reproduce its interaction coverage. Of the 883 overlapping DrugBank pairs, **596 have unknown severity in DDInter**. A listed pair can therefore still lack a severity level.

The captured drugs are whatever happened to be archived, not a designed or representative sample. Do not extrapolate 29% to all DrugBank pairs, all prescriptions or a particular practice. The five testable archived ONCHigh pairs are also too small a set to replace the expanded-list comparison above. This evaluation does not compare the correctness of descriptions or management advice.

## Medicare Part D drug names

The reference is CMS's [Medicare Part D Spending by Drug](https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-d-spending-by-drug), using the [2024-claims CSV selected by the script](https://data.cms.gov/sites/default/files/2026-06/98218f98-166c-4723-8438-c344a4ef96a6/DSD_PTD_RY26_P04_V10_DY24_BGM.csv). The script uses rows where `Mftr_Name` is `Overall`, aggregates `Tot_Clms_2024` by name, and ranks generic and brand columns separately. It sends each distinct name to the resolver.

This tests actual names in a public dispensing-related dataset, including abbreviations, combinations and truncated strings. It does not test patient medication lists or whether the resolved ingredients are clinically correct.

| Measure | Generic column | Brand column |
|---|---:|---:|
| Top 100 names resolved | 94 of 100 | 96 of 100 |
| Top 100 before the rewrite rules | 70 of 100 | 68 of 100 |
| Top 300 names resolved | 274 of 300 | 270 of 300 |
| Share of claims accounted for by names that resolve, across the full column | 94.9% | 95.0% |

The claims-weighted figures cover the full columns, not just the top 100. Generic and brand are separate views of the same claims; do not add them together. Name resolution measures vocabulary coverage, not interaction coverage.

Unresolved top-100 names include truncated generic strings such as `Amoxicillin/Potassium Clav`, devices such as `Pen Needle, Diabetic`, and brand-plus-device strings such as `Lantus Solostar` and `Trelegy Ellipta`. The full unresolved lists are in the JSON.

### Name resolution rules

In 0.1.1, exact lookup on a normalised key comes first. Case, accents and punctuation are normalised for that key. If it fails, the resolver tries the fixed rules in [localddi/textnorm.py](../localddi/textnorm.py), in order:

| `match` rule | What it tries |
|---|---|
| `qualifier-stripped` | Remove a trailing parenthetical qualifier, as in `Acyclovir (topical)`. |
| `normalized` | Expand HCl, HBr, HCTZ, APAP and ASA; remove trailing release/form words such as ER, XR, XL, SR, CR, DR, ODT and HFA. |
| `salt-stripped` | Remove a trailing salt word, only if the remainder matches an RxNorm ingredient. |
| `combination` | Split forms such as `A/B`, `A-B` or `A with B`; every part must resolve. |

The native API returns the rule used in `match`; ordinary lookups can also return `exact`, `alias`, `source-name` or `rxcui`. `Coumadin` resolves through an alias to warfarin. There is no similarity or fuzzy auto-matching. A misspelling stays unresolved with suggestions that are never applied automatically.

These rules reduce names to ingredients. Removing a route qualifier or release form discards information that can matter clinically. Resolving every component of a combination does not validate the combination or ensure its interactions are in DDInter. The DDInter source-name import counts above use the importer's matching rules; the CMS results measure the query-time resolver.

## Engine lookup time

The script times 500 random lists at each size, with a fixed random seed. It resolves sampled RxCUIs and runs the interaction query inside the engine. **There is no HTTP request in this measurement.**

| Drugs per list | Median | p95 |
|---|---:|---:|
| 2 | 0.08 ms | 0.10 ms |
| 10 | 0.42 ms | 0.53 ms |
| 25 | 1.45 ms | 1.75 ms |

These are timings from the recorded run, not a service latency or throughput guarantee. They exclude HTTP overhead, name-string resolution, downloads and import. The JSON does not record the machine specification, so it cannot support a hardware-normalised comparison.

## What these results do not show

- Clinical correctness, false-positive rates or DDInter's own accuracy. Reference-pair overlap is not clinical sensitivity or specificity.
- Correctness of every name match, alias or rewrite, or suitability of ingredient-only matching for a particular route, dose or patient.
- Complete replacement of DrugBank or the old NLM service. The archived comparison shows substantial missing content.
- Behaviour in a running OpenEMR install or a production EHR. localddi has not been tested inside OpenEMR.
- Patient outcomes, alert usefulness, mechanism or management accuracy, or food, disease and allergy interaction coverage.

The 158 offline tests check software behaviour. They are not clinical validation. A successful name lookup, a passing test or a fast response does not establish safety.

## Reproduce

From the repository root, with Python 3.10 or newer and localddi installed, import the data first. Read and accept the DDInter non-commercial licence at the import prompt:

```bash
pip install -e .
localddi import
python scripts/evaluate.py --json out.json
```

If an import already exists, the requested evaluation command is simply:

```bash
python scripts/evaluate.py --json out.json
```

The script uses the configured database by default. To select a database explicitly:

```bash
python scripts/evaluate.py --db /path/to/localddi.sqlite --json out.json
```

It downloads the three references at run time and caches them under `evaluation-cache` beside the database. The reference datasets and response bodies are not bundled. The offline server needs no network after import, but the evaluation needs network access when its cache is empty. Reusing a cache avoids re-downloading the references. `--cache` selects another cache directory; `--partd-csv` selects a local copy of the CMS file.

Keep the database, import report, reference cache, software version and output JSON together if you need to repeat a snapshot. Compare the database metadata and denominators before comparing percentages. A later RxNorm release, upstream download or changed capture manifest can change the results; timings also depend on the machine. The command reproduces the method, not a promise of identical future numbers.
