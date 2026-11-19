"""Tests for api."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "corpus" / "out"
TOKEN = "0" * 64


@pytest.fixture(scope="module", autouse=True)
def corpus() -> None:
    if not (CORPUS / "rechnung_din5008.pdf").exists():
        subprocess.run(
            [sys.executable, str(ROOT / "corpus" / "generate.py")],
            check=True, capture_output=True,
        )


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory):
    data = tmp_path_factory.mktemp("appdata")
    previous_environment = dict(os.environ)
    os.environ.update(
        {
            "SUBSTRAKT_TOKEN": TOKEN,
            "SUBSTRAKT_MODE": "airgap",
            "SUBSTRAKT_DATA_DIR": str(data),
            "SUBSTRAKT_ROOTS": str(CORPUS),
        }
    )
    os.environ.pop("SUBSTRAKT_DEV", None)

    import substrakt.app as app_module

    importlib.reload(app_module)

    # `test_non_local_request_is_rejected` creates its own client.
    with TestClient(app_module.app, client=("127.0.0.1", 51234)) as c:
        yield c

    os.environ.clear()
    os.environ.update(previous_environment)
    importlib.reload(app_module)


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


# --- Security -----------------------------------------------------------


def test_health_does_not_require_token(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mode"] == "airgap"


def test_access_without_token_is_denied(client: TestClient) -> None:
    response = client.post("/documents", json={"path": str(CORPUS / "rechnung_din5008.pdf")})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("not-authorized")


def test_access_with_wrong_token_is_denied(client: TestClient) -> None:
    response = client.post(
        "/documents",
        json={"path": str(CORPUS / "rechnung_din5008.pdf")},
        headers={"Authorization": "Bearer " + "f" * 64},
    )
    assert response.status_code == 401


def test_non_local_request_is_rejected(tmp_path: Path) -> None:
    import substrakt.app as app_module

    with TestClient(app_module.app, client=("10.0.0.5", 40000)) as unknown:
        response = unknown.get("/health")

    assert response.status_code == 403
    assert response.json()["type"].endswith("not-local")


def test_path_outside_read_roots_is_rejected(client: TestClient) -> None:
    response = client.post("/documents", json={"path": "/etc/passwd"}, headers=auth())
    assert response.status_code == 403
    assert response.json()["type"].endswith("path-not-allowed")
    
    assert "/etc/passwd" not in response.text


# --- Documents -------------------------------------------------------------


@pytest.fixture
def doc_id(client: TestClient) -> str:
    response = client.post(
        "/documents",
        json={"path": str(CORPUS / "rechnung_din5008.pdf")},
        headers=auth(),
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_loading_document_omits_word_index(client: TestClient, doc_id: str) -> None:
    response = client.get(f"/documents/{doc_id}", headers=auth())
    data = response.json()

    assert response.status_code == 200
    assert "words" not in data
    assert data["kind"] == "pdf"
    assert data["meta"]["word_count"] > 0
    assert len(data["pages"]) == 1


def test_page_words(client: TestClient, doc_id: str) -> None:
    response = client.get(f"/documents/{doc_id}/pages/0/words", headers=auth())
    assert response.status_code == 200

    words = response.json()["words"]
    assert len(words) > 40

    first = words[0]
    assert first["locator"]["kind"] == "pdf_rect"
    assert first["locator"]["x0"] >= 0
    assert first["confidence"] is None, "The text layer is exact, not an estimate"


def test_page_out_of_range(client: TestClient, doc_id: str) -> None:
    response = client.get(f"/documents/{doc_id}/pages/99/words", headers=auth())
    assert response.status_code == 404
    assert response.json()["type"].endswith("page-not-found")


def test_plain_text(client: TestClient, doc_id: str) -> None:
    response = client.get(f"/documents/{doc_id}/text", headers=auth())
    data = response.json()

    assert response.status_code == 200
    assert data["text_source"] == "text_layer"
    assert "2026-0147" in data["chunks"][0]["text"]


def test_render_page_returns_png(client: TestClient, doc_id: str) -> None:
    response = client.get(f"/documents/{doc_id}/pages/0/render?scale=1", headers=auth())
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_document_bytes(client: TestClient, doc_id: str) -> None:
    response = client.get(f"/documents/{doc_id}/file", headers=auth())
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")

    missing = client.get("/documents/gibtsnicht/file", headers=auth())
    assert missing.status_code == 404


def test_unknown_document(client: TestClient) -> None:
    response = client.get("/documents/abc123/text", headers=auth())
    assert response.status_code == 404
    assert response.json()["type"].endswith("unknown-document")


# --- Spreadsheets --------------------------------------------------------------


def test_sheets_and_raster(client: TestClient) -> None:
    loaded = client.post(
        "/documents", json={"path": str(CORPUS / "positionen.xlsx")}, headers=auth()
    )
    assert loaded.status_code == 200
    doc_id = loaded.json()["id"]

    sheets = client.get(f"/documents/{doc_id}/sheets", headers=auth()).json()
    assert len(sheets) == 3
    assert sheets[0]["name"] == "Positionen"
    assert sheets[0]["columns"] <= 10, "Padded columns were not removed"

    raster = client.get(f"/documents/{doc_id}/sheets/0/raster", headers=auth()).json()
    assert raster["name"] == "Positionen"
    assert any("Bezeichnung" in cell for row in raster["rows"] for cell in row)





def test_corrupt_pdf_returns_problem_json(client: TestClient) -> None:
    response = client.post(
        "/documents", json={"path": str(CORPUS / "defekt.pdf")}, headers=auth()
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")

    data = response.json()
    assert data["type"].endswith("document-corrupt")
    assert data["title"]
    
    assert "Traceback" not in response.text
    assert "File \"" not in response.text


def test_empty_file(client: TestClient) -> None:
    response = client.post(
        "/documents", json={"path": str(CORPUS / "leer.csv")}, headers=auth()
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("document-empty")


def test_missing_file(client: TestClient) -> None:
    response = client.post(
        "/documents", json={"path": str(CORPUS / "does-not-exist.pdf")}, headers=auth()
    )
    assert response.status_code in (403, 404)


# --- OpenAPI ---------------------------------------------------------------


def test_sample_fields_come_from_document_kind(client: TestClient) -> None:
    response = client.get("/sample-fields", headers=auth())
    assert response.status_code == 200
    fields = {f["name"]: f for f in response.json()}
    assert fields["document_number"]["label_rule"]["value"] == "identifier"
    assert "Rechnungsnummer" in fields["document_number"]["label_rule"]["patterns"]


def test_invalid_custom_document_kind_returns_problem_json(client: TestClient) -> None:
    import substrakt.app as app_module

    custom = app_module.CONFIG.data_dir / "document_kinds"
    custom.mkdir(parents=True, exist_ok=True)
    file = custom / "invoice.yml"
    file.write_text(
        "name: invoice\ntitle: R\nfields:\n  - name: a\n    json_type: unsupported\n",
        encoding="utf-8",
    )
    try:
        response = client.get("/sample-fields", headers=auth())
    finally:
        file.unlink()
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    data = response.json()
    assert data["type"].endswith("document-kind-invalid")
    assert data["key"] == "document-kind-invalid"
    assert data["file"] == "invoice.yml"
    assert data["error"][0]["location"] == "fields.0.json_type"
    assert "Traceback" not in response.text


def test_openapi_covers_contract(client: TestClient) -> None:
    """Make every endpoint required by the desktop contract visible."""
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"])

    expected = {
        "/health",
        "/documents",
        "/documents/{doc_id}",
        "/documents/{doc_id}/pages/{page}/words",
        "/documents/{doc_id}/pages/{page}/render",
        "/documents/{doc_id}/text",
        "/documents/{doc_id}/file",
        "/documents/{doc_id}/sheets",
        "/documents/{doc_id}/sheets/{index}/raster",
        "/documents/{doc_id}/extract",
        "/documents/{doc_id}/export",
        "/sample-fields",
        "/document-types",
        "/document-types/{type_id}",
        "/inbox/entries",
        "/inbox/settings",
        "/inbox/entries/{entry_id}",
        "/inbox/entries/{entry_id}/duplicate-decision",
        "/inbox/entries/{entry_id}/correction",
        "/inbox/entries/{entry_id}/approval",
        "/pipeline-profiles/{name}/kinds",
        "/jobs",
        "/jobs/{job_id}/release",
        "/shutdown",
    }
    assert expected <= paths, f"Missing endpoints: {expected - paths}"


# --- Recognised kind ----------------------------------------------------


def test_extract_without_fields_uses_the_recognised_kind(client: TestClient) -> None:
    doc_id = client.post(
        "/documents", json={"path": str(CORPUS / "insurance" / "policy_a_1.pdf")}, headers=auth()
    ).json()["id"]
    run = client.post(f"/documents/{doc_id}/extract", json={}, headers=auth()).json()
    assert run["kind"] == "policy"
    values = {r["field"]: r for r in run["results"]}
    assert values["policy_number"]["grounded"] and values["policy_number"]["locator"]["kind"] == "pdf_rect"


def test_extract_reports_no_kind_for_a_document_that_fits_two(client: TestClient) -> None:
    doc_id = client.post(
        "/documents", json={"path": str(CORPUS / "insurance" / "both_policy_and_invoice.pdf")}, headers=auth()
    ).json()["id"]
    run = client.post(f"/documents/{doc_id}/extract", json={}, headers=auth()).json()
    assert run == {"results": [], "duration_ms": run["duration_ms"], "ungrounded": 0, "kind": None}


# --- Saved result -------------------------------------------------------

# Matches across a line break, so the value is read but gets no location.
UNLOCATED = {
    "name": "number_line",
    "json_type": "string",
    "regex": r"Rechnungsnummer[\s\S]{0,80}?\n\S+",
}


def test_export_contains_a_value_confirmed_without_a_location(client: TestClient) -> None:
    doc_id = client.post(
        "/documents", json={"path": str(CORPUS / "rechnung_din5008.pdf")}, headers=auth()
    ).json()["id"]
    url = f"/documents/{doc_id}/export"

    unconfirmed = client.post(url, json={"fields": [UNLOCATED]}, headers=auth()).json()
    assert unconfirmed["provenance"]["number_line"]["value"]
    assert "number_line" not in unconfirmed["data"]

    confirmed = client.post(
        url, json={"fields": [UNLOCATED], "confirmed": ["number_line"]}, headers=auth()
    ).json()
    provenance = confirmed["provenance"]["number_line"]
    assert "2026-0147" in confirmed["data"]["number_line"]
    assert provenance["confirmed"] is True
    assert provenance["grounded"] is False


def test_confirming_a_value_that_was_not_read_adds_nothing(client: TestClient) -> None:
    doc_id = client.post(
        "/documents", json={"path": str(CORPUS / "rechnung_din5008.pdf")}, headers=auth()
    ).json()["id"]
    absent = {"name": "absent", "json_type": "string", "regex": "no such text anywhere"}

    result = client.post(
        f"/documents/{doc_id}/export",
        json={"fields": [absent], "confirmed": ["absent"]},
        headers=auth(),
    ).json()
    assert "absent" not in result["data"]


# --- Event loop ---------------------------------------------------------


def test_status_answers_while_a_concurrent_document_is_being_read(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from substrakt.parsers import pdf

    started, release = threading.Event(), threading.Event()
    real_parse = pdf.parse

    def slow_parse(*arguments):
        started.set()
        release.wait(30)
        return real_parse(*arguments)

    monkeypatch.setattr(pdf, "parse", slow_parse)
    # A fresh copy, because an already loaded file is answered without parsing.
    copy = CORPUS / "concurrent_copy.pdf"
    copy.write_bytes((CORPUS / "rechnung_din5008.pdf").read_bytes() + b"\n%copy\n")
    answers: dict[str, int] = {}

    def load() -> None:
        response = client.post("/documents", json={"path": str(copy)}, headers=auth())
        answers["load"] = response.status_code

    def status() -> None:
        answers["health"] = client.get("/health").status_code

    loading = threading.Thread(target=load)
    asking = threading.Thread(target=status)
    try:
        loading.start()
        assert started.wait(10)
        asking.start()
        asking.join(5)
        answered_while_reading = "health" in answers and "load" not in answers
    finally:
        release.set()
        loading.join(30)
        asking.join(30)
        copy.unlink()

    assert answered_while_reading
    assert answers == {"health": 200, "load": 200}


# --- Inbox ----------------------------------------------------------------


def test_profile_kinds_name_each_kind_with_its_values_and_which_one_an_approval_requires(
    client: TestClient,
) -> None:
    profiles = Path(os.environ["SUBSTRAKT_DATA_DIR"]) / "pipeline_profiles"
    profiles.mkdir(exist_ok=True)
    (profiles / "kinds_listed.yml").write_text(
        "name: kinds_listed\ntitle: Listed\ntarget: test_target\ncustomer_folder_level: 1\n"
        "kinds:\n  invoice:\n    values:\n      document_number: Nummer\n"
        "    optional:\n      total_amount: Betrag\n",
        encoding="utf-8",
    )

    [kind] = client.get("/pipeline-profiles/kinds_listed/kinds", headers=auth()).json()
    unknown = client.get("/pipeline-profiles/absent/kinds", headers=auth())

    assert kind["name"] == "invoice" and kind["title"]
    assert [(value["name"], value["required"]) for value in kind["values"]] == [
        ("document_number", True), ("total_amount", False),
    ]
    assert all(value["label"] for value in kind["values"])
    assert unknown.json()["key"] == "pipeline-profile-unknown"


def test_profile_kinds_carry_the_type_of_each_value_from_the_kind_file(
    client: TestClient,
) -> None:
    """Review masks a date by its type, never by a value or kind name (v002 Z5.1)."""
    from substrakt import document_kinds

    profiles = Path(os.environ["SUBSTRAKT_DATA_DIR"]) / "pipeline_profiles"
    profiles.mkdir(exist_ok=True)
    (profiles / "kinds_typed.yml").write_text(
        "name: kinds_typed\ntitle: Typed\ntarget: test_target\ncustomer_folder_level: 1\n"
        "kinds:\n  invoice:\n    values:\n      document_date: Datum\n"
        "    optional:\n      total_amount: Betrag\n      document_number: Nummer\n",
        encoding="utf-8",
    )

    [kind] = client.get("/pipeline-profiles/kinds_typed/kinds", headers=auth()).json()

    fields = {f.name: f.json_type for f in document_kinds.load("invoice").fields}
    assert {v["name"]: v["json_type"] for v in kind["values"]} == {
        name: fields[name] for name in ("document_date", "total_amount", "document_number")
    }
    assert {v["json_type"] for v in kind["values"]} == {"date", "number", "string"}


def test_inbox_endpoints_choose_profile_and_folder_and_list_what_arrived(
    client: TestClient,
) -> None:
    import substrakt.app as app_module

    profiles = Path(os.environ["SUBSTRAKT_DATA_DIR"]) / "pipeline_profiles"
    profiles.mkdir(exist_ok=True)
    (profiles / "scans.yml").write_text(
        "name: scans\ntitle: Scans\ntarget: test_target\ncustomer_folder_level: 1\n"
        "kinds:\n  invoice:\n    values:\n      document_number: Nummer\n",
        encoding="utf-8",
    )
    folder = CORPUS / "inbox_endpoint"
    (folder / "Meier").mkdir(parents=True, exist_ok=True)
    scan = folder / "Meier" / "scan.pdf"
    scan.write_bytes((CORPUS / "rechnung_din5008.pdf").read_bytes() + b"\n%inbox\n")
    try:
        outside = client.post("/inbox/settings", json={"folder": "/etc"}, headers=auth())
        assert outside.status_code == 403
        assert outside.json()["key"] == "path-not-allowed"
        unknown = client.post("/inbox/settings", json={"profile": "absent"}, headers=auth())
        assert unknown.json()["key"] == "pipeline-profile-unknown"
        assert client.get("/inbox/settings").status_code == 401

        chosen = client.post(
            "/inbox/settings", json={"profile": "scans", "folder": str(folder)}, headers=auth()
        ).json()
        assert (chosen["folder"], chosen["profile"], chosen["watching"]) == (
            str(folder), "scans", True,
        )
        assert {"name": "scans", "title": "Scans"} in chosen["profiles"]
        assert client.get("/inbox/settings", headers=auth()).json() == chosen

        app_module._inbox().poll()
        app_module._inbox().poll()
        [entry] = client.get("/inbox/entries", headers=auth()).json()
        imports = client.get("/inbox/imports", headers=auth()).json()
        described = client.get("/pipeline-profiles/scans", headers=auth()).json()
        absent = client.get("/pipeline-profiles/absent", headers=auth())
        answers = _review_and_approve(client, entry["id"], folder)
    finally:
        shutil.rmtree(folder)

    assert (entry["state"], entry["customer"], entry["profile"]) == ("waiting", "Meier", "scans")
    assert imports[-1]["id"] == entry["import_id"]
    assert (imports[-1]["folder"], imports[-1]["finished_at"] is not None) == (str(folder), True)
    assert (described["title"], described["customer_folder_level"]) == ("Scans", 1)
    [kind] = described["kinds"]
    assert (kind["name"], kind["title"]) == ("invoice", "Rechnung")
    assert kind["values"] == [
        {"name": "document_number", "label": "Belegnummer", "target_name": "Nummer",
         "required": True},
    ]
    assert absent.json()["key"] == "pipeline-profile-unknown"
    assert answers == {
        "hand-over folder": str(folder / "Ausgabe"),
        "correction refused": "correction-refused",
        "corrected": "2026-0148",
        "approval of nothing": "inbox-entry-unknown",
        "job": "failed",
        "reason": "target-without-writer",
        "listed": True,
        "release of nothing": "job-unknown",
        "released": "failed",
        "retention": 30,
        "decision without a mark": "correction-refused",
        "retention of nothing": 422,
        "deleted": {"deleted": True},
        "deleted twice": "inbox-entry-unknown",
        "entries": [],
        "jobs": [],
        "without token": 401,
        "files": [],
    }


def _review_and_approve(client: TestClient, entry_id: int, folder: Path) -> dict[str, object]:
    """Correct, approve and release through the endpoints; the target has no writer."""

    def post(path: str, body: dict | None = None) -> dict:
        return client.post(path, json=body, headers=auth()).json()

    entry = f"/inbox/entries/{entry_id}"
    refused = post(f"{entry}/correction", {"values": {"no_such_value": "1"}})
    corrected = post(f"{entry}/correction", {"values": {"document_number": "2026-0148"}})
    job = post(f"{entry}/approval")
    return {
        "hand-over folder": client.get("/inbox/settings", headers=auth()).json()[
            "handover_folder"
        ],
        "correction refused": refused["key"],
        "corrected": next(
            value["value"] for value in corrected["values"] if value["field"] == "document_number"
        ),
        "approval of nothing": post("/inbox/entries/999/approval")["key"],
        "job": job["state"],
        "reason": job["transitions"][-1]["reason"],
        "listed": client.get("/jobs", headers=auth()).json() == [job],
        "release of nothing": post("/jobs/absent/release")["key"],
        "released": post(f"/jobs/{job['id']}/release")["state"],
        "without token": client.post(f"{entry}/approval").status_code,
        "files": sorted(file.name for file in (folder / "Ausgabe").glob("*.json")),
        "retention": post("/inbox/settings", {"retention_days": 30})["retention_days"],
        "retention of nothing": client.post(
            "/inbox/settings", json={"retention_days": 0}, headers=auth()
        ).status_code,
        "decision without a mark": post(f"{entry}/duplicate-decision", {"same": True})["key"],
        "deleted": client.delete(entry, headers=auth()).json(),
        "deleted twice": client.delete(entry, headers=auth()).json()["key"],
        "entries": client.get("/inbox/entries", headers=auth()).json(),
        "jobs": client.get("/jobs", headers=auth()).json(),
    }
    assert (entry["file_name"], entry["kind"]) == ("scan.pdf", "invoice")
    assert any(value["locator"] for value in entry["values"])
