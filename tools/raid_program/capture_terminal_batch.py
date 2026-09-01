from __future__ import annotations

from collections.abc import Callable
from typing import Any


FailureClassifier = Callable[..., tuple[str | None, list[str]]]
EvidenceRequester = Callable[[str], dict[str, Any]]


def _failure_projection(
    *,
    classification: str,
    failure_reason: str,
    status_rejections: list[str],
    terminal_status: dict[str, Any],
    terminal_kind: str | None,
    elapsed_seconds: float,
    evidence_reason: str,
    request_final_evidence: EvidenceRequester,
) -> tuple[dict[str, Any], dict[str, Any]]:
    forced_evidence = request_final_evidence(evidence_reason)
    failure = {
        "detected": True,
        "classification": classification,
        "failure_reason": failure_reason,
        "terminal_status": terminal_status,
        "status_rejections": status_rejections,
        "route": terminal_status.get("validation_route"),
        "raid_runtime": terminal_status.get("raid_runtime"),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "final_forced_evidence": forced_evidence.get("gate_passed") is True,
        "final_forced_evidence_report": forced_evidence,
    }
    if terminal_kind is not None:
        failure["terminal_kind"] = terminal_kind
    abort: dict[str, Any] = {"detected": False}
    if forced_evidence.get("gate_passed") is not True:
        abort = {
            "detected": True,
            "classification": "infrastructure_abort",
            "reason": "terminal_failure_forced_evidence_incomplete",
            "missing_channels": forced_evidence.get("missing_channels", []),
            "rejections": forced_evidence.get("rejections", []),
            "elapsed_seconds": round(elapsed_seconds, 3),
        }
    return failure, abort


def classify_terminal_failure_batch(
    statuses: list[dict[str, Any]],
    *,
    profile_name: str,
    elapsed_seconds: float,
    request_final_evidence: EvidenceRequester,
    preflight_classifier: FailureClassifier,
    runtime_classifier: FailureClassifier,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Apply preflight, then gameplay precedence across the complete batch."""

    classifiers = (
        (
            preflight_classifier,
            "infrastructure_abort",
            "admission_preflight",
            "terminal_preflight_failure",
        ),
        (
            runtime_classifier,
            "gameplay_failure",
            None,
            "terminal_runtime_failure",
        ),
    )
    for classifier, classification, terminal_kind, evidence_reason in classifiers:
        for status in statuses:
            reason, rejections = classifier(status, profile_name=profile_name)
            if reason is not None:
                return _failure_projection(
                    classification=classification,
                    failure_reason=reason,
                    status_rejections=rejections,
                    terminal_status=status,
                    terminal_kind=terminal_kind,
                    elapsed_seconds=elapsed_seconds,
                    evidence_reason=evidence_reason,
                    request_final_evidence=request_final_evidence,
                )
    return None
