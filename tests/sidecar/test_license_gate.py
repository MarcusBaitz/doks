"""The licence gate admits Gemma 4 weights and keeps older Gemma forbidden."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-licenses.py"

# The script name has a hyphen, so it cannot be imported by name.
_spec = importlib.util.spec_from_file_location("check_licenses", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
sys.modules["check_licenses"] = gate
_spec.loader.exec_module(gate)

POLICY = gate.load_policy()


@pytest.mark.parametrize(
    "repo",
    [
        "google/gemma-4-E4B-it",
        "google/gemma-4-E2B-it",
        "google/gemma-4-12B-it",
        "google/gemma-4-E4B-it-qat-q4_0-gguf",
        "Google/Gemma-4-31B-it",
    ],
)
def test_gemma_4_weights_published_by_google_are_admitted(repo):
    assert gate.evaluate_model(repo, POLICY) is None


@pytest.mark.parametrize(
    "repo",
    [
        "google/gemma-3-4b-it",
        "google/gemma-3-4b-it-qat-q4_0-gguf",
        "google/gemma-3n-E4B-it",
        "google/gemma-2-2b-it",
        "google/gemma-1.1-2b-it",
        "google/gemma-7b",
        "google/embeddinggemma-300m",
        "GOOGLE/GEMMA-3-27B-IT",
    ],
)
def test_gemma_3_3n_and_older_stay_forbidden(repo):
    reason = gate.evaluate_model(repo, POLICY)
    assert reason is not None and "Gemma Terms of Use" in reason


def test_without_the_admission_gemma_4_falls_back_to_forbidden():
    policy = copy.deepcopy(POLICY)
    policy["admitted_models"] = []
    assert gate.evaluate_model("google/gemma-4-E4B-it", policy) is not None


@pytest.mark.parametrize("change", [{"license": "Gemma"}, {"license_url": ""}, {"checked": ""}])
def test_an_admission_without_a_permissive_licence_or_its_record_admits_nothing(change):
    policy = copy.deepcopy(POLICY)
    policy["admitted_models"] = [{**policy["admitted_models"][0], **change}]
    assert gate.evaluate_model("google/gemma-4-E4B-it", policy) is not None


def test_the_admission_does_not_reach_other_forbidden_families():
    assert gate.evaluate_model("LiquidAI/LFM2-1.2B", POLICY) is not None
    assert gate.evaluate_model("mistralai/mistral-ocr-4-1", POLICY) is not None


def test_the_fetch_script_names_its_repositories_and_none_is_forbidden():
    repositories = gate.model_repositories(gate.FETCH_SCRIPT.read_text())
    assert "ggml-org/granite-docling-258M-GGUF" in repositories
    assert gate.check_models(repositories, POLICY).findings == []


def test_a_fetch_script_that_loads_gemma_3n_fails_the_gate_and_gemma_4_does_not():
    line = '"vlm/model.gguf|https://huggingface.co/google/{}/resolve/abc/model.gguf|00|x"'

    older = gate.check_models(gate.model_repositories(line.format("gemma-3n-E4B-it")), POLICY)
    assert [finding.package.name for finding in older.findings] == ["google/gemma-3n-E4B-it"]

    newer = gate.model_repositories(line.format("gemma-4-E4B-it-qat-q4_0-gguf"))
    assert newer == ["google/gemma-4-E4B-it-qat-q4_0-gguf"]
    assert gate.check_models(newer, POLICY).findings == []
