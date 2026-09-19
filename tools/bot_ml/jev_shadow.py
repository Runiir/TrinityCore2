"""Collect local per-actor diagnostic judgments from a closed raid review.

This is offline diagnostic research, not an action-policy dataset or a live
controller. Predictions are never labels. Rows remain quarantined until a
separate evidence review supplies complete identity and an adjudicated label.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tools.bot_ml import analyze_magmaw_trace as analyzer
from tools.bot_ml import laya_packets

SCHEMA = "raid_diagnostic_shadow_v1"
MODEL = laya_packets.MODEL
ENDPOINT = "http://127.0.0.1:8000/v1/systemone"
CONTRACT = "actor_diagnostic_v2"
REQUIRED_IDENTITY = (
    "run_id", "attempt_id", "server_epoch", "source_commit", "build_receipt_sha256",
    "binary_sha256", "config_sha256", "route_sha256", "roster_sha256",
    "capture_schema", "terminal_receipt_sha256", "evidence_dvc_md5",
    "script_contract_revision",
)


def encoded(value: Any) -> bytes:
    # SimpleJev candidate order is semantic. Never sort criteria or request keys.
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def execution_source() -> dict[str, dict[str, str | None]]:
    """Hash source files backing the imported modules at batch startup.

    Supplied backend receipts retain their own client claims.  A missing
    source file remains unknown instead of being represented by a guessed
    digest.
    """
    modules = {
        "writer": sys.modules[__name__],
        "packet_builder": laya_packets,
        "hosted_serializer": analyzer,
    }
    result: dict[str, dict[str, str | None]] = {}
    for name, module in modules.items():
        source_path = getattr(module, "__file__", None)
        path = Path(source_path) if isinstance(source_path, str) else None
        if path is not None and path.suffix == ".pyc":
            path = path.with_suffix(".py")
        result[name] = {
            "module": getattr(module, "__name__", None),
            "source_sha256": sha(path.read_bytes()) if path is not None and path.is_file() else None,
        }
    return result


def _qwen_actor_packets(review: dict[str, Any], model: str) -> list[dict[str, Any]]:
    state = review["jev_input"]["state"]
    boss = state.get("boss_dps_review") or {}
    packets = []
    for actor in boss.get("actor_loss_signals", []):
        guid = actor.get("bot_guid")
        if not guid:
            continue
        # Reuse the deterministic screen, duty context and corrected timeline.
        # Do not duplicate the whole group's timelines in every actor request.
        actor_state = {
            "task": "Review one raid actor's diagnostic evidence",
            "authority": "advisory only; native evidence and human review decide repairs",
            "run_id": state["run_id"], "segment_id": state.get("segment_id"),
            "native_gameplay_outcome": state.get("native_gameplay_outcome"),
            "actor_review": actor,
            "limitations": [
                "Landed effects, including procs, are not completed casts.",
                "Owner damage gaps exclude pets but unknown effects may remain.",
                "Aggregate interval overlap alone cannot locate failures inside a gap.",
                "WCL whole-fight DPS is context, not a matched acceptance threshold.",
                "Required duties and phase coverage may explain apparent losses.",
            ],
        }
        questions = analyzer._jev_questions(False, include_next_fix=False,
            actor_specs=[actor], include_timeline=False, include_assignment=False)
        questions = {k: v for k, v in questions.items() if k.startswith("actor_action_")}
        packets.append({"model": model, "state": actor_state, "questions": questions})
    return packets


def actor_packets(review: dict[str, Any], model: str = MODEL) -> list[dict[str, Any]]:
    """Build Laya packets by default, retaining the explicit Qwen path."""
    if model == laya_packets.MODEL:
        return laya_packets.actor_packets(review, model)
    return _qwen_actor_packets(review, model)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("local shadow endpoint redirected; request refused")


def call_local(packet: dict[str, Any], endpoint: str, timeout: float = 30) -> dict[str, Any]:
    url = urlparse(endpoint)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"} or url.username or url.password:
        raise ValueError("local shadow requires an unauthenticated loopback HTTP endpoint")
    request = Request(endpoint, data=encoded(packet), method="POST",
                      headers={"Content-Type": "application/json"})
    with build_opener(NoRedirect).open(request, timeout=timeout) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("local response exceeds 2 MB")
    result = json.loads(payload)
    if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
        raise ValueError("local response is not a typed answer object")
    if result.get("model") != packet["model"]:
        raise ValueError("local response model identity mismatch")
    if set(result.get("answers", {})) != set(packet["questions"]):
        raise ValueError("local response question identity mismatch")
    analyzer._validate_typed_answers(result["answers"], packet["questions"])
    return result


def training_reasons(identity: dict[str, Any], response: dict[str, Any] | None) -> list[str]:
    reasons = ["adjudicated_label_missing"]
    if any(not identity.get(key) for key in REQUIRED_IDENTITY):
        reasons.append("identity_missing_or_mismatch")
    if identity.get("closed") is not True:
        reasons.append("terminal_receipt_unverified")
    if identity.get("script_fidelity_verified") is not True:
        reasons.append("script_fidelity_blocked")
    if response is None:
        reasons.append("prediction_unavailable")
    return reasons


def review_prediction(packet: dict[str, Any], response: dict[str, Any] | None) -> dict[str, Any]:
    """Record deterministic contradictions separately from the raw prediction."""
    actor = packet["state"].get("actor_review") or {}
    reasons = []
    for answer in (response or {}).get("answers", {}).values():
        choice = answer.get("choice")
        if choice == "encounter_assignment":
            if not actor.get("required_assignment_active") or actor.get("assignment_status") != "incomplete":
                reasons.append("assignment_repair_not_supported_by_observed_duty")
        elif choice not in {"collect_more_canaries", "insufficient_role_evidence"} and actor.get("counterfactual_status") != "eligible":
            reasons.append("counterfactual_evidence_unavailable_or_ineligible")
    return {"status": "unavailable" if response is None else "review_required" if reasons else "advisory_only",
            "reasons": sorted(set(reasons)), "ground_truth_label": False}


def make_row(packet: dict[str, Any], *, identity: dict[str, Any], backend: dict[str, Any],
             response: dict[str, Any] | None, latency_sec: float | None,
             error: str | None = None, source: str = "local_request",
             teacher: dict[str, Any] | None = None) -> dict[str, Any]:
    # Match the hosted client's actual serializer, including top-level order
    # and ASCII escaping. Local requests use encoded(packet) directly.
    body = (json.dumps({"state": packet["state"], "model": packet["model"],
                        "questions": packet["questions"]},
                       separators=(",", ":"), sort_keys=False).encode()
            if source == "hosted_request" else encoded(packet))
    run_id = packet["state"]["run_id"]
    if identity.get("run_id") != run_id:
        raise ValueError("packet and evidence run identities differ")
    actor = packet["state"].get("actor_review") or {}
    return {
        "schema": SCHEMA, "task": "post_run_diagnostic_review",
        "contract": CONTRACT, "recorded_at": datetime.now(timezone.utc).isoformat(),
        "example_id": sha(encoded([run_id, actor.get("bot_guid"), sha(body)])),
        "run_id": run_id, "actor_guid": actor.get("bot_guid"),
        "split_group": run_id, "split_assignment": "unassigned",
        "identity": identity, "backend": backend, "source": source,
        "request_json": body.decode(), "request_sha256": sha(body),
        "response": response, "response_sha256": sha(encoded(response)) if response else None,
        "latency_sec": latency_sec, "error": error,
        "teacher_prediction": teacher, "label": None,
        "prediction_review": review_prediction(packet, response),
        "admission": "quarantine", "quarantine_reasons": training_reasons(identity, response),
        "training_eligible": False, "action_policy_eligible": False,
        "action_authorized": False,
    }


def write_batch(packets: list[dict[str, Any]], output: Path, *, identity: dict[str, Any],
                backend: dict[str, Any], endpoint: str = ENDPOINT,
                prepare_only: bool = False,
                request_fn: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
                request_source: str = "local_request") -> dict[str, Any]:
    if identity.get("closed") is not True:
        raise ValueError("shadow capture requires an explicitly closed evidence batch")
    if not packets:
        raise ValueError("review has no actor packets")
    if len({p["state"]["actor_review"]["bot_guid"] for p in packets}) != len(packets):
        raise ValueError("duplicate actor packets")
    for packet in packets:
        if packet["state"]["run_id"] != identity.get("run_id"):
            raise ValueError("packet and evidence run identities differ")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    # Exclusive creation preserves historical predictions instead of overwriting them.
    with (output / "examples.jsonl").open("x", encoding="utf-8") as stream:
        for packet in packets:
            start = time.monotonic()
            response, error = None, None
            try:
                if not prepare_only:
                    response = (request_fn or call_local)(packet, endpoint)
            except (OSError, ValueError, analyzer.JevError) as exc:
                error = f"{type(exc).__name__}: {exc}"
            row = make_row(packet, identity=identity, backend=backend, response=response,
                latency_sec=round(time.monotonic() - start, 4) if not prepare_only else None,
                error=error, source="prepared" if prepare_only else request_source)
            stream.write(encoded(row).decode() + "\n")
            stream.flush()
            rows.append(row)
    summary = {
        "schema": SCHEMA, "run_id": identity["run_id"], "examples": len(rows),
        "predictions": sum(row["response"] is not None for row in rows),
        "errors": sum(row["error"] is not None for row in rows),
        "training_eligible": 0, "quarantined": len(rows),
        "predictions_requiring_review": sum(row["prediction_review"]["status"] == "review_required" for row in rows),
        "reason_counts": dict(Counter(reason for row in rows for reason in row["quarantine_reasons"])),
        "payload_bytes": (output / "examples.jsonl").stat().st_size,
        "action_authorized": False,
    }
    (output / "summary.json").write_bytes(encoded(summary) + b"\n")
    # This directory is explicitly owned by the caller, never the repository's dvc.yaml.
    from dvclive import Live
    with Live(dir=str(output / "dvclive"), save_dvc_exp=False, dvcyaml=False) as live:
        for key in ("examples", "predictions", "errors", "quarantined", "payload_bytes"):
            live.log_metric(key, summary[key])
        live.log_param("contract", CONTRACT)
        live.log_param("run_id", identity["run_id"])
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True,
                        help="analyze_magmaw_trace --prepare-only output")
    parser.add_argument("--identity", type=Path, required=True,
                        help="closed evidence identity JSON, unknown fields stay absent")
    parser.add_argument("--backend-receipt", type=Path, required=True,
                        help="server revision, model checkpoint, device/dtype and prompt revision")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--model")
    parser.add_argument("--backend", choices=("local", "hosted"), default="local")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    review = json.loads(args.review.read_text())
    identity = json.loads(args.identity.read_text())
    identity["review_sha256"] = sha(args.review.read_bytes())
    backend = json.loads(args.backend_receipt.read_text())
    supplied_execution_source = backend.get("execution_source")
    if supplied_execution_source is not None:
        backend["supplied_execution_source"] = supplied_execution_source
    backend["execution_source"] = execution_source()
    request_fn = None
    if args.backend == "hosted":
        if args.model not in (None, analyzer.JEV_MODEL) or args.endpoint != ENDPOINT:
            parser.error("hosted review uses the configured Jev API model and endpoint")
        packets = laya_packets.actor_packets(review, analyzer.JEV_MODEL)
        backend["execution_backend"] = {
            "provider": "typesafe_hosted",
            "endpoint": analyzer.JEV_URL,
            "requested_model": analyzer.JEV_MODEL,
        }
        if not args.prepare_only:
            key = analyzer._jev_key(args.env_file)
            def request_fn(packet, _endpoint):
                return analyzer._call_jev(packet["state"], key, packet["questions"])
    else:
        packets = actor_packets(review, args.model or MODEL)
    summary = write_batch(packets, args.output, identity=identity,
        backend=backend, endpoint=args.endpoint, prepare_only=args.prepare_only,
        request_fn=request_fn,
        request_source="hosted_request" if args.backend == "hosted" else "local_request")
    print(json.dumps(summary))
    return 2 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
