"""Ruff rejects a network library in the shipped sidecar."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SIDECAR = Path(__file__).resolve().parents[2] / "sidecar"
RUFF = [sys.executable, "-m", "ruff", "check", "--no-cache"]


def ruff(source: str) -> subprocess.CompletedProcess[str]:
    """Check source as if it were a module of the shipped package."""
    return subprocess.run(
        [*RUFF, "--stdin-filename", str(SIDECAR / "substrakt" / "probe.py"), "-"],
        input=source, cwd=SIDECAR, capture_output=True, text=True,
    )


@pytest.mark.parametrize(
    "source",
    [
        "import requests\n\nrequests.get('https://example.com')\n",
        "import urllib.request\n\nurllib.request.urlopen('https://example.com')\n",
        "from urllib.request import urlopen\n\nurlopen('https://example.com')\n",
        "import httpx\n\nhttpx.get('https://example.com')\n",
    ],
)
def test_ruff_rejects_a_network_import_in_the_sidecar(source: str) -> None:
    result = ruff(source)
    assert result.returncode == 1
    assert "TID251" in result.stdout


def test_ruff_accepts_a_module_without_a_network_import() -> None:
    result = ruff("import json\n\nprint(json.dumps({}))\n")
    assert result.returncode == 0, result.stdout


def test_the_shipped_sidecar_has_no_banned_import() -> None:
    result = subprocess.run([*RUFF, "substrakt/"], cwd=SIDECAR, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
