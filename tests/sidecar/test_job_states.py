"""Job states around a hand-over: the dry run before it, the person's report after it.

The clerk sees what a run would write before anything is written, starts the
run, imports the file by hand and reports the result. Every state change goes
through ``Jobs.move``; nothing is written or handed over again by itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import Desk
from test_api import auth, client  # noqa: F401  (the fixture of the API tests)
from test_hand_over import Office

from substrakt import gdv, hand_over
from substrakt.errors import ImportReasonMissing


@pytest.fixture
def office(desk: Desk, corpus: Path) -> Office:
    return Office(desk, corpus)


def _approved(office: Office, *files: str, customer: str = "Okafor") -> list[str]:
    return [office.jobs.approve(office.arrive(customer, file).id).id for file in files]


def test_job_states_simulation_lists_the_contracts_of_a_run_and_writes_nothing(office: Office) -> None:
    ids = _approved(office, "policy_b_1.pdf", "premium_invoice_c_1.pdf")
    _approved(office, "policy_b_2.pdf", customer="Brandt")

    preview = hand_over.simulate(office.jobs, office.desk.inbox, "Okafor")
    assert preview.problem is None and preview.waiting == {}
    assert sorted(i for contract in preview.contracts for i in contract) == sorted(ids)
    assert list(office.handover.iterdir()) == []
    assert {job.state for job in office.jobs.all()} == {"pending"}

    # The run writes exactly what the simulation showed.
    assert sorted(job.id for job in office.run("Okafor") if job.state == "handed_over") == sorted(ids)


def test_job_states_simulation_groups_the_jobs_of_one_policy_number_as_one_contract(
    office: Office,
) -> None:
    truth = next(i for i in office.truth if i["file"] == "policy_b_1.pdf")["values"]
    first = office.jobs.approve(office.arrive("Okafor", "policy_b_1.pdf").id).id
    other = office.jobs.approve(office.arrive("Okafor", "policy_b_2.pdf").id).id
    preview = hand_over.simulate(office.jobs, office.desk.inbox, "Okafor")
    assert sorted(preview.contracts) == sorted([[first], [other]])
    file = office.jobs.get(first).file
    names = {kind: spec["values"] for kind, spec in hand_over._profile(file)["kinds"].items()}
    job = file.model_dump()
    assert gdv._policy(job, names) == "".join(c for c in truth["policy_number"] if c.isalnum())


def test_job_states_simulation_names_a_refused_value_before_the_run(office: Office) -> None:
    truth = next(i for i in office.truth if i["file"] == "policy_b_1.pdf")["values"]
    first = office.arrive("Okafor", "policy_b_1.pdf")
    second = office.arrive(
        "Okafor", "policy_b_2.pdf",
        insurer=truth["insurer"], policy_number=truth["policy_number"],
        line_of_business=truth["line_of_business"],
    )
    ids = [office.jobs.approve(entry.id).id for entry in (first, second)]

    preview = hand_over.simulate(office.jobs, office.desk.inbox, "Okafor")
    assert preview.contracts == []
    assert preview.waiting == {i: [{"item": "one_contract_per_policy_number"}] for i in ids}
    assert list(office.handover.iterdir()) == []


def test_job_states_simulation_names_incomplete_settings_and_a_missing_folder(
    desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    office = Office(desk, corpus, block="\nhand_over:\n  format: gdv\n  encoding: cp850\n")
    _approved(office, "policy_b_1.pdf")
    preview = hand_over.simulate(office.jobs, office.desk.inbox, "Okafor")
    assert preview.problem is not None
    assert preview.problem.startswith("hand-over-settings-invalid: ")
    assert "hand_over.broker_number" in preview.problem

    monkeypatch.setattr(office.desk.inbox, "handover_folder", lambda: None)
    preview = hand_over.simulate(office.jobs, office.desk.inbox, "Okafor")
    assert preview.problem == hand_over.REASON_NO_FOLDER


def test_job_states_imported_moves_the_handed_over_jobs_of_the_customer_to_done(office: Office) -> None:
    ids = _approved(office, "policy_b_1.pdf", "premium_invoice_c_1.pdf")
    [other] = _approved(office, "policy_b_2.pdf", customer="Brandt")
    office.run("Okafor")
    office.run("Brandt")
    [file] = [f for f in office.gdv_files() if f.name.startswith("Okafor_")]

    done = office.jobs.report_import("Okafor", imported=True)
    assert sorted(job.id for job in done) == sorted(ids)
    for job in done:
        last = job.transitions[-1]
        assert (job.state, last.from_state, last.reason) == ("done", "handed_over", "import-confirmed")
        assert last.account
    # The file stays where it was imported from; the other customer is untouched.
    assert file.exists()
    assert office.jobs.get(other).state == "handed_over"
    # A second report finds nothing more to move.
    assert office.jobs.report_import("Okafor", imported=True) == []


def test_job_states_failed_import_keeps_the_reason_removes_the_file_and_waits_for_a_person(
    office: Office,
) -> None:
    [job_id] = _approved(office, "policy_b_1.pdf")
    office.run("Okafor")
    [file] = office.gdv_files()
    job_file = Path(office.jobs.get(job_id).handover_path)

    [failed] = office.jobs.report_import("Okafor", imported=False, reason="  Kunde   nicht gefunden ")
    last = failed.transitions[-1]
    assert (failed.state, last.reason) == ("failed", "import-failed: Kunde nicht gefunden")
    assert last.account and failed.handover_path is None
    assert not file.exists() and not job_file.exists()

    # Nothing is handed over again by itself, not even after a release.
    office.jobs.hand_over_pending()
    assert office.jobs.get(job_id).state == "failed"
    assert office.jobs.release(job_id).state == "pending"
    assert office.gdv_files() == []
    # The release leads back to the simulation, and a person starts the next run.
    assert hand_over.simulate(office.jobs, office.desk.inbox, "Okafor").contracts == [[job_id]]
    [again] = office.run("Okafor")
    assert again.state == "handed_over" and len(office.gdv_files()) == 1


def test_job_states_failed_import_without_a_reason_is_refused_and_changes_nothing(office: Office) -> None:
    [job_id] = _approved(office, "policy_b_1.pdf")
    office.run("Okafor")
    with pytest.raises(ImportReasonMissing):
        office.jobs.report_import("Okafor", imported=False, reason="   ")
    assert office.jobs.get(job_id).state == "handed_over" and len(office.gdv_files()) == 1


def test_job_states_report_leaves_pending_and_failed_jobs_alone(office: Office) -> None:
    [job_id] = _approved(office, "policy_b_1.pdf")
    assert office.jobs.report_import("Okafor", imported=True) == []
    assert office.jobs.get(job_id).state == "pending"


def test_job_states_endpoints_preview_and_report_need_the_token(client) -> None:  # noqa: F811
    body = {"customer": "Niemand"}
    preview = client.post("/jobs/hand-over/preview", json=body, headers=auth())
    assert preview.status_code == 200
    assert preview.json()["contracts"] == [] and preview.json()["customer"] == "Niemand"
    assert client.post("/jobs/hand-over/preview", json=body).status_code == 401

    report = {**body, "imported": True}
    assert client.post("/jobs/hand-over/result", json=report, headers=auth()).json() == []
    assert client.post("/jobs/hand-over/result", json=report).status_code == 401
    refused = client.post(
        "/jobs/hand-over/result", json={**body, "imported": False}, headers=auth()
    )
    assert refused.status_code == 422 and refused.json()["key"] == "import-reason-missing"
