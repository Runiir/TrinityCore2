import subprocess
import sys
import shutil
from contextlib import nullcontext

import pytest

from tools.raid_program.shared_instance_console import ConsoleTransport


@pytest.fixture
def console(tmp_path):
    path = tmp_path / "console.log"
    # A real child writes the command boundary and responds in fragments.
    child = '''import sys,time
print('TC>', flush=True)
for line in sys.stdin:
    verb=line.split()[1]
    if verb=='silent': continue
    action='botauto_'+verb
    if verb=='start' and line.split()[2]!='rejected':
        action='botauto_status'
    if verb=='combatlog' and line.split()[2]!='rejected':
        print('{"action":"botauto_combatlog_chunk"}', flush=True)
        if line.split()[2]=='incomplete':
            print('TC>',flush=True)
            continue
        time.sleep(.02)
        action+='_complete'
    ok='false' if line.split()[2]=='rejected' else 'true'
    print('{"ok":'+ok+',"action":"'+action+'"}',flush=True)
    print('TC>',flush=True)
'''
    with path.open("wb") as log:
        process = subprocess.Popen([sys.executable, "-u", "-c", child],
                                   stdin=subprocess.PIPE, stdout=log, stderr=log)
        transport = ConsoleTransport(process, path)
        try:
            transport.wait_ready(2)
            yield transport
        finally:
            process.terminate()
            process.wait(timeout=2)
            process.stdin.close()


def test_fresh_boundaries_and_chunk_completion(console):
    first, code, timeout = console(".botauto status test", 2)
    assert not code and not timeout and first.count('"action"') == 1
    second, code, timeout = console(".botauto combatlog test", 2)
    assert not code and not timeout
    assert "botauto_status" not in second
    assert "botauto_combatlog_chunk" in second and "botauto_combatlog_complete" in second


def test_timeout_poisoning_prevents_late_reply_reuse(console):
    _, code, timeout = console(".botauto silent test", 0.05)
    assert code and timeout
    assert console(".botauto status test", 2) == ("", 1, False)


@pytest.mark.parametrize("cohort,action", [("test", "botauto_status"), ("rejected", "botauto_start")])
def test_native_start_response_variants_complete_without_timeout(console, cohort, action):
    raw, code, timed_out = console(f".botauto start {cohort}", 2)
    assert not code and not timed_out
    assert f'"action":"{action}"' in raw
    assert console(".botauto status test", 2)[1:] == (0, False)


def test_native_combatlog_rejection_is_a_reply_not_a_timeout(console):
    raw, code, timed_out = console(".botauto combatlog rejected", 2)
    assert not code and not timed_out
    assert '"action":"botauto_combatlog"' in raw
    assert console(".botauto status test", 2)[1:] == (0, False)


def test_combatlog_chunk_without_completion_is_insufficient(console):
    _, code, timed_out = console(".botauto combatlog incomplete", 0.1)
    assert code and timed_out


def test_command_injection_rejected(console):
    with pytest.raises(ValueError):
        console(".botauto status test\nserver exit", 2)


def test_owned_startup_failure_is_closed_and_attributed(tmp_path, monkeypatch):
    from tools.raid_program import shared_instance_console as module

    monkeypatch.setattr(module, "live_validation_lock", lambda *_: nullcontext())
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs:
                        subprocess.CompletedProcess([], 1))
    binary = tmp_path / "fake-server"
    binary.write_text(f"#!{sys.executable}\nraise SystemExit(2)\n")
    binary.chmod(0o700)
    lifecycle = {}
    with pytest.raises(RuntimeError, match="exited during startup"):
        with module.owned_console(repository=tmp_path, source=tmp_path,
                                  binary=binary, config=tmp_path / "conf",
                                  output_dir=tmp_path, startup_timeout_sec=2,
                                  lifecycle=lifecycle):
            pytest.fail("failed child reached native admission")
    assert lifecycle["server_started"] is True
    assert lifecycle["process_exited"] is True
    assert lifecycle["process_return_code"] == 2


def test_existing_worldserver_blocks_provisioning(tmp_path, monkeypatch):
    from tools.raid_program import shared_instance_console as module

    monkeypatch.setattr(module, "live_validation_lock", lambda *_: nullcontext())
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs:
                        subprocess.CompletedProcess([], 0))
    with pytest.raises(RuntimeError, match="worldserver already exists"):
        with module.owned_console(repository=tmp_path, source=tmp_path,
                                  binary=tmp_path / "unused", config=tmp_path / "unused",
                                  output_dir=tmp_path,
                                  before_launch=lambda: pytest.fail("foreign server was provisioned")):
            pytest.fail("foreign server was admitted")


def test_executed_inode_rejects_binary_replacement_even_if_path_restored(tmp_path):
    from tools.raid_program.shared_instance_console import verify_process_binary
    from tools.raid_program.shared_instance_fixture import sha256

    original, replacement = sys.executable, shutil.which("tail")
    assert original and replacement
    # Multicall coreutils dispatches from the executable basename too.
    binary = tmp_path / "tail"
    shutil.copyfile(original, binary)
    binary.chmod(0o700)
    expected = sha256(binary)
    # Simulate replacement between verified preflight and Popen.
    binary.unlink()
    shutil.copyfile(replacement, binary)
    binary.chmod(0o700)
    process = subprocess.Popen(["tail", "-f", "/dev/null"], executable=str(binary),
                               stdout=subprocess.DEVNULL)
    try:
        # Restoring the pathname must not hide that different bytes executed.
        binary.unlink()
        shutil.copyfile(original, binary)
        assert sha256(binary) == expected
        with pytest.raises(RuntimeError, match="executable differs"):
            verify_process_binary(process, expected)
    finally:
        process.terminate()
        process.wait(timeout=2)
