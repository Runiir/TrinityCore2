"""Play-mode evidence guard: human play sessions never become validation evidence.

Play mode (docs/bot_raids/human_play_mode.md) lets humans raid with trained bots.
Its runs are recorded for later ML training, but they must never enter the
scoreboard, verdicts, graph acceptance or the evidence archives. The C++ side
tags cohort payloads with "cohort_purpose": "validation" today and
"cohort_purpose": "play" plus "play_session_id" in play mode.

A payload or run is play when any of these holds:
  - a JSON object at any depth has "cohort_purpose" == "play";
  - a JSON object at any depth has "play_session_id" set to a non-empty string;
  - a run directory or tarball contains a file named play_session.json;
  - the path lies under artifacts/play_sessions/.
"cohort_purpose": "validation", or no marker at all, is not play.

Files are scanned as raw bytes with compiled regexes in bounded chunks
(latest.json is ~26 MB and report.json ~32 MB), so they are never parsed.
Markers inside JSON-encoded strings (escaped quotes) also count: a guard
refuses rather than misses. In-memory objects are walked. A str that starts
with "{" or "[" is scanned as JSON text; any other str is a path.
"""
from __future__ import annotations

import os
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

PLAY_SESSION_FILE = "play_session.json"
PLAY_SESSIONS_PARTS = ("artifacts", "play_sessions")
PLAY_EXCLUSION_REASON = "play_mode_run"  # scoreboard exclusion for a kill record carrying a play marker
PLAY_TERMINAL_REASON = "play_mode"  # graph run terminal class that can never accept anything
PLAY_MODE_CONFIG_KEY = "BotWorld.PlayMode.Enable"
JSON_SUFFIXES = (".json", ".jsonl", ".ndjson")
TARBALL_SUFFIXES = (".tar.gz", ".tgz", ".tar")

_PURPOSE_NEEDLE = b"cohort_purpose"
_SESSION_NEEDLE = b"play_session_id"
_PURPOSE = re.compile(rb'\\*"cohort_purpose\\*"\s*:\s*\\*"play\\*"')
_SESSION = re.compile(rb'\\*"play_session_id\\*"\s*:\s*\\*"([^"\\]+)\\*"')
_CONFIG_VALUE = re.compile(rf"^\s*{re.escape(PLAY_MODE_CONFIG_KEY)}\s*=\s*(?P<value>[^\s#]+)", re.MULTILINE)
_CHUNK = 1 << 20
_OVERLAP = 4096  # a marker split across two chunks is found whole in the next window
_MAX_REASONS = 8


class PlayModeRefused(ValueError):
    """Base class for play-mode refusals."""


class PlayModeEvidenceRefused(PlayModeRefused):
    """Play-mode evidence reached a scoring, acceptance or archive path."""


class PlayModeConfigRefused(PlayModeRefused):
    """A validation run was asked to start from a config that enables play mode."""


def _under_play_sessions(path: PurePosixPath | Path) -> bool:
    parts = path.parts
    return any(parts[index:index + 2] == PLAY_SESSIONS_PARTS for index in range(len(parts) - 1))


def _scan_bytes(data: bytes, source: str, reasons: dict[str, None]) -> None:
    if _PURPOSE_NEEDLE in data and _PURPOSE.search(data):
        reasons[f'{source}: "cohort_purpose": "play"'] = None
    if _SESSION_NEEDLE in data:
        for match in _SESSION.finditer(data):
            session = match.group(1).decode("utf-8", "replace")
            reasons[f'{source}: "play_session_id": "{session}"'] = None


def _scan_stream(stream: BinaryIO, source: str, reasons: dict[str, None]) -> None:
    tail = b""
    while block := stream.read(_CHUNK):
        window = tail + block
        _scan_bytes(window, source, reasons)
        tail = window[-_OVERLAP:]


def _scan_file(path: Path, reasons: dict[str, None]) -> None:
    try:
        with path.open("rb") as stream:
            _scan_stream(stream, str(path), reasons)
    except OSError:
        return


def _scan_tarball(path: Path, reasons: dict[str, None]) -> None:
    try:
        with tarfile.open(path, "r|*") as tar:
            for member in tar:
                name = PurePosixPath(member.name)
                source = f"{path}!{member.name}"
                if name.name == PLAY_SESSION_FILE:
                    reasons[f"{source}: play session file"] = None
                if _under_play_sessions(name):
                    reasons[f"{source}: member under artifacts/play_sessions/"] = None
                if member.isfile() and member.name.endswith(JSON_SUFFIXES):
                    stream = tar.extractfile(member)
                    if stream is not None:
                        _scan_stream(stream, source, reasons)
    except (OSError, tarfile.TarError):
        return


def _path_markers(path: Path, reasons: dict[str, None]) -> None:
    for candidate in (path, path.resolve()):
        if _under_play_sessions(candidate):
            reasons[f"{path}: under artifacts/play_sessions/"] = None
    if path.name == PLAY_SESSION_FILE:
        reasons[f"{path}: play session file"] = None
    if path.is_dir():
        for folder, _, files in os.walk(path):
            for name in sorted(files):
                child = Path(folder) / name
                if name == PLAY_SESSION_FILE:
                    reasons[f"{child}: play session file"] = None
                elif name.endswith(JSON_SUFFIXES):
                    _scan_file(child, reasons)
    elif path.is_file():
        if path.name.endswith(TARBALL_SUFFIXES):
            _scan_tarball(path, reasons)
        else:
            _scan_file(path, reasons)


def _walk(value: Any, reasons: dict[str, None]) -> None:
    stack: list[tuple[Any, str]] = [(value, "$")]
    while stack:
        node, where = stack.pop()
        if isinstance(node, dict):
            if node.get("cohort_purpose") == "play":
                reasons[f'{where}: "cohort_purpose": "play"'] = None
            session = node.get("play_session_id")
            if isinstance(session, str) and session:
                reasons[f'{where}: "play_session_id": "{session}"'] = None
            stack.extend((child, f"{where}.{key}") for key, child in node.items()
                         if isinstance(child, (dict, list, tuple)))
        elif isinstance(node, (list, tuple)):
            stack.extend((child, f"{where}[{index}]") for index, child in enumerate(node)
                         if isinstance(child, (dict, list, tuple)))


def find_play_markers(obj_or_path: Any) -> list[str]:
    """Human-readable reasons the object, file, run dir or tarball is play-mode evidence; [] when it is not."""
    reasons: dict[str, None] = {}
    if isinstance(obj_or_path, (bytes, bytearray)):
        _scan_bytes(bytes(obj_or_path), "payload", reasons)
    elif isinstance(obj_or_path, str) and obj_or_path.lstrip()[:1] in ("{", "["):
        _scan_bytes(obj_or_path.encode("utf-8"), "payload", reasons)
    elif isinstance(obj_or_path, (str, os.PathLike)):
        _path_markers(Path(obj_or_path), reasons)
    else:
        _walk(obj_or_path, reasons)
    return list(reasons)


def is_play(obj_or_path: Any) -> bool:
    return bool(find_play_markers(obj_or_path))


def refuse_play(obj_or_path: Any, context: str) -> None:
    """Raise PlayModeEvidenceRefused when the object or path carries any play marker."""
    reasons = find_play_markers(obj_or_path)
    if reasons:
        shown = "; ".join(reasons[:_MAX_REASONS]) + (f"; ... {len(reasons) - _MAX_REASONS} more"
                                                      if len(reasons) > _MAX_REASONS else "")
        raise PlayModeEvidenceRefused(
            f"{context}: refusing play-mode evidence ({shown}). Play runs are recorded for ML only and never "
            "enter the scoreboard, verdicts, graph acceptance or evidence archives.")


def play_mode_config_enabled(text: str) -> bool:
    """True when any uncommented BotWorld.PlayMode.Enable line is 1/true/yes/on (quotes allowed)."""
    return any(match.group("value").strip().strip('"').lower() in {"1", "true", "yes", "on"}
               for match in _CONFIG_VALUE.finditer(text))


def refuse_play_mode_config(text: str, source: str) -> None:
    """Validation never starts from a config that enables play mode."""
    if play_mode_config_enabled(text):
        raise PlayModeConfigRefused(
            f"{source} sets {PLAY_MODE_CONFIG_KEY} = 1: validation runs never start in play mode. "
            f"Use a validation config with {PLAY_MODE_CONFIG_KEY} = 0 (play sessions use make host-world-play).")
