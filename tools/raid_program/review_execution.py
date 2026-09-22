"""Bind a review adapter to a real Codex reviewer rollout.

The graph stores a small review adapter, while this module verifies that its
reviewer identity and verdict came from one independent Codex session.  Only
the final JSON message and a hash of the rollout prefix are retained; the
rollout transcript is never copied into repository evidence.
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
ROOT = Path(__file__).resolve().parents[2]
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_FINDINGS_BYTES = 256 * 1024


class ReviewExecutionError(ValueError):
    """Raised when a review cannot be proven from a Codex rollout."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewExecutionError(message)


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


def _read_rollout(path: Path, root: Path, selected_prefix_bytes: int | None = None) -> dict[str, Any]:
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
                    raise ReviewExecutionError("review rollout contains invalid JSON") from exc
                _require(isinstance(value, Mapping), "review rollout records must be JSON objects")
                kind = value.get("type")
                payload = value.get("payload")
                if kind == "session_meta":
                    _require(isinstance(payload, Mapping), "review rollout session metadata missing")
                    if metadata is not None:
                        raise ReviewExecutionError("review rollout contains duplicate session metadata")
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
        _require(reached_selected_prefix and after.st_size >= selected_prefix_bytes and before.st_ino == after.st_ino, "review rollout prefix was truncated or replaced")
        try:
            with path.open("rb") as stream:
                prefix = stream.read(selected_prefix_bytes)
        except OSError as exc:
            raise ReviewExecutionError("cannot reread proven rollout prefix") from exc
        _require(len(prefix) == selected_prefix_bytes and _sha256(prefix) == prefix_hasher.hexdigest(), "review rollout prefix changed while it was being read")
    _require(metadata is not None, "review rollout session metadata missing")
    _require(isinstance(metadata.get("id"), str) and metadata["id"], "review rollout identity missing")
    _require(_has_subagent_source(metadata), "review rollout is not an independent Codex subagent session")
    cwd = metadata.get("cwd")
    if cwd is not None:
        _require(Path(str(cwd)).resolve() == root.resolve(), "review rollout checkout differs from coordinator worktree")
    _require(finals, "review rollout must contain a final response")
    if selected_prefix_bytes is None:
        final = finals[-1]
    else:
        matches = [row for row in finals if row["end_offset"] == selected_prefix_bytes]
        _require(len(matches) == 1, "review rollout does not contain the proven final prefix")
        final = matches[0]
    return {"metadata": metadata, "final": final}


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
        _require(isinstance(expected, str) and SHA256_RE.fullmatch(expected) is not None, "invalid reviewed file hash")
        normalized[path] = expected
    current = graph.snapshot(root, paths)
    _require(normalized == current, "review file hashes do not match current files")
    return normalized


def verify_review(
    root: Path,
    review: Mapping[str, Any],
    *,
    implementer_session_id: str | None = None,
    sessions_root: Path | None = None,
) -> dict[str, str]:
    """Verify a review adapter and its rollout proof without writing files."""

    _require(isinstance(review, Mapping), "review receipt must be an object")
    _require(review.get("kind") in {"review", "supporting_review", "supporting_workflow_review"}, "review receipt kind required")
    _require(review.get("authority") == "coordinator_attestation", "review receipt authority required")
    reviewer = review.get("reviewer_session_id")
    _require(isinstance(reviewer, str) and reviewer, "reviewer session identity required")
    _require(isinstance(review.get("unit_id"), str) and review["unit_id"], "review unit identity required")
    _require(review.get("producer") == reviewer, "review producer must be the proven reviewer session")
    verdict = review.get("verdict")
    _require(isinstance(verdict, str) and verdict, "review verdict required")
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
    _require(report.get("schema") == "cata_raid_review_report_v1", "review report schema mismatch")
    _require(report.get("reviewer_session_id") == reviewer, "review report reviewer identity mismatch")
    _require(report.get("verdict") == verdict, "review report verdict mismatch")
    hashes = _validated_file_hashes(root, report.get("file_hashes"))
    _require(review.get("file_hashes") == hashes, "review receipt file hashes mismatch")
    _require(report.get("findings") is not None, "review report findings missing")
    _require(len(_canonical(report.get("findings"))) <= MAX_FINDINGS_BYTES, "review findings are too large")

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
    try:
        final_document = json.loads(final["text"])
    except json.JSONDecodeError as exc:
        raise ReviewExecutionError("review final response must be JSON") from exc
    _require(isinstance(final_document, Mapping), "review final response must be a JSON object")
    allowed = {"verdict", "file_hashes", "findings", "tests", "limits"}
    _require(set(final_document) <= allowed and {"verdict", "file_hashes", "findings"} <= set(final_document), "review final response has unexpected fields")
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
    try:
        final_document = json.loads(final["text"])
    except json.JSONDecodeError as exc:
        raise ReviewExecutionError("review final response must be JSON") from exc
    _require(isinstance(final_document, Mapping), "review final response must be a JSON object")
    allowed = {"verdict", "file_hashes", "findings", "tests", "limits"}
    _require(set(final_document) <= allowed and {"verdict", "file_hashes", "findings"} <= set(final_document), "review final response has unexpected fields")
    hashes = _validated_file_hashes(root, final_document.get("file_hashes"), tested_files)
    _require(isinstance(final_document.get("verdict"), str) and final_document["verdict"], "review verdict required")
    _require(len(_canonical(final_document.get("findings"))) <= MAX_FINDINGS_BYTES, "review findings are too large")
    state, _ = _state_for_unit(root)
    unit_id = state["development_graph"]["unit"]["id"]
    proof = {
        "schema": "codex_rollout_review_proof_v1",
        "rollout_path": str(rollout),
        "session_id": reviewer,
        "prefix_bytes": final["end_offset"],
        "prefix_sha256": final["prefix_sha256"],
        "final_message_bytes": len(final["text"].encode("utf-8")),
        "final_message_sha256": final["message_sha256"],
    }
    report = {
        "schema": "cata_raid_review_report_v1",
        "reviewer_session_id": reviewer,
        "verdict": final_document["verdict"],
        "file_hashes": hashes,
        "findings": final_document["findings"],
        "proof": proof,
    }
    for key in ("tests", "limits"):
        if key in final_document:
            report[key] = final_document[key]
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
        "file_hashes": hashes,
        "review_report": report_ref_target,
        "evidence": [report_ref_target],
    }
    verify_review(root, receipt, implementer_session_id=implementer_session_id, sessions_root=sessions_root)
    receipt_target = Path(receipt_path) if receipt_path is not None else report_target.with_suffix(".receipt.json")
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


def main(argv: list[str] | None = None) -> int:
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
