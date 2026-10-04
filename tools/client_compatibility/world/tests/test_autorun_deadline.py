"""Diagnostic I/O cannot extend a normally bounded autorun input interval."""
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_ground_modes as module


@pytest.mark.parametrize('partial_failure',[False,True])
def test_autorun_stops_without_reading_the_journal(monkeypatch,partial_failure):
    events=[];row={}
    def key(value,hold):
        events.append(('key',value,hold))
        if partial_failure and len(events)==1:raise RuntimeError('partial sender failure')
    t=SimpleNamespace(io=SimpleNamespace(key=key),persist=lambda:None,
        ground_bar={'keys':{'MOVEFORWARD':['W']}})
    monkeypatch.setattr(module.time,'sleep',lambda seconds:events.append(('wait',seconds)))
    monkeypatch.setattr(module,'entries',lambda *_:pytest.fail('read before movement stop'))
    if partial_failure:
        with pytest.raises(RuntimeError,match='partial sender failure'):module.autorun_inputs(t,'Num_Lock',row)
        assert events==[('key','Num_Lock',.4),('key','w',.2)]
        assert row['input_transport'][0]['qualification'] is False
    else:
        module.autorun_inputs(t,'Num_Lock',row)
        assert events==[('key','Num_Lock',.4),('wait',1.2),('key','Num_Lock',.4)]
        assert [r['toggle'] for r in row['input_transport']]==['start','stop']
