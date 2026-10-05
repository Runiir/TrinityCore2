from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_chat_voice as module


@pytest.mark.parametrize('binding,change',[
    (module.ACTION,{}),(module.ACTION,{'muted':False}),
    (module.ACTION,{'logged_in':True}),(module.ACTION,{'deafened':True}),
    ('TOGGLEFPS',{}),
])
def test_local_mute_requires_owned_binding_and_only_expected_voice_change(monkeypatch,binding,change):
    before={'available':True,'muted':False,'deafened':False,'logged_in':False}
    voice={**before,'muted':True,**change};results=[]
    monkeypatch.setattr(module,'detail',lambda t,label:{'voice':voice})
    def step(label,goal,actions,oracle,**kwargs):
        assert actions['mute']=={'kind':'key','value':'ctrl+shift+F12','hold':1.2}
        result=oracle({'binding_probe':binding},{},'mute');results.append(result);return result
    t=SimpleNamespace(step=step)
    if binding==module.ACTION and not change:
        module.toggle(t,before,True,'chat.mute_voice')
        assert all(results[0]['oracle']['checks'].values())
    else:
        with pytest.raises(RuntimeError):module.toggle(t,before,True,'chat.mute_voice')
        assert results[0]['status']=='client_or_protocol_failure'
