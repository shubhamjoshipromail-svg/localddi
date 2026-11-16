# Data and licensing

**The code is MIT. The data is not, and it is not in this repository.** `localddi import` downloads the data to your machine from its publishers, under their terms. You are the licensee.

## What gets downloaded

| | RxNorm Current Prescribable Content | DDInter 2.0 |
|---|---|---|
| Used for | Drug names, RxCUIs, and mapping brands and products to ingredients | Which pairs of drugs interact, and how severe |
| Publisher | U.S. National Library of Medicine | Computational Biology & Drug Design Group, Central South University |
| Fetched from | `https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_current.zip` (about 75 MB) | Fourteen CSV files under `https://ddinter2.scbdd.com/static/media/download/` (about 30 MB) |
| Licence | Public domain; NLM states "No license required" and no UMLS login is needed ([source](https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html)) | **CC BY-NC-SA 4.0** ([DDInter terms](https://ddinter2.scbdd.com/terms/)) |
| Commercial use | Allowed | **Not allowed** |
| In this repository | A few dozen rows, as a test fixture | Nothing |

Both statements were read on the publishers' own pages in November 2026. They can change; check before you rely on them.

## What DDInter's licence means for you

This is a plain reading of the licence, not legal advice.

- **NonCommercial.** DDInter's terms page says the data is for "personal, non-commercial, informational or scholarly use". Running localddi with DDInter data inside a commercial product or a paid service is outside that. Whether use in a clinic or a non-profit counts as non-commercial is a question for DDInter and your own counsel, not something this project can answer. For anything commercial, contact DDInter for permission or import data you have licensed (below).
- **Attribution.** Credit DDInter wherever you show its data. localddi puts the attribution and licence in every response (`sources[]` in the native API, `sourceDisclaimer` in the NLM-compatible one) so it travels with the data. Keep it visible to your users.
- **ShareAlike.** The SQLite database that `localddi import` builds is adapted from DDInter. If you share that file, or serve responses from it to other people, that material stays under CC BY-NC-SA 4.0.
- **One inconsistency worth knowing.** The 2022 journal article describing DDInter is itself published under CC BY-NC (no ShareAlike). The website's terms, which cover the data downloads, say CC BY-NC-SA. localddi treats the stricter one as binding.

`localddi import` will not download DDInter until you pass `--accept-ddinter-license` or answer the prompt.

Please cite DDInter if you publish work that uses it:

> Xiong G, et al. DDInter: an online drug–drug interaction database towards improving clinical decision-making and patient safety. *Nucleic Acids Research*, 2022. doi:10.1093/nar/gkab880
>
> Tian et al. DDInter 2.0: an enhanced drug interaction resource with expanded data coverage, new interaction types, and improved user interface. *Nucleic Acids Research*, published online 2024. doi:10.1093/nar/gkae726

## Is there a permissively licensed interaction dataset to bundle instead?

I looked and did not find one I could confirm, so nothing is bundled.

- **ONC high-priority list** (Phansalkar et al., JAMIA 2012): 15 drug-class pairs, which NLM's API served as `ONCHigh`. The companion paper is open access, but I could not find an explicit licence for the list as a dataset, and it is class-level, so it needs a maintained class-to-drug expansion to be usable. Not bundled.
- **DrugBank**: the open (CC0) subset contains names and identifiers, not interactions. The interaction data is under a non-commercial academic licence or a paid one.
- **CredibleMeds, Drugs.com, Lexicomp, Medi-Span, First Databank**: proprietary or registration-gated terms.
- **TWOSIDES / OFFSIDES** and similar mined datasets are statistical signals from adverse-event reports, not curated interaction statements; presenting them as "these drugs interact" would mislead.

If you know of a curated, openly licensed source, please open an issue.

## Bring your own data

If you have interaction data you are licensed to use, import it instead of (or alongside) DDInter:

```bash
localddi import --no-ddinter --csv my_interactions.csv \
  --source-name "MySource" --source-license "Proprietary, licensed to Example Clinic"
```

CSV columns: `drug_a`, `drug_b` (required); `severity` (`contraindicated`, `major`, `moderate`, `minor`; anything else becomes `unknown`), `description`, `management`, `drug_a_id`, `drug_b_id`, `rxcui_a`, `rxcui_b` (optional). Names are matched to RxNorm ingredients exactly as DDInter's are; give RxCUIs to skip name matching.

## How the import works

1. Read `RXNCONSO.RRF` and `RXNREL.RRF` from the RxNorm zip (rows with `SAB=RXNORM` only). Every concept — brand, clinical drug, pack — is mapped to its ingredient(s) by walking RxNorm's own relationships.
2. Read the DDInter CSV files (one per ATC drug category). The same pair appears in more than one file; duplicates are collapsed.
3. Match each DDInter drug name to exactly one RxNorm ingredient: exact match on the normalised name; then a small built-in list of international synonyms (`localddi/data/aliases.csv`, for example *acetylsalicylic acid* → *aspirin*); then the name with a trailing qualifier such as "(topical)" removed. There is no fuzzy matching.
4. Store one row per interacting ingredient pair. Pairs where either drug has no RxNorm match are left out and counted.
5. Write `import-report.json` next to the database, listing every unmatched name.

## Measured on a real import

Import run on 15 November 2026: RxNorm prescribable release dated 2 November 2026, all 14 DDInter files, localddi 0.1.0.

| | |
|---|---|
| RxNorm concepts loaded | 79,025 (5,886 ingredients) |
| Rows in the DDInter files | 507,655 |
| Unique drug pairs after removing duplicates | 234,981 |
| Interactions stored | 176,263 (75% of unique pairs) |
| Pairs dropped because a drug had no RxNorm match | 58,718 |
| Pairs dropped because both drugs are the same ingredient | 0 |
| DDInter drugs | 1,971 |
| matched exactly | 1,401 |
| matched after removing a qualifier such as "(topical)" | 171 |
| matched through the built-in synonym list | 24 |
| not matched | 375 (19%) |
| Stored rows by level | major 28,327 · moderate 100,708 · minor 6,776 · unknown 40,452 |
| Database size | 33 MB |

Duplicate rows for the same pair never disagreed about the level in this data; if they ever do, the importer keeps the most severe.

Who the 375 unmatched drugs are, from reading the list: mostly drugs withdrawn or no longer marketed in the United States (rofecoxib, astemizole, terfenadine, tolbutamide, digitoxin), vaccines and immune globulins that the two vocabularies name differently, herbal products (kava, ginkgo, garlic), radiopharmaceuticals and contrast agents named by salt, and insulin and interferon variants. I did not attempt to match these by hand beyond clear international-name synonyms, because a wrong match is worse than a missing one.

**"Unknown" level.** 23% of stored rows have DDInter's level "Unknown": the pair is listed but DDInter assigns no severity. I do not know how DDInter's curators intend that level to be read. localddi returns these rows with `severity: "unknown"` (`N/A` on the NLM-compatible endpoints) and lets you exclude them with `LOCALDDI_MIN_SEVERITY=minor`.

### The 14 files

DDInter publishes its interactions as one CSV per ATC drug category. Its download page links eight (A, B, D, H, L, P, R, V). Files for the other six categories (C cardiovascular, G genito-urinary and sex hormones, J anti-infectives, M musculoskeletal, N nervous system, S sensory organs) are served from the same directory with the same naming pattern but are not linked from the page; I found them by trying the pattern after noticing that sildenafil + nitroglycerin was absent from the linked eight. With only the linked files the import stores 121,242 interactions; with all fourteen, 176,263.

localddi downloads all fourteen by default and treats the unlinked six as optional (a missing one produces a warning, not a failure). They carry the same DDInter data under the same terms page, but DDInter has not, as far as I can see, said anything about them specifically. If that makes you uncomfortable, use `--ddinter-linked-only`.

### What was not measured

- **Accuracy against a clinical reference.** No comparison with Lexicomp, Micromedex, Stockley's or any other reference has been done. Eleven textbook pairs were checked by hand and were present; that is a smoke test.
- **Correctness of every name match.** Exact matches on normalised names are low-risk; the 24 synonym matches come from a hand-written list (`localddi/data/aliases.csv`) that a pharmacist has not reviewed.
- **Agreement with the old NLM API.** NLM served different sources (DrugBank and ONCHigh), so results are not expected to match and were not compared.

## What this data cannot tell you

- **Absence is not safety.** A pair with no row may simply be missing from DDInter, or one drug may be among the unmatched names.
- **Severity only.** The DDInter download files have a level (Major / Moderate / Minor / Unknown) and nothing else: no mechanism, no management advice, no evidence grade. DDInter's website shows more than its download files contain.
- **Ingredient level.** Dose, route, timing, patient age, renal function and everything else that determines whether an interaction matters clinically are ignored. A topical and an oral form of the same ingredient are treated alike; where DDInter lists route-specific entries (for example "Dexamethasone (topical)"), they are folded into the ingredient and every matching row is returned.
- **US vocabulary.** RxNorm's prescribable subset covers drugs marketed in the United States. Drugs sold only elsewhere are not recognised.
- **No drug-food, drug-disease or allergy checks.**
- **A snapshot.** The data is as old as your last import. DDInter 2.0's site reports its last update as 14 May 2024.
- **Nobody has clinically validated localddi's matching or output.**
