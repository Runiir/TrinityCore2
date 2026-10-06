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
        site_id=row['archaeology'].get('site_id') if row['archaeology'].get('can_survey') else None
        if site_id is not None:
            from .boundaries import constrain
            bounded=constrain(row,{'world':point,'source':'short obstacle recovery',
                'color':'green','distance_yards':4,'arrived':False,'arrival_tolerance_yards':.5})
            point=bounded['world']
        clear=None
        if pose:
            start=[world['north'],world['west'],pose['height_yards']]
            end=[point['north'],point['west'],pose['height_yards']]
            try:clear=model_collision.clear_body_segment(world['instance'],start,end)
            except (RuntimeError,OSError,ValueError):pass
        result[name]={'target':point,'distance_yards':math.hypot(point['north']-world['north'],point['west']-world['west']),
            'reference_collision_clear':clear,
            'reference_matches_live_assets':False}
    return result
