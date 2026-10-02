"""Shutdown must not escalate a reused PID; a verified hung client is bounded."""
import signal
from pathlib import Path
import pytest
from tools.client_compatibility import lab_runtime as lab


@pytest.mark.parametrize('reused',[False,True])
def test_hung_client_escalation_is_bound_to_original_identity(tmp_path,monkeypatch,reused):
    proc=tmp_path/'proc';member=proc/'555';member.mkdir(parents=True)
    stat=member/'stat';stat.write_text('555 (gamescope) S 1 555 555 0\n')
    (member/'comm').write_text('gamescope\n');(member/'cmdline').write_bytes(b'owned fixture')
    original={'pid':555,'start_ticks':'123'};queries=[];signals=[]
    def owned(kind):
        queries.append(kind)
        return {**original,'start_ticks':'999'} if reused and len(queries)>1 else original
    def send(pid,sig):
        signals.append((pid,sig))
        if sig==signal.SIGKILL:stat.write_text('555 (gamescope) Z 1 555 555 0\n')
    monkeypatch.setattr(lab,'owned_process',owned)
    monkeypatch.setattr(lab,'Path',lambda value:proc if value=='/proc' else Path(value))
    monkeypatch.setattr(lab.os,'killpg',send);monkeypatch.setattr(lab.time,'sleep',lambda _:None)
    if reused:
        with pytest.raises(RuntimeError,match='identity changed'):lab.stop('client')
        assert signals==[(555,signal.SIGTERM)]
    else:
        lab.stop('client');assert signals==[(555,signal.SIGTERM),(555,signal.SIGKILL)]
