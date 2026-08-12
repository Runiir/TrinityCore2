from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from tools.raid_program import capture_no_bots_baseline as baseline


ROOT = Path(__file__).resolve().parents[1]


def test_tracked_identity_hashes_dirty_content_without_exposing_content(monkeypatch, tmp_path: Path) -> None:
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("secret-like payload\n", encoding="utf-8")
    monkeypatch.setattr(baseline, "ROOT", tmp_path)

    def output(command: list[str], **_: object) -> str | bytes:
        if command[1:] == ["rev-parse", "HEAD"]:
            return "a" * 40 + "\n"
        assert command[1:] == ["ls-files", "--modified", "--others", "--exclude-standard", "-z"]
        return b"tracked.txt\0"

    monkeypatch.setattr(baseline.subprocess, "check_output", output)
    identity = baseline.tracked_identity()
    assert identity["head"] == "a" * 40
    assert identity["dirty_file_count"] == 1
    assert len(identity["dirty_content_sha256"]) == 64
    assert "secret-like payload" not in json.dumps(identity)


def test_sha256_file_and_memory_probes_are_compact(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    payload.write_bytes(b"raid-baseline")
    assert baseline.sha256_file(payload) == hashlib.sha256(b"raid-baseline").hexdigest()
    memory = baseline.meminfo()
    assert memory["MemTotal"] > 0
    assert memory["MemAvailable"] > 0
    psi = baseline.memory_psi()
    assert set(psi) == {"some_avg10", "full_avg10"}
    assert all(value >= 0.0 for value in psi.values())


def test_process_sample_has_resource_fields() -> None:
    sample = baseline.process_sample(os.getpid())
    assert sample["process_cpu_ticks"] >= 0
    assert sample["process_rss_bytes"] > 0
    assert sample["memory_available_bytes"] > 0
    assert sample["host_load_1m"] >= 0.0


def test_report_path_preserves_external_binary_identity(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "worktree"
    root.mkdir()
    monkeypatch.setattr(baseline, "ROOT", root)
    assert baseline.report_path(root / "config.conf") == "config.conf"
    assert baseline.report_path(tmp_path / "shared-build/worldserver") == str(tmp_path / "shared-build/worldserver")
