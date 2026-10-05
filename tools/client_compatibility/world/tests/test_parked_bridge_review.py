"""An offline scout deployment requires current owned character-selection evidence."""
import copy,json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_parked_bridge as parked


def setup(monkeypatch,tmp_path):
    root=tmp_path/'evidence';root.mkdir();old=root/'episode.json';old.write_text('{}')
    image=root/'selection.png';image.write_bytes(b'fixture image')
    monitor={'second_monitor_verified':True,'pid':12,'input_isolation':{'actor':'scout','game_pid':13}}
    monkeypatch.setattr(parked.lab,'ROOT',tmp_path)
    current_monitor=copy.deepcopy(monitor)
    monkeypatch.setattr(parked.owned_input,'focus',lambda:copy.deepcopy(current_monitor))
    review={'reviewed':True,'kind':'before_bridge_deployment','selected_character':'Harnesstwo',
        'selected_level':1,'episode_sha256':parked.lab.sha256(old),'frame':{'file':image.name,
        'sha256':parked.lab.sha256(image),'monitor':monitor}}
    path=root/'review.json'
    t=SimpleNamespace(receipt={'runtime':{'client':{'pid':12}}})
    return t,path,old,image,review


def test_current_owned_scout_selection_is_accepted_without_input(monkeypatch,tmp_path):
    t,path,old,image,data=setup(monkeypatch,tmp_path);path.write_text(json.dumps(data))
    assert parked.review(t,path,old,'before_bridge_deployment')==data


@pytest.mark.parametrize('change',['unreviewed','wrong_kind','wrong_character','wrong_level','wrong_source',
    'wrong_hash','wrong_pid','primary_monitor','wrong_actor','wrong_game','stale','outside'])
def test_unbound_stale_other_character_or_monitor_reviews_are_refused(monkeypatch,tmp_path,change):
    t,path,old,image,data=setup(monkeypatch,tmp_path)
    if change=='unreviewed':data['reviewed']=False
    elif change=='wrong_kind':data['kind']='after_bridge_deployment'
    elif change=='wrong_character':data['selected_character']='Harnessdwarf'
    elif change=='wrong_level':data['selected_level']=85
    elif change=='wrong_source':data['episode_sha256']='a'*64
    elif change=='wrong_hash':data['frame']['sha256']='a'*64
    elif change=='wrong_pid':data['frame']['monitor']['pid']=14
    elif change=='primary_monitor':data['frame']['monitor']['second_monitor_verified']=False
    elif change=='wrong_actor':data['frame']['monitor']['input_isolation']['actor']='primary'
    elif change=='wrong_game':data['frame']['monitor']['input_isolation']['game_pid']=14
    elif change=='stale':monkeypatch.setattr(parked.time,'time',lambda:image.stat().st_mtime+121)
    else:
        outside=tmp_path/'outside.png';outside.write_bytes(image.read_bytes());data['frame']['file']='../outside.png'
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError):parked.review(t,path,old,'before_bridge_deployment')
