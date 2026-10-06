"""Current public observations and separately derived activity conditions."""
import json
import math
from . import runtime,pending_find
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def pending(row):
    """Read a latch without changing it or depending on an action receipt."""
    path=runtime.ROOT/'run/pending_find.json'
    if not path.exists():return None
    value=json.loads(path.read_text());world=row['archaeology'].get('world')
    if value['runtime']!=row['runtime']:raise RuntimeError('pending find belongs to another owned client')
    if not world or value['origin']['instance']!=world['instance']:return None
    if pending_find.gained(value['fragments'],row) or (
            value.get('looted_finds') is not None and
            row['archaeology'].get('looted_finds',0)>value['looted_finds']):return None
    return value


def reduce(row,latch=None):
    m,a,ui=row['movement'],row['archaeology'],row.get('farm_ui') or {}
    pickup=pending_find.facts(row,latch)
    facts={key:a.get(key) for key in ('mounted','flying','falling','swimming','casting','loot_open','can_survey')}
    facts.update(in_world=m['in_world'],combat=m['in_combat'],dead=m['dead'],
        on_taxi=m['on_taxi'],health_percent=m['health_percent'],speed=m.get('speed'),
        map_id=m['map_id'],world=a.get('world'),
        artifact_uncollected=pickup['uncollected'],artifact_named=pickup['named_target'],
        survey_ready=(ui.get('survey') or {}).get('ready'),
        minimap_clear=(row.get('minimap_finds') or {}).get('clear'),
        canopic_jars_in_bags=a.get('canopic_jars_in_bags',0),
        recipe_known=bool(ui.get('recipe_known') or a.get('recipe_items_in_bags',0)))
    portal=(ui.get('route') or {}).get('portal');world=a.get('world')
    target=portal.get('from') if portal else None
    facts['portal_distance_yards']=(math.hypot(world['north']-target['north'],world['west']-target['west'])
        if world and target and world['instance']==target['instance'] else None)
    if facts['recipe_known']:activity='recipe_found'
    elif facts['canopic_jars_in_bags']:activity='jar_found'
    elif not facts['in_world'] or facts['dead']:activity='unavailable'
    elif facts['combat']:activity='combat'
    elif pickup['uncollected']:activity='pickup'
    elif facts['can_survey']:activity='dig'
    else:activity='travel'
    return {'facts':facts,'pickup_facts':pickup,'activity':activity,
        'transition_conditions':{'onward_travel':not pickup['uncollected'],
            'survey':facts['can_survey'] is True and facts['survey_ready'] is True and not pickup['uncollected'],
            'combat':facts['combat'],
            'use_portal':facts['portal_distance_yards'] is not None and facts['portal_distance_yards']<30},
        'observed_at':row.get('observed_at'),'valid':True}
