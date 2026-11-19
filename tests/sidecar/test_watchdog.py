"""The parent watchdog checks the shell without ever signalling it on Windows."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import substrakt.app as app

WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = app._WAIT_TIMEOUT


class Kernel32:
    """Stand-in for the three calls the Windows branch makes."""

    def __init__(self, handle: int, wait_result: int) -> None:
        self.handle, self.wait_result, self.closed = handle, wait_result, []

    def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
        return self.handle

    def WaitForSingleObject(self, handle: int, milliseconds: int) -> int:
        return self.wait_result

    def CloseHandle(self, handle: int) -> None:
        self.closed.append(handle)


@pytest.fixture
def one_round(monkeypatch: pytest.MonkeyPatch):
    """Let the watchdog loop run exactly once and record a shutdown request."""
    rounds = iter([False, True])
    stopped: list[bool] = []
    event = SimpleNamespace(wait=lambda _: next(rounds), set=lambda: stopped.append(True))
    monkeypatch.setattr(app, "_beenden", event)
    return stopped


def as_windows(monkeypatch: pytest.MonkeyPatch, kernel32: Kernel32) -> None:
    def kill(*_):
        raise AssertionError("os.kill terminates the target process on Windows")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False)


def test_watchdog_on_windows_never_signals_a_running_parent(monkeypatch, one_round) -> None:
    kernel32 = Kernel32(handle=7, wait_result=WAIT_TIMEOUT)
    as_windows(monkeypatch, kernel32)

    app._watchdog_pid(4321)

    assert one_round == []
    assert kernel32.closed == [7]


@pytest.mark.parametrize(("handle", "wait_result"), [(7, WAIT_OBJECT_0), (0, WAIT_TIMEOUT)])
def test_watchdog_on_windows_stops_when_the_parent_ended_or_is_gone(
    monkeypatch, one_round, handle, wait_result
) -> None:
    as_windows(monkeypatch, Kernel32(handle, wait_result))

    app._watchdog_pid(4321)

    assert one_round == [True]


def test_watchdog_elsewhere_keeps_running_while_the_parent_lives(monkeypatch, one_round) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    app._watchdog_pid(os.getpid())

    assert one_round == []


def test_watchdog_elsewhere_stops_when_the_parent_is_gone(monkeypatch, one_round) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    ended = subprocess.Popen([sys.executable, "-c", "pass"])
    ended.wait()

    app._watchdog_pid(ended.pid)

    assert one_round == [True]
