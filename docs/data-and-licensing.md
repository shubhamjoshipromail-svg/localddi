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

- **ONC high-priority list** (Phansalkar et al., JAMIA 2012): the class-level list behind NLM's `ONCHigh` source needs a maintained class-to-drug expansion to be usable. The companion paper is open access, but I could not confirm an explicit licence for the list as a dataset. The evaluation downloads the University of Pittsburgh group's expansion at run time; neither it nor the original list is bundled. Public availability for comparison does not establish permission to redistribute it. See [evaluation.md](evaluation.md).
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

1. Read `RXNCONSO.RRF` and `RXNREL.RRF` from the RxNorm zip (rows with `SAB=RXNORM` only). Each concept, including brands, clinical drugs and packs, is mapped to its ingredient(s) by walking RxNorm's own relationships.
2. Read the DDInter CSV files (one per ATC drug category). The same pair appears in more than one file; duplicates are collapsed.
3. Match each DDInter drug name to exactly one RxNorm ingredient using an indexed normalised name, which can also come from the small built-in alias list (`localddi/data/aliases.csv`, for example *acetylsalicylic acid* → *aspirin*). If that fails, try the name with a trailing qualifier such as "(topical)" removed. There is no fuzzy matching. The query-time rewrites described below are separate from this source-name import step.
4. Store one row per interacting ingredient pair. Pairs where either drug has no RxNorm match are left out and counted.
5. Write `import-report.json` next to the database, listing every unmatched name.

## Measured on a real import

Import run on 15 November 2026: RxNorm prescribable release dated 2 November 2026, all 14 DDInter files, localddi 0.1.1.

| | |
|---|---|
| Rows in the DDInter files | 507,655 |
| Unique drug pairs after removing duplicates | 234,981 |
| Interactions stored | 176,817 (75% of unique pairs) |
| Pairs dropped because a drug had no RxNorm match | 58,164 |
| DDInter drugs | 1,971 |
| matched to an RxNorm ingredient | 1,598 (81%) |
| matched exactly | 1,402 |
| matched after removing a qualifier such as "(topical)" | 173 |
| matched through the built-in synonym list | 23 |
| not matched | 373 (19%) |
| Stored rows by level | major 28,339 · moderate 101,194 · minor 6,832 · unknown 40,452 |
| Database size | 33 MB |

Duplicate rows for the same pair never disagreed about the level in this data; if they ever do, the importer keeps the most severe.

The 373 unmatched drugs include drugs no longer marketed in the United States, vaccines and herbal products named differently in the two vocabularies. The import report lists every unmatched name. These names are not filled in by similarity matching.

**"Unknown" level.** 23% of stored rows have DDInter's level "Unknown": the pair is listed but DDInter assigns no severity. I do not know how DDInter's curators intend that level to be read. localddi returns these rows with `severity: "unknown"` (`N/A` on the NLM-compatible endpoints) and lets you exclude them with `LOCALDDI_MIN_SEVERITY=minor`.

### The 14 files

DDInter publishes its interactions as one CSV per ATC drug category. Its download page links eight (A, B, D, H, L, P, R, V). Files for the other six categories (C cardiovascular, G genito-urinary and sex hormones, J anti-infectives, M musculoskeletal, N nervous system, S sensory organs) are served from the same directory with the same naming pattern but are not linked from the page; I found them by trying the pattern after noticing that sildenafil + nitroglycerin was absent from the linked eight. The import with all fourteen stores 176,817 interactions.

All fourteen files (A B C D G H J L M N P R S V) have the same five columns: `DDInterID_A`, `Drug_A`, `DDInterID_B`, `Drug_B`, `Level`. Per file, 81–85% of drugs match RxNorm and 66–84% of pairs are kept. These are per-file ranges; pairs repeated across files are deduplicated in the combined import.

localddi downloads all fourteen by default. In 0.1.1, import warns if any of the fourteen is missing, including when using only the linked files. Missing categories can leave out interactions. The unlinked six carry the same DDInter data under the same terms page, but DDInter has not, as far as I can see, said anything about them specifically. If that makes you uncomfortable, use `--ddinter-linked-only`.

### Name resolution at query time

The source-name import counts above are separate from the new query-time rewrites. After exact lookup fails, 0.1.1 tries `qualifier-stripped`, `normalized`, `salt-stripped`, then `combination`. Abbreviations are expanded, trailing release words can be removed, and a trailing salt is removed only if the remainder is an RxNorm ingredient. Every part of a combination must resolve. The native API returns the rule in `match`. The discontinued brand `Coumadin` resolves through an alias to warfarin. There is no fuzzy auto-matching; a misspelling stays unresolved with suggestions. These rules can discard route or formulation information and have not been clinically validated. See [evaluation.md](evaluation.md#name-resolution-rules).

### What was measured

The reproducible [evaluation](evaluation.md) compares the imported database with the expanded ONC high-priority list and archived NLM responses, and checks names from CMS Medicare Part D spending data. It lists 721 of 793 testable ONC pairs (90.9%) and 883 of 3,050 testable archived DrugBank pairs (29%). DDInter covers far fewer pairs than DrugBank did in those captures; this is a real limitation. The archive is not a designed sample. Of the top 100 CMS names by 2024 claims, 94 generic and 96 brand names resolve. These are overlap and resolution measurements, not clinical validation.

### What was not measured

- **Clinical correctness, false positives or DDInter's own accuracy.** The ONC and archived NLM comparisons measure whether reference pairs are listed, not whether every output is correct. There has been no clinical validation or comparison with Lexicomp, Micromedex or Stockley's. Eleven textbook pairs were checked by hand and were present; that is a smoke test.
- **Correctness of every name match.** The 23 source-drug synonym matches come from a hand-written list (`localddi/data/aliases.csv`) that a pharmacist has not reviewed. Neither those matches nor the query-time rewrite rules have had a clinical review.
- **Population-wide agreement with the old NLM API.** The archived responses now provide a measured comparison, but their drugs are whatever happened to be captured. They do not represent all of DrugBank or all medication lists.
- **Behaviour inside OpenEMR.** localddi has not been tested in a running OpenEMR install or against a production EHR.

## What this data cannot tell you

- **Absence is not safety.** A pair with no row may simply be missing from DDInter, or one drug may be among the unmatched names.
- **Severity only.** The DDInter download files have a level (Major / Moderate / Minor / Unknown) and nothing else: no mechanism, no management advice, no evidence grade. DDInter's website shows more than its download files contain.
- **Ingredient level.** Dose, route, timing, patient age, renal function and everything else that determines whether an interaction matters clinically are ignored. A topical and an oral form of the same ingredient are treated alike; where DDInter lists route-specific entries (for example "Dexamethasone (topical)"), they are folded into the ingredient and every matching row is returned.
- **US vocabulary.** RxNorm's prescribable subset covers drugs marketed in the United States. Drugs sold only elsewhere are not recognised.
- **No drug-food, drug-disease or allergy checks.**
- **A snapshot.** The data is as old as your last import. DDInter 2.0's site reports its last update as 14 May 2024.
- **Nobody has clinically validated localddi's matching or output.**
