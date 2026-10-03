"""Changed layouts must never combine stale button coordinates with new pages."""
from types import SimpleNamespace
from PIL import Image
import pytest
from tools.client_compatibility import interaction_operations as module
from tools.client_compatibility.observation import interactions
from tools.second_client import ctl


@pytest.mark.parametrize('changes_count',[True,False])
def test_changed_control_catalog_discards_old_pages(tmp_path,monkeypatch,changes_count):
    def sample(page,revision,rows,total=24):
        return {'guid':'Player-1-00000001','mode':'controls','panels':['CharacterFrame'],
            'page':page,'page_size':12,'control_count':total,'control_snapshot':revision,'controls':rows,'sequence':page}
    old=[{'name':'old coordinates'}];first=[{'name':'new first page'}];second=[{'name':'new second page'}]
    samples=[sample(1,1,old)]
    if changes_count:samples.append(sample(1,2,first,12))
    else:samples.extend([sample(2,2,second),sample(1,2,first)])
    states=iter(samples);t=SimpleNamespace(out=tmp_path,guid='Player-1-00000001',receipt={},persist=lambda:None)
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    monkeypatch.setattr(ctl,'shot',lambda path:Image.new('RGB',(1,1)).save(path))
    monkeypatch.setattr(interactions,'decode_image',lambda _:next(states))
    assert module.controls(t)==first+([] if changes_count else second)


def test_reuse_requires_an_observed_matching_complete_catalog_and_retains_current_frame(tmp_path,monkeypatch):
    panels=['CharacterFrame'];rows=[{'name':'verified button'}]
    state={'guid':'Player-1-00000001','mode':'controls','panels':panels,'page':1,'page_size':12,
        'control_count':12,'control_snapshot':9,'controls':rows,'sequence':1}
    t=SimpleNamespace(out=tmp_path,guid=state['guid'],receipt={},persist=lambda:None)
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    monkeypatch.setattr(ctl,'shot',lambda path:Image.new('RGB',(1,1)).save(path))
    monkeypatch.setattr(interactions,'decode_image',lambda _:state)
    assert module.controls(t)==rows
    state['sequence']=2
    assert module.controls(t)==rows
    assert t.receipt['control_catalog_reuse'][0]['sequence']==2
    assert (tmp_path/t.receipt['control_catalog_reuse'][0]['frame']['file']).is_file()
    state['control_snapshot']=10;state['controls']=[{'name':'changed button'}]
    assert module.controls(t)==state['controls']
    assert len(t.receipt['control_catalog_reuse'])==1
