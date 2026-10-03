"""Compare stock melee damage and rendered DPS to owned native packet fields."""
import argparse,json,math,re,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require
from .interaction_equipment_sets import detail
from .interaction_equipment_set_roundtrip import open_character,restore_display,stable
from .interaction_tooltips import baseline
from .observation.inventory import Inventory
from .world.objects import INDEX


def native_damage(oracle):
    fields=oracle.poll().objects.get(oracle.guid,{})
    names=['UNIT_FIELD_MINDAMAGE','UNIT_FIELD_MAXDAMAGE','PLAYER_FIELD_MOD_DAMAGE_DONE_PCT',
        'UNIT_FIELD_BASEATTACKTIME']
    if any(INDEX[name] not in fields for name in names):
        raise RuntimeError('owned native damage/speed fields are not all attributable')
    def floating(name):return struct.unpack('<f',struct.pack('<I',fields[INDEX[name]]))[0]
    low,high=floating(names[0]),floating(names[1]);speed=fields[INDEX[names[3]]]/1000
    pct=floating(names[2])
    if not all(math.isfinite(v) and v>0 for v in [low,high,speed,pct]):
        raise RuntimeError('native damage fixture is not positive and finite')
    return {'minimum':low,'maximum':high,'percentage':pct,'speed':speed,'dps':(low+high)/2/speed,
        'fields':{name:{'index':INDEX[name],'raw':fields[INDEX[name]]} for name in names}}


def close(a,b,tolerance=.02):
    return isinstance(a,(int,float)) and math.isfinite(a) and math.isclose(a,b,rel_tol=1e-5,abs_tol=tolerance)


def suite(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned geared primary warrior')
    session=actors.session_entry(t.fixture)['session']
    oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    original=stable(baseline());t.receipt['baseline']=original;t.receipt['native_session']=session;t.persist()
    collapsed=None
    try:
        open_character(t,'damage.character')
        collapsed=not any(c['name']=='PaperDollSidebarTab1' for c in controls(t))
        t.receipt['display_baseline']={'collapsed':collapsed};t.persist()
        if collapsed:
            require(click_case(t,'damage.expand','Expand the stock character sidebar.',
                lambda c:c['name']=='CharacterFrameExpandButton',
                lambda b,a,s:{'status':'character_expand_pass' if s and a.get('character_expanded') else
                    'client_or_protocol_failure'},await_state=lambda a:a.get('character_expanded') is True),
                'character_expand_pass')
        require(click_case(t,'damage.stats','Select the stock character stats sidebar.',
            lambda c:c['name']=='PaperDollSidebarTab1',
            lambda b,a,s:{'status':'character_stats_sidebar_pass' if s and
                detail(t,'selected_stats')['stats']['sheet'] else 'client_or_protocol_failure'}),
            'character_stats_sidebar_pass')
        def outcome(b,a,s):
            native=native_damage(oracle);public=detail(t,'character_damage')['stats'];damage=public['damage'];speed=public['attack_speed']
            melee=[row for row in public['sheet'] if row.get('category')=='MELEE' and
                re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',row.get('label') or '').strip().removesuffix(':')=='DPS']
            text=re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',melee[0].get('text') or '').replace(',','') if len(melee)==1 else ''
            try:shown=float(text)
            except ValueError:shown=None
            checks={'ordinary_hover':s=='inspect','native_damage':len(damage)==7 and
                close(damage[0],native['minimum']) and close(damage[1],native['maximum']),
                'native_percentage':len(damage)==7 and close(damage[6],native['percentage'],1e-6),
                'native_speed':bool(speed) and close(speed[0],native['speed'],.001),
                'rendered_dps':close(shown,native['dps'],.1),
                'native_resources_preserved':stable(baseline())==original,
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'character_damage_display_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'native':native,'public':public,'rendered_melee_dps_text':text}}
        require(t.step('character.stats.damage_modifiers','Inspect native melee damage and the stock rendered DPS.',
            {'inspect':{'kind':'hover','value':[1110,580],'description':'Move the pointer away from the character stat rows.'}},
            outcome,diagnostic_action='inspect'),'character_damage_display_pass')
    finally:
        try:restore_display(t,collapsed)
        finally:
            t.receipt['native_after']=stable(baseline());t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
            if not t.receipt['native_resources_preserved']:raise RuntimeError('character damage trial changed native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
