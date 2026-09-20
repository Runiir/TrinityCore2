"""Review a worker or orchestrator checkpoint with Jev/Laya advice.

The model reviews a proposed change; it never executes commands, approves a
checkpoint, or supplies an acceptance label.  Deterministic findings and model
answers are retained as separate records for coordinator adjudication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.bot_ml import analyze_magmaw_trace as analyzer
from tools.bot_ml import jev_shadow
from tools.bot_ml import laya_packets

SCHEMA = "worker_checkpoint_review_v1"
MODEL_QUESTIONS = (
    "scope_fit",
    "evidence_supports_proposed_change",
    "acceptance_claim_supported",
)
REQUIRED_FIELDS = (
    "task_id", "objective", "first_broken_edge", "allowed_files",
    "forbidden_changes", "acceptance_conditions", "observations",
    "evidence_excerpts", "proposed_change", "acceptance_claim", "stage",
    "changed_files", "tests", "required_test_commands",
)


def encoded(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_hashes() -> dict[str, Any]:
    result = jev_shadow.execution_source()
    path = Path(__file__)
    result["worker_checkpoint"] = {
        "module": __name__,
        "source_sha256": sha(path.read_bytes()) if path.is_file() else None,
    }
    return result


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return value


def validate_checkpoint(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(checkpoint, Mapping):
        raise ValueError("checkpoint must be a JSON object")
    missing = [name for name in REQUIRED_FIELDS if name not in checkpoint]
    if missing:
        raise ValueError(f"checkpoint fields missing: {', '.join(missing)}")
    result = dict(checkpoint)
    for name in ("task_id", "objective", "first_broken_edge", "proposed_change",
                 "acceptance_claim"):
        if not isinstance(result[name], str) or not result[name].strip():
            raise ValueError(f"{name} must be a non-empty string")
    _string_list(result["allowed_files"], "allowed_files")
    _string_list(result["forbidden_changes"], "forbidden_changes")
    _string_list(result["changed_files"], "changed_files")
    _string_list(result["required_test_commands"], "required_test_commands")
    if result["stage"] not in {"plan", "result"}:
        raise ValueError("stage must be plan or result")
    changed_source = result.get("changed_files_source", "unknown")
    if changed_source not in {"coordinator_observed", "observed_git_index", "unknown", "checkpoint_claim"}:
        raise ValueError("changed_files_source must be coordinator_observed, observed_git_index, unknown, or checkpoint_claim")
    result["changed_files_source"] = changed_source
    if result.get("subject", "worker") not in {"worker", "orchestrator"}:
        raise ValueError("subject must be worker or orchestrator")
    if result.get("subject") == "orchestrator":
        goal = result.get("goal_context")
        if not isinstance(goal, Mapping) or any(not goal.get(key) for key in (
                "parent_objective", "latest_user_direction", "current_plan", "remaining_requirements")):
            raise ValueError("orchestrator review requires parent goal, user direction, plan, and remaining requirements")
    for name in ("acceptance_conditions", "observations", "evidence_excerpts", "tests"):
        if not isinstance(result[name], list):
            raise ValueError(f"{name} must be a list")
    for test in result["tests"]:
        if not isinstance(test, Mapping):
            raise ValueError("tests must contain objects")
    return result


def _evidence_path(item: Mapping[str, Any]) -> str | None:
    for key in ("path", "artifact", "file"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _resolve(path: str, base_dir: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else base_dir / candidate


def deterministic_findings(checkpoint: Mapping[str, Any], base_dir: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    allowed = set(checkpoint["allowed_files"])
    outside = sorted(set(checkpoint["changed_files"]) - allowed)
    if outside:
        findings.append({"kind": "outside_allowed_files", "status": "fail", "files": outside})

    if checkpoint["stage"] == "result":
        tests = checkpoint["tests"]
        receipts = {}
        for test in tests:
            command = test.get("command")
            if isinstance(command, str) and command:
                if command in receipts:
                    findings.append({"kind": "duplicate_required_test_receipt", "status": "fail",
                                     "command": command})
                receipts[command] = test
        required_commands = checkpoint["required_test_commands"]
        for command in required_commands:
            test = receipts.get(command)
            if test is None:
                findings.append({"kind": "missing_required_tests", "status": "fail",
                                 "command": command, "detail": "required command has no receipt"})
                continue
            status = test.get("exit_status")
            if type(status) is not int:
                findings.append({"kind": "missing_required_tests", "status": "fail",
                                 "command": command, "detail": "command and integer exit_status are required"})
            elif status != 0:
                findings.append({"kind": "failed_required_test", "status": "fail",
                                 "command": command, "exit_status": status})

    for item in checkpoint["evidence_excerpts"]:
        if not isinstance(item, Mapping):
            continue
        cited = _evidence_path(item)
        if not cited:
            findings.append({"kind": "missing_cited_artifact", "status": "fail",
                             "detail": "evidence excerpt has no artifact path"})
            continue
        path = _resolve(cited, base_dir)
        if not path.is_file():
            findings.append({"kind": "missing_cited_artifact", "status": "fail", "path": cited})
            continue
        expected = item.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            findings.append({"kind": "missing_cited_artifact_sha256", "status": "fail", "path": cited})
            continue
        actual = sha(path.read_bytes())
        if actual != expected.lower():
            findings.append({"kind": "cited_artifact_sha256_mismatch", "status": "fail",
                             "path": cited, "expected": expected, "actual": actual})

    status = "fail" if findings else "pass"
    return {"status": status, "findings": findings,
            "test_receipts_basis": "reported command and exit status; execution is not independently verified"}


def questions() -> dict[str, dict[str, Any]]:
    return {
        "scope_fit": {
            "type": "choice",
            "instructions": "Judge whether the proposed next action fits the assigned objective and scope. If goal_context exists, respect its latest user direction, preserve remaining parent requirements, and compare the next action to the current plan.",
            "criteria": {
                "supported": "The proposed action follows the current authorized plan, addresses the assigned edge, and respects scope boundaries without dropping outstanding requirements.",
                "contradicted": "The proposed action violates a boundary, abandons outstanding requirements, repeats closed work without new evidence, or takes an unrelated detour not requested by the user.",
                "insufficient_evidence": "The checkpoint does not state enough about the proposed or changed files to determine scope.",
            },
        },
        "evidence_supports_proposed_change": {
            "type": "choice",
            "instructions": "Judge whether the cited observations and evidence support the proposed worker change.",
            "criteria": {
                "supported": "The cited facts directly support the proposed change and do not require an invented metric, attribution, or causal step.",
                "contradicted": "The cited facts directly conflict with the proposed change or support a different first broken edge.",
                "insufficient_evidence": "The evidence is missing, unverifiable, indirect, or too incomplete to distinguish the proposal from alternatives.",
            },
        },
        "acceptance_claim_supported": {
            "type": "choice",
            "instructions": "Judge whether the explicit acceptance claim is supported at its stated scope by the stage, receipts, and cited results. Compare the claimed behavior with operations actually executed by the test or native path: a test that only assigns expected values and asserts them is not execution evidence. A bounded unit-test claim may be supported while full live acceptance remains pending.",
            "criteria": {
                "supported": "The claim is limited to behavior actually exercised by the recorded test or native path, such as a named resolver fixture invoking the changed operation; it does not claim unobserved native, live, or full-task acceptance.",
                "contradicted": "The claim asserts native, live, or runtime behavior while the evidence only assigns expected values, asserts a hand-built result, shows a narrower path, or records a failed required test.",
                "insufficient_evidence": "The checkpoint is a plan, or its receipts and artifacts cannot establish whether the claimed operation actually executed at the stated bounded scope.",
            },
        },
    }


def build_packet(checkpoint: Mapping[str, Any], model: str) -> dict[str, Any]:
    # Lossless references remove repeated paths/commands, not evidence or limits.
    # The full checkpoint remains in the receipt and deterministic checks.
    allowed = checkpoint["allowed_files"]
    required = checkpoint["required_test_commands"]
    changed = checkpoint["changed_files"]
    tests = []
    for test in checkpoint["tests"]:
        compact = dict(test)
        if compact.get("command") in required:
            compact["required_test_commands_index"] = required.index(compact.pop("command"))
        tests.append(compact)
    evidence = []
    for index, item in enumerate(checkpoint["evidence_excerpts"]):
        if isinstance(item, Mapping):
            evidence.append({"id": item.get("id", str(index)),
                             "excerpt": item.get("excerpt", item.get("text", ""))})
        else:
            evidence.append({"id": str(index), "excerpt": item})
    state = {
        "task": "Review one bounded " + checkpoint.get("subject", "worker") + " checkpoint",
        "authority": "advisory only; coordinator owns execution, acceptance, and user approval",
        "checkpoint": {
            "objective": checkpoint["objective"],
            "first_broken_edge": checkpoint["first_broken_edge"],
            "allowed_files": checkpoint["allowed_files"],
            "forbidden_changes": checkpoint["forbidden_changes"],
            "acceptance_conditions": checkpoint["acceptance_conditions"],
            "acceptance_claim": checkpoint["acceptance_claim"],
            "observations": checkpoint["observations"],
            "evidence_excerpts": evidence,
            "proposed_change": checkpoint["proposed_change"],
            "stage": checkpoint["stage"],
            "changed_files": {
                "allowed_files_indices": [allowed.index(path) for path in changed if path in allowed],
                "other_paths": [path for path in changed if path not in allowed],
                "source": checkpoint.get("changed_files_source", "unknown"),
            },
            "tests": tests,
            "required_test_commands": checkpoint["required_test_commands"],
        },
    }
    if checkpoint.get("goal_context") is not None:
        state["checkpoint"]["goal_context"] = checkpoint["goal_context"]
    return {"model": model, "state": state, "questions": questions()}


def _request_bytes(packet: Mapping[str, Any], provider: str) -> bytes:
    if provider == "hosted_jev":
        return json.dumps({"state": packet["state"], "model": packet["model"],
                           "questions": packet["questions"]},
                          separators=(",", ":"), sort_keys=False).encode()
    return encoded(packet)


def _provider_backend(provider: str, endpoint: str, sources: dict[str, Any]) -> dict[str, Any]:
    if provider == "local_laya":
        return {"provider": provider, "endpoint": endpoint,
                "requested_model": laya_packets.MODEL, "execution_source": sources,
                "action_authority": False}
    return {"provider": provider, "endpoint": analyzer.JEV_URL,
            "requested_model": analyzer.JEV_MODEL, "execution_source": sources,
            "action_authority": False}


def _model_status(response: dict[str, Any] | None, error: str | None) -> str:
    if response is None:
        return "unknown"
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(MODEL_QUESTIONS):
        return "unknown"
    choices = []
    for answer in answers.values():
        if not isinstance(answer, Mapping) or not isinstance(answer.get("choice"), str):
            return "unknown"
        choices.append(answer["choice"])
    if not set(choices).issubset({"supported", "contradicted", "insufficient_evidence"}):
        return "unknown"
    return "advisory" if not error else "unknown"


def review_checkpoint(checkpoint: Mapping[str, Any], output: Path, *, backend: str = "local",
                      endpoint: str = jev_shadow.ENDPOINT, env_file: Path = Path(".env"),
                      prepare_only: bool = False, base_dir: Path = Path(".")) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    checkpoint = validate_checkpoint(checkpoint)
    deterministic = deterministic_findings(checkpoint, base_dir)
    output.mkdir(parents=True)
    packet_by_provider = {
        "local_laya": build_packet(checkpoint, laya_packets.MODEL),
        "hosted_jev": build_packet(checkpoint, analyzer.JEV_MODEL),
    }
    providers = ["local_laya", "hosted_jev"] if backend == "both" else [
        "local_laya" if backend == "local" else "hosted_jev"
    ]
    sources = source_hashes()
    rows: list[dict[str, Any]] = []
    hosted_key = None
    if "hosted_jev" in providers and not prepare_only:
        try:
            hosted_key = analyzer._jev_key(env_file)
        except Exception as exc:
            hosted_key = exc
    for provider in providers:
        packet = packet_by_provider[provider]
        request = _request_bytes(packet, provider)
        response, error = None, None
        started = time.monotonic()
        if not prepare_only:
            try:
                if provider == "local_laya":
                    response = jev_shadow.call_local(packet, endpoint)
                elif isinstance(hosted_key, Exception):
                    raise hosted_key
                else:
                    response = analyzer._call_jev(packet["state"], hosted_key, packet["questions"])
            except Exception as exc:  # retain provider failure, never retry here
                error = f"{type(exc).__name__}: {exc}"
        row = {
            "schema": SCHEMA, "recorded_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider, "request_sha256": sha(request),
            "request_json": request.decode(),
            "response": response,
            "response_sha256": sha(encoded(response)) if response is not None else None,
            "latency_sec": round(time.monotonic() - started, 4) if not prepare_only else None,
            "error": error, "backend": _provider_backend(provider, endpoint, sources),
            "model_status": "prepared" if prepare_only else _model_status(response, error),
        }
        rows.append(row)

    checkpoint_bytes = encoded(checkpoint)
    (output / "checkpoint.json").write_bytes(checkpoint_bytes + b"\n")
    with (output / "examples.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(encoded(row).decode() + "\n")
    summary = {
        "schema": SCHEMA, "task_id": checkpoint["task_id"], "stage": checkpoint["stage"],
        "subject": checkpoint.get("subject", "worker"),
        "backend": backend, "examples": len(rows),
        "responses": sum(row["response"] is not None for row in rows),
        "errors": sum(row["error"] is not None for row in rows),
        "checkpoint_sha256": sha(checkpoint_bytes),
        "changed_files_source": checkpoint.get("changed_files_source", "unknown"),
        "execution_source": sources,
        "deterministic": deterministic,
        "model_status": {row["provider"]: row["model_status"] for row in rows},
        "coordinator_review_required": True,
        "automatic_pass": False, "execution_authority": False,
        "prepare_only": prepare_only,
    }
    (output / "summary.json").write_bytes(encoded(summary) + b"\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "--checkpoint", dest="checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("local", "hosted", "both"), default="local")
    parser.add_argument("--endpoint", default=jev_shadow.ENDPOINT)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    try:
        summary = review_checkpoint(checkpoint, args.output, backend=args.backend,
                                    endpoint=args.endpoint, env_file=args.env_file,
                                    prepare_only=args.prepare_only,
                                    base_dir=args.checkpoint.parent)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
