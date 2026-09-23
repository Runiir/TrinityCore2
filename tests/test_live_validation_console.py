"""The linear console reader keeps the historical framing rules."""
from __future__ import annotations

import json
import os
import random
import re
import select
import subprocess
import sys
import textwrap
import time

import pytest

from tools.bot_ml import live_validation_console as console
from tools.bot_ml import run_live_bot_validation as live


class ScriptedProcess:
    class Stdout:
        def fileno(self) -> int:
            return 42

    def __init__(self, chunks: list[str]) -> None:
        self.chunks = [chunk.encode() for chunk in chunks]
        self.stdout = self.Stdout()

    def poll(self):
        return None if self.chunks else 0


def quadratic_reference(process, deadline, required_text="", terminal_marker=False):
    """Verbatim framing of the pre-change reader (the regression oracle)."""
    output: list[str] = []
    fd = process.stdout.fileno()
    pre_marker_prompt_at = None
    response_started = False
    terminal_frame_started = False
    scan_tail = ""
    chunk_marker = required_text.replace("_complete", "_chunk") if terminal_marker else ""
    while process.poll() is None and time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([fd], [], [], min(1.0, remaining))
        if not ready:
            if (
                required_text
                and not response_started
                and pre_marker_prompt_at is not None
                and time.monotonic() - pre_marker_prompt_at >= 1.0
            ):
                break
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        text = chunk.decode(errors="replace")
        output.append(text)
        joined = scan_tail + text if terminal_marker else "".join(output)
        if terminal_marker:
            scan_tail = joined[-max(64, len(required_text), len(chunk_marker)):]
            response_started = response_started or bool(chunk_marker and chunk_marker in joined)
        if required_text:
            marker_index = joined.find(required_text)
            if terminal_marker:
                if terminal_frame_started:
                    if "\n" in text:
                        break
                elif marker_index >= 0:
                    terminal_frame_started = True
                    response_started = True
                    if "\n" in joined[marker_index + len(required_text):]:
                        break
            elif marker_index >= 0 and "TC>" in joined[marker_index + len(required_text):]:
                break
            if marker_index < 0 and not response_started:
                prompts = [match.start() for match in re.finditer("TC>", joined)]
                if prompts:
                    if pre_marker_prompt_at is None:
                        pre_marker_prompt_at = time.monotonic()
                    elif len(prompts) > 1:
                        break
                if pre_marker_prompt_at is not None and time.monotonic() - pre_marker_prompt_at >= 1.0:
                    break
        if not required_text and ("TC>" in text or "TC>" in joined[-16:]):
            break
    return "".join(output)


def _split(stream: str, rng: random.Random) -> list[str]:
    chunks: list[str] = []
    index = 0
    while index < len(stream):
        size = rng.choice([1, 2, 3, 5, 17, 64, 4096])
        chunks.append(stream[index:index + size])
        index += size
    return chunks


STREAMS = [
    ('{"action":"botauto_status","target_bots":10}\nTC> tail', '"target_bots"', False),
    ("echo\nTC> " + '{"trace_schema_version":1,"bots":[]}\n' + "TC> next", '"trace_schema_version"', False),
    ("unsolicited\nTC> still\nTC> late", '"diagnosis_schema_version"', False),
    ("no marker here\nTC> ", "", False),
    ('TC> {"action":"botauto_combatlog_chunk","sequence":0}\n{"action":"botauto_combatlog_complete"}\nafter', '"action":"botauto_combatlog_complete"', True),
    ('{"duration_minutes":1}' + "x" * 9000 + "TC> ", '"duration_minutes"', False),
]


@pytest.mark.parametrize("stream,marker,terminal", STREAMS)
@pytest.mark.parametrize("seed", range(6))
def test_linear_reader_matches_historical_framing(monkeypatch, stream, marker, terminal, seed):
    """Random chunk splits (including split markers/prompts) frame identically."""
    rng = random.Random(seed)
    chunks = _split(stream, rng)
    results = []
    for reader in (quadratic_reference, console.read_until_console_prompt):
        process = ScriptedProcess(list(chunks))
        monkeypatch.setattr(select, "select", lambda fds, *_args, p=process: (fds if p.chunks else [], [], []))
        monkeypatch.setattr(os, "read", lambda _fd, size, p=process: p.chunks.pop(0))
        results.append(reader(process, time.monotonic() + 0.3, marker, terminal))
    assert results[1] == results[0]


def test_harness_reader_is_the_linear_reader():
    assert live.read_until_console_prompt.__doc__ and "linear" in live.read_until_console_prompt.__doc__
    assert live.linear_read_until_console_prompt is console.read_until_console_prompt


PRODUCER = textwrap.dedent(
    """
    import os, sys, time
    body = sys.stdin.buffer.readline() and open(sys.argv[1], 'rb').read()
    out = sys.stdout.fileno()
    started = time.monotonic()
    view = memoryview(body + b"\\nTC> ")
    while view:
        view = view[os.write(out, view):]
    open(sys.argv[2], 'w').write(str(time.monotonic() - started))
    time.sleep(5)
    """
)


def test_large_trace_response_does_not_block_the_writer(tmp_path):
    """A 12 MB response is drained in well under a second (was 4.8-25 s)."""
    entry = {"sequence": 1, "action": "cast_combat_spell", "movement_planner": {"x": "y" * 5000}}
    payload = {
        "ok": True,
        "action": "botauto_trace",
        "trace_schema_version": 1,
        "bots": [{"bot_guid": guid, "entries": [entry] * 120} for guid in range(10)],
    }
    body = tmp_path / "trace.json"
    body.write_text(json.dumps(payload), encoding="utf-8")
    assert body.stat().st_size > 6_000_000
    blocked = tmp_path / "blocked.txt"
    producer = tmp_path / "producer.py"
    producer.write_text(PRODUCER, encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(producer), str(body), str(blocked)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert console.enlarge_pipe_buffer(process.stdout) >= 64 * 1024
        started = time.monotonic()
        process.stdin.write("go\n")
        process.stdin.flush()
        output = console.read_until_console_prompt(
            process, time.monotonic() + 60, '"trace_schema_version"'
        )
        elapsed = time.monotonic() - started
    finally:
        process.kill()
        process.wait()
    assert output.endswith("TC> ")
    assert len(output) >= body.stat().st_size
    assert elapsed < 3.0
    assert float(blocked.read_text()) < 3.0
