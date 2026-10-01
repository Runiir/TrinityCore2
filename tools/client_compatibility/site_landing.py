"""Choose a dry, flat arrival within a public digsite polygon."""
import math
from . import ground_navigation as ground,site_boundaries


def select(site,origin):
    attempts=[];requests=[(origin,30)]
    # A coarse polygon's nearest detail face can be steep while a nearby
    # point on the same connected ground is flat. Probe the site, not just
    # its arithmetic center. No archaeological target position is consulted.
    for radius in [15,30,60,90]:
        for index in range(8):
            angle=index*math.tau/8
            point=[origin[0]+radius*math.cos(angle),origin[1]+radius*math.sin(angle),origin[2]]
            if site_boundaries.inside_segment(site['polygon'],origin,point):requests.append((point,8))
    for requested,radius in requests:
        # The initial center has never supported an observed Survey. Its
        # nearest polygon can be a disconnected cliff surface. Validate the
        # destination's actual supporting patch rather than that component.
        try:point=ground.landing_point(site['map'],requested,radius=radius)
        except RuntimeError as error:
            attempts.append({'requested':requested,'failure':str(error)});continue
        accepted=(site_boundaries.inside_segment(site['polygon'],origin,point) and
                  not ground.water_at(site['map'],point)['water_above_feet'])
        patch=None
        if accepted:
            try:patch=ground.site_ground_patch(site['map'],point)
            except RuntimeError as error:
                accepted=False;attempts.append({'requested':requested,'selected':point,'failure':str(error)})
        attempts.append({'requested':requested,'selected':point,'accepted':accepted})
        if accepted:return point,{'source':'public site polygon and broad flat NAV_GROUND; no private find coordinates',
            'attempts':attempts,'maximum_detail_slope_degrees':20,'dry_arrival_required':True,'safe_patch':patch,
            'connection_to_unverified_site_center_required':False}
    raise RuntimeError('no dry flat arrival in the bounded public digsite search')
