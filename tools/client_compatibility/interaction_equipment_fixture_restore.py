"""Restore the exact helmet and set name left by a closed failed roundtrip."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case
from .interaction_macros import edit_case,require
from .interaction_tooltips import baseline
from .interaction_equipment_sets import sets,NAME,detail
from .interaction_equipment_set_roundtrip import stable,open_manager,row,hover_button,restore_display,RENAMED


def suite(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':raise ValueError('require owned failed episode')
    old=json.loads(source.read_text());original=old['baseline']['native'];saved=old['baseline']['sets']
    if old.get('completed') or not old.get('finished_at') or old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime']:
        raise RuntimeError('fixture restoration requires the exact closed failed actor/runtime')
    cases={c['id']:c for c in old['cases']}
    if cases['character.equipment_set_save']['status']!='equipment_set_save_pass' or not cases['character.unequip']['oracle']['native_matches']:
        raise RuntimeError('failed source must prove the renamed set and successful native helmet relocation')
    current=stable(baseline());expected=stable(original);inventory=expected['archaeology_inventory_money']['inventory']['items']
    helmet=next(r for r in inventory if r[:3]==[1,0,0]);helmet_id=helmet[4];helmet[2]=38;inventory.sort()
    renamed=stable(saved)
    if len(renamed['rows'])!=1 or renamed['rows'][0][3]!=NAME:raise RuntimeError('source set baseline differs')
    renamed['rows'][0][3]=RENAMED
    if current!=expected or stable(sets())!=renamed:raise RuntimeError('current fixture differs beyond the exact expected helmet/name changes')
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},baseline={'native':original,'sets':saved},
        expected_pre_recovery={'native':expected,'sets':renamed});t.persist()
    collapsed=old['display_baseline']['collapsed']
    try:
        open_manager(t,'restore.set');row(t,RENAMED,'restore.select')
        def equipped(b,a,s):
            probe=detail(t,'restored_helmet')
            checks={'selected':s,'native_original':stable(baseline())==original,
                'public_equipped':probe['count']==1 and probe['sets'][0]['equipped'],
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'equipment_fixture_restored' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':probe}}
        require(click_case(t,'restore.equip','Restore the helmet with the normally saved equipment set.',
            lambda c:c['name']=='PaperDollFrameEquipSet',equipped,
            await_state=lambda a:(a.get('equipment') or [None])[0]==helmet_id),'equipment_fixture_restored')
        probe=detail(t,'restore_name_before');id=probe['sets'][0]['id']
        row(t,RENAMED,'restore.hover',True);hover_button(t,'edit',id,'restore.edit_hover')
        require(click_case(t,'restore.edit','Open the stock equipment-set edit menu.',
            lambda c:c.get('equipment_set_button')=='edit' and c.get('equipment_set_id')==id,
            lambda b,a,s:{'status':'edit_menu_pass' if s and 'ContextMenu' in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda a:'ContextMenu' in a['panels']),'edit_menu_pass')
        require(click_case(t,'restore.name_dialog','Open the stock name and icon dialog.',lambda c:c['text']=='Change Name/Icon',
            lambda b,a,s:{'status':'name_dialog_pass' if s and 'GearManagerPopupFrame' in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda a:'GearManagerPopupFrame' in a['panels']),'name_dialog_pass')
        require(edit_case(t,'restore.name','Restore the exact original set name.',lambda c:c['kind']=='EditBox',NAME),'ui_edit_pass')
        require(click_case(t,'restore.name_save','Save the exact original set name.',lambda c:c['text']=='Okay',
            lambda b,a,s:{'status':'equipment_fixture_name_restored' if s and stable(sets())==saved and
                stable(baseline())==original else 'client_or_protocol_failure'}),'equipment_fixture_name_restored')
    finally:
        try:restore_display(t,collapsed)
        finally:
            t.receipt['native_after']={'native':stable(baseline()),'sets':stable(sets())}
            t.receipt['native_resources_preserved']=t.receipt['native_after']['native']==original;t.persist()
    if t.receipt['native_after']!=old['baseline']:raise RuntimeError('exact equipment fixture remains unrestored')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.source);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
