"""The native /v1 API."""

from fastapi.testclient import TestClient

from localddi import DISCLAIMER
from localddi.app import create_app


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["data_loaded"] is True


def test_check_by_name(client):
    response = client.get("/v1/interactions", params={"drugs": "warfarin,aspirin"})
    assert response.status_code == 200
    body = response.json()
    assert body["disclaimer"] == DISCLAIMER
    assert body["summary"] == {
        "drugs_resolved": 2,
        "drugs_unresolved": 0,
        "pairs_checked": 1,
        "interactions_found": 1,
        "highest_severity": "major",
        "by_severity": {"major": 1},
        "complete": True,
    }
    interaction = body["interactions"][0]
    assert interaction["severity"] == "major"
    assert interaction["source"] == "DEMO"
    assert {interaction["drug_a"]["name"], interaction["drug_b"]["name"]} == {"warfarin", "aspirin"}
    assert {interaction["drug_a"]["rxcui"], interaction["drug_b"]["rxcui"]} == {"11289", "1191"}
    assert interaction["description"].startswith("[DEMO]")
    assert body["sources"][0]["license"] == "CC0-1.0"


def test_check_by_rxcui_matches_check_by_name(client):
    by_name = client.get("/v1/interactions", params={"drugs": "warfarin,aspirin"}).json()
    by_rxcui = client.get("/v1/interactions", params={"rxcuis": "11289,1191"}).json()
    assert by_name["interactions"][0]["severity"] == by_rxcui["interactions"][0]["severity"]
    assert by_rxcui["summary"]["interactions_found"] == 1


def test_order_of_inputs_does_not_change_the_finding(client):
    one = client.get("/v1/interactions", params={"drugs": "warfarin,aspirin"}).json()
    two = client.get("/v1/interactions", params={"drugs": "aspirin,warfarin"}).json()
    assert one["summary"] == two["summary"]


def test_brand_names_and_mixed_inputs(client):
    body = client.get("/v1/interactions", params={"drugs": "Zocor", "rxcuis": "207106"}).json()
    assert body["summary"]["interactions_found"] == 1
    interaction = body["interactions"][0]
    assert {interaction["drug_a"]["input"], interaction["drug_b"]["input"]} == {"Zocor", "207106"}
    assert {interaction["drug_a"]["name"], interaction["drug_b"]["name"]} == {"simvastatin", "fluconazole"}


def test_repeated_parameters(client):
    body = client.get("/v1/interactions?drugs=warfarin&drugs=ibuprofen").json()
    assert body["summary"]["highest_severity"] == "moderate"


def test_three_drugs_sorted_by_severity(client):
    body = client.get("/v1/interactions", params={"drugs": "acetaminophen,warfarin,fluconazole,ibuprofen"}).json()
    assert body["summary"]["pairs_checked"] == 6
    assert [i["severity"] for i in body["interactions"]] == ["major", "moderate", "minor"]
    assert body["summary"]["by_severity"] == {"major": 1, "moderate": 1, "minor": 1}


def test_combination_product_checks_each_ingredient(client):
    body = client.get("/v1/interactions", params={"drugs": "Percocet,sertraline,warfarin"}).json()
    pairs = {frozenset((i["drug_a"]["name"], i["drug_b"]["name"])) for i in body["interactions"]}
    assert pairs == {frozenset(("oxycodone", "sertraline")), frozenset(("acetaminophen", "warfarin"))}
    assert all("Percocet" in (i["drug_a"]["input"], i["drug_b"]["input"]) for i in body["interactions"])


def test_no_interaction_listed(client):
    body = client.get("/v1/interactions", params={"drugs": "aspirin,simvastatin"}).json()
    assert body["interactions"] == []
    assert body["summary"]["highest_severity"] is None
    assert body["summary"]["complete"] is True


def test_same_drug_twice_is_not_an_interaction(client):
    body = client.get("/v1/interactions", params={"drugs": "warfarin,warfarin sodium"}).json()
    assert body["interactions"] == []


def test_unresolved_drug_marks_answer_incomplete(client):
    body = client.get("/v1/interactions", params={"drugs": "warfarine,aspirin"}).json()
    assert body["summary"]["complete"] is False
    assert body["summary"]["drugs_unresolved"] == 1
    assert body["interactions"] == []
    unresolved = body["drugs"][0]
    assert unresolved["resolved"] is False
    assert "warfarin" in unresolved["suggestions"]


def test_min_severity_filter(client):
    params = {"drugs": "acetaminophen,warfarin,fluconazole,ibuprofen", "min_severity": "moderate"}
    body = client.get("/v1/interactions", params=params).json()
    assert [i["severity"] for i in body["interactions"]] == ["major", "moderate"]
    assert client.get("/v1/interactions", params={"drugs": "a,b", "min_severity": "bogus"}).status_code == 400


def test_source_filter(client):
    body = client.get("/v1/interactions", params={"drugs": "warfarin,aspirin", "sources": "nothere"}).json()
    assert body["interactions"] == []
    body = client.get("/v1/interactions", params={"drugs": "warfarin,aspirin", "sources": "demo"}).json()
    assert len(body["interactions"]) == 1


def test_post_body(client):
    response = client.post("/v1/interactions", json={"drugs": ["sertraline"], "rxcuis": ["10689"]})
    assert response.status_code == 200
    assert response.json()["summary"]["highest_severity"] == "major"


def test_missing_and_too_many_drugs(client):
    assert client.get("/v1/interactions").status_code == 400
    assert client.post("/v1/interactions", json={}).status_code == 400
    many = ",".join(str(n) for n in range(51))
    response = client.get("/v1/interactions", params={"rxcuis": many})
    assert response.status_code == 400
    assert "At most 50" in response.json()["error"]


def test_resolve_endpoint(client):
    body = client.get("/v1/drugs/resolve", params={"name": "Tylenol"}).json()
    assert body["resolved"] is True
    assert body["rxcui"] == "202433"
    assert body["tty"] == "BN"
    assert body["ingredients"] == [{"rxcui": "161", "name": "acetaminophen"}]


def test_drug_interactions_endpoint(client):
    body = client.get("/v1/drugs/11289/interactions").json()
    assert body["drug"]["name"] == "warfarin"
    assert body["interactions_found"] == 4
    assert {i["interacts_with"]["name"] for i in body["interactions"]} == {
        "aspirin", "fluconazole", "ibuprofen", "acetaminophen",
    }
    assert all(i["ingredient"]["rxcui"] == "11289" for i in body["interactions"])
    major = client.get("/v1/drugs/11289/interactions", params={"min_severity": "major"}).json()
    assert major["interactions_found"] == 2
    assert client.get("/v1/drugs/424242424242/interactions").status_code == 404


def test_status(client):
    body = client.get("/v1/status").json()
    assert body["interactions"] == 8
    assert body["rxnorm_version"] == "demo-fixture"
    assert body["sources"][0]["name"] == "DEMO"
    assert body["sources"][0]["interactions"] == 8
    report = body["import_report"]["sources"]["DEMO"]
    assert report["drugs_unmatched"] == 1
    assert "unmatched_drugs" not in report


def test_openapi_and_docs(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "localddi"
    for path in ("/v1/interactions", "/REST/interaction/list.json", "/REST/interaction/interaction.json"):
        assert path in schema["paths"]
    assert client.get("/docs").status_code == 200


def test_no_data_returns_503_with_instructions(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALDDI_API_KEY", raising=False)
    empty = TestClient(create_app(tmp_path / "missing.sqlite"))
    assert empty.get("/health").json()["data_loaded"] is False
    response = empty.get("/v1/interactions", params={"drugs": "warfarin,aspirin"})
    assert response.status_code == 503
    assert "localddi import" in response.json()["error"]
    assert empty.get("/REST/interaction/list.json", params={"rxcuis": "1 2"}).status_code == 503


def test_api_key(db_file, monkeypatch):
    monkeypatch.setenv("LOCALDDI_API_KEY", "s3cret")
    locked = TestClient(create_app(db_file))
    assert locked.get("/health").status_code == 200
    assert locked.get("/v1/status").status_code == 401
    assert locked.get("/REST/interaction/list.json", params={"rxcuis": "11289 1191"}).status_code == 401
    assert locked.get("/v1/status", headers={"X-API-Key": "wrong"}).status_code == 401
    assert locked.get("/v1/status", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert locked.get("/v1/status", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_no_cors_headers_by_default(client):
    response = client.get("/health", headers={"Origin": "https://example.org"})
    assert "access-control-allow-origin" not in response.headers


def test_responses_are_deterministic(client):
    url = "/v1/interactions?drugs=acetaminophen,warfarin,fluconazole,ibuprofen,Percocet,sertraline"
    assert client.get(url).content == client.get(url).content


def test_server_wide_severity_floor(db_file, monkeypatch):
    monkeypatch.delenv("LOCALDDI_API_KEY", raising=False)
    monkeypatch.setenv("LOCALDDI_MIN_SEVERITY", "minor")
    floored = TestClient(create_app(db_file))
    # oxycodone + sertraline is the fixture's only row of unknown severity
    assert floored.get("/v1/interactions", params={"drugs": "oxycodone,sertraline"}).json()["interactions"] == []
    assert set(floored.get("/REST/interaction/list.json?rxcuis=7804+36437").json()) == {"nlmDisclaimer"}
    assert floored.get("/v1/drugs/36437/interactions").json()["interactions_found"] == 1
    assert floored.get("/v1/status").json()["min_severity_floor"] == "minor"
    body = floored.get("/v1/interactions", params={"drugs": "warfarin,acetaminophen"}).json()
    assert body["interactions"][0]["severity"] == "minor"
