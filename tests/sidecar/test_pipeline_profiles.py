"""A pipeline profile is a checked YAML file; code names no target application."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from substrakt import pipeline_profiles
from substrakt.errors import PipelineProfileInvalid, PipelineProfileUnknown
from substrakt.pipeline_profiles import PipelineProfile

ROOT = Path(__file__).resolve().parents[2]
DICTIONARIES = [ROOT / "src" / "i18n" / "de.ts", ROOT / "src" / "i18n" / "en.ts"]

VALID = """\
name: scans
title: Scans
target: test_target
customer_folder_level: 2
kinds:
  invoice:
    values:
      document_number: Nummer
      total_amount: Betrag
"""


@pytest.fixture
def directory(tmp_path: Path):
    """A user directory for profiles, removed from the loader afterwards."""
    pipeline_profiles.configure(tmp_path)
    yield tmp_path
    pipeline_profiles.configure(None)


def write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.yml").write_text(text, encoding="utf-8")


def rejection(directory: Path, name: str, text: str) -> PipelineProfileInvalid:
    write(directory, name, text)
    with pytest.raises(PipelineProfileInvalid) as raised:
        pipeline_profiles.load(name)
    return raised.value


def test_pipeline_profile_valid_file_names_folder_level_kinds_values_and_target(directory) -> None:
    write(directory, "scans", VALID)

    profile = pipeline_profiles.load("scans")

    assert profile.target == "test_target"
    assert profile.customer_folder_level == 2
    assert profile.kinds["invoice"].values == {
        "document_number": "Nummer",
        "total_amount": "Betrag",
    }
    assert pipeline_profiles.titles()["scans"] == "Scans"
    assert profile.hand_over is None


def test_pipeline_profile_lists_optional_values_next_to_the_required_ones(directory) -> None:
    write(directory, "scans", VALID + "    optional:\n      iban: IBAN\n")

    expected = pipeline_profiles.load("scans").kinds["invoice"]

    assert expected.optional == {"iban": "IBAN"}
    assert "iban" not in expected.values
    twice = rejection(
        directory, "other", VALID.replace("scans", "other") + "    optional:\n      total_amount: B\n"
    )
    assert "required and as optional: total_amount" in twice.fields["error"][0]["message"]
    unknown = rejection(
        directory, "third", VALID.replace("scans", "third") + "    optional:\n      no_such: B\n"
    )
    assert unknown.fields["error"][0]["location"] == "kinds.invoice.optional.no_such"


def test_pipeline_profile_passes_the_hand_over_settings_through_unchecked(directory) -> None:
    write(directory, "scans", VALID + "hand_over:\n  encoding: cp850\n  anything: [1, 2]\n")

    assert pipeline_profiles.load("scans").hand_over == {"encoding": "cp850", "anything": [1, 2]}
    assert rejection(directory, "other", VALID.replace("scans", "other") + "hand_over: text\n")


def test_pipeline_profile_overview_columns_must_be_values_a_kind_reads(directory) -> None:
    write(directory, "scans", VALID + "overview_columns:\n  total_amount: Betrag\n")

    assert pipeline_profiles.load("scans").overview_columns == {"total_amount": "Betrag"}
    unread = rejection(
        directory, "other", VALID.replace("scans", "other") + "overview_columns:\n  iban: IBAN\n"
    )
    assert unread.fields["error"][0]["location"] == "overview_columns.iban"


def test_pipeline_profile_takes_the_customer_from_the_named_folder_level() -> None:
    folder = Path("/scans")

    def customer(level: int | None, file: str) -> str | None:
        profile = PipelineProfile(
            name="p", title="P", target="t", customer_folder_level=level,
            kinds={"invoice": {"values": {"iban": "IBAN"}}},
        )
        return profile.customer_of(folder / file, folder)

    assert customer(1, "Meier/policy.pdf") == "Meier"
    assert customer(1, "Meier/2026/policy.pdf") == "Meier"
    assert customer(2, "2026/Meier/policy.pdf") == "Meier"
    assert customer(1, "policy.pdf") is None
    assert customer(2, "Meier/policy.pdf") is None
    assert customer(None, "Meier/policy.pdf") is None


def test_pipeline_profile_with_an_unknown_key_is_rejected_with_a_stable_key(directory) -> None:
    error = rejection(directory, "scans", VALID + "watch_subfolders: true\n")

    assert error.key == "pipeline-profile-invalid"
    assert error.fields["file"] == "scans.yml"
    assert error.fields["error"][0]["location"] == "watch_subfolders"
    for dictionary in DICTIONARIES:
        assert f"'{error.key}'" in dictionary.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("change", "location"),
    [
        (("  invoice:", "  no_such_kind:"), "kinds.no_such_kind"),
        (("document_number: Nummer", "no_such_value: Nummer"), "kinds.invoice.values.no_such_value"),
        (("customer_folder_level: 2\n", ""), "customer_folder_level"),
        (("customer_folder_level: 2", "customer_folder_level: 0"), "customer_folder_level"),
        (("target: test_target", "target: Some Program"), "(file)"),
    ],
)
def test_pipeline_profile_with_a_missing_kind_value_or_folder_level_is_rejected(
    directory, change, location
) -> None:
    error = rejection(directory, "scans", VALID.replace(*change))

    assert error.fields["error"][0]["location"] == location


def test_pipeline_profile_without_any_kind_is_rejected(directory) -> None:
    without_kinds = VALID[: VALID.index("kinds:")]

    assert rejection(directory, "scans", without_kinds).fields["error"][0]["location"] == "kinds"
    assert rejection(directory, "other", without_kinds.replace("scans", "other") + "kinds: {}\n")


def test_pipeline_profile_name_must_match_its_file(directory) -> None:
    assert rejection(directory, "renamed", VALID).fields["error"][0]["location"] == "name"


def test_pipeline_profile_that_does_not_exist_is_unknown_in_both_languages(directory) -> None:
    with pytest.raises(PipelineProfileUnknown) as raised:
        pipeline_profiles.load("absent")

    for dictionary in DICTIONARIES:
        assert f"'{raised.value.key}'" in dictionary.read_text(encoding="utf-8")


def test_pipeline_profile_is_active_without_a_choice_only_when_it_is_the_only_one(
    directory, monkeypatch
) -> None:
    write(directory, "scans", VALID)
    with pytest.raises(PipelineProfileUnknown):
        pipeline_profiles.active(None)
    assert pipeline_profiles.active("scans").name == "scans"

    monkeypatch.setattr(pipeline_profiles, "BUILTIN", directory)
    assert pipeline_profiles.active(None).name == "scans"


def test_pipeline_profile_in_the_user_directory_replaces_the_bundled_one(directory) -> None:
    shipped = next(iter(pipeline_profiles.titles()))
    write(directory, shipped, VALID.replace("scans", shipped).replace("Scans", "Replaced"))

    assert pipeline_profiles.titles()[shipped] == "Replaced"
    assert pipeline_profiles.load(shipped).target == "test_target"


def test_pipeline_profile_schema_file_matches_the_model(tmp_path: Path) -> None:
    assert pipeline_profiles.schema_is_current(), (
        "pipeline_profile.schema.json is stale: "
        'uv run python -c "from substrakt import pipeline_profiles as p; p.write_schema()"'
    )
    schema = json.loads(pipeline_profiles.schema_text())
    assert schema["additionalProperties"] is False
    assert {"name", "target", "customer_folder_level", "kinds"} <= set(schema["required"])

    stale = tmp_path / "pipeline_profile.schema.json"
    stale.write_text(pipeline_profiles.schema_text().replace('"target"', '"stale"', 1))
    assert not pipeline_profiles.schema_is_current(stale)


def shipped_profiles() -> list[Path]:
    return sorted(pipeline_profiles.BUILTIN.glob("*.yml"))


def test_pipeline_profile_shipped_files_are_valid_descriptions() -> None:
    assert shipped_profiles()
    for file in shipped_profiles():
        profile = pipeline_profiles._read(file, (0, 0))
        assert profile.name == file.stem


def test_pipeline_profile_shipped_files_name_kinds_and_values_that_exist() -> None:
    for file in shipped_profiles():
        assert pipeline_profiles.load(file.stem).kinds


CODE_FOLDERS = ("sidecar/substrakt", "src", "src-tauri/src")
CODE_SUFFIXES = {".py", ".rs", ".ts", ".tsx"}


def files_naming_a_title(titles: set[str], root: Path, folders=CODE_FOLDERS) -> list[str]:
    """Return every code file under ``folders`` that contains one of ``titles``.

    An empty set or an empty title would build a pattern that matches every
    file or none at all, so both are refused instead of passing silently.
    The private overlay check calls this with its own titles.
    """
    if not titles or not all(title.strip() for title in titles):
        raise ValueError("a target name check needs at least one title, none empty")
    pattern = re.compile("|".join(re.escape(title) for title in titles), re.IGNORECASE)
    code = [
        file
        for folder in folders
        for file in (root / folder).rglob("*")
        if file.suffix in CODE_SUFFIXES
    ]
    if not code:
        raise ValueError(f"no code files under {folders} in {root}")
    return [str(file) for file in code if pattern.search(file.read_text(encoding="utf-8"))]


def shipped_titles() -> set[str]:
    return {pipeline_profiles._read(file, (0, 0)).title for file in shipped_profiles()}


def test_pipeline_profile_files_are_the_only_place_that_names_a_target_application() -> None:
    code = [f for d in CODE_FOLDERS for f in (ROOT / d).rglob("*") if f.suffix in CODE_SUFFIXES]
    assert len(code) > 50
    assert files_naming_a_title(shipped_titles(), ROOT) == []


def test_target_application_check_finds_the_shipped_title_in_a_module(tmp_path: Path) -> None:
    [title] = shipped_titles()
    module = tmp_path / "sidecar" / "substrakt" / "writer.py"
    module.parent.mkdir(parents=True)
    module.write_text(f'TARGET = "{title.upper()}"\n', encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "clean.ts").write_text("export const x = 1;\n", encoding="utf-8")

    assert files_naming_a_title({title}, tmp_path) == [str(module)]


@pytest.mark.parametrize("titles", [set(), {""}, {"  "}])
def test_target_application_check_refuses_an_empty_title_set(titles: set[str]) -> None:
    with pytest.raises(ValueError):
        files_naming_a_title(titles, ROOT)


def test_pipeline_profile_the_core_ships_one_neutral_example_with_the_insurance_keys() -> None:
    from substrakt import jobs

    assert [file.name for file in shipped_profiles()] == ["insurance_folder.yml"]
    profile = pipeline_profiles.load("insurance_folder")
    assert profile.target not in jobs.WRITERS
    assert profile.hand_over is None
    assert profile.customer_folder_level == 1

    fixture = ROOT / "tests" / "sidecar" / "fixtures" / "shipped_profile_keys.json"
    keys = {
        name: {"values": sorted(kind.values), "optional": sorted(kind.optional)}
        for name, kind in profile.kinds.items()
    }
    assert keys == json.loads(fixture.read_text(encoding="utf-8"))
