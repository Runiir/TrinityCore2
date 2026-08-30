from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import shutil
import subprocess

import pytest

import tools.raid_program.chainwielder_prestart_bundle as bundle
import tools.raid_program.chainwielder_runtime_config_authority as authority
from tools.raid_program.canonical_route_staging import stage_tracked_snapshot
from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    sha256_file,
)
from tools.raid_program.tracked_runtime_config_derivation import (
    OUTPUT_SHA256,
    RECIPE_PATH,
    TEMPLATE_PATH,
    derive_runtime_config,
)


CONTRACT_SOURCE = Path(
    "experiments/configs/cata_raid_tracked_base_runtime_config_contract_v1.json"
)
CONTRACT_RELATIVE = "experiments/configs/runtime-config-contract.json"


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def _build_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bundle,
        "_verify_gate_bearing_build_receipt",
        lambda _receipt, _policy: {"valid": True, "gate_bearing": True},
    )


def _source_tree(root: Path) -> tuple[str, str]:
    return _git(root, "rev-parse", "HEAD"), _git(
        root, "rev-parse", "HEAD^{tree}"
    )


def _fixture(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "source"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    for relative in (TEMPLATE_PATH, RECIPE_PATH):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(Path(relative).read_bytes())
    contract = root / CONTRACT_RELATIVE
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_bytes(CONTRACT_SOURCE.read_bytes())
    legacy_source = root / "legacy-base.conf"
    legacy_source.write_text(
        'BotWorld.RuntimeProfile = "old"\nBotWorld.AutoStart = 1\n',
        encoding="utf-8",
    )
    profile_manifest = root / bundle.PROFILE_MANIFEST_RELATIVE_PATH
    _write_json(profile_manifest, {
        "schema": "bot_world_runtime_profiles_v1",
        "profiles": [{
            "name": bundle.SCENARIO_ID,
            "description": "selected diagnostic profile",
            "target_population": 10,
            "pool_tag_filter": bundle.SCENARIO_ID,
            "allow_raids": True,
            "diagnostic_only": True,
            "validation_route": {
                "enable": True,
                "manifest_path": "dataset/validation_scenarios/routes.jsonl",
                "advance_mode": "terminal",
                "scenario_id": bundle.SCENARIO_ID,
            },
        }],
    })
    ledger = root / bundle.TRACKED_LEDGER_RELATIVE_PATH
    _write_json(ledger, {"schema": "recurrence_ledger_test_v1"})
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture source")
    commit, tree = _source_tree(root)

    external = tmp_path / "external"
    external.mkdir()
    derived_root = tmp_path / "derived"
    derived_root.mkdir()
    derived = derive_runtime_config(
        worktree=root,
        contract_relative_path=CONTRACT_RELATIVE,
        expected_source_commit=commit,
        expected_source_tree=tree,
        external_run_root=derived_root,
        destination_name="base-runtime.conf",
    )
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"\x7fELFderived-runtime-config")
    build_receipt = external / "build.json"
    _write_json(build_receipt, {
        "classification": "success",
        "exit_code": 0,
        "commit": commit,
        "output_artifacts": [{
            "kind": "worldserver_elf",
            "path": str(binary.resolve()),
            "sha256": sha256_file(binary),
            "produced_by_ticket": True,
        }],
    })
    build_policy = external / "policy.json"
    _write_json(build_policy, {"test": "policy"})
    decision = external / "decision.json"
    _write_json(decision, {
        "build_admitted": False,
        "canary_admitted": False,
        "fixture_expansion_admitted": True,
        "fixture_expansion_target_ids": [
            CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        ],
        "fixture_expansion_requests": [],
        "invalidated_fixture_ids": [],
        "failing_fixture_ids": [],
        "missing_fixture_ids": [],
        "pending_fixture_ids": [CHAINWIELDER_CHECKPOINT_FIXTURE_ID],
        "stale_fixture_ids": [],
    })
    suite_receipt = external / "suite.json"
    _write_json(suite_receipt, {
        "schema": "trinity_raid_regression_suite_receipt_v1",
        "source_identity": commit,
        "verifications": [{
            "fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
            "fixture_revision": 1,
            "passed": True,
        }],
    })
    route_manifest = external / "route.json"
    roster = [{
        "roster_slot_id": f"slot-{index}",
        "guid": 30_000 + index,
        "name": f"Bot{index}",
        "class_spec": "test_spec",
        "role": "dps" if index > 5 else "support",
    } for index in range(1, 11)]
    shared = {
        "scenario_id": bundle.SCENARIO_ID,
        "runtime_profile_id": bundle.SCENARIO_ID,
        "map_id": 669,
        "expected_bot_count": 10,
        "bot_start_map_id": 669,
        "bot_start_x": -345.872,
        "bot_start_y": -224.344,
        "bot_start_z": 193.127,
        "bot_start_o": 0.0,
        "roster_identity": roster,
        "diagnostic_only": True,
        "diagnostic_parent_scenario_id": "blackwing_descent_10n",
        "diagnostic_prerequisite_state": {
            "certifies_predecessors": False,
            "precompleted_boss_entries": [],
        },
    }
    _write_json(route_manifest, {
        "schema": "bot_live_validation_route_manifest_v1",
        "scenario_id": bundle.SCENARIO_ID,
        "routes": [
            {**shared, "step": 1, "route_node_id": "bwd.entry.regroup",
             "kind": "regroup", "source_entry": 0},
            {**shared, "step": 2,
             "route_node_id": "bwd.magmaw.chainwielder", "kind": "trash",
             "source_entry": 42649},
            {**shared, "step": 3,
             "route_node_id": "bwd.magmaw.drudges", "kind": "trash",
             "source_entry": 42362},
            {**shared, "step": 4,
             "route_node_id": "bwd.magmaw.encounter", "kind": "boss",
             "source_entry": 41570},
        ],
    })
    paths = {
        "binary": binary,
        "build_receipt": build_receipt,
        "build_policy": build_policy,
        "decision": decision,
        "suite_receipt": suite_receipt,
        "route_manifest": route_manifest,
        "base_runtime_config_receipt": Path(derived["receipt_path"]),
        "ledger": ledger,
    }
    kwargs = {
        "worktree": root,
        "output_dir": tmp_path / "bundle",
        "source_commit": commit,
        "source_tree": tree,
        **paths,
        **{f"{key}_sha256": sha256_file(path)
           for key, path in paths.items()},
        "base_runtime_config_receipt_sha256": derived["receipt_sha256"],
        "base_runtime_config_authority": authority.TRACKED_DERIVED_AUTHORITY,
        "base_runtime_config_contract_relative_path": CONTRACT_RELATIVE,
        "scenario_id": bundle.SCENARIO_ID,
        "runtime_profile_id": bundle.SCENARIO_ID,
        "pool_tag": bundle.SCENARIO_ID,
        "actor_guid": bundle.ACTOR_GUID,
        "checkpoint_fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    }
    return {
        "root": root,
        "output": tmp_path / "bundle",
        "derived": derived,
        "derived_path": Path(derived["destination"]["path"]),
        "legacy_source": legacy_source,
        "kwargs": kwargs,
    }


def _create(fixture: dict[str, object]) -> dict[str, object]:
    return bundle.create_bundle(**fixture["kwargs"])  # type: ignore[arg-type]


def _rewrite_receipt(
    fixture: dict[str, object], mutation: str,
) -> None:
    receipt_path = Path(fixture["derived"]["receipt_path"])
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    if mutation == "schema":
        value["schema"] = "foreign"
    elif mutation == "source":
        value["source_commit"] = "0" * 40
    elif mutation == "contract":
        value["contract"]["sha256"] = "0" * 64
    elif mutation == "input":
        value["typed_inputs_sha256"] = "0" * 64
    elif mutation == "inventory":
        value["substitution_inventory_sha256"] = "0" * 64
    elif mutation == "output":
        value["output_sha256"] = "0" * 64
    elif mutation == "destination":
        value["destination"]["path"] += ".foreign"
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    receipt_path.write_bytes(payload)
    fixture["kwargs"]["base_runtime_config_receipt_sha256"] = hashlib.sha256(
        payload
    ).hexdigest()


def test_real_bundle_consumes_authenticated_derived_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    calls = 0
    real_verify = authority.verify_derived_runtime_config_snapshot

    def counted_verify(**arguments):
        nonlocal calls
        calls += 1
        return real_verify(**arguments)

    monkeypatch.setattr(
        authority, "verify_derived_runtime_config_snapshot", counted_verify
    )
    result = _create(fixture)
    copied = fixture["output"] / bundle.BUNDLE_NAMES["base_runtime_config"]

    assert calls == 1
    assert result["valid"] is True
    assert len(copied.read_bytes()) == authority.DERIVED_OUTPUT_LENGTH
    assert sha256_file(copied) == OUTPUT_SHA256
    assert bundle.verify_bundle(fixture["output"])["valid"] is True


def test_post_verification_locator_replacement_cannot_change_bundle_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    real_verify = authority.verify_derived_runtime_config_snapshot

    def replace_after_verify(**arguments):
        verified = real_verify(**arguments)
        path = Path(verified["snapshot_path"])
        path.unlink()
        path.write_bytes(b"foreign-after-verification\n")
        return verified

    monkeypatch.setattr(
        authority,
        "verify_derived_runtime_config_snapshot",
        replace_after_verify,
    )
    assert _create(fixture)["valid"] is True
    copied = fixture["output"] / bundle.BUNDLE_NAMES["base_runtime_config"]
    assert sha256_file(copied) == OUTPUT_SHA256
    assert copied.read_bytes() != fixture["derived_path"].read_bytes()


@pytest.mark.parametrize(
    "selection",
    [None, "foreign", True, [authority.TRACKED_DERIVED_AUTHORITY],
     [authority.TRACKED_DERIVED_AUTHORITY] * 2],
)
def test_missing_foreign_ambiguous_or_duplicate_selection_fails_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selection: object,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["kwargs"]["base_runtime_config_authority"] = selection
    staging_calls = 0
    real_mkdtemp = bundle.tempfile.mkdtemp

    def counted_mkdtemp(*arguments, **keywords):
        nonlocal staging_calls
        staging_calls += 1
        return real_mkdtemp(*arguments, **keywords)

    monkeypatch.setattr(bundle.tempfile, "mkdtemp", counted_mkdtemp)
    with pytest.raises(
        bundle.BundleError, match="runtime_config_authority_selection_invalid"
    ):
        _create(fixture)
    assert staging_calls == 0
    assert not fixture["output"].exists()


@pytest.mark.parametrize(
    "mutation",
    ["schema", "source", "contract", "input", "inventory", "output",
     "destination"],
)
def test_coherent_derivation_receipt_drift_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_receipt(fixture, mutation)
    staging_calls = 0

    def reject_staging(*_arguments, **_keywords):
        nonlocal staging_calls
        staging_calls += 1
        raise AssertionError("staging must not begin")

    monkeypatch.setattr(bundle.tempfile, "mkdtemp", reject_staging)
    with pytest.raises(bundle.BundleError):
        _create(fixture)
    assert staging_calls == 0
    assert not fixture["output"].exists()


@pytest.mark.parametrize("mutation", ["bytes", "inode", "symlink"])
def test_derived_locator_drift_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    fixture = _fixture(tmp_path)
    path = fixture["derived_path"]
    payload = path.read_bytes()
    if mutation == "bytes":
        path.write_bytes(b"mutated\n")
    else:
        replacement = path.with_name("replacement.conf")
        replacement.write_bytes(payload)
        path.unlink()
        if mutation == "inode":
            replacement.rename(path)
        else:
            path.symlink_to(replacement)
    staging_calls = 0

    def reject_staging(*_arguments, **_keywords):
        nonlocal staging_calls
        staging_calls += 1
        raise AssertionError("staging must not begin")

    monkeypatch.setattr(bundle.tempfile, "mkdtemp", reject_staging)
    with pytest.raises(bundle.BundleError):
        _create(fixture)
    assert staging_calls == 0


@pytest.mark.parametrize(
    "receipt_hash",
    ["0" * 64,
     "8b20b393839886bfe9d5906dd198a6f56eeaadcf7d220b5f1d83d044dd7ea449",
     "a4820b7f1cffef45f366517a40bd96a5be19cef61d30fc3c34b2df0304fdbfae"],
)
def test_foreign_stale_or_observed_hash_is_not_authority(
    tmp_path: Path, receipt_hash: str,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["kwargs"]["base_runtime_config_receipt_sha256"] = receipt_hash
    with pytest.raises(bundle.BundleError, match="derivation_receipt_hash_mismatch"):
        _create(fixture)
    assert not fixture["output"].exists()


def test_raw_template_and_caller_summary_cannot_bypass_authority(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    template = fixture["root"] / TEMPLATE_PATH
    fixture["kwargs"].update({
        "base_runtime_config_receipt": template,
        "base_runtime_config_receipt_sha256": sha256_file(template),
    })
    with pytest.raises(
        bundle.BundleError, match="derivation_receipt_location_invalid"
    ):
        _create(fixture)
    parameters = inspect.signature(bundle.create_bundle).parameters
    assert "base_runtime_config_bytes" not in parameters
    assert "base_runtime_config_verified" not in parameters
    assert "allow_runtime_config_fallback" not in parameters


def test_explicit_legacy_tracked_snapshot_remains_separate(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    legacy_root = tmp_path / "legacy-snapshot"
    legacy_root.mkdir()
    staged = stage_tracked_snapshot(
        worktree=fixture["root"],
        source_path=fixture["legacy_source"],
        expected_sha256=sha256_file(fixture["legacy_source"]),
        external_run_root=legacy_root,
        artifact_label="legacy-base-runtime-config",
    )
    fixture["kwargs"].update({
        "base_runtime_config_authority": (
            authority.LEGACY_TRACKED_SNAPSHOT_AUTHORITY
        ),
        "base_runtime_config_contract_relative_path": None,
        "base_runtime_config_receipt": Path(staged["receipt_path"]),
        "base_runtime_config_receipt_sha256": staged["receipt_sha256"],
    })
    assert _create(fixture)["valid"] is True
    copied = fixture["output"] / bundle.BUNDLE_NAMES["base_runtime_config"]
    assert copied.read_bytes() == fixture["legacy_source"].read_bytes()


def test_legacy_and_derived_authority_arguments_cannot_be_mixed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["kwargs"]["base_runtime_config_authority"] = (
        authority.LEGACY_TRACKED_SNAPSHOT_AUTHORITY
    )
    with pytest.raises(
        bundle.BundleError,
        match="runtime_config_authority_arguments_ambiguous",
    ):
        _create(fixture)
    assert not fixture["output"].exists()
