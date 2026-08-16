from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tools.bot_ml import batch_evidence_lifecycle as lifecycle
from tools.bot_ml.live_validation_session import canonical_sha256


def _accepted_report() -> dict[str, object]:
    return {
        "schema": "bot_live_validation_report_v1",
        "returncode": 0,
        "timed_out": False,
        "stages": [{"stage": "focused-test", "missing": []}],
        "failure_labels": [],
        "validation_context": {},
        "evidence": {},
        "validation_route_manifest": {},
        "watchdog_state": {},
    }


def _capture(repository: Path) -> tuple[Path, dict[str, object]]:
    if not (repository / ".git").exists():
        subprocess.run(
            ["git", "init", "-q"], cwd=repository, check=True, capture_output=True
        )
    batch = repository / "batches" / "test-batch"
    manifest = lifecycle.capture_batch(
        batch,
        batch_id="test-batch",
        raw_rows=[{"event": "start"}, {"event": "complete"}],
        compact_rows=[{"metric": "damage", "value": 1.0}],
        exact_manifests={"config_sha256": "a" * 64},
        summary={"closed": True},
        acceptance_report=_accepted_report(),
    )
    return batch, manifest


class _PublishRunner:
    def __init__(self, batch: Path):
        self.batch = batch
        self.commands: list[list[str]] = []

    def __call__(
        self, command: list[str] | tuple[str, ...], cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        command = list(command)
        self.commands.append(command)
        if command[:4] == ["git", "check-ignore", "-v", "--no-index"]:
            return subprocess.CompletedProcess(command, 1, "", "")
        if command[:2] == ["dvc", "add"]:
            for name in ("raw", "compact"):
                document = (
                    "outs:\n"
                    f"- md5: {hashlib.md5(name.encode()).hexdigest()}.dir\n"
                    "  size: 10\n"
                    "  nfiles: 2\n"
                    "  hash: md5\n"
                    f"  path: {name}\n"
                )
                (self.batch / f"{name}.dvc").write_text(document, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")


def _publish(repository: Path, batch: Path, *, evict: bool) -> tuple[dict, _PublishRunner]:
    runner = _PublishRunner(batch)
    receipt = lifecycle.publish_batch(
        repository,
        batch,
        runner=runner,
        evict_after_verify=evict,
    )
    return receipt, runner


def test_validate_capture_recomputes_manifest_self_identity(tmp_path: Path):
    batch, _ = _capture(tmp_path)
    manifest_path = batch / "retained/final_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["batch_id"] = "tampered-but-stored-identity-unchanged"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        lifecycle.BatchLifecycleError, match="manifest self-identity mismatch"
    ):
        lifecycle.validate_capture(batch)


def test_publish_uses_quiet_cloud_status_and_capture_binds_pointer_document(
    tmp_path: Path,
):
    batch, _ = _capture(tmp_path)
    receipt, runner = _publish(tmp_path, batch, evict=False)

    assert [
        "dvc",
        "status",
        "-q",
        "-c",
        "batches/test-batch/raw.dvc",
        "batches/test-batch/compact.dvc",
    ] in runner.commands
    assert lifecycle.validate_capture(batch)["batch_id"] == "test-batch"

    receipt_path = batch / "retained/publication_receipt.json"
    tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
    raw_pointer = next(
        row for row in tampered["pointers"] if row["path"].endswith("raw.dvc")
    )
    raw_pointer["pointer_document"] = raw_pointer["pointer_document"].replace(
        "path: raw", "path: ../raw"
    )
    raw_pointer["pointer_sha256"] = hashlib.sha256(
        raw_pointer["pointer_document"].encode("utf-8")
    ).hexdigest()
    tampered.pop("receipt_sha256")
    tampered["receipt_sha256"] = canonical_sha256(tampered)
    receipt_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(
        lifecycle.BatchLifecycleError, match="outside the batch contract"
    ):
        lifecycle.validate_capture(batch)

    assert receipt["remote_verified"] is True


def test_force_reconstruction_bypasses_old_receipt_and_evicts_exact_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    batch, manifest = _capture(tmp_path)
    publication, _ = _publish(tmp_path, batch, evict=True)
    old_receipt = {
        "schema": "bot_immutable_batch_reconstruction_receipt_v1",
        "batch_id": manifest["batch_id"],
        "batch_identity_sha256": manifest["identity_sha256"],
        "publication_receipt_sha256": publication["receipt_sha256"],
        "remote_reconstructed": True,
        "targeted_eviction_complete": True,
        "domain_verification_id": "",
        "domain_verification": {},
    }
    old_receipt["receipt_sha256"] = canonical_sha256(old_receipt)
    reconstruction_path = batch / "retained/reconstruction_receipt.json"
    reconstruction_path.write_text(json.dumps(old_receipt), encoding="utf-8")
    unrelated = batch / "unrelated.keep"
    unrelated.write_text("must survive exact eviction", encoding="utf-8")

    calls: list[str] = []

    def unavailable(*_args, **_kwargs):
        calls.append("unavailable")
        raise lifecycle.BatchLifecycleError("remote unavailable")

    monkeypatch.setattr(lifecycle, "hydrate_batch", unavailable)
    assert (
        lifecycle.verify_remote_reconstruction_and_evict(tmp_path, batch)
        == old_receipt
    )
    assert calls == []
    with pytest.raises(lifecycle.BatchLifecycleError, match="remote unavailable"):
        lifecycle.verify_remote_reconstruction_and_evict(
            tmp_path, batch, force_reconstruct=True
        )
    assert calls == ["unavailable"]
    assert unrelated.read_text(encoding="utf-8") == "must survive exact eviction"

    def reconstructed(_repository: Path, reconstructed_batch: Path, **_kwargs):
        calls.append("reconstructed")
        (reconstructed_batch / "raw").mkdir()
        (reconstructed_batch / "compact").mkdir()
        return {
            "batch_id": manifest["batch_id"],
            "batch_identity_sha256": manifest["identity_sha256"],
            "hydrated": True,
        }

    monkeypatch.setattr(lifecycle, "hydrate_batch", reconstructed)
    forced = lifecycle.verify_remote_reconstruction_and_evict(
        tmp_path, batch, force_reconstruct=True
    )

    assert calls == ["unavailable", "reconstructed"]
    assert forced["force_reconstructed"] is True
    assert not (batch / "raw").exists()
    assert not (batch / "compact").exists()
    assert unrelated.read_text(encoding="utf-8") == "must survive exact eviction"


def test_force_reconstruction_evicts_payload_when_domain_verifier_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    batch, manifest = _capture(tmp_path)
    _publish(tmp_path, batch, evict=True)
    pointer_bytes = {
        name: (batch / name).read_bytes() for name in ("raw.dvc", "compact.dvc")
    }
    bootstrap = batch / "retained/bootstrap_index.json"
    bootstrap.write_text('{"tracked": true}\n', encoding="utf-8")
    unrelated = batch / "unrelated.keep"
    unrelated.write_text("preserve", encoding="utf-8")

    def reconstructed(_repository: Path, reconstructed_batch: Path, **_kwargs):
        for name in (
            "raw",
            "compact",
            ".hydrate-dvc-cache",
            ".batch-dvc-cache",
        ):
            target = reconstructed_batch / name
            target.mkdir()
            (target / "materialized.bin").write_bytes(b"payload")
        return {
            "batch_id": manifest["batch_id"],
            "batch_identity_sha256": manifest["identity_sha256"],
            "hydrated": True,
        }

    def failed_domain_verifier(_batch: Path):
        raise RuntimeError("nested domain verifier exploded")

    monkeypatch.setattr(lifecycle, "hydrate_batch", reconstructed)
    with pytest.raises(RuntimeError, match="nested domain verifier exploded"):
        lifecycle.verify_remote_reconstruction_and_evict(
            tmp_path,
            batch,
            force_reconstruct=True,
            verify_hydrated=failed_domain_verifier,
        )

    for name in ("raw", "compact", ".hydrate-dvc-cache", ".batch-dvc-cache"):
        assert not (batch / name).exists()
    assert bootstrap.read_text(encoding="utf-8") == '{"tracked": true}\n'
    assert unrelated.read_text(encoding="utf-8") == "preserve"
    assert {
        name: (batch / name).read_bytes() for name in ("raw.dvc", "compact.dvc")
    } == pointer_bytes
    assert (batch / "retained/publication_receipt.json").is_file()
    assert (batch / "retained/final_manifest.json").is_file()
