"""Find a progressive, flat in-site landing from an ordinary telescope bearing."""
import math
from . import ground_navigation as ground,site_boundaries


def select(site,start,heading,distance):
    attempts=[]
    # Flat terrain beside a cliff can be closer than the selected walking
    # distance. Do not repeatedly land behind the noisy telescope bearing.
    distances=list(dict.fromkeys([distance,max(3,distance/2),7,min(84,distance*2),min(84,distance*3)]))
    for offset in [0,-math.pi/4,math.pi/4]:
        for requested in distances:
            angle=heading+offset
            clipped=site_boundaries.clip_distance(site['polygon'],start,angle,requested)
            if clipped<1.5:continue
            waypoint=[start[0]+math.cos(angle)*clipped,start[1]+math.sin(angle)*clipped,start[2]]
            try:point=ground.landing_point(site['map'],waypoint,start=start)
            except RuntimeError as error:
                attempts.append({'waypoint':waypoint,'failure':str(error)});continue
            progress=(point[0]-start[0])*math.cos(heading)+(point[1]-start[1])*math.sin(heading)
            accepted=(progress>=1.5 and math.dist(point[:2],start[:2])>=3 and
                      site_boundaries.inside_segment(site['polygon'],start,point))
            attempts.append({'waypoint':waypoint,'landing':point,'bearing_progress_yards':progress,'accepted':accepted})
            if accepted:
                return point,{'selected':point,'maximum_detail_slope_degrees':20,'attempts':attempts,
                    'source':'public telescope bearing, site polygon and static ground detail triangles; no private find coordinates'}
    raise RuntimeError('no progressive flat in-site landing near the public survey bearing')
