import math
from tools.client_compatibility.travel_inputs import face
from tools.client_compatibility.observation.archaeology import angle_error


def test_real_failed_heading_converges_with_fifteen_fps_key_quantization(monkeypatch):
    from tools.client_compatibility import travel_inputs
    monkeypatch.setattr(travel_inputs.time,'sleep',lambda _:None)
    position=[-3008.395996,1205.061035,229.458923,1.457702398]
    goal=[-2985.91675,1692.75,69.3390198]
    class Observer:
        def poll(self):return {'position':position}
    class Inputs:
        def key(self,key,hold):
            # The actual failed packet trace alternated around 1.44 and 1.65.
            rotation=max(1,round(hold*15))*math.pi/15
            position[3]=(position[3]+(rotation if key=='a' else -rotation))%math.tau
    assert face(Inputs(),Observer(),goal)==[]
    position[3]=0
    assert face(Inputs(),Observer(),goal)
    heading=math.atan2(goal[1]-position[1],goal[0]-position[0])
    assert abs(angle_error(heading,position[3]))<.12
    assert 21*math.sin(.12)<3  # local survey leg's arrival radius
