import math
import pytest
from tools.client_compatibility import terrain_geometry as terrain,ground_navigation as ground,lab_runtime as lab


def test_native_four_triangle_interpolation_preserves_a_plane(monkeypatch):
    v9=[2*x+3*y for x in range(129) for y in range(129)]
    v8=[2*(x+.5)+3*(y+.5) for x in range(128) for y in range(128)]
    monkeypatch.setattr(terrain,'tile',lambda *_:(b'',tuple([0]*11),0,0,1,v9,v8))
    for x,y in [(.8,.1),(.1,.8),(.8,.7),(.7,.8)]:
        point=[(32-(3+x)/128)*terrain.GRID,(32-(4+y)/128)*terrain.GRID]
        assert math.isclose(terrain.height(530,point),2*(3+x)+3*(4+y),abs_tol=1e-8)


@pytest.mark.skipif(not (lab.BASE/'data/maps/5303931.map').exists(),reason='public terrain absent')
def test_trial72_client_contact_matches_raw_terrain_not_the_buried_mesh_floor():
    ground_point=[-4183,400.416656,49.1118813]
    assert terrain.height(530,ground_point)==pytest.approx(74.45959,abs=.02)
    foot=[-4177.74,401.22,60.72]
    assert abs(terrain.height(530,foot)-foot[2])<1
    with pytest.raises(RuntimeError,match='covered|detached'):
        ground.safe_landing_patch(530,ground_point)
