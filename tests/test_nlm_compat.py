"""The /REST/interaction endpoints must have the same JSON structure as NLM's.

The expected key sets below were read from archived NLM responses (URLs in
docs/nlm-compatibility.md). Only structure is compared; the content differs
because the data source differs.
"""

# Keys at each level of the archived list.json response (7 Feb 2022).
LIST_TOP = {"nlmDisclaimer", "fullInteractionTypeGroup"}
GROUP_KEYS = {"sourceDisclaimer", "sourceName", "fullInteractionType"}
FULL_TYPE_KEYS = {"comment", "minConcept", "interactionPair"}
PAIR_KEYS = {"interactionConcept", "severity", "description"}
CONCEPT_KEYS = {"minConceptItem", "sourceConceptItem"}
MIN_CONCEPT_KEYS = {"rxcui", "name", "tty"}
SOURCE_CONCEPT_KEYS = {"id", "name", "url"}

# Keys of the archived interaction.json response (4 May 2021).
SINGLE_TOP = {"nlmDisclaimer", "userInput", "interactionTypeGroup"}
SINGLE_GROUP_KEYS = {"sourceDisclaimer", "sourceName", "interactionType"}
SINGLE_TYPE_KEYS = {"comment", "minConceptItem", "interactionPair"}


def all_strings(value):
    if isinstance(value, dict):
        return all(all_strings(item) for item in value.values())
    if isinstance(value, list):
        return all(all_strings(item) for item in value)
    return isinstance(value, str)


def check_pair(pair):
    assert set(pair) == PAIR_KEYS
    assert len(pair["interactionConcept"]) == 2
    for concept in pair["interactionConcept"]:
        assert set(concept) == CONCEPT_KEYS
        assert set(concept["minConceptItem"]) == MIN_CONCEPT_KEYS
        assert set(concept["sourceConceptItem"]) == SOURCE_CONCEPT_KEYS


def test_list_structure(client):
    # '+' in a raw query string is how NLM clients, OpenEMR included, separate RxCUIs.
    response = client.get("/REST/interaction/list.json?rxcuis=207106+152923+11289")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == LIST_TOP
    assert all_strings(body)  # NLM: "Numbers are expressed as strings."
    group = body["fullInteractionTypeGroup"][0]
    assert set(group) == GROUP_KEYS
    assert group["sourceName"] == "DEMO"
    assert len(group["fullInteractionType"]) == 2
    for item in group["fullInteractionType"]:
        assert set(item) == FULL_TYPE_KEYS
        assert len(item["minConcept"]) == 2
        for concept in item["minConcept"]:
            assert set(concept) == MIN_CONCEPT_KEYS
        for pair in item["interactionPair"]:
            check_pair(pair)


def test_list_resolves_products_to_ingredients(client):
    body = client.get("/REST/interaction/list.json?rxcuis=207106+152923").json()
    item = body["fullInteractionTypeGroup"][0]["fullInteractionType"][0]
    # minConcept echoes the inputs (branded tablets) ...
    assert {c["rxcui"] for c in item["minConcept"]} == {"207106", "152923"}
    assert {c["tty"] for c in item["minConcept"]} == {"SBD"}
    # ... and interactionConcept carries the ingredients they resolve to.
    pair = item["interactionPair"][0]
    assert {c["minConceptItem"]["name"] for c in pair["interactionConcept"]} == {"simvastatin", "fluconazole"}
    assert {c["minConceptItem"]["tty"] for c in pair["interactionConcept"]} == {"IN"}
    assert pair["severity"] == "major"
    assert item["comment"].startswith("Drug1 (rxcui = ")
    assert "is resolved to" in item["comment"]


def test_fields_openemr_reads_are_present(client):
    """OpenEMR's C_Prescription reads exactly these paths."""
    body = client.get("/REST/interaction/list.json?rxcuis=11289+1191").json()
    item = body["fullInteractionTypeGroup"][0]["fullInteractionType"][0]
    assert item["comment"]
    assert item["minConcept"][0]["name"] and item["minConcept"][1]["name"]
    assert item["interactionPair"][0]["severity"] == "major"
    assert item["interactionPair"][0]["description"].startswith("[DEMO]")


def test_list_accepts_space_and_percent_encoding(client):
    plus = client.get("/REST/interaction/list.json?rxcuis=11289+1191").json()
    encoded = client.get("/REST/interaction/list.json?rxcuis=11289%201191").json()
    assert plus == encoded


def test_parameter_names_are_case_insensitive(client):
    lower = client.get("/REST/interaction/list.json?rxcuis=11289+1191").json()
    upper = client.get("/REST/interaction/list.json?RXCUIS=11289+1191").json()
    assert lower == upper


def test_list_without_interactions_has_only_the_disclaimer(client):
    body = client.get("/REST/interaction/list.json?rxcuis=1191+36567").json()
    assert set(body) == {"nlmDisclaimer"}
    unknown = client.get("/REST/interaction/list.json?rxcuis=1191+99999999").json()
    assert set(unknown) == {"nlmDisclaimer"}


def test_generated_description_and_unknown_severity(client):
    body = client.get("/REST/interaction/list.json?rxcuis=7804+36437").json()
    pair = body["fullInteractionTypeGroup"][0]["fullInteractionType"][0]["interactionPair"][0]
    assert pair["severity"] == "N/A"  # what NLM returned when a source had no severity
    assert pair["description"] == "DEMO lists an interaction of unclassified severity between Sertraline and Oxycodone."
    body = client.get("/REST/interaction/list.json?rxcuis=11289+5640").json()
    pair = body["fullInteractionTypeGroup"][0]["fullInteractionType"][0]["interactionPair"][0]
    assert pair["description"] == "DEMO lists a moderate interaction between Warfarin and Ibuprofen."


def test_sources_parameter(client):
    assert set(client.get("/REST/interaction/list.json?rxcuis=11289+1191&sources=DrugBank").json()) == {"nlmDisclaimer"}
    assert "fullInteractionTypeGroup" in client.get("/REST/interaction/list.json?rxcuis=11289+1191&sources=DEMO").json()


def test_list_validation(client):
    assert client.get("/REST/interaction/list.json").status_code == 400
    many = "+".join(str(n) for n in range(51))
    assert client.get(f"/REST/interaction/list.json?rxcuis={many}").status_code == 400


def test_single_structure(client):
    response = client.get("/REST/interaction/interaction.json?rxcui=11289")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == SINGLE_TOP
    assert body["userInput"] == {"sources": [""], "rxcui": "11289"}
    group = body["interactionTypeGroup"][0]
    assert set(group) == SINGLE_GROUP_KEYS
    item = group["interactionType"][0]
    assert set(item) == SINGLE_TYPE_KEYS
    assert item["minConceptItem"] == {"rxcui": "11289", "name": "warfarin", "tty": "IN"}
    assert item["comment"] == "warfarin (11289) is resolved to warfarin (11289)"
    assert len(item["interactionPair"]) == 4
    for pair in item["interactionPair"]:
        check_pair(pair)
        # The queried drug is always the first concept of the pair.
        assert pair["interactionConcept"][0]["minConceptItem"]["rxcui"] == "11289"


def test_single_for_combination_brand(client):
    body = client.get("/REST/interaction/interaction.json?rxcui=42844").json()  # Percocet
    items = body["interactionTypeGroup"][0]["interactionType"]
    assert {item["comment"] for item in items} == {
        "Percocet (42844) is resolved to acetaminophen (161)",
        "Percocet (42844) is resolved to oxycodone (7804)",
    }


def test_single_without_interactions(client):
    body = client.get("/REST/interaction/interaction.json?rxcui=99999999").json()
    assert set(body) == {"nlmDisclaimer", "userInput"}
    assert client.get("/REST/interaction/interaction.json").status_code == 400


def test_sources_endpoint(client):
    body = client.get("/REST/interaction/sources.json").json()
    assert set(body) == {"nlmDisclaimer", "sourceList"}  # same keys as the archived NLM response
    assert body["sourceList"] == {"source": ["DEMO"]}


def test_disclaimer_says_it_is_not_nlm(client):
    body = client.get("/REST/interaction/list.json?rxcuis=11289+1191").json()
    assert body["nlmDisclaimer"].startswith("This response does not come from NLM.")
    group = body["fullInteractionTypeGroup"][0]
    assert "License: CC0-1.0." in group["sourceDisclaimer"]


def test_xml_and_unknown_paths_are_refused_clearly(client):
    for path in ("/REST/interaction/list.xml", "/REST/interaction/list", "/REST/interaction/version.json"):
        response = client.get(path, params={"rxcuis": "11289 1191"})
        assert response.status_code == 404
        assert "not implemented" in response.json()["error"]
