"""Linear-time worldserver console framing for the live validation harness.

The worldserver prints every CLI response with ``printf`` + ``fflush`` on the
world thread (``CliRunnable.cpp`` ``utf8print``).  When stdout is a pipe the
world thread blocks until the harness has drained all but the last pipe buffer
of the response, so the harness read rate bounds the world-thread stall.

The previous reader re-joined, sliced and scanned the whole accumulated
response for every 4 KiB chunk.  That is quadratic: a 12.65 MB
``.botauto trace all 128 delta`` response took 4.8-25 s to read on the
validation host, and the world thread was frozen for that long.  This reader
keeps the exact framing rules but scans only a bounded tail plus the new
chunk, so its cost is linear in the response size.
"""
from __future__ import annotations

import os
import select
import subprocess
import time
from typing import Any

CONSOLE_PROMPT = "TC>"
PRE_MARKER_PROMPT_GRACE_SEC = 1.0
CONSOLE_READ_CHUNK_BYTES = 64 * 1024
# Linux caps unprivileged pipes at /proc/sys/fs/pipe-max-size (1 MiB by
# default).  A 1 MiB buffer lets status/diagnose-sized responses complete
# without the world thread ever waiting on the harness.
CONSOLE_PIPE_BUFFER_BYTES = 1024 * 1024
_F_SETPIPE_SZ = 1031
_F_GETPIPE_SZ = 1032


def enlarge_pipe_buffer(file_obj: Any, size: int = CONSOLE_PIPE_BUFFER_BYTES) -> int:
    """Best-effort pipe enlargement; return the resulting size or 0."""
    try:
        import fcntl
    except ImportError:  # pragma: no cover - non-POSIX
        return 0
    try:
        fd = file_obj.fileno()
    except (AttributeError, OSError, ValueError):
        return 0
    set_op = getattr(fcntl, "F_SETPIPE_SZ", _F_SETPIPE_SZ)
    get_op = getattr(fcntl, "F_GETPIPE_SZ", _F_GETPIPE_SZ)
    try:
        fcntl.fcntl(fd, set_op, int(size))
    except OSError:
        pass
    try:
        return int(fcntl.fcntl(fd, get_op))
    except OSError:
        return 0


def _count_new_prompts(window: str, old_tail_len: int) -> int:
    """Count prompts in ``window`` that end inside the new text only."""
    count = 0
    start = max(0, old_tail_len - len(CONSOLE_PROMPT) + 1)
    while True:
        index = window.find(CONSOLE_PROMPT, start)
        if index < 0:
            return count
        count += 1
        start = index + len(CONSOLE_PROMPT)


def read_until_console_prompt(
    process: subprocess.Popen[str],
    deadline: float,
    required_text: str = "",
    terminal_marker: bool = False,
    *,
    grace_sec: float | None = None,
) -> str:
    """Read one console response with the historical framing rules.

    * No marker: stop at the first prompt.
    * Structured marker: stop at the first prompt after the first marker.
      Prompts before the marker can be the echo of the command itself; a
      second pre-marker prompt, or one prompt followed by
      ``PRE_MARKER_PROMPT_GRACE_SEC`` of silence, ends the read so the
      parser can fail closed.
    * Terminal (chunked export) marker: stop at the newline that ends the
      marker frame; no trailing prompt is required.
    """
    if process.stdout is None:
        return ""
    grace = PRE_MARKER_PROMPT_GRACE_SEC if grace_sec is None else grace_sec
    output: list[str] = []
    fd = process.stdout.fileno()
    pre_marker_prompt_at: float | None = None
    response_started = False
    terminal_frame_started = False
    scan_tail = ""
    chunk_marker = required_text.replace("_complete", "_chunk") if terminal_marker else ""
    # Bounded state for the non-terminal scan.  ``tail`` always holds the
    # last ``tail_keep`` characters of the accumulated output.
    tail_keep = max(len(required_text), len(CONSOLE_PROMPT), 16)
    tail = ""
    marker_found = False
    post_marker_tail = ""
    prompt_count = 0
    while process.poll() is None and time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([fd], [], [], min(1.0, remaining))
        if not ready:
            if (
                required_text
                and not response_started
                and pre_marker_prompt_at is not None
                and time.monotonic() - pre_marker_prompt_at >= grace
            ):
                break
            continue
        chunk = os.read(fd, CONSOLE_READ_CHUNK_BYTES)
        if not chunk:
            break
        text = chunk.decode(errors="replace")
        output.append(text)
        window = tail + text
        old_tail_len = len(tail)
        tail = window[-tail_keep:]
        if not required_text:
            # New text plus the prompt-length overlap covers every prompt
            # the historical ``text``/``joined[-16:]`` check could see.
            if CONSOLE_PROMPT in window[max(0, old_tail_len - len(CONSOLE_PROMPT) + 1):]:
                break
            continue
        if terminal_marker:
            joined = scan_tail + text
            scan_tail = joined[-max(64, len(required_text), len(chunk_marker)):]
            response_started = response_started or bool(chunk_marker and chunk_marker in joined)
            marker_index = joined.find(required_text)
            # The action marker may end one read while the JSON envelope
            # continues in the next.  Native frames end at newline; a
            # trailing console prompt is not required for these exports.
            if terminal_frame_started:
                if "\n" in text:
                    break
            elif marker_index >= 0:
                terminal_frame_started = True
                response_started = True
                if "\n" in joined[marker_index + len(required_text):]:
                    break
            if marker_index < 0 and not response_started:
                prompts = joined.count(CONSOLE_PROMPT)
                if prompts:
                    if pre_marker_prompt_at is None:
                        pre_marker_prompt_at = time.monotonic()
                    elif prompts > 1:
                        break
                if (
                    pre_marker_prompt_at is not None
                    and time.monotonic() - pre_marker_prompt_at >= grace
                ):
                    break
            continue
        if marker_found:
            scan = post_marker_tail + text
            if CONSOLE_PROMPT in scan:
                break
            post_marker_tail = scan[-(len(CONSOLE_PROMPT) - 1):]
            continue
        marker_index = window.find(required_text)
        if marker_index >= 0:
            marker_found = True
            after = window[marker_index + len(required_text):]
            if CONSOLE_PROMPT in after:
                break
            post_marker_tail = after[-(len(CONSOLE_PROMPT) - 1):]
            continue
        # A prompt before the required marker can be the console echo for
        # the command that is still streaming.  Ignore it and wait for a
        # prompt after the marker so the next command cannot interleave
        # with this response.  If the marker never arrives, the bounded read
        # returns incomplete output and the parser fails closed.
        prompt_count += _count_new_prompts(window, old_tail_len)
        if prompt_count:
            if pre_marker_prompt_at is None:
                pre_marker_prompt_at = time.monotonic()
            elif prompt_count > 1:
                break
        if (
            pre_marker_prompt_at is not None
            and time.monotonic() - pre_marker_prompt_at >= grace
        ):
            break
    return "".join(output)
