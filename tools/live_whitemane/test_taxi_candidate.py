import pytest
from . import taxi
from .test_farm_loop import row


def test_an_unknown_origin_uses_the_fresh_named_native_npc_at_its_coordinates():
    r=row();r['farm_ui']['soft_interact'].update(name='Kurzel',exists=True)
    origin={'id':652,'point':r['archaeology']['world']}
    assert taxi.origin_names(r,origin)=={'Kurzel'}
    assert taxi.origin_names(r,{'id':23,'point':origin['point']})=={'Doras'}
    r['farm_ui']['soft_interact']['exists']=False
    with pytest.raises(RuntimeError,match='no named flight master candidate'):taxi.origin_names(r,origin)
    r['farm_ui']['soft_interact']['exists']=True
    origin['point']={**origin['point'],'north':3}
    with pytest.raises(RuntimeError,match='no named flight master candidate'):taxi.origin_names(r,origin)
