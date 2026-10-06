import copy
from types import SimpleNamespace
from . import dig_session,dig_feedback,runtime,inputs
from .test_farm_loop import row


def test_perimeter_mismatch_removes_movement_estimate_but_allows_in_place_survey(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    before=row();before['movement'].update(sequence=1,facing_radians=0)
    before['archaeology'].update(can_survey=True,site_id=185,falling=False,loot_open=False,
        looted_finds=0,successful_surveys=0)
    before['farm_ui']['survey']={'ready':True}
    sent=[]
    def observe(_):
        r=copy.deepcopy(before);r['archaeology']['successful_surveys']=int(bool(sent))
        return r
    monkeypatch.setattr(dig_session,'observe',observe)
    monkeypatch.setattr(dig_session,'telescope',lambda r,s:{'entry':206590} if r['archaeology']['successful_surveys'] else None)
    monkeypatch.setattr(dig_session.routes,'select',lambda *args:({'source':'GatherMate marker','world':{
        'instance':1,'north':20,'west':0},'arrived':False},0))
    def constrain(*args,**kwargs):
        raise RuntimeError('current point does not match the active public digsite perimeter')
    monkeypatch.setattr(dig_session,'constrain',constrain)
    def choose(state):
        assert not state['instrument_current'] and state['guide_source'] is None
        assert 'perimeter' in state['guide_error']
        return 'survey',{'model':'fake'},{},{}
    monkeypatch.setattr(dig_session,'choose',choose)
    monkeypatch.setattr(inputs,'execute',lambda title,action,args:sent.append((action,args)) or {})
    def survey(folder,before,send,observer,telescope):
        return {'inputs':[send(before)],'after':observer(folder/'after.png')}
    monkeypatch.setattr(dig_feedback,'survey',survey)
    monkeypatch.setattr(dig_session,'walk',lambda *_ ,**kw:(_ for _ in ()).throw(AssertionError('unverified movement')))
    result=dig_session.run(SimpleNamespace(output=tmp_path/'dig',steps=1,loot_at=None,auto_loot=True,graph=None))
    assert result['failure'] is None and len(sent)==1
    assert sent[0][0]=='button' and sent[0][1]['button']==8
