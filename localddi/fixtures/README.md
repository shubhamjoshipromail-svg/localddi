# Test fixture

Used by the test suite and by `localddi import --demo`. **Not clinical data.**

- `rrf/RXNCONSO.RRF`, `rrf/RXNREL.RRF`: 33 real concepts (11 ingredients and a few brands and tablets) copied unchanged from the RxNorm Current Prescribable Content release of 2 November 2026. NLM publishes that subset as public domain with no licence required.
- `demo_interactions.csv`: eleven hand-written rows in localddi's generic CSV format. The drug pairs and levels were chosen to exercise the importer (a synonym, a route qualifier, a duplicate pair, an unknown drug, a same-ingredient pair), not to state medical facts. Nothing here comes from DDInter or any other interaction database.
