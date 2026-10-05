"""Unchanged settings on a stale UI frame cannot qualify reload persistence."""
import pytest
from tools.client_compatibility.interaction_settings_persistence import reload_checks


def test_command_entry_reaches_suite_with_supported_settings_constructor(monkeypatch,tmp_path):
    import inspect,sys
    from contextlib import nullcontext
    from tools.client_compatibility import interaction_settings_persistence as module
    signature=inspect.signature(module.SettingsTrial);called=[]
    class FakeTrial:
        def __init__(self,*args,**kwargs):
            signature.bind(*args,**kwargs)
            self.receipt={'completed':False,'failure':None}
        def persist(self):pass
    def native(trial,operations,preserve_settings):
        called.append((operations,preserve_settings))
    monkeypatch.setattr(module,'SettingsTrial',FakeTrial)
    monkeypatch.setattr(module,'native_suite',native)
    monkeypatch.setattr(module,'actor',lambda name:nullcontext())
    monkeypatch.setattr(module.lab,'ROOT',tmp_path)
    monkeypatch.setattr(sys,'argv',['settings-persistence','--output',str(tmp_path/'evidence/run')])
    module.main()
    assert called==[(module.suite,False)]


def fixture():
    return {'sequence':500,'guid':'owned'},{'sequence':10,'guid':'owned'},'same','same',[
        {'selected_text':'/reload','matches':True,'submitted':True}],'owned'


def test_owned_verified_reload_with_new_observer_generation_passes():
    assert all(reload_checks(*fixture()).values())


@pytest.mark.parametrize('change',['stale','foreign','new_session','unsubmitted','wrong_command','mismatched_text'])
def test_stale_or_unattributed_reload_cannot_claim_persistence(change):
    before,after,session,current,rows,guid=fixture()
    if change=='stale':after['sequence']=501
    elif change=='foreign':after['guid']='other'
    elif change=='new_session':current='other'
    elif change=='unsubmitted':rows[0]['submitted']=False
    elif change=='wrong_command':rows[0]['selected_text']='/logout'
    else:rows[0]['matches']=False
    assert not all(reload_checks(before,after,session,current,rows,guid).values())
