"""A selected observer page must return to the ordinary passive cycle."""
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_quest_settings as settings


@pytest.mark.parametrize('fails',[False,True])
def test_read_only_page_selection_always_restores_cycle(monkeypatch,fails):
    calls=[];t=SimpleNamespace(receipt={},persist=lambda:None,observe=lambda label:calls.append(('observe',label)))
    monkeypatch.setattr(settings,'command',lambda trial,text:calls.append(('command',text)))
    def read(trial,label):
        calls.append(('read',label))
        if fails:raise RuntimeError('decode failed')
        return {'cvars':{'softTargetInteract':'1'}}
    monkeypatch.setattr(settings,'detail',read)
    if fails:
        with pytest.raises(RuntimeError,match='decode failed'):settings.snapshot(t,'settings_check')
    else:assert settings.snapshot(t,'settings_check')=={'cvars':{'softTargetInteract':'1'}}
    assert calls==[('command','/tcui settings'),('read','settings_check'),('command','/tcui'),
        ('observe','settings_check_passive_cycle_restored')]
    assert t.receipt['quest_settings_diagnostics'][0]['qualified'] is False
