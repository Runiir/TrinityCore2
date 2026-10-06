"""Short local movement alternatives after an observed blocked travel command."""
import math
from tools.client_compatibility import model_collision


def candidates(row,target):
    world=row['archaeology']['world'];heading=row['movement']['facing_radians']
    if target and target.get('instance')==world['instance']:
        heading=math.atan2(target['west']-world['west'],target['north']-world['north'])
    pose=row.get('owned_pose');result={}
    for name,offset in [('step_left',math.pi/2),('step_right',-math.pi/2),
                        ('step_back',math.pi),('step_forward',0)]:
        direction=heading+offset
        point={'instance':world['instance'],'north':world['north']+4*math.cos(direction),
            'west':world['west']+4*math.sin(direction)}
        clear=None
        if pose:
            start=[world['north'],world['west'],pose['height_yards']]
            end=[point['north'],point['west'],pose['height_yards']]
            clear=model_collision.clear_body_segment(world['instance'],start,end)
        result[name]={'target':point,'distance_yards':4,'reference_collision_clear':clear,
            'reference_matches_live_assets':False}
    return result
