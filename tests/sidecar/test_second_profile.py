"""A second profile is a file in the data directory; reading, customer and job follow it."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import yaml
from conftest import Desk, put
from test_api import auth, client  # noqa: F401  (the fixture of the API tests)
from test_privacy import settle_values, truth_of

from substrakt import gdv, pipeline_profiles
from substrakt import jobs as jobs_module
from substrakt.inbox import OUTPUT
from substrakt.jobs import JobFile, Jobs

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "second_profile.yml"
GUIDE = ROOT / "docs" / "pipeline-profiles.md"
SECOND = "file_archive"
INSURANCE = "insurance"


@pytest.fixture
def two_profiles(desk: Desk):
    """The shipped profile and, as a file in the user directory, the second one."""
    profiles = desk.root / "profiles"
    for other in profiles.glob("*.yml"):
        other.unlink()
    shutil.copy(FIXTURE, profiles / f"{SECOND}.yml")
    handover = desk.folder / OUTPUT
    [shipped] = [name for name in pipeline_profiles.titles() if name != SECOND]
    return shipped, handover


def arrive(desk: Desk, corpus: Path, relative: str, source: Path) -> object:
    put(desk, relative, source.read_bytes())
    desk.settle()
    return desk.entries()[relative]


def test_second_profile_differs_from_the_shipped_one_in_everything_a_profile_decides(
    two_profiles: tuple[str, Path],
) -> None:
    shipped = pipeline_profiles.load(two_profiles[0])
    second = pipeline_profiles.load(SECOND)

    assert second.target != shipped.target
    assert second.customer_folder_level != shipped.customer_folder_level
    assert set(second.kinds) != set(shipped.kinds)
    assert second.kinds["policy"].values != shipped.kinds["policy"].values
    assert second.hand_over is None


def test_second_profile_decides_kind_customer_and_job_content_without_a_code_change(
    desk: Desk, corpus: Path, two_profiles: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped, handover = two_profiles
    written: list[JobFile] = []
    monkeypatch.setitem(
        jobs_module.WRITERS, "invented_archive", lambda file, _: written.append(file)
    )
    jobs = Jobs(desk.inbox)

    # Under the shipped profile the first folder level names the customer.
    desk.inbox.choose_profile(shipped)
    desk.inbox.choose_folder(str(desk.folder))
    before = arrive(desk, corpus, "2026/Okafor/first.pdf", corpus / INSURANCE / "policy_a_1.pdf")
    assert (before.profile, before.customer) == (shipped, "2026")  # type: ignore[attr-defined]

    # The second profile is chosen; nothing else changes.
    desk.inbox.choose_profile(SECOND)
    policy = arrive(desk, corpus, "2026/Okafor/second.pdf", corpus / INSURANCE / "policy_a_2.pdf")
    invoice = arrive(desk, corpus, "2026/Meier/invoice.pdf", corpus / "rechnung_din5008.pdf")
    loose = arrive(desk, corpus, "2026/loose.pdf", corpus / INSURANCE / "policy_a_3.pdf")

    assert (policy.profile, policy.kind, policy.customer) == (SECOND, "policy", "Okafor")  # type: ignore[attr-defined]
    assert (invoice.kind, invoice.customer) == ("invoice", "Meier")  # type: ignore[attr-defined]
    assert loose.customer is None, "a file above the customer level has no customer"  # type: ignore[attr-defined]
    assert desk.inbox.entry(before.id).profile == shipped, "what was read keeps its profile"  # type: ignore[attr-defined]

    settle_values(desk, policy, truth_of(corpus, "policy_a_2.pdf"))  # type: ignore[arg-type]
    job = jobs.approve(policy.id)  # type: ignore[attr-defined]
    on_disk = json.loads((handover / f"{job.id}.json").read_text(encoding="utf-8"))

    expected = truth_of(corpus, "policy_a_2.pdf")["values"]
    assert (on_disk["profile"], on_disk["target"], on_disk["customer"]) == (
        SECOND, "invented_archive", "Okafor",
    )
    assert {name: value["normalized"] for name, value in on_disk["values"].items()} == {
        "Vertrag": expected["policy_number"],
        "Kunde": expected["policyholder"],
        "Ausgestellt": expected["issue_date"],
    }
    assert [file.id for file in written] == [job.id]

    job = jobs.approve(invoice.id)  # type: ignore[attr-defined]
    assert set(job.file.values) == {"Belegnr", "Summe"}
    assert job.file.kind == "invoice"


def test_second_profile_for_a_target_without_a_writer_fails_with_the_reason(
    desk: Desk, corpus: Path, two_profiles: tuple[str, Path]
) -> None:
    _, handover = two_profiles
    desk.inbox.choose_profile(SECOND)
    desk.inbox.choose_folder(str(desk.folder))
    invoice = arrive(desk, corpus, "2026/Meier/invoice.pdf", corpus / "rechnung_din5008.pdf")

    job = Jobs(desk.inbox).approve(invoice.id)  # type: ignore[attr-defined]

    assert (job.state, job.transitions[-1].reason) == ("failed", "target-without-writer")
    assert (job.file.profile, job.file.target) == (SECOND, "invented_archive")
    assert list(handover.iterdir()) == []


def test_second_profile_in_the_data_directory_of_the_application_can_be_chosen(
    client,  # noqa: F811
) -> None:
    import substrakt.app as app_module

    directory = Path(os.environ["SUBSTRAKT_DATA_DIR"]) / "pipeline_profiles"
    assert pipeline_profiles._custom == app_module.CONFIG.data_dir / "pipeline_profiles"
    assert directory == app_module.CONFIG.data_dir / "pipeline_profiles"
    directory.mkdir(exist_ok=True)
    file = directory / f"{SECOND}.yml"
    try:
        before = client.get("/inbox/settings", headers=auth()).json()
        assert SECOND not in [choice["name"] for choice in before["profiles"]]

        shutil.copy(FIXTURE, file)
        listed = client.get("/inbox/settings", headers=auth()).json()
        chosen = client.post("/inbox/settings", json={"profile": SECOND}, headers=auth()).json()
    finally:
        file.unlink(missing_ok=True)

    assert {"name": SECOND, "title": "Aktenablage Beispiel"} in listed["profiles"]
    assert chosen["profile"] == SECOND


def test_second_profile_names_stand_in_no_code_and_in_no_shipped_file() -> None:
    names = [SECOND, "invented_archive", "Aktenablage Beispiel"]
    shipped = [
        file
        for folder in ("sidecar/substrakt", "src", "src-tauri/src")
        for file in (ROOT / folder).rglob("*")
        if file.suffix in {".py", ".rs", ".ts", ".tsx", ".yml", ".json"}
    ]

    assert len(shipped) > 50
    for file in shipped:
        text = file.read_text(encoding="utf-8")
        assert [name for name in names if name in text] == [], str(file)


# --- Z7.7: the guide ---------------------------------------------------------------


def test_second_profile_guide_rebuilds_the_shipped_profile() -> None:
    """Following the guide step by step ends in the content of the shipped file."""
    guide = GUIDE.read_text(encoding="utf-8")
    [shipped] = sorted(pipeline_profiles.BUILTIN.glob("*.yml"))
    blocks = [part.split("```")[0] for part in guide.split("```yaml\n")[1:]]
    result = guide.split("<!-- worked-example")[1].split("```yaml\n")[1].split("```")[0]

    rebuilt = pipeline_profiles.PipelineProfile.model_validate(yaml.safe_load(result))

    assert rebuilt == pipeline_profiles.load(shipped.stem)
    # The steps before it show the same lines, not another profile.
    lines = set(result.splitlines())
    for step in blocks[:3]:
        assert set(step.splitlines()) <= lines, step


def test_second_profile_guide_names_every_key_of_the_schema() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    keys = [
        *pipeline_profiles.PipelineProfile.model_fields,
        *pipeline_profiles.ExpectedValues.model_fields,
        *gdv.Settings.model_fields,
    ]

    assert len(keys) > 15
    assert [key for key in keys if f"`{key}`" not in guide and f".{key}`" not in guide] == []
