"""Self-contained evidence closure for the joined DPS + Stonecore campaign.

The ignored campaign directories are deliberately disposable.  This module
therefore copies the *small* immutable identity and receipt documents into the
outer DVC raw object and writes a Git-trackable bootstrap for that outer
object.  Verification of a hydrated outer object never consults an ambient
campaign path.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .live_validation_session import canonical_sha256
from .phase8_calibration_adapter import DEFAULT_SCENARIOS
from .phase8_evidence_identity import validate_manifest as validate_phase8_manifest
from .phase9_evidence_identity import validate_manifest as validate_phase9_manifest


CLOSURE_SCHEMA = "joined_16_dps_14_stonecore_evidence_closure_v1"
BOOTSTRAP_SCHEMA = "joined_campaign_dvc_bootstrap_v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PHASE9_TERMINAL_CONDITIONS = (
    "strict_route_clear",
    "server_attributed_machine_failure",
    "semantic_progress_plateau_watchdog",
    "no_progress_watchdog",
    "repeated_decision_watchdog",
    "death_loop_watchdog",
    "controller_interruption",
)


class JoinedEvidenceError(ValueError):
    """The joined campaign is incomplete, inconsistent, or tampered."""


def _json_object(document: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(document)
    except json.JSONDecodeError as exc:
        raise JoinedEvidenceError(f"malformed JSON document: {label}") from exc
    if not isinstance(payload, dict):
        raise JoinedEvidenceError(f"expected JSON object: {label}")
    return payload


def _document_record(path: Path, repository: Path) -> dict[str, Any]:
    path = path.resolve()
    try:
        relative = path.relative_to(repository.resolve())
    except ValueError as exc:
        raise JoinedEvidenceError(f"evidence path is outside repository: {path}") from exc
    document = path.read_text(encoding="utf-8")
    encoded = document.encode("utf-8")
    return {
        "path": relative.as_posix(),
        "size": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "document": document,
    }


def _embedded_document(record: Mapping[str, Any], label: str) -> dict[str, Any]:
    document = record.get("document")
    path = str(record.get("path") or "")
    if (
        not isinstance(document, str)
        or not path
        or Path(path).is_absolute()
        or ".." in Path(path).parts
        or int(record.get("size") or -1) != len(document.encode("utf-8"))
        or hashlib.sha256(document.encode("utf-8")).hexdigest()
        != str(record.get("sha256") or "")
    ):
        raise JoinedEvidenceError(f"embedded document identity mismatch: {label}")
    return _json_object(document, label)


def _self_hash(payload: Mapping[str, Any], key: str) -> str:
    identity = dict(payload)
    stored = str(identity.pop(key, ""))
    if not SHA256_RE.fullmatch(stored) or canonical_sha256(identity) != stored:
        raise JoinedEvidenceError(f"self identity mismatch: {key}")
    return stored


def _resolve(repository: Path, value: str) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (repository / path).resolve()
    try:
        resolved.relative_to(repository.resolve())
    except ValueError as exc:
        raise JoinedEvidenceError(f"evidence reference is outside repository: {value}") from exc
    return resolved


def _required_document(path: Path, repository: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise JoinedEvidenceError(f"missing {label}: {path}")
    return _document_record(path, repository)


def _leaf_bundle(
    repository: Path,
    lane: str,
    attempt_dir: Path,
    started_name: str,
    result_name: str,
) -> dict[str, Any]:
    started = _required_document(attempt_dir / started_name, repository, "start receipt")
    result = _required_document(attempt_dir / result_name, repository, "result receipt")
    result_payload = _json_object(result["document"], "leaf result receipt")
    row = result_payload.get("result") or {}
    if not isinstance(row, Mapping):
        raise JoinedEvidenceError("leaf result receipt has no result object")
    attempt_id = str(row.get("attempt_id") or "")
    if not attempt_id:
        raise JoinedEvidenceError("leaf result receipt has no attempt id")
    accepted = _dps_accepted(row) if lane == "dps" else _phase9_accepted(row)
    leaf: dict[str, Any] = {
        "lane": lane,
        "attempt_id": attempt_id,
        "attempt_directory": str(attempt_dir.resolve().relative_to(repository.resolve())),
        "started_receipt": started,
        "result_receipt": result,
        "classification": str(row.get("classification") or ""),
        "selected_for_gate": accepted,
    }
    batch = attempt_dir / "batch"
    receipt_paths = {
        "final_manifest": batch / "retained/final_manifest.json",
        "publication_receipt": batch / "retained/publication_receipt.json",
        "reconstruction_receipt": batch / "retained/reconstruction_receipt.json",
    }
    if accepted:
        for name, path in receipt_paths.items():
            leaf[name] = _required_document(path, repository, f"accepted leaf {name}")
        publication_payload = _json_object(
            leaf["publication_receipt"]["document"], "leaf publication receipt"
        )
        pointers = publication_payload.get("pointers") or []
        if not isinstance(pointers, list) or len(pointers) != 2:
            raise JoinedEvidenceError(f"leaf DVC pointer set is incomplete: {attempt_id}")
        leaf["dvc_pointers"] = pointers
        leaf["publication_state"] = "remote_reconstructed_and_evicted"
    else:
        # A crash can occur before the child creates a batch.  The immutable
        # start/result receipts still consume and classify that ordinal.  If
        # the child produced a bounded report/log, embed their exact bytes in
        # the outer DVC object rather than inventing a leaf publication.
        failure_evidence: list[dict[str, Any]] = []
        for path in (
            attempt_dir / "report.json",
            attempt_dir / "runner.log",
            attempt_dir / "phase9_runner.log",
        ):
            if path.is_file():
                if path.stat().st_size > 8 * 1024 * 1024:
                    raise JoinedEvidenceError(
                        f"failure evidence exceeds bounded closure size: {attempt_id}"
                    )
                failure_evidence.append(_document_record(path, repository))
        leaf["failure_evidence"] = failure_evidence
        present_receipts = {
            name: _document_record(path, repository)
            for name, path in receipt_paths.items()
            if path.is_file()
        }
        if present_receipts:
            leaf["failure_batch_documents"] = present_receipts
            leaf["dvc_pointers"] = []
            leaf["publication_state"] = "failure_batch_documents_not_gate_bearing"
        else:
            leaf["dvc_pointers"] = []
            leaf["publication_state"] = "not_created_before_failure"
    return leaf


def _dps_try_directories(
    output_root: Path, plan: Mapping[str, Any], ledger: Sequence[Mapping[str, Any]]
) -> list[Path]:
    by_id: dict[str, Path] = {}
    for row in ledger:
        attempt_id = str(row.get("attempt_id") or "")
        relative = str(row.get("attempt_directory") or "")
        if not attempt_id or not relative:
            raise JoinedEvidenceError("DPS ledger row lacks its physical directory")
        path = (output_root / relative).resolve()
        if attempt_id in by_id or not path.is_dir():
            raise JoinedEvidenceError(f"DPS physical directory is missing or duplicate: {attempt_id}")
        by_id[attempt_id] = path

    materialized = {
        path.parent.resolve()
        for path in output_root.rglob("physical_try_started.json")
        if "joined_campaign_promotion_batch" not in path.parts
    }
    if materialized != set(by_id.values()):
        raise JoinedEvidenceError("DPS ledger does not include every materialized try")
    if len(plan.get("attempts") or []) != 16:
        raise JoinedEvidenceError("DPS plan is not the exact 16-spec plan")
    return [by_id[str(row["attempt_id"])] for row in ledger]


def _phase9_try_directories(
    repository: Path, plan: Mapping[str, Any], ledger: Sequence[Mapping[str, Any]]
) -> list[Path]:
    by_id: dict[str, Path] = {}
    for row in ledger:
        attempt_id = str(row.get("attempt_id") or "")
        relative = str(row.get("output_dir") or "")
        if not attempt_id or not relative:
            raise JoinedEvidenceError("Phase 9 ledger row lacks its physical directory")
        path = _resolve(repository, relative)
        if attempt_id in by_id or not path.is_dir():
            raise JoinedEvidenceError(
                f"Phase 9 physical directory is missing or duplicate: {attempt_id}"
            )
        by_id[attempt_id] = path

    expected_candidates: set[Path] = set()
    for logical in plan.get("attempts") or []:
        if not isinstance(logical, Mapping):
            continue
        base = _resolve(repository, str(logical.get("output_dir") or ""))
        if base.is_dir():
            expected_candidates.add(base.resolve())
        expected_candidates.update(
            path.resolve()
            for path in base.parent.glob(f"{base.name}-retry-*")
            if path.is_dir()
        )
    materialized = {
        path.parent.resolve()
        for directory in expected_candidates
        for path in [directory / "phase9_physical_try_started.json"]
        if path.is_file()
    }
    if materialized != set(by_id.values()):
        raise JoinedEvidenceError("Phase 9 ledger does not include every materialized try")
    return [by_id[str(row["attempt_id"])] for row in ledger]


def build_joined_campaign_closure(
    repository: Path,
    phase9_state_path: Path,
    joined_verification: Mapping[str, Any],
) -> dict[str, Any]:
    """Capture all small documents needed to reconstruct the joined claim."""
    repository = repository.resolve()
    phase9_state_path = phase9_state_path.resolve()
    phase9_state = _json_object(
        phase9_state_path.read_text(encoding="utf-8"), "Phase 9 state"
    )
    phase9_plan_path = _resolve(repository, str(phase9_state.get("run_plan") or ""))
    phase9_plan = _json_object(
        phase9_plan_path.read_text(encoding="utf-8"), "Phase 9 plan"
    )
    dps_state_path = _resolve(
        repository, str(phase9_plan.get("dps_acceptance_state_path") or "")
    )
    dps_root = dps_state_path.parent
    dps_state = _json_object(dps_state_path.read_text(encoding="utf-8"), "DPS state")
    dps_plan_path = dps_root / "campaign_plan.json"
    dps_plan = _json_object(dps_plan_path.read_text(encoding="utf-8"), "DPS plan")

    dps_config_path = _resolve(repository, str(dps_state.get("config_path") or ""))
    dps_config = _json_object(
        dps_config_path.read_text(encoding="utf-8"), "DPS acceptance config"
    )
    phase9_identity_path = _resolve(
        repository, str(phase9_plan.get("evidence_identity_manifest_path") or "")
    )
    phase9_identity = _json_object(
        phase9_identity_path.read_text(encoding="utf-8"), "Phase 9 identity"
    )
    matrix_path = _resolve(repository, str(phase9_plan.get("matrix_path") or ""))

    exact_documents: dict[str, dict[str, Any]] = {
        "dps_acceptance_config": _required_document(
            dps_config_path, repository, "DPS acceptance config"
        ),
        "dps_campaign_plan": _required_document(dps_plan_path, repository, "DPS plan"),
        "dps_campaign_state": _required_document(dps_state_path, repository, "DPS state"),
        "dps_evidence_identity": _required_document(
            dps_root / "evidence_identity_manifest.json", repository, "DPS identity"
        ),
        "phase9_run_plan": _required_document(
            phase9_plan_path, repository, "Phase 9 plan"
        ),
        "phase9_operator_state": _required_document(
            phase9_state_path, repository, "Phase 9 state"
        ),
        "joined_campaign_verification": _required_document(
            phase9_state_path.parent / "joined_campaign_verification.json",
            repository,
            "joined campaign verification",
        ),
        "phase9_evidence_identity": _required_document(
            phase9_identity_path, repository, "Phase 9 identity"
        ),
        "phase9_pairwise_matrix": _required_document(
            matrix_path, repository, "Phase 9 matrix"
        ),
    }
    optional = {
        "dps_acceptance_verification": dps_root / "acceptance_verification.json",
        "dps_append_ledger": dps_root / "physical_try_ledger.jsonl",
        "phase9_append_ledger": phase9_state_path.parent / "phase9_physical_try_ledger.jsonl",
    }
    for name, path in optional.items():
        if path.is_file():
            exact_documents[name] = _document_record(path, repository)
    for name in (
        "roster",
        "stonecore_pair_policy",
        "role_calibration_policy",
        "target_catalog",
        "reference_catalog",
    ):
        value = str(dps_config.get(name) or "")
        if value:
            exact_documents[f"phase8_config_{name}"] = _required_document(
                _resolve(repository, value), repository, name
            )
    exact_documents["phase8_calibration_scenarios"] = _required_document(
        DEFAULT_SCENARIOS, repository, "Phase 8 calibration scenarios"
    )
    route_path = str(
        (phase9_identity.get("route_summary") or {}).get("route_manifest_path") or ""
    )
    if route_path:
        exact_documents["phase9_route_manifest"] = _required_document(
            _resolve(repository, route_path), repository, "Phase 9 route manifest"
        )

    dps_ledger = [
        dict(row)
        for row in dps_state.get("physical_try_ledger") or []
        if isinstance(row, Mapping)
    ]
    phase9_ledger = [
        dict(row)
        for row in phase9_state.get("physical_try_ledger") or []
        if isinstance(row, Mapping)
    ]
    dps_dirs = _dps_try_directories(dps_root, dps_plan, dps_ledger)
    phase9_dirs = _phase9_try_directories(repository, phase9_plan, phase9_ledger)
    leaves = [
        _leaf_bundle(
            repository,
            "dps",
            path,
            "physical_try_started.json",
            "physical_try_result.json",
        )
        for path in dps_dirs
    ] + [
        _leaf_bundle(
            repository,
            "phase9",
            path,
            "phase9_physical_try_started.json",
            "phase9_physical_try_result.json",
        )
        for path in phase9_dirs
    ]
    closure = {
        "schema": CLOSURE_SCHEMA,
        "evidence_scope": {
            "dps_unique_spec_qualifications": 16,
            "dps_max_physical_tries_per_spec": 2,
            "stonecore_combinations": 7,
            "stonecore_successes_per_combination": 2,
            "stonecore_player_like_successes": 14,
        },
        "exact_documents": exact_documents,
        "physical_ledgers": {
            "dps": dps_ledger,
            "phase9": phase9_ledger,
        },
        "materialized_try_ids": {
            "dps": [str(row.get("attempt_id") or "") for row in dps_ledger],
            "phase9": [str(row.get("attempt_id") or "") for row in phase9_ledger],
        },
        "leaf_batches": leaves,
        "joined_verification": dict(joined_verification),
    }
    if len(json.dumps(closure, sort_keys=True).encode("utf-8")) > 64 * 1024 * 1024:
        raise JoinedEvidenceError("joined closure exceeds the bounded 64 MiB payload")
    closure["closure_sha256"] = canonical_sha256(closure)
    verification = verify_joined_campaign_closure(closure)
    if verification.get("passed") is not True:
        raise JoinedEvidenceError(
            "joined closure failed construction verification: "
            + ",".join(verification.get("failure_reasons") or [])
        )
    return closure


def _pointer_rows_valid(rows: Any) -> bool:
    if not isinstance(rows, list) or len(rows) != 2:
        return False
    names: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            return False
        path = Path(str(row.get("path") or ""))
        name = path.name
        document = str(row.get("pointer_document") or "")
        if name not in {"raw.dvc", "compact.dvc"} or name in names or not document:
            return False
        names.add(name)
        if hashlib.sha256(document.encode("utf-8")).hexdigest() != row.get(
            "pointer_sha256"
        ):
            return False
        try:
            pointer = yaml.safe_load(document)
        except yaml.YAMLError:
            return False
        outs = pointer.get("outs") if isinstance(pointer, dict) else None
        if not isinstance(outs, list) or len(outs) != 1:
            return False
        output = outs[0]
        if not isinstance(output, Mapping) or Path(str(output.get("path") or "")).name != name.removesuffix(".dvc"):
            return False
        if str(output.get("md5") or "") != str(row.get("dvc_md5") or ""):
            return False
    return names == {"raw.dvc", "compact.dvc"}


def _verify_leaf_domain(
    *,
    lane: str,
    physical: Mapping[str, Any],
    result: Mapping[str, Any],
    reconstruction: Mapping[str, Any],
    domain_context: Mapping[str, Any],
) -> None:
    remote = reconstruction.get("domain_verification") or {}
    if lane == "dps":
        domain_identity = {
            "schema": "cata_raid_dps_remote_calibration_reconstruction_v1",
            "attempt": dict(physical),
            "policy_sha256": domain_context.get("policy_sha256"),
            "targets_sha256": domain_context.get("targets_sha256"),
            "references_sha256": domain_context.get("references_sha256"),
            "scenarios_sha256": domain_context.get("scenarios_sha256"),
            "evidence_identity_manifest_sha256": domain_context.get(
                "identity_manifest_sha256"
            ),
            "fixture_provenance": {
                "evidence_class": "non_certifying_calibration_fixture",
                "excluded_from_training_corpus": True,
                "runtime_mode": "calibration_fixture",
                "non_certifying_assistance": True,
            },
        }
        evaluation = remote.get("evaluation") or {}
        requested = remote.get("requested_calibration") or {}
        remote_identity = remote.get("role_calibration_identity") or {}
        session = remote.get("session_identity") or {}
        valid_content = bool(
            remote.get("schema")
            == "cata_raid_dps_remote_calibration_verification_v1"
            and remote.get("verified") is True
            and remote.get("attempt_id") == physical.get("attempt_id")
            and remote.get("source_transport_verified") is True
            and remote.get("provenance_verified") is True
            and remote.get("evidence_build_identity_compatible") is True
            and remote.get("evidence_identity_manifest_sha256")
            == domain_context.get("identity_manifest_sha256")
            and requested.get("target_spec") == physical.get("runtime_join_key")
            and requested.get("mode") == physical.get("mode")
            and int(requested.get("seed") or 0) == int(physical.get("seed") or 0)
            and remote_identity.get("spec_target_id")
            == physical.get("spec_target_id")
            and session.get("cohort_id") == physical.get("cohort_id")
            and int(session.get("attempt_index") or 0)
            == int(physical.get("attempt_index") or 0)
            and evaluation.get("passed") is True
            and evaluation.get("hard_floor_passed") is True
            and evaluation.get("optimization_target_met") is True
            and float(evaluation.get("reference_ratio") or 0.0) >= 0.85
            and not evaluation.get("failure_reasons")
            and result.get("remote_source_report_sha256")
            == remote.get("source_report_sha256")
            and result.get("remote_evaluation_sha256")
            == remote.get("evaluation_sha256")
            and result.get("remote_compact_binding_sha256")
            == remote.get("compact_binding_sha256")
        )
    elif lane == "phase9":
        domain_identity = {
            "schema": "phase9_remote_full_clear_reconstruction_v1",
            "attempt_id": physical.get("attempt_id"),
            "composition_sha256": physical.get("composition_sha256"),
            "party_sha256": physical.get("party_sha256"),
            "success_ordinal": physical.get("success_ordinal"),
            "physical_try_ordinal": physical.get("physical_try_ordinal"),
            "physical_identity_sha256": physical.get("physical_identity_sha256"),
            "plan_sha256": domain_context.get("plan_sha256"),
            "identity_manifest_sha256": domain_context.get(
                "identity_manifest_sha256"
            ),
        }
        valid_content = bool(
            remote.get("schema") == "phase9_remote_full_clear_verification_v1"
            and remote.get("verified") is True
            and remote.get("attempt_id") == physical.get("attempt_id")
            and remote.get("execution_policy") == "run_to_completion"
            and remote.get("overall_wall_clock_timeout_sec") is None
            and remote.get("source_transport_verified") is True
            and remote.get("runtime_identity_valid") is True
            and remote.get("attempt_identity_valid") is True
            and remote.get("exact_party_valid") is True
            and remote.get("server_route_start_provisioned") is True
            and remote.get("cleanup_complete") is True
            and (remote.get("heroic_admission") or {}).get("verified") is True
            and result.get("remote_source_report_sha256")
            == remote.get("source_report_sha256")
            and result.get("remote_compact_binding_sha256")
            == remote.get("compact_binding_sha256")
            and result.get("remote_acceptance_verification_sha256")
            == remote.get("acceptance_verification_sha256")
        )
    else:
        raise JoinedEvidenceError("unknown joined leaf lane")
    if (
        reconstruction.get("domain_verification_id")
        != canonical_sha256(domain_identity)
        or not valid_content
    ):
        raise JoinedEvidenceError(
            f"accepted leaf domain reconstruction is invalid: {physical.get('attempt_id')}"
        )


def _verify_leaf(
    leaf: Mapping[str, Any],
    expected_result: Mapping[str, Any],
    domain_context: Mapping[str, Any],
) -> None:
    attempt_id = str(leaf.get("attempt_id") or "")
    started = _embedded_document(leaf.get("started_receipt") or {}, f"{attempt_id}:start")
    result_receipt = _embedded_document(
        leaf.get("result_receipt") or {}, f"{attempt_id}:result"
    )
    if leaf.get("classification") != expected_result.get("classification"):
        raise JoinedEvidenceError(f"leaf classification is invalid: {attempt_id}")
    result = result_receipt.get("result") or {}
    comparable_expected = dict(expected_result)
    if isinstance(result, Mapping):
        for derived in ("started_receipt_sha256", "result_receipt_sha256"):
            if derived not in result:
                comparable_expected.pop(derived, None)
    if not isinstance(result, Mapping) or dict(result) != comparable_expected:
        raise JoinedEvidenceError(f"leaf result does not match physical ledger: {attempt_id}")
    started_hash = _self_hash(started, "started_receipt_sha256")
    result_hash = _self_hash(result_receipt, "result_receipt_sha256")
    physical = started.get("physical_attempt") or {}
    if not isinstance(physical, Mapping):
        raise JoinedEvidenceError(f"leaf start lacks physical identity: {attempt_id}")
    if (
        attempt_id != str(result.get("attempt_id") or "")
        or attempt_id != str(physical.get("attempt_id") or "")
        or result_receipt.get("started_receipt_sha256") != started_hash
        or result_receipt.get("physical_identity_sha256")
        != physical.get("physical_identity_sha256")
        or result.get("result_receipt_sha256") not in {None, "", result_hash}
    ):
        raise JoinedEvidenceError(f"leaf receipt chain is invalid: {attempt_id}")
    if result.get("started_receipt_sha256") not in {None, "", started_hash}:
        raise JoinedEvidenceError(f"leaf result start binding is invalid: {attempt_id}")
    if expected_result.get("result_receipt_sha256") not in {None, "", result_hash}:
        raise JoinedEvidenceError(f"leaf result receipt binding is invalid: {attempt_id}")

    lane = str(leaf.get("lane") or "")
    accepted = _dps_accepted(expected_result) if lane == "dps" else _phase9_accepted(expected_result)
    if leaf.get("selected_for_gate") is not accepted:
        raise JoinedEvidenceError(f"leaf gate selection is invalid: {attempt_id}")
    has_publication = all(
        name in leaf
        for name in (
            "final_manifest",
            "publication_receipt",
            "reconstruction_receipt",
        )
    )
    if accepted and not has_publication:
        raise JoinedEvidenceError(f"accepted leaf lacks remote publication: {attempt_id}")
    if not accepted:
        if leaf.get("publication_state") not in {
            "not_created_before_failure",
            "failure_batch_documents_not_gate_bearing",
            "partial_failure_batch_not_gate_bearing",
        } or leaf.get("dvc_pointers") != []:
            raise JoinedEvidenceError(f"failed leaf publication state is invalid: {attempt_id}")
        evidence = leaf.get("failure_evidence") or []
        if not isinstance(evidence, list):
            raise JoinedEvidenceError(f"failed leaf evidence is malformed: {attempt_id}")
        for index, record in enumerate(evidence):
            _embedded_text_document(record, f"{attempt_id}:failure:{index}")
        partial = leaf.get("failure_batch_documents") or {}
        if not isinstance(partial, Mapping):
            raise JoinedEvidenceError(
                f"failed leaf partial batch evidence is malformed: {attempt_id}"
            )
        for name, record in partial.items():
            payload = _embedded_document(
                record, f"{attempt_id}:partial-failure-batch:{name}"
            )
            hash_key = {
                "final_manifest": "identity_sha256",
                "publication_receipt": "receipt_sha256",
                "reconstruction_receipt": "receipt_sha256",
            }.get(str(name))
            if hash_key is None:
                raise JoinedEvidenceError(
                    f"failed leaf has an unknown partial receipt: {attempt_id}"
                )
            _self_hash(payload, hash_key)
        return

    manifest = _embedded_document(
        leaf.get("final_manifest") or {}, f"{attempt_id}:manifest"
    )
    publication = _embedded_document(
        leaf.get("publication_receipt") or {}, f"{attempt_id}:publication"
    )
    reconstruction = _embedded_document(
        leaf.get("reconstruction_receipt") or {}, f"{attempt_id}:reconstruction"
    )
    manifest_hash = _self_hash(manifest, "identity_sha256")
    publication_hash = _self_hash(publication, "receipt_sha256")
    reconstruction_hash = _self_hash(reconstruction, "receipt_sha256")
    leaf_batch_path = Path(str(leaf.get("attempt_directory") or "")) / "batch"
    pointer_parents = {
        Path(str(row.get("path") or "")).parent
        for row in publication.get("pointers") or []
        if isinstance(row, Mapping)
    }
    if (
        not str(manifest.get("batch_id") or "")
        or publication.get("batch_id") != manifest.get("batch_id")
        or reconstruction.get("batch_id") != manifest.get("batch_id")
        or publication.get("batch_identity_sha256") != manifest_hash
        or publication.get("raw_bundle_sha256")
        != (manifest.get("raw") or {}).get("bundle_sha256")
        or publication.get("compact_bundle_sha256")
        != (manifest.get("compact") or {}).get("bundle_sha256")
        or reconstruction.get("batch_identity_sha256") != manifest_hash
        or reconstruction.get("publication_receipt_sha256") != publication_hash
        or publication.get("remote_verified") is not True
        or reconstruction.get("remote_reconstructed") is not True
        or reconstruction.get("targeted_eviction_complete") is not True
        or not _pointer_rows_valid(publication.get("pointers"))
        or publication.get("pointers") != leaf.get("dvc_pointers")
        or pointer_parents != {leaf_batch_path}
        or leaf.get("publication_state") != "remote_reconstructed_and_evicted"
    ):
        raise JoinedEvidenceError(f"leaf publication chain is invalid: {attempt_id}")
    if accepted:
        _verify_leaf_domain(
            lane=lane,
            physical=physical,
            result=expected_result,
            reconstruction=reconstruction,
            domain_context=domain_context,
        )
    if result.get("receipt_sha256") not in {None, "", publication_hash}:
        raise JoinedEvidenceError(f"leaf result publication binding is invalid: {attempt_id}")
    if result.get("reconstruction_receipt_sha256") not in {
        None,
        "",
        reconstruction_hash,
    }:
        raise JoinedEvidenceError(f"leaf result reconstruction binding is invalid: {attempt_id}")


def _dps_accepted(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("classification") == "accepted"
        and row.get("accepted") is True
        and row.get("child_returncode_observed") is True
        and row.get("returncode") == 0
        and row.get("report_returncode") == 0
        and row.get("timed_out") is False
        and row.get("calibration_acceptance_passed") is True
        and row.get("acceptable_final_evidence") is True
        and row.get("all_passed") is True
        and row.get("hard_floor_passed") is True
        and row.get("optimization_target_met") is True
        and float(row.get("reference_ratio") or 0.0) >= 0.85
        and row.get("remote_transport_verified") is True
        and row.get("remote_provenance_verified") is True
        and row.get("remote_evidence_class") == "non_certifying_calibration_fixture"
        and row.get("remote_excluded_from_training_corpus") is True
        and row.get("remote_runtime_mode") == "calibration_fixture"
        and row.get("remote_non_certifying_assistance") is True
        and row.get("published") is True
        and row.get("remote_reconstruction_verified") is True
        and row.get("targeted_eviction_complete") is True
        and row.get("passed") is True
    )


def _phase9_accepted(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("classification") == "accepted"
        and row.get("passed") is True
        and row.get("child_returncode_observed") is True
        and row.get("returncode") == 0
        and row.get("transport_classification") == "child_exited"
        and row.get("execution_policy") == "run_to_completion"
        and row.get("overall_wall_clock_timeout_sec") is None
        and row.get("outer_timed_out") is False
        and row.get("controller_interrupted") is False
        and row.get("process_group_gone") is True
        and row.get("report_returncode") == 0
        and row.get("timed_out") is False
        and row.get("remote_verified") is True
        and row.get("remote_reconstruction_verified") is True
        and row.get("remote_domain_verified") is True
        and row.get("remote_transport_verified") is True
        and row.get("targeted_eviction_complete") is True
        and row.get("exact_party_verified") is True
        and row.get("heroic_admission_verified") is True
        and row.get("server_route_start_provisioned") is True
        and row.get("identity_matches") is True
        and row.get("cleanup_complete") is True
    )


def _verify_jsonl_chain(
    record: Mapping[str, Any], expected_summary: Mapping[str, Any]
) -> list[dict[str, Any]]:
    document = record.get("document")
    if not isinstance(document, str):
        raise JoinedEvidenceError("append ledger document is missing")
    if document and not document.endswith("\n"):
        raise JoinedEvidenceError("append ledger has an unterminated tail")
    # This validates exact bytes/path before interpreting the JSONL rows.
    _embedded_text_document(record, "append ledger")
    previous = ""
    rows: list[dict[str, Any]] = []
    for sequence, line in enumerate(document.splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JoinedEvidenceError("append ledger contains malformed JSON") from exc
        if not isinstance(row, dict):
            raise JoinedEvidenceError("append ledger row is not an object")
        identity = dict(row)
        stored = str(identity.pop("event_sha256", ""))
        if (
            int(row.get("sequence") or 0) != sequence
            or str(row.get("previous_event_sha256") or "") != previous
            or canonical_sha256(identity) != stored
        ):
            raise JoinedEvidenceError("append ledger chain is invalid")
        previous = stored
        rows.append(row)
    if expected_summary and (
        int(expected_summary.get("event_count") or 0) != len(rows)
        or str(expected_summary.get("tail_sha256") or "") != previous
        or str(expected_summary.get("file_sha256") or "") != record.get("sha256")
    ):
        raise JoinedEvidenceError("append ledger summary binding is invalid")
    return rows


def _phase9_expected_append_events(
    plan: Mapping[str, Any],
    identity: Mapping[str, Any],
    ledger: Sequence[Mapping[str, Any]],
    leaves: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    plan_sha = str(plan.get("plan_sha256") or "")
    identity_sha = str(identity.get("manifest_sha256") or "")
    expected: dict[str, dict[str, Any]] = {
        f"campaign:{plan_sha}": {
            "event_id": f"campaign:{plan_sha}",
            "event": "campaign_started",
            "run_plan_sha256": plan_sha,
            "identity_manifest_sha256": identity_sha,
            "logical_success_slot_count": 14,
        }
    }
    for result in ledger:
        attempt_id = str(result.get("attempt_id") or "")
        leaf = leaves[attempt_id]
        started = _embedded_document(
            leaf.get("started_receipt") or {}, f"{attempt_id}:append-start"
        )
        result_receipt = _embedded_document(
            leaf.get("result_receipt") or {}, f"{attempt_id}:append-result"
        )
        physical_sha = str(result.get("physical_identity_sha256") or "")
        common = {
            "run_plan_sha256": plan_sha,
            "identity_manifest_sha256": identity_sha,
            "logical_attempt_id": result.get("logical_attempt_id"),
            "attempt_id": attempt_id,
            "serial_index": int(result.get("serial_index") or 0),
            "composition_id": result.get("composition_id"),
            "success_ordinal": int(result.get("success_ordinal") or 0),
            "physical_try_ordinal": int(result.get("physical_try_ordinal") or 0),
            "physical_identity_sha256": physical_sha,
            "started_receipt_sha256": started.get("started_receipt_sha256"),
        }
        start_id = f"started:{physical_sha}"
        result_id = f"result:{physical_sha}"
        expected[start_id] = {
            "event_id": start_id,
            "event": "physical_try_started",
            **common,
        }
        expected[result_id] = {
            "event_id": result_id,
            "event": "physical_try_result",
            **common,
            "result_receipt_sha256": result_receipt.get(
                "result_receipt_sha256"
            ),
            "classification": result.get("classification"),
            "accepted": _phase9_accepted(result),
            "child_returncode_observed": result.get(
                "child_returncode_observed"
            )
            is True,
            "child_returncode": result.get("returncode"),
            "timed_out": result.get("timed_out"),
            "publication_receipt_sha256": result.get("receipt_sha256"),
            "reconstruction_receipt_sha256": result.get(
                "reconstruction_receipt_sha256"
            ),
        }
    return expected


def _verify_phase9_append_event_set(
    events: Sequence[Mapping[str, Any]],
    expected: Mapping[str, Mapping[str, Any]],
) -> None:
    observed: dict[str, dict[str, Any]] = {}
    positions: dict[str, int] = {}
    for event in events:
        event_id = str(event.get("event_id") or "")
        comparable = {
            key: value
            for key, value in event.items()
            if key
            not in {
                "schema",
                "sequence",
                "previous_event_sha256",
                "event_sha256",
            }
        }
        if not event_id or event_id in observed:
            raise JoinedEvidenceError("Phase 9 append ledger has duplicate event ids")
        observed[event_id] = comparable
        positions[event_id] = int(event.get("sequence") or 0)
        if expected.get(event_id) != comparable:
            raise JoinedEvidenceError(
                f"Phase 9 append event differs from immutable receipt: {event_id}"
            )
    if set(observed) != set(expected):
        raise JoinedEvidenceError(
            "Phase 9 append ledger event set differs from every materialized try"
        )
    for event_id, position in positions.items():
        if event_id.startswith("result:"):
            start_id = "started:" + event_id.removeprefix("result:")
            if start_id not in positions or positions[start_id] >= position:
                raise JoinedEvidenceError("Phase 9 result event precedes start event")


def _embedded_text_document(record: Mapping[str, Any], label: str) -> str:
    document = record.get("document")
    path = str(record.get("path") or "")
    if not isinstance(document, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise JoinedEvidenceError(f"embedded text document is malformed: {label}")
    encoded = document.encode("utf-8")
    if int(record.get("size") or -1) != len(encoded) or hashlib.sha256(encoded).hexdigest() != record.get("sha256"):
        raise JoinedEvidenceError(f"embedded text document identity mismatch: {label}")
    return document


def verify_joined_campaign_closure(closure: Mapping[str, Any]) -> dict[str, Any]:
    """Pure verification: only ``closure`` is consulted."""
    reasons: list[str] = []
    verified_dps = 0
    verified_phase9 = 0
    physical_dps = 0
    physical_phase9 = 0
    try:
        if closure.get("schema") != CLOSURE_SCHEMA:
            raise JoinedEvidenceError("joined closure schema mismatch")
        closure_hash = _self_hash(closure, "closure_sha256")
        documents = closure.get("exact_documents") or {}
        required = {
            "dps_acceptance_config",
            "dps_campaign_plan",
            "dps_campaign_state",
            "dps_evidence_identity",
            "phase8_config_role_calibration_policy",
            "phase8_config_target_catalog",
            "phase8_config_reference_catalog",
            "phase8_calibration_scenarios",
            "phase9_run_plan",
            "phase9_operator_state",
            "joined_campaign_verification",
            "phase9_evidence_identity",
            "phase9_pairwise_matrix",
        }
        if not isinstance(documents, Mapping) or not required.issubset(documents):
            raise JoinedEvidenceError("joined exact document set is incomplete")
        parsed = {
            name: _embedded_document(documents[name], name)
            for name in required
        }
        for name, record in documents.items():
            if name in {"dps_append_ledger", "phase9_append_ledger"}:
                _embedded_text_document(record, name)
            elif name not in parsed:
                _embedded_document(record, name)
        dps_config = parsed["dps_acceptance_config"]
        dps_plan = parsed["dps_campaign_plan"]
        dps_state = parsed["dps_campaign_state"]
        phase9_plan = parsed["phase9_run_plan"]
        phase9_state = parsed["phase9_operator_state"]
        matrix = parsed["phase9_pairwise_matrix"]
        _self_hash(dps_plan, "plan_sha256")
        _self_hash(dps_state, "state_sha256")
        _self_hash(phase9_plan, "plan_sha256")
        _self_hash(phase9_state, "state_sha256")
        dps_identity = validate_phase8_manifest(parsed["dps_evidence_identity"])
        phase9_artifact_hashes = {
            "target_catalog_sha256": documents[
                "phase8_config_target_catalog"
            ]["sha256"],
            "pair_policy_sha256": documents[
                "phase8_config_stonecore_pair_policy"
            ]["sha256"],
            "pairwise_matrix_sha256": documents["phase9_pairwise_matrix"][
                "sha256"
            ],
            "route_manifest_sha256": documents["phase9_route_manifest"][
                "sha256"
            ],
        }
        phase9_identity = validate_phase9_manifest(
            parsed["phase9_evidence_identity"],
            artifact_hashes=phase9_artifact_hashes,
        )
        dps_build = dps_identity.get("build_identity") or {}
        phase9_build = phase9_identity.get("build_identity") or {}
        projection_fields = (
            "git_commit",
            "source_tree_clean",
            "worldserver_binary_sha256",
            "database_snapshot_sha256",
            "database_schema_sha256",
            "profile_content_hash",
        )
        dps_projection = {field: dps_build.get(field) for field in projection_fields}
        phase9_projection = {
            field: phase9_build.get(field) for field in projection_fields
        }
        if (
            dps_projection != phase9_projection
            or dps_projection.get("source_tree_clean") is not True
            or not SHA256_RE.fullmatch(
                str(dps_projection.get("worldserver_binary_sha256") or "")
            )
            or canonical_sha256(dps_projection)
            != str(
                (dps_identity.get("component_hashes") or {}).get(
                    "build_projection_sha256"
                )
                or ""
            )
            or canonical_sha256(phase9_projection)
            != str(
                (phase9_identity.get("component_hashes") or {}).get(
                    "build_projection_sha256"
                )
                or ""
            )
        ):
            raise JoinedEvidenceError(
                "Phase 8 and Phase 9 validated build projections differ"
            )

        if (
            dps_state.get("config_sha256")
            != documents["dps_acceptance_config"].get("sha256")
            or phase9_plan.get("matrix_file_sha256")
            != documents["phase9_pairwise_matrix"].get("sha256")
            or phase9_plan.get("dps_acceptance_state_sha256")
            != documents["dps_campaign_state"].get("sha256")
        ):
            raise JoinedEvidenceError("campaign inputs do not match embedded exact bytes")
        if not (
            phase9_plan.get("execution_policy") == "run_to_completion"
            and phase9_plan.get("overall_wall_clock_timeout_sec") is None
            and phase9_plan.get("retry_policy")
            == "unlimited_physical_tries_until_terminal_success"
            and tuple(phase9_plan.get("terminal_conditions") or ())
            == PHASE9_TERMINAL_CONDITIONS
            and all(
                attempt.get("execution_policy") == "run_to_completion"
                and attempt.get("overall_wall_clock_timeout_sec") is None
                and "--run-to-completion" in (attempt.get("command") or [])
                and "--timeout-sec" not in (attempt.get("command") or [])
                for attempt in phase9_plan.get("attempts") or []
                if isinstance(attempt, Mapping)
            )
            and phase9_state.get("execution_policy") == "run_to_completion"
            and phase9_state.get("overall_wall_clock_timeout_sec") is None
            and phase9_state.get("retry_policy")
            == "unlimited_physical_tries_until_terminal_success"
            and tuple(phase9_state.get("terminal_conditions") or ())
            == PHASE9_TERMINAL_CONDITIONS
        ):
            raise JoinedEvidenceError(
                "Phase 9 evidence is not bound to run-to-completion execution"
            )
        phase9_artifacts = phase9_identity.get("artifact_hashes") or {}
        artifact_records = {
            "target_catalog_sha256": "phase8_config_target_catalog",
            "pair_policy_sha256": "phase8_config_stonecore_pair_policy",
            "pairwise_matrix_sha256": "phase9_pairwise_matrix",
            "route_manifest_sha256": "phase9_route_manifest",
        }
        if any(
            name not in documents
            or phase9_artifacts.get(hash_name) != documents[name].get("sha256")
            for hash_name, name in artifact_records.items()
        ):
            raise JoinedEvidenceError(
                "Phase 9 artifact hashes do not match the embedded closure"
            )

        ledgers = closure.get("physical_ledgers") or {}
        dps_ledger = [dict(row) for row in ledgers.get("dps") or []]
        phase9_ledger = [dict(row) for row in ledgers.get("phase9") or []]
        if dps_ledger != dps_state.get("physical_try_ledger"):
            raise JoinedEvidenceError("DPS physical ledger is not exact")
        if phase9_ledger != phase9_state.get("physical_try_ledger"):
            raise JoinedEvidenceError("Phase 9 physical ledger is not exact")
        physical_dps = len(dps_ledger)
        physical_phase9 = len(phase9_ledger)
        materialized = closure.get("materialized_try_ids") or {}
        if materialized.get("dps") != [row.get("attempt_id") for row in dps_ledger]:
            raise JoinedEvidenceError("DPS materialized try set differs from ledger")
        if materialized.get("phase9") != [row.get("attempt_id") for row in phase9_ledger]:
            raise JoinedEvidenceError("Phase 9 materialized try set differs from ledger")

        leaves = [dict(row) for row in closure.get("leaf_batches") or []]
        leaf_by_lane: dict[str, dict[str, dict[str, Any]]] = {"dps": {}, "phase9": {}}
        for leaf in leaves:
            lane = str(leaf.get("lane") or "")
            attempt_id = str(leaf.get("attempt_id") or "")
            if lane not in leaf_by_lane or not attempt_id or attempt_id in leaf_by_lane[lane]:
                raise JoinedEvidenceError("duplicate or malformed leaf identity")
            leaf_by_lane[lane][attempt_id] = leaf
        if set(leaf_by_lane["dps"]) != {str(row.get("attempt_id") or "") for row in dps_ledger}:
            raise JoinedEvidenceError("DPS leaf set differs from materialized ledger")
        if set(leaf_by_lane["phase9"]) != {str(row.get("attempt_id") or "") for row in phase9_ledger}:
            raise JoinedEvidenceError("Phase 9 leaf set differs from materialized ledger")
        dps_domain_context = {
            "policy_sha256": documents[
                "phase8_config_role_calibration_policy"
            ]["sha256"],
            "targets_sha256": documents["phase8_config_target_catalog"]["sha256"],
            "references_sha256": documents[
                "phase8_config_reference_catalog"
            ]["sha256"],
            "scenarios_sha256": documents["phase8_calibration_scenarios"]["sha256"],
            "identity_manifest_sha256": dps_identity["manifest_sha256"],
        }
        phase9_domain_context = {
            "plan_sha256": phase9_plan["plan_sha256"],
            "identity_manifest_sha256": phase9_identity["manifest_sha256"],
        }
        for row in dps_ledger:
            _verify_leaf(
                leaf_by_lane["dps"][str(row["attempt_id"])],
                row,
                dps_domain_context,
            )
        for row in phase9_ledger:
            _verify_leaf(
                leaf_by_lane["phase9"][str(row["attempt_id"])],
                row,
                phase9_domain_context,
            )

        dps_attempts = [dict(row) for row in dps_plan.get("attempts") or []]
        dps_targets = [str(value) for value in dps_config.get("dps_targets") or []]
        if (
            dps_plan.get("schema") != "cata_raid_dps_acceptance_campaign_plan_v1"
            or dps_state.get("schema") != "cata_raid_dps_acceptance_campaign_state_v2"
            or dps_state.get("passed") is not True
            or dps_state.get("active_attempt") is not None
            or int(dps_plan.get("max_tries_per_dps_spec") or 0) != 2
            or int(dps_state.get("max_tries_per_dps_spec") or 0) != 2
            or len(dps_attempts) != len(dps_targets) != 16
            or len(set(dps_targets)) != 16
            or {str(row.get("spec_target_id") or "") for row in dps_attempts}
            != set(dps_targets)
            or not 16 <= len(dps_ledger) <= 32
        ):
            raise JoinedEvidenceError("DPS campaign is not the exact 16-spec max-two gate")
        for logical in dps_attempts:
            logical_id = str(logical.get("attempt_id") or "")
            rows = [row for row in dps_ledger if row.get("logical_attempt_id") == logical_id]
            ordinals = [int(row.get("physical_try_ordinal") or 0) for row in rows]
            accepted = [index for index, row in enumerate(rows) if _dps_accepted(row)]
            if (
                not 1 <= len(rows) <= 2
                or ordinals != list(range(1, len(rows) + 1))
                or len(accepted) != 1
                or accepted[0] != len(rows) - 1
                or any(row.get("spec_target_id") != logical.get("spec_target_id") for row in rows)
            ):
                raise JoinedEvidenceError(f"DPS retry sequence is invalid: {logical_id}")
            verified_dps += 1

        phase9_attempts = [dict(row) for row in phase9_plan.get("attempts") or []]
        pinned = [dict(row) for row in matrix.get("serial_canaries") or []]
        expected_pairs = [
            (str(row.get("composition_id") or ""), ordinal, row.get("ordered_party"))
            for row in pinned
            for ordinal in (1, 2)
        ]
        observed_pairs = [
            (
                str(row.get("composition_id") or ""),
                int(row.get("clear_ordinal") or 0),
                row.get("ordered_party"),
            )
            for row in phase9_attempts
        ]
        if (
            phase9_plan.get("schema") != "all_spec_phase9_serial_run_plan_v1"
            or phase9_state.get("schema") != "phase9_serial_canary_operator_state_v3"
            or phase9_state.get("status") != "passed"
            or phase9_state.get("promotion_gate_passed") is not True
            or phase9_state.get("active_attempt") is not None
            or len(pinned) != 7
            or len(phase9_attempts) != 14
            or observed_pairs != expected_pairs
        ):
            raise JoinedEvidenceError("Phase 9 plan is not the pinned seven combinations twice")
        accepted_rows: list[dict[str, Any]] = []
        for logical in phase9_attempts:
            logical_id = str(logical.get("attempt_id") or "")
            rows = [row for row in phase9_ledger if row.get("logical_attempt_id") == logical_id]
            ordinals = [int(row.get("physical_try_ordinal") or 0) for row in rows]
            accepted = [index for index, row in enumerate(rows) if _phase9_accepted(row)]
            if (
                not rows
                or ordinals != list(range(1, len(rows) + 1))
                or len(accepted) != 1
                or accepted[0] != len(rows) - 1
                or any(row.get("composition_id") != logical.get("composition_id") for row in rows)
                or any(int(row.get("success_ordinal") or 0) != int(logical.get("clear_ordinal") or 0) for row in rows)
            ):
                raise JoinedEvidenceError(f"Phase 9 retry sequence is invalid: {logical_id}")
            accepted_rows.append(rows[accepted[0]])
        accepted_pairs = [
            (str(row.get("composition_id") or ""), int(row.get("success_ordinal") or 0))
            for row in accepted_rows
        ]
        if accepted_pairs != [(value[0], value[1]) for value in expected_pairs]:
            raise JoinedEvidenceError("Phase 9 accepted rows do not prove exact 7x2 coverage")
        verified_phase9 = len(accepted_rows)

        if "phase9_append_ledger" not in documents:
            raise JoinedEvidenceError("Phase 9 append-only physical ledger is missing")
        phase9_events = _verify_jsonl_chain(
            documents["phase9_append_ledger"], phase9_state.get("append_ledger") or {}
        )
        _verify_phase9_append_event_set(
            phase9_events,
            _phase9_expected_append_events(
                phase9_plan,
                phase9_identity,
                phase9_ledger,
                leaf_by_lane["phase9"],
            ),
        )
        if "dps_append_ledger" in documents:
            _verify_jsonl_chain(
                documents["dps_append_ledger"], dps_state.get("append_ledger") or {}
            )
        joined = closure.get("joined_verification") or {}
        if (
            not isinstance(joined, Mapping)
            or dict(joined) != parsed["joined_campaign_verification"]
            or joined.get("schema") != "phase9_joined_campaign_verification_v1"
            or not SHA256_RE.fullmatch(
                str(joined.get("verification_sha256") or "")
            )
            or canonical_sha256(
                {
                    key: value
                    for key, value in joined.items()
                    if key != "verification_sha256"
                }
            )
            != joined.get("verification_sha256")
            or joined.get("passed") is not True
            or int(joined.get("verified_phase9_attempt_count") or 0) != 14
            or int(joined.get("verified_dps_attempt_count") or 0) != 16
        ):
            raise JoinedEvidenceError("source joined verification did not pass")
    except (JoinedEvidenceError, TypeError, ValueError, KeyError) as exc:
        reasons.append(str(exc))
        closure_hash = str(closure.get("closure_sha256") or "")
    result = {
        "schema": "joined_campaign_closure_verification_v1",
        "passed": not reasons and verified_dps == 16 and verified_phase9 == 14,
        "failure_reasons": reasons,
        "closure_sha256": closure_hash,
        "verified_dps_logical_qualifications": verified_dps,
        "verified_dps_physical_tries": physical_dps,
        "verified_phase9_player_like_clears": verified_phase9,
        "verified_phase9_physical_tries": physical_phase9,
    }
    result["verification_sha256"] = canonical_sha256(result)
    return result


def build_outer_bootstrap(
    repository: Path,
    batch_root: Path,
    closure_sha256: str,
    domain_verification_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the Git-tracked discovery record after outer reconstruction."""
    repository = repository.resolve()
    batch_root = batch_root.resolve()
    manifest = _required_document(
        batch_root / "retained/final_manifest.json", repository, "outer final manifest"
    )
    publication = _required_document(
        batch_root / "retained/publication_receipt.json",
        repository,
        "outer publication receipt",
    )
    reconstruction = _required_document(
        batch_root / "retained/reconstruction_receipt.json",
        repository,
        "outer reconstruction receipt",
    )
    publication_payload = _json_object(publication["document"], "outer publication")
    bootstrap = {
        "schema": BOOTSTRAP_SCHEMA,
        "campaign_id": str(publication_payload.get("batch_id") or ""),
        "batch_path": str(batch_root.relative_to(repository)),
        "closure_sha256": closure_sha256,
        "domain_verification_identity": dict(domain_verification_identity),
        "outer_final_manifest": manifest,
        "outer_publication_receipt": publication,
        "outer_reconstruction_receipt": reconstruction,
        "outer_dvc_pointers": publication_payload.get("pointers") or [],
    }
    bootstrap["bootstrap_sha256"] = canonical_sha256(bootstrap)
    verify_joined_campaign_bootstrap(bootstrap)
    return bootstrap


def verify_joined_campaign_bootstrap(bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    if bootstrap.get("schema") != BOOTSTRAP_SCHEMA:
        raise JoinedEvidenceError("joined bootstrap schema mismatch")
    bootstrap_hash = _self_hash(bootstrap, "bootstrap_sha256")
    batch_path = Path(str(bootstrap.get("batch_path") or ""))
    campaign_id = str(bootstrap.get("campaign_id") or "")
    closure_hash = str(bootstrap.get("closure_sha256") or "")
    if (
        not campaign_id
        or batch_path.is_absolute()
        or ".." in batch_path.parts
        or not SHA256_RE.fullmatch(closure_hash)
    ):
        raise JoinedEvidenceError("joined bootstrap identity is incomplete")
    manifest = _embedded_document(
        bootstrap.get("outer_final_manifest") or {}, "outer manifest"
    )
    publication = _embedded_document(
        bootstrap.get("outer_publication_receipt") or {}, "outer publication"
    )
    reconstruction = _embedded_document(
        bootstrap.get("outer_reconstruction_receipt") or {}, "outer reconstruction"
    )
    manifest_hash = _self_hash(manifest, "identity_sha256")
    publication_hash = _self_hash(publication, "receipt_sha256")
    _self_hash(reconstruction, "receipt_sha256")
    domain_identity = bootstrap.get("domain_verification_identity") or {}
    domain_verification = reconstruction.get("domain_verification") or {}
    pointer_parents = {
        Path(str(row.get("path") or "")).parent
        for row in bootstrap.get("outer_dvc_pointers") or []
        if isinstance(row, Mapping)
    }
    retained_records = {
        "final_manifest.json": bootstrap.get("outer_final_manifest") or {},
        "publication_receipt.json": bootstrap.get("outer_publication_receipt") or {},
        "reconstruction_receipt.json": bootstrap.get(
            "outer_reconstruction_receipt"
        )
        or {},
    }
    retained_paths_valid = all(
        Path(str(record.get("path") or ""))
        == batch_path / "retained" / name
        for name, record in retained_records.items()
        if isinstance(record, Mapping)
    ) and len(retained_records) == 3
    if (
        manifest.get("batch_id") != campaign_id
        or publication.get("batch_id") != campaign_id
        or reconstruction.get("batch_id") != campaign_id
        or publication.get("batch_identity_sha256") != manifest_hash
        or publication.get("raw_bundle_sha256")
        != (manifest.get("raw") or {}).get("bundle_sha256")
        or publication.get("compact_bundle_sha256")
        != (manifest.get("compact") or {}).get("bundle_sha256")
        or reconstruction.get("batch_identity_sha256") != manifest_hash
        or reconstruction.get("publication_receipt_sha256") != publication_hash
        or publication.get("remote_verified") is not True
        or reconstruction.get("remote_reconstructed") is not True
        or reconstruction.get("targeted_eviction_complete") is not True
        or not isinstance(domain_identity, Mapping)
        or domain_identity.get("closure_sha256") != closure_hash
        or reconstruction.get("domain_verification_id")
        != canonical_sha256(domain_identity)
        or not isinstance(domain_verification, Mapping)
        or domain_verification.get("verified") is not True
        or domain_verification.get("closure_sha256") != closure_hash
        or int(domain_verification.get("verified_dps_logical_qualifications") or 0)
        != 16
        or int(domain_verification.get("verified_phase9_player_like_clears") or 0)
        != 14
        or not 16
        <= int(domain_verification.get("verified_dps_physical_tries") or 0)
        <= 32
        or int(domain_verification.get("verified_phase9_physical_tries") or 0)
        < 14
        or int(
            domain_verification.get("accepted_leaf_remote_reconstructions") or 0
        )
        != 30
        or domain_verification.get(
            "accepted_leaf_targeted_eviction_complete"
        )
        is not True
        or publication.get("pointers") != bootstrap.get("outer_dvc_pointers")
        or not _pointer_rows_valid(bootstrap.get("outer_dvc_pointers"))
        or pointer_parents != {batch_path}
        or not retained_paths_valid
    ):
        raise JoinedEvidenceError("outer publication chain is invalid")
    return {
        "schema": "joined_campaign_dvc_bootstrap_verification_v1",
        "passed": True,
        "campaign_id": campaign_id,
        "bootstrap_sha256": bootstrap_hash,
        "closure_sha256": closure_hash,
    }


def write_outer_bootstrap(repository: Path, bootstrap: Mapping[str, Any]) -> Path:
    """Write one immutable, Git-trackable campaign discovery document."""
    verification = verify_joined_campaign_bootstrap(bootstrap)
    campaign_id = str(verification["campaign_id"])
    if not re.fullmatch(r"[A-Za-z0-9._-]+", campaign_id):
        raise JoinedEvidenceError("campaign id is not safe for a tracked path")
    path = repository.resolve() / "experiments/evidence_indexes" / campaign_id / "bootstrap.json"
    document = json.dumps(dict(bootstrap), indent=2, sort_keys=True) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") != document:
        raise JoinedEvidenceError("joined campaign bootstrap is immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(path)
    return path


def materialize_outer_bootstrap(repository: Path, bootstrap: Mapping[str, Any]) -> Path:
    """Restore only the small outer pointer/receipt graph in a clean checkout."""
    verify_joined_campaign_bootstrap(bootstrap)
    repository = repository.resolve()
    batch_root = (repository / str(bootstrap["batch_path"])).resolve()
    try:
        batch_root.relative_to(repository)
    except ValueError as exc:
        raise JoinedEvidenceError("bootstrap batch path escapes repository") from exc
    retained = batch_root / "retained"
    retained.mkdir(parents=True, exist_ok=True)
    records = {
        retained / "final_manifest.json": bootstrap["outer_final_manifest"],
        retained / "publication_receipt.json": bootstrap["outer_publication_receipt"],
        retained / "reconstruction_receipt.json": bootstrap[
            "outer_reconstruction_receipt"
        ],
    }
    for path, record in records.items():
        document = _embedded_text_document(record, path.name)
        if path.is_file() and path.read_text(encoding="utf-8") != document:
            raise JoinedEvidenceError(f"bootstrap target conflicts: {path}")
        path.write_text(document, encoding="utf-8")
    for row in bootstrap.get("outer_dvc_pointers") or []:
        name = Path(str(row.get("path") or "")).name
        pointer = batch_root / name
        document = str(row.get("pointer_document") or "")
        if pointer.is_file() and pointer.read_text(encoding="utf-8") != document:
            raise JoinedEvidenceError(f"bootstrap pointer conflicts: {pointer}")
        pointer.write_text(document, encoding="utf-8")
    return batch_root


def reconstruct_outer_from_bootstrap(
    repository: Path, bootstrap_path: Path
) -> dict[str, Any]:
    """Force-pull, verify from the embedded closure, and exactly evict it.

    This is the clean-checkout entry point: the only required local campaign
    file is the tracked bootstrap.  A historical reconstruction receipt never
    bypasses the fresh remote pull.
    """
    from .batch_evidence_lifecycle import verify_remote_reconstruction_and_evict

    bootstrap = _json_object(
        bootstrap_path.read_text(encoding="utf-8"), "joined bootstrap"
    )
    verify_joined_campaign_bootstrap(bootstrap)
    batch_root = materialize_outer_bootstrap(repository, bootstrap)
    closure_sha = str(bootstrap["closure_sha256"])
    receipt = verify_remote_reconstruction_and_evict(
        repository.resolve(),
        batch_root,
        domain_verification_id=canonical_sha256(
            bootstrap["domain_verification_identity"]
        ),
        verify_hydrated=lambda hydrated: verify_hydrated_outer_closure(
            hydrated,
            closure_sha,
            repository=repository.resolve(),
            recursively_verify_accepted_leaves=True,
        ),
        force_reconstruct=True,
    )
    if (
        receipt.get("remote_reconstructed") is not True
        or receipt.get("targeted_eviction_complete") is not True
        or (receipt.get("domain_verification") or {}).get("closure_sha256")
        != closure_sha
    ):
        raise JoinedEvidenceError("clean-checkout outer reconstruction failed")
    return receipt


def verify_hydrated_outer_closure(
    batch_root: Path,
    expected_closure_sha256: str,
    *,
    repository: Path | None = None,
    recursively_verify_accepted_leaves: bool = False,
) -> dict[str, Any]:
    """Domain verifier passed to the DVC round-trip controller."""
    source_path = batch_root / "raw/acceptance_source_report.json"
    source = _json_object(source_path.read_text(encoding="utf-8"), "outer source report")
    closure = source.get("joined_campaign_closure") or {}
    verification = verify_joined_campaign_closure(closure)
    recursive: dict[str, Any] = {
        "verified": not recursively_verify_accepted_leaves,
        "accepted_leaf_count": 0,
        "targeted_eviction_complete": not recursively_verify_accepted_leaves,
    }
    if verification.get("passed") is True and recursively_verify_accepted_leaves:
        if repository is None:
            raise JoinedEvidenceError(
                "recursive leaf verification requires the DVC repository"
            )
        recursive = _recursively_verify_accepted_leaves(
            repository.resolve(), closure
        )
    verified = bool(
        verification.get("passed") is True
        and verification.get("closure_sha256") == expected_closure_sha256
        and recursive.get("verified") is True
        and int(recursive.get("accepted_leaf_count") or 0) == 30
        and recursive.get("targeted_eviction_complete") is True
    )
    return {
        "schema": "joined_campaign_hydrated_closure_verification_v1",
        "verified": verified,
        "source_report_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "closure_sha256": verification.get("closure_sha256"),
        "closure_verification_sha256": verification.get("verification_sha256"),
        "verified_dps_logical_qualifications": verification.get(
            "verified_dps_logical_qualifications"
        ),
        "verified_phase9_player_like_clears": verification.get(
            "verified_phase9_player_like_clears"
        ),
        "verified_dps_physical_tries": verification.get(
            "verified_dps_physical_tries"
        ),
        "verified_phase9_physical_tries": verification.get(
            "verified_phase9_physical_tries"
        ),
        "failure_reasons": verification.get("failure_reasons") or [],
        "accepted_leaf_remote_reconstructions": int(
            recursive.get("accepted_leaf_count") or 0
        ),
        "accepted_leaf_targeted_eviction_complete": recursive.get(
            "targeted_eviction_complete"
        )
        is True,
    }


def _restore_embedded_record(
    repository: Path,
    record: Mapping[str, Any],
    *,
    created: list[Path],
) -> Path:
    document = _embedded_text_document(record, str(record.get("path") or "record"))
    path = (repository / str(record["path"])).resolve()
    try:
        path.relative_to(repository)
    except ValueError as exc:
        raise JoinedEvidenceError("embedded record path escapes repository") from exc
    existed = path.is_file()
    if existed and path.read_text(encoding="utf-8") != document:
        raise JoinedEvidenceError(f"embedded record conflicts with checkout: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    if not existed:
        created.append(path)
    return path


def _remove_created_scaffold(repository: Path, created: Sequence[Path]) -> None:
    parents: set[Path] = set()
    for path in reversed(list(created)):
        path.unlink(missing_ok=True)
        parents.add(path.parent)
    for parent in sorted(parents, key=lambda value: len(value.parts), reverse=True):
        current = parent
        while current != repository:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


def _recursively_verify_accepted_leaves(
    repository: Path, closure: Mapping[str, Any]
) -> dict[str, Any]:
    """Freshly pull every gate-bearing leaf using closure-only identities."""
    from .batch_evidence_lifecycle import verify_remote_reconstruction_and_evict
    from .run_cata_raid_dps_acceptance import verify_hydrated_calibration
    from .run_phase9_serial_canaries import verify_hydrated_phase9_attempt

    documents = closure.get("exact_documents") or {}
    dps_identity = _embedded_document(
        documents.get("dps_evidence_identity") or {}, "recursive DPS identity"
    )
    phase9_identity = _embedded_document(
        documents.get("phase9_evidence_identity") or {}, "recursive Phase 9 identity"
    )
    policy_record = documents.get("phase8_config_role_calibration_policy") or {}
    created_config: list[Path] = []
    for name in (
        "phase8_config_role_calibration_policy",
        "phase8_config_target_catalog",
        "phase8_config_reference_catalog",
        "phase8_calibration_scenarios",
    ):
        _restore_embedded_record(
            repository, documents.get(name) or {}, created=created_config
        )
    policy_path = (repository / str(policy_record.get("path") or "")).resolve()
    accepted_leaves = [
        dict(leaf)
        for leaf in closure.get("leaf_batches") or []
        if isinstance(leaf, Mapping) and leaf.get("selected_for_gate") is True
    ]
    created_leaf_files: list[Path] = []
    verified_count = 0
    try:
        for leaf in accepted_leaves:
            attempt_id = str(leaf.get("attempt_id") or "")
            attempt_dir = (repository / str(leaf.get("attempt_directory") or "")).resolve()
            try:
                attempt_dir.relative_to(repository)
            except ValueError as exc:
                raise JoinedEvidenceError(
                    f"accepted leaf path escapes repository: {attempt_id}"
                ) from exc
            batch_root = attempt_dir / "batch"
            for name, relative in (
                ("final_manifest", "retained/final_manifest.json"),
                ("publication_receipt", "retained/publication_receipt.json"),
                ("reconstruction_receipt", "retained/reconstruction_receipt.json"),
            ):
                record = leaf.get(name) or {}
                expected_path = batch_root / relative
                restored = _restore_embedded_record(
                    repository, record, created=created_leaf_files
                )
                if restored != expected_path:
                    raise JoinedEvidenceError(
                        f"accepted leaf receipt path is misplaced: {attempt_id}"
                    )
            for pointer in leaf.get("dvc_pointers") or []:
                pointer_path = batch_root / Path(str(pointer.get("path") or "")).name
                pointer_record = {
                    "path": str(pointer_path.relative_to(repository)),
                    "size": len(str(pointer.get("pointer_document") or "").encode("utf-8")),
                    "sha256": pointer.get("pointer_sha256"),
                    "document": pointer.get("pointer_document"),
                }
                _restore_embedded_record(
                    repository, pointer_record, created=created_leaf_files
                )
            started = _embedded_document(
                leaf.get("started_receipt") or {}, f"{attempt_id}:recursive-start"
            )
            physical = started.get("physical_attempt") or {}
            embedded_reconstruction = _embedded_document(
                leaf.get("reconstruction_receipt") or {},
                f"{attempt_id}:recursive-reconstruction",
            )
            required_domain = str(
                embedded_reconstruction.get("domain_verification_id") or ""
            )
            if leaf.get("lane") == "dps":
                verifier = lambda hydrated, attempt=dict(physical): verify_hydrated_calibration(
                    hydrated, attempt, policy_path, dps_identity
                )
            elif leaf.get("lane") == "phase9":
                verifier = lambda hydrated, attempt=dict(physical): verify_hydrated_phase9_attempt(
                    hydrated, attempt, phase9_identity
                )
            else:
                raise JoinedEvidenceError(f"unknown accepted leaf lane: {attempt_id}")
            historical_reconstruction = str(
                (leaf["reconstruction_receipt"] or {}).get("document") or ""
            )
            try:
                reconstructed = verify_remote_reconstruction_and_evict(
                    repository,
                    batch_root,
                    domain_verification_id=required_domain,
                    verify_hydrated=verifier,
                    force_reconstruct=True,
                )
            finally:
                # The lifecycle controller rewrites this small receipt even
                # when a fresh domain comparison later fails. Restore the
                # immutable campaign-bound document on every exit path.
                (batch_root / "retained/reconstruction_receipt.json").write_text(
                    historical_reconstruction,
                    encoding="utf-8",
                )
            if (
                reconstructed.get("remote_reconstructed") is not True
                or reconstructed.get("targeted_eviction_complete") is not True
                or reconstructed.get("domain_verification")
                != embedded_reconstruction.get("domain_verification")
            ):
                raise JoinedEvidenceError(
                    f"accepted leaf remote reconstruction differs: {attempt_id}"
                )
            verified_count += 1
    finally:
        _remove_created_scaffold(repository, created_leaf_files)
        _remove_created_scaffold(repository, created_config)
    return {
        "verified": verified_count == len(accepted_leaves) == 30,
        "accepted_leaf_count": verified_count,
        "targeted_eviction_complete": all(
            not (
                repository
                / str(leaf.get("attempt_directory") or "")
                / "batch/raw"
            ).exists()
            and not (
                repository
                / str(leaf.get("attempt_directory") or "")
                / "batch/compact"
            ).exists()
            for leaf in accepted_leaves
        ),
    }
