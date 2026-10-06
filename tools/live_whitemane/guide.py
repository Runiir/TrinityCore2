"""Keep an explicit visible-marker waypoint; telescope search follows failed attempts."""
import math


def select(row, session, tool):
    a,m=row['archaeology'],row['movement']; world=a['world']
    find=row.get('visible_find')
    approach=find or session.get('pickup_approach')
    if approach and session.get('reapproach_find'):
        endpoint=approach['world']
        distance=math.hypot(endpoint['north']-world['north'],endpoint['west']-world['west'])
        if endpoint['instance']!=world['instance'] or distance>40:
            raise RuntimeError('pickup approach is outside its observed local range')
        heading=math.atan2(endpoint['west']-world['west'],endpoint['north']-world['north'])
        error=(heading-m['facing_radians']+math.pi)%math.tau-math.pi
        tolerance=.1 if approach.get('source')=='named find forward range approach' else .5
        return {'source':'visible owned archaeology find' if find else approach.get('source','last green Survey endpoint'),
            'world':endpoint,'color':'green',
            'distance_yards':distance,'arrived':distance<=tolerance,'arrival_tolerance_yards':tolerance,
            'heading_relative_to_player':'aligned' if abs(error)<=.18 else 'left' if error>0 else 'right'},error
    visited=session.setdefault('visited_marker_ids',[])
    target=session.get('marker_target')
    if target and target['world']['instance'] != world['instance']:
        raise RuntimeError('marker target belongs to another world instance')
    if not session.get('marker_fallback') and target is None:
        for marker in a['visible_markers']:
            if marker['marker_id'] in visited: continue
            heading=marker['heading_radians'];distance=marker['distance_yards']
            target={'source':'GatherMate marker','marker_id':marker['marker_id'],
                    'world':{'instance':world['instance'],'north':world['north']+math.cos(heading)*distance,
                             'west':world['west']+math.sin(heading)*distance}}
            session['marker_target']=target
            break
    if session.get('marker_fallback'): target=None
    if target:
        endpoint=target['world']; distance=math.hypot(endpoint['north']-world['north'],endpoint['west']-world['west'])
        heading=math.atan2(endpoint['west']-world['west'],endpoint['north']-world['north'])
        color='green' if distance<=40 else 'yellow' if distance<=80 else 'red'
        guide={**target,'color':color,'distance_yards':round(distance,2),
            'arrived':distance<=.5,'arrival_tolerance_yards':.5}
    elif tool or session.get('telescope_target'):
        saved=session.get('telescope_target')
        if saved and saved['color']=='green' and 'recorded_marker_matches' not in saved:
            session.pop('telescope_target',None);saved=None
            if not tool:return None,None
        if saved:
            endpoint=saved['world'];color=saved['color']
            distance=math.hypot(endpoint['north']-world['north'],endpoint['west']-world['west'])
            heading=math.atan2(endpoint['west']-world['west'],endpoint['north']-world['north'])
            tolerance=6 if saved['color']=='red' else 4 if saved['color']=='yellow' else .5
            guide={**saved,'distance_yards':round(distance,2),'arrived':distance<=tolerance}
            error=(heading-m['facing_radians']+math.pi)%math.tau-math.pi
            guide['heading_relative_to_player']='aligned' if abs(error)<=.18 else 'left' if error>0 else 'right'
            return guide,error
        color={206590:'red',206589:'yellow',204272:'green'}[tool['entry']]
        arrow=a.get('arrow')
        if arrow and arrow.get('boundary_verified') and abs(arrow['observed_at']-tool['observed_at'])<=2:
            endpoint=arrow['endpoint']; distance=math.hypot(endpoint['north']-world['north'],endpoint['west']-world['west'])
            heading=math.atan2(endpoint['west']-world['west'],endpoint['north']-world['north'])
        else:
            if color!='green':raise RuntimeError('waiting for a boundary-verified public addon arrow')
            heading=tool['facing_radians'];distance=3
            endpoint={'instance':world['instance'],'north':world['north']+math.cos(heading)*distance,
                      'west':world['west']+math.sin(heading)*distance}
        public=(row.get('farm_ui') or {}).get('survey_guidance') or {}
        candidate=(public.get('candidate_matches') is True and
            abs(public.get('at',0)-tool['observed_at'])<=2)
        if color=='green' and not candidate:
            # The addon's default 40-yard line is an uncertain color range,
            # not a measured artifact distance. Follow the user's short-step
            # rule, then Survey again instead of crossing that whole range.
            distance=min(distance,3)
            endpoint={'instance':world['instance'],'north':world['north']+math.cos(heading)*distance,
                      'west':world['west']+math.sin(heading)*distance}
        guide={'source':'Survey telescope','color':color,'distance_yards':round(distance,2),
               'arrived':False,'world':endpoint,'recorded_marker_matches':candidate,
               'distance_is_estimate':True,'arrival_tolerance_yards':.5 if color=='green' else 6 if color=='red' else 4}
        session['telescope_target']=dict(guide)
    else: return None,None
    error=(heading-m['facing_radians']+math.pi)%math.tau-math.pi
    guide['heading_relative_to_player']='aligned' if abs(error)<=.18 else 'left' if error>0 else 'right'
    return guide,error


def marker_survey_outcome(session, guide, fresh_tool, artifact_discovered):
    if guide and guide['source']=='GatherMate marker' and guide['arrived'] and not artifact_discovered:
        attempts=session.get('marker_failed_surveys',0)+1
        session['marker_failed_surveys']=attempts
        if attempts>=2:
            session['visited_marker_ids'].append(guide['marker_id'])
            session['marker_target']=None
            session['marker_fallback']=True


def pickup(session,row=None):
    target=session.get('marker_target')
    visited=session.setdefault('visited_marker_ids',[])
    if target and target['marker_id'] not in visited:visited.append(target['marker_id'])
    if row:
        # A find discovered by telescope can add its saved GatherMate marker
        # only after gathering. Do not immediately Survey twice at that spot.
        closest=min(row['archaeology'].get('visible_markers') or [],
            key=lambda marker:marker['distance_yards'],default=None)
        if closest and closest['distance_yards']<=.5 and closest['marker_id'] not in visited:
            visited.append(closest['marker_id'])
    session.update(marker_target=None,marker_fallback=False,marker_failed_surveys=0)
    session.pop('telescope_target',None)
    session.pop('reapproach_find',None);session.pop('pickup_retries',None)
    session.pop('pickup_approach',None);session.pop('last_green_endpoint',None)


def model_state(row, guide, artifact_visible):
    """Encode the selected addon guide in the retained head's direction slot.

    The legacy slot is called 'telescope'. It represents route bearing and
    distance band here, including a recorded marker. The original source and
    exact endpoint stay in the receipt; no preferred action is supplied.
    """
    m,a=row['movement'],row['archaeology']
    current=bool(guide and not guide['arrived'])
    state={'task':'recover an archaeology find',
        'available':m['in_world'] and m['health_percent']>0 and not any(m[k] for k in ('dead','in_combat','on_taxi')),
        'casting':a['casting'],'artifact_visible':bool(artifact_visible),'instrument_current':current,
        'telescope':{'color':guide['color'],'heading_relative_to_player':guide['heading_relative_to_player'],
                     'distance_yards':guide['distance_yards']} if current else None}
    return state
