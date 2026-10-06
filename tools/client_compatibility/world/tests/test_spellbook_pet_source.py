"""Pet recon accepts the real actor receipt schema and rejects unrelated summons."""
import json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_spellbook_pet_recon as recon


@pytest.mark.parametrize('change',[None,'actor','runtime','session','unfinished','failure','input','spell','caster'])
def test_owned_summon_source_binding(tmp_path,monkeypatch,change):
    monkeypatch.setattr(recon.lab,'ROOT',tmp_path)
    source=tmp_path/'evidence/summon/episode.json';source.parent.mkdir(parents=True)
    t=SimpleNamespace(fixture={'guid':4,'account_id':2},receipt={'runtime':{'client':{'pid':7}}})
    e={'actor':t.fixture,'runtime':t.receipt['runtime'],'native_session':'owned',
        'completed':True,'failure':None,'finished_at':42,'summon_input_sent':True,
        'native_summon_outcomes':[{'spell':688,'caster':4}]}
    if change=='actor':e['actor']={'guid':5,'account_id':3}
    elif change=='runtime':e['runtime']={'client':{'pid':8}}
    elif change=='session':e['native_session']='other'
    elif change=='unfinished':e.pop('finished_at')
    elif change=='failure':e['failure']='interrupted'
    elif change=='input':e['summon_input_sent']=False
    elif change=='spell':e['native_summon_outcomes'][0]['spell']=697
    elif change=='caster':e['native_summon_outcomes'][0]['caster']=5
    source.write_text(json.dumps(e))
    if change:
        with pytest.raises(RuntimeError):recon.summon_source(t,source,'owned')
    else:assert recon.summon_source(t,source,'owned')==e
