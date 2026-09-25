import os
import stat

from app.engines.detect import detect_all, probe


def _make_cli(tmp_path, name, version_output):
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\necho '{version_output}'\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


async def test_probe_found(tmp_path, monkeypatch):
    _make_cli(tmp_path, "opencode", "0.6.3")
    monkeypatch.setenv("PATH", str(tmp_path))
    result = await probe("opencode")
    assert result.available and result.version == "0.6.3"
    assert result.path and result.path.endswith("opencode")


async def test_probe_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    result = await probe("opencode")
    assert not result.available and "not found" in result.reason


async def test_detect_all_reports_each_cli(tmp_path, monkeypatch):
    _make_cli(tmp_path, "codex", "codex 1.0")
    monkeypatch.setenv("PATH", str(tmp_path))
    results = await detect_all({"opencode": "OpenCode", "codex": "Codex"})
    assert results["codex"].available
    assert not results["opencode"].available
