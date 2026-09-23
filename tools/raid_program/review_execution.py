"""Bind a review adapter to an independent reviewer's final JSON.

The graph stores a small review adapter, while this module verifies that its
reviewer identity and verdict came from one independent session.  The default
transport is a Codex rollout: only the final JSON message and a hash of the
rollout prefix are retained; the rollout transcript is never copied into
repository evidence.  ``import-json`` binds a Claude Code reviewer subagent's
final JSON (``review_transport: external_json``) to that subagent's persisted
transcript prefix in the same way, plus both session ids and the current file
hashes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.raid_program import development_graph as graph


SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
TRANSCRIPTS_ROOT = Path.home() / ".claude" / "projects"
ROOT = Path(__file__).resolve().parents[2]
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_FINDINGS_BYTES = 256 * 1024
# Only ``approved`` advances the graph; both spellings of the rejection verdict are retained.
SUPPORTED_REVIEW_VERDICTS = frozenset({"approved", "changes_requested", "changes_required"})
EXTERNAL_TRANSPORT = "external_json"
TRANSCRIPT_PROOF_SCHEMA = "claude_transcript_review_proof_v1"
MAX_EXTERNAL_REPORT_BYTES = 1024 * 1024
FINAL_FIELDS = frozenset({"verdict", "file_hashes", "findings", "tests", "limits"})
REQUIRED_FINAL_FIELDS = frozenset({"verdict", "file_hashes", "findings"})
EXTERNAL_REPORT_FIELDS = FINAL_FIELDS | {
    "schema", "reviewer_session_id", "proof", "review_transport", "implementer_session_id",
    "source_report_sha256", "source_report_path",
}


class ReviewExecutionError(ValueError):
    """Raised when a review cannot be proven from a Codex rollout."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _require(condition: bool, message: str, *, code: str | None = None) -> None:
    if not condition:
        raise ReviewExecutionError(message, code=code)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sessions_path(path: str | Path, sessions_root: Path | None = None) -> Path:
    root = (sessions_root or SESSIONS_ROOT).expanduser().resolve()
    _require(isinstance(path, (str, Path)) and str(path), "review rollout path required")
    candidate = Path(path).expanduser().resolve()
    _require(candidate.is_relative_to(root), "review rollout must be under ~/.codex/sessions")
    _require(candidate.is_file() and candidate.suffix == ".jsonl", "review rollout must be an existing JSONL file")
    return candidate


def _message_text(payload: Mapping[str, Any]) -> str:
    content = payload.get("content")
    _require(isinstance(content, list) and content, "final review message has no content")
    chunks: list[str] = []
    for item in content:
        _require(isinstance(item, Mapping) and item.get("type") == "output_text", "final review must contain output text only")
        text = item.get("text")
        _require(isinstance(text, str), "final review output text must be a string")
        chunks.append(text)
    return "".join(chunks)


def _has_subagent_source(metadata: Mapping[str, Any]) -> bool:
    source = metadata.get("source")
    if not isinstance(source, Mapping):
        return False
    subagent = source.get("subagent")
    return bool(subagent) and (not isinstance(subagent, Mapping) or bool(subagent.get("thread_spawn") or subagent.get("agent_path") or subagent.get("agent_nickname")))


def _read_rollout(
    path: Path,
    root: Path,
    selected_prefix_bytes: int | None = None,
    *,
    require_final: bool = True,
) -> dict[str, Any]:
    """Read a stable rollout and return only identity/final-message metadata."""

    before = path.stat()
    metadata: dict[str, Any] | None = None
    finals: list[dict[str, Any]] = []
    prefix_hasher = hashlib.sha256()
    offset = 0
    reached_selected_prefix = False
    try:
        with path.open("rb") as stream:
            for line in stream:
                if selected_prefix_bytes is not None and offset + len(line) > selected_prefix_bytes:
                    break
                offset += len(line)
                prefix_hasher.update(line)
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ReviewExecutionError("review rollout contains invalid JSON", code="rollout_invalid_json") from exc
                _require(isinstance(value, Mapping), "review rollout records must be JSON objects", code="rollout_record_invalid")
                kind = value.get("type")
                payload = value.get("payload")
                if kind == "session_meta":
                    _require(isinstance(payload, Mapping), "review rollout session metadata missing", code="session_metadata_invalid")
                    if metadata is not None:
                        raise ReviewExecutionError("review rollout contains duplicate session metadata", code="duplicate_session_metadata")
                    metadata = dict(payload)
                elif kind == "response_item" and isinstance(payload, Mapping):
                    if payload.get("type") == "message" and payload.get("role") == "assistant" and payload.get("phase") == "final_answer":
                        text = _message_text(payload)
                        finals.append({
                            "text": text,
                            "end_offset": offset,
                            "prefix_sha256": prefix_hasher.copy().hexdigest(),
                            "message_sha256": _sha256(text.encode("utf-8")),
                        })
                if selected_prefix_bytes is not None and offset == selected_prefix_bytes:
                    reached_selected_prefix = True
                    break
    except OSError as exc:
        raise ReviewExecutionError("cannot read review rollout") from exc
    after = path.stat()
    if selected_prefix_bytes is None:
        _require(
            (before.st_size, before.st_mtime_ns, before.st_ino)
            == (after.st_size, after.st_mtime_ns, after.st_ino),
            "review rollout changed while it was being read",
        )
    else:
        _require(
            reached_selected_prefix and after.st_size >= selected_prefix_bytes and before.st_ino == after.st_ino,
            "review rollout prefix was truncated or replaced",
            code="rollout_prefix_unstable",
        )
        try:
            with path.open("rb") as stream:
                prefix = stream.read(selected_prefix_bytes)
        except OSError as exc:
            raise ReviewExecutionError("cannot reread proven rollout prefix", code="rollout_prefix_unreadable") from exc
        _require(
            len(prefix) == selected_prefix_bytes and _sha256(prefix) == prefix_hasher.hexdigest(),
            "review rollout prefix changed while it was being read",
            code="rollout_prefix_changed",
        )
    _require(metadata is not None, "review rollout session metadata missing", code="session_metadata_missing")
    _require(isinstance(metadata.get("id"), str) and metadata["id"], "review rollout identity missing", code="rollout_identity_missing")
    _require(_has_subagent_source(metadata), "review rollout is not an independent Codex subagent session", code="independent_subagent_required")
    cwd = metadata.get("cwd")
    if cwd is not None:
        _require(
            Path(str(cwd)).resolve() == root.resolve(),
            "review rollout checkout differs from coordinator worktree",
            code="checkout_mismatch",
        )
    if require_final:
        _require(finals, "review rollout must contain a final response", code="final_response_missing")
    final: dict[str, Any] | None = None
    if finals:
        if selected_prefix_bytes is None or not require_final:
            final = finals[-1]
        else:
            matches = [row for row in finals if row["end_offset"] == selected_prefix_bytes]
            _require(len(matches) == 1, "review rollout does not contain the proven final prefix", code="final_prefix_missing")
            final = matches[0]
    return {
        "metadata": metadata,
        "final": final,
        "finals": finals,
        "prefix_bytes": offset,
        "prefix_sha256": prefix_hasher.hexdigest(),
    }


def preflight_review(
    root: Path,
    rollout_path: str | Path,
    *,
    reviewer_session_id: str,
    implementer_session_id: str,
    sessions_root: Path | None = None,
    prefix_bytes: int | None = None,
    prefix_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate a fresh reviewer transcript before waiting for its final JSON.

    The current complete line boundary is captured when ``prefix_bytes`` is
    omitted.  Callers can pass a previous ``prefix_bytes``/``prefix_sha256``
    pair to prove that the captured prefix remained unchanged while the
    reviewer continued writing its transcript.  This function is read-only;
    it never emits a report or receipt.
    """

    root = root.resolve()
    _require(
        isinstance(reviewer_session_id, str) and reviewer_session_id,
        "reviewer session identity required",
        code="reviewer_identity_required",
    )
    _require(
        isinstance(implementer_session_id, str) and implementer_session_id,
        "implementer session identity required for reviewer preflight",
        code="implementer_identity_required",
    )
    _require(
        reviewer_session_id != implementer_session_id,
        "reviewer session must differ from implementer",
        code="self_review",
    )
    if prefix_bytes is None:
        _require(prefix_sha256 is None, "rollout prefix hash requires a prefix length", code="prefix_binding_incomplete")
    else:
        _require(type(prefix_bytes) is int and prefix_bytes > 0, "rollout prefix length must be positive", code="prefix_length_invalid")
        _require(
            isinstance(prefix_sha256, str) and SHA256_RE.fullmatch(prefix_sha256) is not None,
            "rollout prefix hash is invalid",
            code="prefix_hash_invalid",
        )

    rollout = _sessions_path(rollout_path, sessions_root)
    if prefix_bytes is None:
        try:
            prefix_bytes = rollout.stat().st_size
        except OSError as exc:
            raise ReviewExecutionError("cannot stat review rollout", code="rollout_unreadable") from exc
        _require(prefix_bytes > 0, "review rollout prefix is empty", code="prefix_empty")
    observed = _read_rollout(rollout, root, prefix_bytes, require_final=False)
    captured_hash = observed["prefix_sha256"]
    if prefix_sha256 is not None:
        _require(
            captured_hash == prefix_sha256,
            "review rollout prefix changed since preflight capture",
            code="rollout_prefix_changed",
        )
    metadata = observed["metadata"]
    _require(
        metadata.get("id") == reviewer_session_id,
        "explicit reviewer identity does not match rollout metadata",
        code="reviewer_identity_mismatch",
    )
    cwd = metadata.get("cwd")
    _require(
        isinstance(cwd, str) and cwd,
        "review rollout checkout metadata missing",
        code="checkout_metadata_missing",
    )
    _require(
        Path(cwd).resolve() == root,
        "review rollout checkout differs from coordinator worktree",
        code="checkout_mismatch",
    )
    return {
        "schema": "codex_rollout_review_preflight_v1",
        "ok": True,
        "status": "ready",
        "reviewer_session_id": reviewer_session_id,
        "implementer_session_id": implementer_session_id,
        "rollout_path": str(rollout),
        "checkout": str(root),
        "metadata_count": 1,
        "independent_subagent": True,
        "prefix_bytes": observed["prefix_bytes"],
        "prefix_sha256": captured_hash,
        "final_present": bool(observed["finals"]),
    }


def _repo_ref(root: Path, path: str | Path) -> tuple[dict[str, str], Path]:
    candidate = Path(path).expanduser()
    root_resolved = root.resolve()
    resolved = candidate.resolve() if candidate.is_absolute() else (root_resolved / candidate).resolve()
    _require(resolved.is_relative_to(root_resolved), "review report must be inside the coordinator worktree")
    _require(resolved.is_file(), "review report must be an existing file")
    reference = {"path": resolved.relative_to(root_resolved).as_posix(), "sha256": _sha256(resolved.read_bytes())}
    graph.file_ref(root, reference)
    return reference, resolved


def _validated_file_hashes(root: Path, value: Any, tested_files: Iterable[str] | None = None) -> dict[str, str]:
    _require(isinstance(value, Mapping), "review final file_hashes must be an object")
    paths = list(tested_files) if tested_files is not None else list(value)
    _require(paths and len(paths) == len(set(paths)), "review tested files must be nonempty and unique")
    _require(set(value) == set(paths), "review final file_hashes do not match tested files")
    normalized: dict[str, str] = {}
    for path in paths:
        _require(isinstance(path, str) and not Path(path).is_absolute() and ".." not in Path(path).parts, "invalid reviewed file path")
        expected = value.get(path)
        _require(isinstance(expected, str) and (SHA256_RE.fullmatch(expected) is not None or expected == graph.DELETED),
                 "invalid reviewed file hash")
        normalized[path] = expected
    current = graph.snapshot(root, paths)
    _require(normalized == current, "review file hashes do not match current files", code="stale_file_hashes")
    return normalized


def _validated_verdict(value: Any, supported: frozenset[str] = SUPPORTED_REVIEW_VERDICTS) -> str:
    _require(isinstance(value, str) and value, "review verdict required", code="verdict_missing")
    _require(value in supported, "unsupported review verdict", code="verdict_unsupported")
    return value


def _final_document(text: str) -> dict[str, Any]:
    try:
        final_document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReviewExecutionError("review final response must be JSON", code="final_response_invalid") from exc
    _require(isinstance(final_document, Mapping), "review final response must be a JSON object", code="final_response_invalid")
    _require(
        set(final_document) <= FINAL_FIELDS and REQUIRED_FINAL_FIELDS <= set(final_document),
        "review final response has unexpected fields",
        code="final_response_fields",
    )
    return dict(final_document)


def _optional_fields(document: Mapping[str, Any]) -> dict[str, Any]:
    return {key: document[key] for key in ("tests", "limits") if key in document}


def _transcript_path(path: Any, reviewer: str, transcripts_root: Path | None = None) -> Path:
    base = (transcripts_root or TRANSCRIPTS_ROOT).expanduser().resolve()
    _require(isinstance(path, (str, Path)) and str(path), "reviewer transcript path required", code="transcript_required")
    candidate = Path(path).expanduser().resolve()
    _require(candidate.is_relative_to(base), "reviewer transcript must be under the Claude projects root", code="transcript_outside_root")
    _require(candidate.is_file() and candidate.suffix == ".jsonl", "reviewer transcript must be an existing JSONL file", code="transcript_missing")
    _require(
        candidate.name == f"agent-{reviewer}.jsonl" and candidate.parent.name == "subagents",
        "reviewer transcript is not this reviewer's subagent transcript",
        code="transcript_identity_mismatch",
    )
    # <root>/<project-slug>/<session-id>/subagents/agent-<id>.jsonl plus its meta file.
    _require(candidate.with_suffix(".meta.json").is_file(), "reviewer transcript has no agent meta file", code="transcript_meta_missing")
    _require(candidate.parent.parent.parent.parent == base, "reviewer transcript is not at <root>/<project>/<session>/subagents", code="transcript_outside_root")
    return candidate


def _transcript_session(candidate: Path) -> str:
    return candidate.parent.parent.name


def _project_slug(root: Path) -> str:
    return str(root.resolve()).replace("/", "-")


def _read_transcript(path: Path, root: Path, reviewer: str, selected_prefix_bytes: int | None = None) -> dict[str, Any]:
    """Return the reviewer subagent's final assistant text and its prefix binding.

    Every record must belong to ``reviewer`` as a sidechain in ``root``.  With
    ``selected_prefix_bytes`` only that prefix is read and it must still end with
    the final assistant message; appended records are ignored, as for rollouts.
    """

    before = path.stat()
    final: dict[str, Any] | None = None
    user_after = False
    hasher = hashlib.sha256()
    offset = 0
    reached = False
    try:
        with path.open("rb") as stream:
            for line in stream:
                if selected_prefix_bytes is not None and offset + len(line) > selected_prefix_bytes:
                    break
                offset += len(line)
                hasher.update(line)
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ReviewExecutionError("reviewer transcript contains invalid JSON", code="transcript_invalid_json") from exc
                _require(isinstance(record, Mapping), "reviewer transcript records must be JSON objects", code="transcript_record_invalid")
                _require(record.get("agentId") == reviewer, "reviewer transcript record belongs to another agent", code="transcript_identity_mismatch")
                _require(record.get("isSidechain") is True, "reviewer transcript is not an independent subagent sidechain", code="independent_subagent_required")
                cwd = record.get("cwd")
                _require(
                    isinstance(cwd, str) and bool(cwd) and Path(cwd).resolve() == root,
                    "reviewer transcript checkout differs from coordinator worktree",
                    code="checkout_mismatch",
                )
                _require(
                    record.get("sessionId") == _transcript_session(path) and path.parent.parent.parent.name == _project_slug(root),
                    "reviewer transcript session or project does not match its location",
                    code="transcript_identity_mismatch",
                )
                message = record.get("message")
                role = message.get("role") if isinstance(message, Mapping) else None
                if record.get("type") == "assistant":
                    content = message.get("content") if isinstance(message, Mapping) else None
                    _require(role == "assistant" and isinstance(content, list), "assistant record has no assistant message", code="transcript_record_invalid")
                    items = [item for item in content if isinstance(item, Mapping)]
                    text = "".join(item["text"] for item in items if item.get("type") == "text" and isinstance(item.get("text"), str))
                    tool_use = any(item.get("type") == "tool_use" for item in items)
                    message_id = message.get("id")
                    if final is not None and not user_after and message_id is not None and final["message_id"] == message_id:
                        text, tool_use = final["text"] + text, tool_use or final["tool_use"]
                    final = {
                        "text": text, "tool_use": tool_use, "stop_reason": message.get("stop_reason"),
                        "message_id": message_id, "end_offset": offset, "prefix_sha256": hasher.copy().hexdigest(),
                    }
                    user_after = False
                elif record.get("type") in ("user", "tool") or role in ("user", "tool"):
                    user_after = True
                if selected_prefix_bytes is not None and offset == selected_prefix_bytes:
                    reached = True
                    break
    except OSError as exc:
        raise ReviewExecutionError("cannot read reviewer transcript", code="transcript_unreadable") from exc
    after = path.stat()
    if selected_prefix_bytes is None:
        _require(
            (before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino),
            "reviewer transcript changed while it was being read",
            code="transcript_unstable",
        )
    else:
        _require(
            reached and after.st_size >= selected_prefix_bytes and before.st_ino == after.st_ino,
            "reviewer transcript prefix was truncated or replaced",
            code="transcript_prefix_unstable",
        )
        try:
            with path.open("rb") as stream:
                prefix = stream.read(selected_prefix_bytes)
        except OSError as exc:
            raise ReviewExecutionError("cannot reread proven transcript prefix", code="transcript_unreadable") from exc
        _require(
            len(prefix) == selected_prefix_bytes and _sha256(prefix) == hasher.hexdigest(),
            "reviewer transcript prefix changed while it was being read",
            code="transcript_prefix_changed",
        )
    _require(final is not None, "reviewer transcript has no final assistant message", code="final_response_missing")
    _require(not user_after, "reviewer transcript continues with a user/tool record after its final assistant message", code="final_response_not_last")
    _require(
        bool(final["text"]) and not final["tool_use"] and final["stop_reason"] in (None, "end_turn")
        and len(final["text"].encode("utf-8")) <= MAX_EXTERNAL_REPORT_BYTES,
        "reviewer final assistant message must be a text answer",
        code="final_response_invalid",
    )
    if selected_prefix_bytes is not None:
        _require(final["end_offset"] == selected_prefix_bytes, "reviewer transcript prefix does not end with the final message", code="final_prefix_missing")
    return final


def _contains_document(text: str, expected: Mapping[str, Any]) -> bool:
    """Whether ``text`` embeds a JSON object canonically equal to ``expected``."""

    # Only the LAST JSON object of the message counts: a quoted or example object
    # earlier in the text (for example a conditional approval followed by the real
    # changes_required verdict) must never be importable as the reviewer's answer.
    target = _canonical(expected)
    decoder = json.JSONDecoder()
    tail_ok = re.compile(r"^\s*(```+\s*)?$")
    index = text.rfind("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            value, end = None, None
        if isinstance(value, dict) and end is not None and tail_ok.match(text[end:]):
            return _canonical(value) == target
        index = text.rfind("{", 0, index)
    return False


def _verify_external(
    root: Path,
    review: Mapping[str, Any],
    report: Mapping[str, Any],
    hashes: Mapping[str, str],
    implementer_session_id: str | None,
    transcripts_root: Path | None,
) -> None:
    """Check an ``external_json`` report against its reviewer transcript prefix."""

    reviewer = review["reviewer_session_id"]
    _require(set(report) <= EXTERNAL_REPORT_FIELDS, "external review report has unexpected fields")
    implementer = report.get("implementer_session_id")
    _require(isinstance(implementer, str) and implementer, "external review implementer identity missing")
    _require(reviewer != implementer, "reviewer session must differ from implementer", code="self_review")
    if implementer_session_id is not None:
        _require(implementer == implementer_session_id, "external review implementer identity mismatch")
    _require(isinstance(report.get("findings"), list), "external review findings must be a list")
    for key in ("tests", "limits"):
        _require(key not in report or isinstance(report[key], list), "external review field must be a list: " + key)
    source_sha256 = report.get("source_report_sha256")
    _require(isinstance(source_sha256, str) and SHA256_RE.fullmatch(source_sha256) is not None, "external review source hash invalid")
    _require(isinstance(report.get("source_report_path"), str) and report["source_report_path"], "external review source path missing")
    proof = report.get("proof")
    _require(isinstance(proof, Mapping), "external review transcript proof missing", code="transcript_required")
    _require(proof.get("schema") == TRANSCRIPT_PROOF_SCHEMA, "external review proof schema mismatch", code="transcript_required")
    _require(proof.get("review_transport") == EXTERNAL_TRANSPORT, "external review proof transport mismatch")
    _require(proof.get("session_id") == reviewer, "external review proof session mismatch")
    _require(proof.get("implementer_session_id") == implementer, "external review proof implementer mismatch")
    transcript = _transcript_path(proof.get("transcript_path"), reviewer, transcripts_root)
    prefix_bytes = proof.get("prefix_bytes")
    _require(type(prefix_bytes) is int and prefix_bytes > 0, "transcript proof prefix length missing")
    final = _read_transcript(transcript, root, reviewer, prefix_bytes)
    _require(proof.get("prefix_sha256") == final["prefix_sha256"], "transcript proof prefix hash mismatch", code="transcript_prefix_changed")
    _require(proof.get("final_message_sha256") == _sha256(final["text"].encode("utf-8")), "transcript final message hash mismatch")
    _require(proof.get("final_message_bytes") == len(final["text"].encode("utf-8")), "transcript final message length mismatch")
    document = {"verdict": report["verdict"], "file_hashes": dict(hashes), "findings": report["findings"]} | _optional_fields(report)
    _require(_contains_document(final["text"], document), "reviewer final message does not match the review report", code="final_response_mismatch")


def verify_review(
    root: Path,
    review: Mapping[str, Any],
    *,
    implementer_session_id: str | None = None,
    sessions_root: Path | None = None,
    transcripts_root: Path | None = None,
) -> dict[str, str]:
    """Verify a review adapter and its rollout or transcript proof without writing files."""

    _require(isinstance(review, Mapping), "review receipt must be an object")
    _require(review.get("kind") in {"review", "supporting_review", "supporting_workflow_review"}, "review receipt kind required")
    _require(review.get("authority") == "coordinator_attestation", "review receipt authority required")
    reviewer = review.get("reviewer_session_id")
    _require(isinstance(reviewer, str) and reviewer, "reviewer session identity required")
    _require(isinstance(review.get("unit_id"), str) and review["unit_id"], "review unit identity required")
    _require(review.get("producer") == reviewer, "review producer must be the proven reviewer session")
    verdict = _validated_verdict(review.get("verdict"))
    if implementer_session_id is not None:
        _require(reviewer != implementer_session_id, "reviewer session must differ from implementer")

    report_ref = review.get("review_report")
    _require(isinstance(report_ref, Mapping), "review report reference required")
    evidence = review.get("evidence")
    _require(isinstance(evidence, list) and any(item == report_ref for item in evidence), "review evidence must include the report")
    report_path = graph.file_ref(root, dict(report_ref))
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewExecutionError("review report must be valid JSON") from exc
    _require(isinstance(report, Mapping), "review report must be a JSON object")
    transport = report.get("review_transport")
    _require(transport in (None, EXTERNAL_TRANSPORT), "unsupported review transport")
    _require(report.get("schema") == "cata_raid_review_report_v1", "review report schema mismatch")
    _require(report.get("reviewer_session_id") == reviewer, "review report reviewer identity mismatch")
    _require(report.get("verdict") == verdict, "review report verdict mismatch")
    hashes = _validated_file_hashes(root, report.get("file_hashes"))
    _require(review.get("file_hashes") == hashes, "review receipt file hashes mismatch")
    _require(report.get("findings") is not None, "review report findings missing")
    _require(len(_canonical(report.get("findings"))) <= MAX_FINDINGS_BYTES, "review findings are too large")
    if transport == EXTERNAL_TRANSPORT:
        _verify_external(root, review, report, hashes, implementer_session_id, transcripts_root)
        return hashes

    proof = report.get("proof")
    _require(isinstance(proof, Mapping), "review rollout proof missing")
    _require(proof.get("schema") == "codex_rollout_review_proof_v1", "review rollout proof schema mismatch")
    rollout = _sessions_path(proof.get("rollout_path"), sessions_root or SESSIONS_ROOT)
    prefix_bytes = proof.get("prefix_bytes")
    _require(type(prefix_bytes) is int and prefix_bytes > 0, "rollout proof prefix length missing")
    observed = _read_rollout(rollout, root, prefix_bytes)
    metadata = observed["metadata"]
    final = observed["final"]
    _require(metadata.get("id") == reviewer, "reviewer session identity is not from rollout metadata")
    _require(proof.get("session_id") == reviewer, "rollout proof session mismatch")
    _require(proof.get("prefix_bytes") == final["end_offset"], "rollout proof prefix length mismatch")
    _require(proof.get("prefix_sha256") == final["prefix_sha256"], "rollout proof prefix hash mismatch")
    _require(proof.get("final_message_sha256") == final["message_sha256"], "rollout final message hash mismatch")
    _require(proof.get("final_message_bytes") == len(final["text"].encode("utf-8")), "rollout final message length mismatch")
    final_document = _final_document(final["text"])
    _require(final_document.get("verdict") == verdict, "final response verdict mismatch")
    _require(final_document.get("file_hashes") == hashes, "final response file hashes mismatch")
    _require(final_document.get("findings") == report.get("findings"), "final response findings mismatch")
    for key in ("tests", "limits"):
        _require((key in final_document) == (key in report), "review report optional field mismatch: " + key)
        if key in final_document:
            _require(final_document[key] == report[key], "final response field mismatch: " + key)
    return hashes


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    path = path.resolve()
    if path.exists():
        raise ReviewExecutionError("refusing to overwrite existing review output")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        temp = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def build_review(
    root: Path,
    rollout_path: str | Path,
    tested_files: Iterable[str],
    report_path: str | Path,
    *,
    receipt_path: str | Path | None = None,
    implementer_session_id: str | None = None,
    sessions_root: Path | None = None,
) -> dict[str, Any]:
    """Create a compact review report and graph receipt from one rollout."""

    root = root.resolve()
    rollout = _sessions_path(rollout_path, sessions_root)
    observed = _read_rollout(rollout, root)
    metadata = observed["metadata"]
    final = observed["final"]
    reviewer = metadata["id"]
    if implementer_session_id is not None:
        _require(reviewer != implementer_session_id, "reviewer session must differ from implementer")
    final_document = _final_document(final["text"])
    _validated_verdict(final_document.get("verdict"))
    hashes = _validated_file_hashes(root, final_document.get("file_hashes"), tested_files)
    _require(len(_canonical(final_document.get("findings"))) <= MAX_FINDINGS_BYTES, "review findings are too large")
    proof = {
        "schema": "codex_rollout_review_proof_v1",
        "rollout_path": str(rollout),
        "session_id": reviewer,
        "prefix_bytes": final["end_offset"],
        "prefix_sha256": final["prefix_sha256"],
        "final_message_bytes": len(final["text"].encode("utf-8")),
        "final_message_sha256": final["message_sha256"],
    }
    receipt_target = Path(receipt_path) if receipt_path is not None else None
    return _write_review(
        root, reviewer, final_document, hashes, proof, report_path, receipt_target,
        implementer_session_id=implementer_session_id, sessions_root=sessions_root,
    )


def _write_review(
    root: Path,
    reviewer: str,
    final_document: Mapping[str, Any],
    hashes: Mapping[str, str],
    proof: Mapping[str, Any],
    report_path: str | Path,
    receipt_path: Path | None,
    *,
    implementer_session_id: str | None,
    sessions_root: Path | None = None,
    transcripts_root: Path | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the compact review report and graph adapter shared by both transports."""

    state, _ = _state_for_unit(root)
    unit_id = state["development_graph"]["unit"]["id"]
    report = {
        "schema": "cata_raid_review_report_v1",
        "reviewer_session_id": reviewer,
        "verdict": final_document["verdict"],
        "file_hashes": dict(hashes),
        "findings": final_document["findings"],
        "proof": dict(proof),
    } | _optional_fields(final_document) | dict(extra or {})
    report_target = (root / Path(report_path)).resolve() if not Path(report_path).is_absolute() else Path(report_path).resolve()
    _require(report_target.is_relative_to(root), "review report must be inside the coordinator worktree")
    report_ref_target = {"path": report_target.relative_to(root).as_posix(), "sha256": _sha256(_canonical(report))}
    _write_new_json(report_target, report)
    report_ref_target["sha256"] = _sha256(report_target.read_bytes())
    receipt = {
        "authority": "coordinator_attestation",
        "kind": "review",
        "unit_id": unit_id,
        "producer": reviewer,
        "reviewer_session_id": reviewer,
        "verdict": final_document["verdict"],
        "file_hashes": dict(hashes),
        "review_report": report_ref_target,
        "evidence": [report_ref_target],
    }
    verify_review(
        root, receipt, implementer_session_id=implementer_session_id,
        sessions_root=sessions_root, transcripts_root=transcripts_root,
    )
    receipt_target = receipt_path if receipt_path is not None else report_target.with_suffix(".receipt.json")
    if not receipt_target.is_absolute():
        receipt_target = root / receipt_target
    receipt_target = receipt_target.resolve()
    _require(receipt_target.is_relative_to(root), "review receipt must be inside the coordinator worktree")
    _write_new_json(receipt_target, receipt)
    receipt_ref = {"path": receipt_target.resolve().relative_to(root).as_posix(), "sha256": _sha256(receipt_target.read_bytes())}
    return {"report": report_ref_target, "receipt": receipt_ref, "reviewer_session_id": reviewer, "verdict": receipt["verdict"]}


def _state_for_unit(root: Path) -> tuple[dict[str, Any], str]:
    path = root / graph.STATE_PATH
    try:
        data = path.read_bytes()
        state = json.loads(data)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewExecutionError("invalid workflow state") from exc
    _require(isinstance(state, dict), "workflow state must be an object")
    graph.check_state(root, state)
    return state, _sha256(data)


def _inside(root: Path, path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    return (candidate if candidate.is_absolute() else root / candidate).resolve()


def import_external_review(
    root: Path,
    report_path: str | Path,
    *,
    reviewer_session_id: str,
    implementer_session_id: str,
    receipt_path: str | Path,
    transcript_path: str | Path,
    transcripts_root: Path | None = None,
    output_report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Record a Claude Code reviewer subagent's final JSON as a review adapter.

    ``report_path`` holds exactly the final JSON the separate reviewer returned
    (``verdict``, ``file_hashes``, ``findings``, optional ``tests``/``limits``).
    ``transcript_path`` is that subagent's persisted JSONL; its last assistant
    message must embed the same JSON and nothing but non-user records may
    follow.  Every hash must match the working tree now; changed files need a
    new review.  The compact report defaults to ``<receipt>.report.json``; no
    output is left behind when any check fails.
    """

    root = root.resolve()
    for value, name in ((reviewer_session_id, "reviewer"), (implementer_session_id, "implementer")):
        _require(isinstance(value, str) and value.strip() == value and value, name + " session identity required", code=name + "_identity_required")
    _require(reviewer_session_id != implementer_session_id, "reviewer session must differ from implementer", code="self_review")
    source = _inside(root, report_path)
    _require(source.is_file(), "reviewer JSON report must be an existing file", code="report_missing")
    raw = source.read_bytes()
    _require(0 < len(raw) <= MAX_EXTERNAL_REPORT_BYTES, "reviewer JSON report is empty or too large", code="report_size")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewExecutionError("reviewer JSON report must be UTF-8", code="final_response_invalid") from exc
    document = _final_document(text)
    _validated_verdict(document.get("verdict"))
    _require(isinstance(document.get("findings"), list), "reviewer findings must be a list", code="findings_invalid")
    for key in ("tests", "limits"):
        _require(key not in document or isinstance(document[key], list), "reviewer field must be a list: " + key, code="optional_field_invalid")
    _require(len(_canonical(document["findings"])) <= MAX_FINDINGS_BYTES, "review findings are too large", code="findings_too_large")
    try:
        hashes = _validated_file_hashes(root, document.get("file_hashes"))
    except graph.GraphError as exc:  # a reviewed file no longer exists
        raise ReviewExecutionError(str(exc) + "; changed files need a new review", code="stale_file_hashes") from exc
    transcript = _transcript_path(transcript_path, reviewer_session_id, transcripts_root)
    final = _read_transcript(transcript, root, reviewer_session_id)
    _require(
        _contains_document(final["text"], document),
        "reviewer final message does not contain this report JSON",
        code="final_response_mismatch",
    )
    receipt_target = _inside(root, receipt_path)
    if output_report_path is None:
        stem = receipt_target.name.removesuffix(".json").removesuffix(".receipt")
        report_target = receipt_target.with_name(stem + ".report.json")
    else:
        report_target = _inside(root, output_report_path)
    _require(len({source, receipt_target, report_target}) == 3, "reviewer JSON, report and receipt paths must differ", code="path_collision")
    final_bytes = final["text"].encode("utf-8")
    proof = {
        "schema": TRANSCRIPT_PROOF_SCHEMA,
        "review_transport": EXTERNAL_TRANSPORT,
        "transcript_path": str(transcript),
        "session_id": reviewer_session_id,
        "implementer_session_id": implementer_session_id,
        "prefix_bytes": final["end_offset"],
        "prefix_sha256": final["prefix_sha256"],
        "final_message_bytes": len(final_bytes),
        "final_message_sha256": _sha256(final_bytes),
    }
    extra = {
        "review_transport": EXTERNAL_TRANSPORT,
        "implementer_session_id": implementer_session_id,
        "source_report_sha256": _sha256(raw),
        "source_report_path": str(source),
    }
    preexisting = {path for path in (report_target, receipt_target) if path.exists()}
    try:
        result = _write_review(
            root, reviewer_session_id, document, hashes, proof, report_target, receipt_target,
            implementer_session_id=implementer_session_id, transcripts_root=transcripts_root, extra=extra,
        )
    except BaseException:
        for path in (report_target, receipt_target):
            if path not in preexisting:
                path.unlink(missing_ok=True)
        raise
    return {"ok": True, "review_transport": EXTERNAL_TRANSPORT, "implementer_session_id": implementer_session_id} | result


def _import_json_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Record an independent review from a Claude Code reviewer subagent's final JSON")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, required=True, help="reviewer final JSON: verdict, file_hashes, findings[, tests, limits]")
    parser.add_argument("--transcript", type=Path, required=True, help="reviewer subagent JSONL: <transcripts-root>/<project>/<session>/subagents/agent-<id>.jsonl")
    parser.add_argument("--transcripts-root", type=Path, help="default ~/.claude/projects")
    parser.add_argument("--reviewer-session-id", "--reviewer-id", dest="reviewer_session_id", required=True, help="reviewer subagent agentId")
    parser.add_argument("--implementer-session-id", "--implementer-id", dest="implementer_session_id", required=True)
    parser.add_argument("--receipt", type=Path, required=True, help="review adapter to write (inside --root)")
    parser.add_argument("--output-report", type=Path, help="compact report to write; default <receipt>.report.json")
    args = parser.parse_args(argv)
    try:
        result = import_external_review(
            args.root.resolve(),
            args.report,
            reviewer_session_id=args.reviewer_session_id,
            implementer_session_id=args.implementer_session_id,
            receipt_path=args.receipt,
            transcript_path=args.transcript,
            transcripts_root=args.transcripts_root,
            output_report_path=args.output_report,
        )
    except (ReviewExecutionError, graph.GraphError, OSError, ValueError) as exc:
        payload = {"ok": False, "code": getattr(exc, "code", None) or "review_import_failed", "error": str(exc)}
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _preflight_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate reviewer rollout identity before its final response")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--reviewer-session-id", "--reviewer-id", dest="reviewer_session_id", required=True)
    parser.add_argument("--implementer-session-id", "--implementer-id", dest="implementer_session_id", required=True)
    parser.add_argument("--sessions-root", type=Path)
    parser.add_argument("--prefix-bytes", type=int)
    parser.add_argument("--prefix-sha256")
    args = parser.parse_args(argv)
    try:
        result = preflight_review(
            args.root.resolve(),
            args.rollout,
            reviewer_session_id=args.reviewer_session_id,
            implementer_session_id=args.implementer_session_id,
            sessions_root=args.sessions_root,
            prefix_bytes=args.prefix_bytes,
            prefix_sha256=args.prefix_sha256,
        )
    except (ReviewExecutionError, OSError, ValueError) as exc:
        payload = {"ok": False, "code": getattr(exc, "code", None) or "review_preflight_failed", "error": str(exc)}
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "preflight":
        return _preflight_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "import-json":
        return _import_json_main(raw_argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--files-json", type=Path, required=True, help="JSON file containing the exact reviewed file path list")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--implementer-session-id")
    parser.add_argument("--sessions-root", type=Path)
    args = parser.parse_args(argv)
    try:
        files_path = args.files_json.resolve()
        files_value = json.loads(files_path.read_text(encoding="utf-8"))
        if isinstance(files_value, Mapping):
            files_value = files_value.get("files")
        _require(isinstance(files_value, list) and all(isinstance(item, str) for item in files_value), "files JSON must be a list of paths")
        result = build_review(
            args.root.resolve(),
            args.rollout,
            files_value,
            args.report,
            receipt_path=args.receipt,
            implementer_session_id=args.implementer_session_id,
            sessions_root=args.sessions_root,
        )
    except (ReviewExecutionError, graph.GraphError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
