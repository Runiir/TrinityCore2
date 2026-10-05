"""Persist discovered finds until public fragment pickup confirms collection."""
import json
import math
import time
from . import runtime
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def fragments(row):
    return {str(r['index']):r['fragments'] for r in row['archaeology']['races']}


def facts(row,value):
    ui=row.get('farm_ui') or {};gathering=ui.get('gathering') or {}
    named=((ui.get('soft_interact') or {}).get('name') in FIND_NAMES or ui.get('tooltip') in FIND_NAMES)
    cast_started=bool(value and gathering.get('starts',0)>value.get('gathering_starts',gathering.get('starts',0)))
    discovered=bool(value or named or row['archaeology'].get('loot_open') or
        (row.get('minimap_finds') or {}).get('confirmed'))
    return {'state':'verify' if row['archaeology'].get('loot_open') else
        'gather' if cast_started and row['archaeology']['casting'] else
        'approach' if value and value.get('out_of_range') else 'locate' if discovered and not named else
        'interact' if discovered else 'dig',
        'uncollected':discovered,'named_target':named,'gather_cast_seen':cast_started,
        'position_is_estimate':bool(value and value.get('approach')),
        'travel_ready':not discovered,'exit_pickup_on':'fragment gain or pickup counter increase'}


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
        'origin':row['archaeology']['world'],'fragments':fragments(row),'source':source,'approach':approach,
        'out_of_range':False,'attempts':0,
        'looted_finds':row['archaeology'].get('looted_finds',0),
        'gathering_starts':((row.get('farm_ui') or {}).get('gathering') or {}).get('starts',0)}
    runtime.write(runtime.ROOT/'run/pending_find.json',value)
    return value


def clear():
    (runtime.ROOT/'run/pending_find.json').unlink(missing_ok=True)


def update(row,session):
    value=load(row)
    confirmed=(row.get('minimap_finds') or {}).get('confirmed') or []
    ui=row.get('farm_ui') or {}
    named=((ui.get('soft_interact') or {}).get('name') in FIND_NAMES or ui.get('tooltip') in FIND_NAMES)
    if not value and (confirmed or row.get('visible_find') or named or row['archaeology']['loot_open'] or
        ((row.get('farm_ui') or {}).get('route') or {}).get('kind')=='pending_loot'):
        approach=row.get('visible_find') or (confirmed[0] if confirmed else session.get('last_green_endpoint'))
        value=latch(row,site_id=session.get('site_id'),approach=approach,source='public visible archaeology find')
    if value:
        approach=row.get('visible_find') or (confirmed[0] if confirmed else value.get('approach'))
        if approach:
            value['approach']=approach
            runtime.write(runtime.ROOT/'run/pending_find.json',value)
        session['pending_find']=value
        if approach:session['pickup_approach']=approach
        session['reapproach_find']=value['out_of_range'] or bool(approach)
    else:
        session.pop('pending_find',None)
        session.pop('reapproach_find',None)
        session.pop('pickup_approach',None)
    return value


def range_error(error):
    return error.get('code') in (274,375) or error.get('message') in ('Out of range.','You are too far away.')


def out_of_range(row,session):
    value=load(row) or latch(row,site_id=session.get('site_id'),approach=session.get('pickup_approach'))
    value.update(out_of_range=True,attempts=value['attempts']+1)
    world=row['archaeology']['world'];heading=row['movement']['facing_radians']
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
