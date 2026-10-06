import math
import pytest
from . import flight_path


def column(x,z):return {'north':x,'west':0,'terrain_height':z,'support_height':z,'highest_surface':z}


def test_a_clear_slope_is_one_diagonal_instead_of_an_ascent_and_horizontal_leg():
    path=flight_path.envelope([column(x,10+x/10) for x in range(0,101,5)],[0,0,10],3,local_floor=True)
    assert len(path)==2 and path[0]['height_yards']==13 and path[-1]['height_yards']==23
    aim=flight_path.aim(path,{'north':0,'west':0},13,30,.1)
    assert aim['pitch_radians']==pytest.approx(math.atan(.1))
    aim=flight_path.aim(path,{'north':50,'west':0},18,30,.1)
    assert aim['pitch_radians']==pytest.approx(math.atan(.1))


def test_the_shortest_envelope_preserves_obstacle_peaks_and_cuts_out_valleys():
    columns=[column(0,10),column(10,5),column(20,30),column(30,10),column(40,20),column(50,10)]
    path=flight_path.envelope(columns,[0,0,10],3,local_floor=True)
    assert [p['north'] for p in path]==[0,20,40,50]
    for c in columns:
        a,b=next((a,b) for a,b in zip(path,path[1:]) if a['north']<=c['north']<=b['north'])
        f=(c['north']-a['north'])/(b['north']-a['north'])
        assert a['height_yards']+(b['height_yards']-a['height_yards'])*f>=c['terrain_height']+3
    aim=flight_path.aim(path,{'north':40,'west':0},23,20,.1)
    assert aim['pitch_radians']<0
