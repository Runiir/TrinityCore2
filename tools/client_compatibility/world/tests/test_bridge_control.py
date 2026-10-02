"""An independent bridge deployment must reject stale or changed binaries."""
import json
import pytest
from tools.client_compatibility.world import control


def test_native_launch_rejects_source_and_binary_drift(tmp_path,monkeypatch):
    binary=tmp_path/'client442_bridge';binary.write_bytes(b'owned bridge fixture')
    receipt=tmp_path/'receipt.json'
    monkeypatch.setattr(control,'BINARY',binary)
    monkeypatch.setattr(control,'RECEIPT',receipt)
    monkeypatch.setattr(control,'source_digest',lambda:'first source')
    receipt.write_text(json.dumps({'source_digest':'first source','binary_sha256':control.lab.sha256(binary)}))
    command,_=control.native_command()
    assert command[0]==str(binary) and 'worldserver' not in command
    monkeypatch.setattr(control,'source_digest',lambda:'changed source')
    with pytest.raises(RuntimeError,match='rebuild'):control.native_command()
    monkeypatch.setattr(control,'source_digest',lambda:'first source')
    binary.write_bytes(b'changed binary')
    with pytest.raises(RuntimeError,match='rebuild'):control.native_command()


def test_native_launch_requires_build_and_bounded_resources(tmp_path,monkeypatch):
    monkeypatch.setattr(control,'BINARY',tmp_path/'absent')
    with pytest.raises(RuntimeError,match='build'):control.native_command()
    for workers,maximum in [(0,64),(33,64),(4,1),(4,1025)]:
        with pytest.raises(ValueError,match='bound'):control.native_command(workers,maximum)
