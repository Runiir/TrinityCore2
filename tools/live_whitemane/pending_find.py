"""Persist discovered finds until public fragment pickup confirms collection."""
import json
import math
import time
from . import runtime
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def fragments(row):
    return {str(r['index']):r['fragments'] for r in row['archaeology']['races']}


def pickup_receipt(row):
    path=runtime.ROOT/'run/last_pickup.json'
    if not path.exists():return None
    value=json.loads(path.read_text())
    return value if value['runtime']==row['runtime'] else None


def confirm_pickup(row,*,name=None):
    """Call only after observed fragment or verified pickup-counter increase."""
    previous=pickup_receipt(row)
    if previous and previous['observed_at']>=row['observed_at']:return previous
    ui=row.get('farm_ui') or {};names={name,ui.get('tooltip'),(ui.get('soft_interact') or {}).get('name')}
    value={'runtime':row['runtime'],'observed_at':row['observed_at'],
        'successful_surveys':row['archaeology'].get('successful_surveys'),
        'looted_finds':row['archaeology'].get('looted_finds'),
        'world':row['archaeology']['world'],'fragments':fragments(row),
        'names':sorted(names & set(FIND_NAMES))}
    runtime.write(runtime.ROOT/'run/last_pickup.json',value);return value


def same_pickup_generation(row,receipt):
    world=row['archaeology'].get('world');origin=receipt.get('world') if receipt else None
    return bool(receipt and receipt['successful_surveys'] is not None and receipt['looted_finds'] is not None
        and origin and world and origin['instance']==world['instance']
        and math.hypot(origin['north']-world['north'],origin['west']-world['west'])<=.25
        and row['archaeology'].get('successful_surveys')==receipt['successful_surveys']
        and row['archaeology'].get('looted_finds')==receipt['looted_finds'])


def named_uncollected(row):
    ui=row.get('farm_ui') or {}
    names={ui.get('tooltip'),(ui.get('soft_interact') or {}).get('name')} & set(FIND_NAMES)
    receipt=pickup_receipt(row)
    return bool(names and (not same_pickup_generation(row,receipt)
        or names-set(receipt['names']) or row.get('visible_find')
        or (row.get('minimap_finds') or {}).get('confirmed')))


def local_approach(row,approach):
    if not approach:return None
    a,b=approach.get('world'),row['archaeology'].get('world')
    return approach if a and b and a['instance']==b['instance'] and math.hypot(
        a['north']-b['north'],a['west']-b['west'])<=40 else None


def facts(row,value):
    ui=row.get('farm_ui') or {};gathering=ui.get('gathering') or {}
    named=named_uncollected(row)
    cast_started=bool(value and gathering.get('starts',0)>value.get('gathering_starts',gathering.get('starts',0)))
    find=row.get('visible_find')
    approach=find or (value or {}).get('approach')
    discovered=bool(value or find or named or row['archaeology'].get('loot_open') or
        (row.get('minimap_finds') or {}).get('confirmed'))
    return {'uncollected':discovered,'named_target':named,'gather_cast_seen':cast_started,
        'discovery_confirmed':bool(named or find or row['archaeology'].get('loot_open')
            or (row.get('minimap_finds') or {}).get('confirmed') or (value or {}).get('discovery_confirmed')),
        'tooltip_search_misses':(value or {}).get('tooltip_search_misses',0),
        'position_is_estimate':bool(approach and approach.get('estimated_position',
            approach.get('source')!='owned_authenticated_visible_find_create_after_own_survey')),
        'artifact_world':approach.get('world') if approach else None,
        'interaction_in_range':True if cast_started else False if value and value.get('out_of_range') else None,
        'loot_open':bool(row['archaeology'].get('loot_open'))}


def stage(observed,casting=False):
    """Derive an activity from facts; this function never changes the facts."""
    if observed['loot_open']:return 'verify'
    if observed['gather_cast_seen'] and casting:return 'gather'
    if observed['interaction_in_range'] is False:return 'approach'
    if observed['uncollected'] and not observed['named_target']:return 'locate'
    return 'interact' if observed['uncollected'] else 'dig'


def gained(baseline,row):
    current=fragments(row)
    return any(current.get(race,0)>amount for race,amount in baseline.items())


def load(row):
    path=runtime.ROOT/'run/pending_find.json'
    if not path.exists():return None
    value=json.loads(path.read_text())
    if value['runtime']!=row['runtime']:raise RuntimeError('pending find belongs to another owned client')
    if not row['archaeology']['world'] or value['origin']['instance']!=row['archaeology']['world']['instance']:
        return None
    if gained(value['fragments'],row) or (value.get('looted_finds') is not None
            and row['archaeology'].get('looted_finds',0)>value['looted_finds']):
        confirm_pickup(row,name=value.get('name'))
        if value.get('captured_find_observed_at') is not None:
            runtime.write(runtime.ROOT/'run/collected_find.json',{
                'runtime':value['runtime'],'observed_at':value['captured_find_observed_at']})
        clear();return None
    receipt=pickup_receipt(row)
    if (same_pickup_generation(row,receipt) and value['fragments']==receipt['fragments']
            and value.get('source')=='public visible archaeology find' and not value.get('approach')
            and not row.get('visible_find') and not (row.get('minimap_finds') or {}).get('confirmed')
            and not row['archaeology'].get('loot_open')):
        # Repair a previously latched lingering tooltip using the already
        # confirmed pickup. A fresh Survey or a located live find takes priority.
        clear();return None
    if 'gathering_starts' not in value:
        value['gathering_starts']=((row.get('farm_ui') or {}).get('gathering') or {}).get('starts',0)
        value['looted_finds']=row['archaeology'].get('looted_finds',0)
        runtime.write(path,value)
    return value


def latch(row,*,site_id=None,approach=None,source='successful Survey without telescope'):
    old=load(row)
    if old:return old
    value={'runtime':row['runtime'],'observed_at':time.time(),'site_id':site_id or row['archaeology']['site_id'],
        'origin':row['archaeology']['world'],'fragments':fragments(row),'source':source,'approach':local_approach(row,approach),
        'out_of_range':False,'attempts':0,
        'discovery_confirmed':source=='public visible archaeology find',
        'looted_finds':row['archaeology'].get('looted_finds',0),
        'gathering_starts':((row.get('farm_ui') or {}).get('gathering') or {}).get('starts',0)}
    ui=row.get('farm_ui') or {}
    value['name']=next((name for name in ((ui.get('soft_interact') or {}).get('name'),ui.get('tooltip'))
        if name in FIND_NAMES),None)
    if row.get('visible_find'):value['captured_find_observed_at']=row['visible_find']['observed_at']
    runtime.write(runtime.ROOT/'run/pending_find.json',value)
    return value


def clear():
    (runtime.ROOT/'run/pending_find.json').unlink(missing_ok=True)


def update(row,session):
    value=load(row)
    from .survey_find import collected
    if row.get('visible_find') and collected(row['visible_find']):row['visible_find']=None
    confirmed=(row.get('minimap_finds') or {}).get('confirmed') or []
    ui=row.get('farm_ui') or {}
    named=named_uncollected(row)
    if not value and (confirmed or row.get('visible_find') or named or row['archaeology']['loot_open'] or
        ((row.get('farm_ui') or {}).get('route') or {}).get('kind')=='pending_loot'):
        approach=row.get('visible_find') or (confirmed[0] if confirmed else session.get('last_green_endpoint'))
        value=latch(row,site_id=session.get('site_id'),approach=approach,source='public visible archaeology find')
    if value:
        if 'tooltip_search_misses' not in value and any('action' in s for s in session.get('steps',[])):
            value['tooltip_search_misses']=sum('no matching public tooltip' in (s.get('failure') or '')
                and s.get('started_at',0)>=value['observed_at'] for s in session['steps'])
        if named or row.get('visible_find') or confirmed or row['archaeology']['loot_open']:
            value['discovery_confirmed']=True
        if named:
            value['name']=next(name for name in ((ui.get('soft_interact') or {}).get('name'),ui.get('tooltip'))
                if name in FIND_NAMES)
        approach=local_approach(row,row.get('visible_find') or (confirmed[0] if confirmed else value.get('approach')))
        value['approach']=approach
        if approach:
            value['approach']=approach
            if row.get('visible_find'):value['captured_find_observed_at']=row['visible_find']['observed_at']
            runtime.write(runtime.ROOT/'run/pending_find.json',value)
        else:runtime.write(runtime.ROOT/'run/pending_find.json',value)
        session['pending_find']=value
        if approach:session['pickup_approach']=approach
        else:session.pop('pickup_approach',None)
        session['reapproach_find']=value['out_of_range'] or bool(approach)
    else:
        session.pop('pending_find',None)
        session.pop('reapproach_find',None)
        session.pop('pickup_approach',None)
    return value


def search_missed(row):
    value=load(row)
    if value:
        value['tooltip_search_misses']=value.get('tooltip_search_misses',0)+1
        runtime.write(runtime.ROOT/'run/pending_find.json',value)


def range_error(error):
    return error.get('code') in (274,375) or error.get('message') in ('Out of range.','You are too far away.')


def out_of_range(row,session):
    value=load(row) or latch(row,site_id=session.get('site_id'),approach=session.get('pickup_approach'))
    value.update(out_of_range=True,attempts=value['attempts']+1)
    world=row['archaeology']['world']
    approach=row.get('visible_find') or value.get('approach')
    height=(approach or {}).get('height_yards',(approach or {}).get('world',{}).get('height_yards'))
    own_height=(row.get('owned_pose') or {}).get('height_yards')
    different_depth=(row['archaeology'].get('swimming') and height is not None and own_height is not None
        and abs(height-own_height)>.5)
    if (approach and approach.get('source')=='owned_authenticated_visible_find_create_after_own_survey'
            and (different_depth or math.hypot(approach['world']['north']-world['north'],approach['world']['west']-world['west'])>.2)):
        value['approach']=approach;session['pickup_approach']=approach
        runtime.write(runtime.ROOT/'run/pending_find.json',value)
        session.update(pending_find=value,reapproach_find=True,walked_since_survey=True)
        return
    heading=row['movement']['facing_radians']
    # The realm's gather radius is small. Shrink the approach after each range
    # error instead of repeatedly crossing the estimated target.
    stride=max(.5,3/2**min(value['attempts']-1,3))
    target={'world':{'instance':world['instance'],'north':world['north']+math.cos(heading)*stride,
        'west':world['west']+math.sin(heading)*stride},'source':'named find forward range approach','stride_yards':stride}
    value['approach']=target;session['pickup_approach']=target
    runtime.write(runtime.ROOT/'run/pending_find.json',value)
    session.update(pending_find=value,reapproach_find=True,walked_since_survey=True)


def can_leave(row):
    return not load(row) and (row.get('minimap_finds') or {}).get('clear') is True


def priority(row,value):
    from . import laya_ui
    signal=row.get('minimap_finds') or {}
    if not value and not signal.get('confirmed'):
        raise ValueError('pickup priority only applies to a detected or pending find')
    state={'goal':'collect all discovered artifacts before more digging or travel',
        'minimap_live_artifacts':[f['name'] for f in signal.get('confirmed') or []],
        'pickup_unconfirmed':bool(value),'out_of_range':bool(value and value['out_of_range']),
        'saved_GatherMate_locations_are_history':True}
    action,request,response=laya_ui.choose(state,
        'Collect when a live artifact is shown or a previous pickup is unconfirmed. Otherwise continue the farm.',
        {'pickup':'Collect the pending archaeology artifact','continue':'Continue the farm'})
    return {'state':state,'choice':action,'request':request,'response':response}


def choose_inspection(row):
    from . import laya_ui
    from .ui_choice import MODEL,REVISION
    signal=row.get('minimap_finds') or {}
    state={'task':'locate the uncollected archaeology find','find_pending':True,
        'minimap_live_finds':len(signal.get('confirmed') or []),'minimap':signal.get('status','unavailable'),
        'find_bearing':'unknown'}
    action,request,response=laya_ui.choose(state,
        'Inspect the minimap to locate the pending find before moving.',
        {'inspect':'Inspect the minimap blips','observe':'Wait without input'})
    return action,{'model':MODEL,'revision':REVISION,'adapter':None},request,response,state
