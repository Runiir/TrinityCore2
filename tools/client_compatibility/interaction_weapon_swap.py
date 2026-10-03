"""Swap two owned two-hand swords through the backpack and restore the fixture."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_macros import require
from .interaction_operations import point
from .interaction_inventory_moves import slot_control
from .interaction_equipment_set_roundtrip import open_character,stable
from .interaction_equipment import stats_check
from .interaction_tooltips import baseline,items
from .observation.inventory import Inventory


def exchanged(original,first,second):
    result=stable(original);rows=result['archaeology_inventory_money']['inventory']['items']
    owned={row[3]:row for row in rows if row[0]==1}
    a,b=owned[first['guid']&0xffffffff],owned[second['guid']&0xffffffff]
    a[1:3],b[1:3]=b[1:3],a[1:3]
    rows.sort(key=lambda row:row[:3])
    return result


def swap(t,oracle,position,worn,stored,expected,case_id):
    control=slot_control(t,*position)
    if control is None:raise RuntimeError('owned backpack weapon control is absent')
    def visible(state):
        bag=next((x for x in state.get('bag_items',[]) if (x['bag'],x['slot'])==position),{})
        return len(state.get('equipment',[]))==19 and state['equipment'][15]==stored['id'] and bag.get('id')==worn['id']
    def outcome(b,a,s):
        oracle.poll();checks={'ordinary_right_click':s=='swap','native_weapon':oracle.equipment(16)==stored,
            'native_backpack':oracle.slot(*position)==worn,'visible_weapon_and_bag':visible(a),
            'complete_native_fixture':stable(baseline())==expected,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'weapon_swap_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native_worn':oracle.equipment(16),'native_stored':oracle.slot(*position)}}
    return t.step(case_id,'Equip the owned backpack sword and exchange its storage with the equipped sword.',
        {'swap':{'kind':'click','value':point(control),'button':3,'description':'Right-click the observed backpack sword.'}},
        outcome,diagnostic_action='swap',await_state=visible)


def open_fixture(t):
    open_character(t,'weapon.character')
    require(t.step('weapon.backpack','Open the backpack with its normal binding.',
        {'open':{'kind':'key','value':'b','description':'Press B.'}},
        lambda b,a,s:{'status':'backpack_open_pass' if 0 in a.get('bags',[]) else 'client_or_protocol_failure'},
        diagnostic_action='open',await_state=lambda a:0 in a.get('bags',[])),'backpack_open_pass')


def suite(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires owned geared primary warrior')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    original=stable(baseline());worn=oracle.equipment(16);position=(0,10);stored=oracle.slot(*position)
    catalog,digest=items([worn['id'],stored['id']])
    if (worn['id']!=78478 or stored['id']!=49778 or not all(x['inventory_type']==17 for x in catalog.values()) or
        oracle.equipment(17)['guid']):raise RuntimeError('requires exact owned Gurthalak/Worn Greatsword two-hand fixture')
    expected=exchanged(original,worn,stored)
    t.receipt.update(baseline=original,native_session=session,weapon_fixture={'worn':worn,'stored':stored,
        'position':position,'catalog':catalog,'catalog_sha256':digest});t.persist()
    try:
        open_fixture(t);require(swap(t,oracle,position,worn,stored,expected,'character.weapon_swap'),'weapon_swap_pass')
        if not stats_check(t,oracle,'alternate_weapon'):raise RuntimeError('alternate sword damage/stats differ from native')
        require(swap(t,oracle,position,stored,worn,original,'weapon.restore'),'weapon_swap_pass')
        if not stats_check(t,oracle,'original_weapon'):raise RuntimeError('restored sword damage/stats differ from native')
    finally:
        try:
            oracle.poll()
            if oracle.equipment(16)==stored and oracle.slot(*position)==worn:
                open_fixture(t);require(swap(t,oracle,position,stored,worn,original,'weapon.cleanup'),'weapon_swap_pass')
            t.clean_panels()
        finally:t.receipt.update(native_after=stable(baseline()));t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('original weapon fixture remains unrestored')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
