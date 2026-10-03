"""Save, use and delete one normally created owned equipment set."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,point,click_case
from .interaction_macros import require,edit_case
from .interaction_tooltips import baseline
from .interaction_equipment_sets import NAME,sets,detail
from .interaction_equipment import change
from .observation.inventory import Inventory

RENAMED='HarnessSaved'


def stable(value):return json.loads(json.dumps(value))


def native_named(name):
    data=sets();rows=[dict(zip(data['columns'],r)) for r in data['rows']]
    return data,len(rows)==1 and rows[0]['name']==name


def public_named(t,label,name):
    probe=detail(t,label);rows=probe.get('sets') or []
    return probe,probe['count']==len(rows)==1 and rows[0]['name']==name


def open_manager(t,label):
    t.clean_panels()
    require(t.step(label+'.open','Open character equipment.',
        {'open':{'kind':'key','value':'c','description':'Press C for character equipment.'}},
        lambda b,a,s:{'status':'character_open_pass' if 'CharacterFrame' in a['panels'] else
            'client_or_protocol_failure'},diagnostic_action='open'),'character_open_pass')
    collapsed=not any(c['name']=='PaperDollSidebarTab3' for c in controls(t))
    if collapsed:
        require(click_case(t,label+'.expand','Expand the character sidebar.',
            lambda c:c['name']=='CharacterFrameExpandButton',
            lambda b,a,s:{'status':'character_expand_pass' if s and
                any(c['name']=='PaperDollSidebarTab3' for c in controls(t)) else
                'client_or_protocol_failure'}),'character_expand_pass')
    require(click_case(t,label+'.manager','Open the equipment manager.',
        lambda c:c['name']=='PaperDollSidebarTab3',
        lambda b,a,s:{'status':'equipment_manager_pass' if s and detail(t,label+'_manager')['manager_visible'] else
            'client_or_protocol_failure'}),'equipment_manager_pass')
    return collapsed


def row(t,name,label,hover=False):
    rows=[c for c in controls(t) if c['kind']=='Button' and c['text']==name]
    if len(rows)!=1:raise RuntimeError('one visible owned equipment-set row is required')
    if hover:
        t.execute({'kind':'hover','value':point(rows[0])})
        state,frame=t.observe(label);t.receipt.setdefault('row_hovers',{})[label]={'state':state,'frame':frame};t.persist()
    else:
        require(click_case(t,label,'Select the owned '+name+' set.',
            lambda c:c['text']==name,
            lambda b,a,s:{'status':'equipment_set_select_pass' if s else 'controller_failure'}),'equipment_set_select_pass')


def suite(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':raise ValueError('require owned set-creation source')
    old=json.loads(source.read_text());original=stable(baseline());saved=stable(sets())
    if (not old.get('completed') or not old.get('finished_at') or not old.get('native_resources_preserved') or
        old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or
        old['native_after']!={'native':original,'sets':saved}):raise RuntimeError('set roundtrip requires exact successful current native/runtime source')
    _,valid=native_named(NAME)
    if not valid:raise RuntimeError('normally created disposable set is absent')
    t.receipt['source']={'file':str(source),'sha256':lab.sha256(source)}
    t.receipt['baseline']={'native':original,'sets':saved};t.persist()
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    item=oracle.equipment(1);empty=[s for s in range(1,17) if not oracle.slot(0,s)['guid']]
    if not item['guid'] or not empty:raise RuntimeError('equipped helmet and empty backpack slot required')
    destination=(0,empty[-1]);collapsed=None
    try:
        collapsed=open_manager(t,'sets.save');row(t,NAME,'sets.save.select');row(t,NAME,'sets.save.hover',True)
        probe,valid=public_named(t,'before_set_edit',NAME)
        if not valid:raise RuntimeError('public created set differs from its native catalog')
        id=probe['sets'][0]['id']
        require(click_case(t,'sets.save.edit','Edit the owned equipment set.',
            lambda c:c.get('equipment_set_button')=='edit' and c.get('equipment_set_id')==id,
            lambda b,a,s:{'status':'equipment_set_edit_menu_pass' if s and 'ContextMenu' in a['panels'] and not
                a.get('lua_errors') and not a.get('blocked_actions') else
                'client_or_protocol_failure'}),'equipment_set_edit_menu_pass')
        require(click_case(t,'sets.save.name_icon','Open the stock name and icon dialog.',
            lambda c:c['text']=='Change Name/Icon',
            lambda b,a,s:{'status':'equipment_set_dialog_pass' if s and 'GearManagerPopupFrame' in a['panels'] and not
                a.get('lua_errors') and not a.get('blocked_actions') else
                'client_or_protocol_failure'}),'equipment_set_dialog_pass')
        require(edit_case(t,'sets.save.name','Rename the disposable set.',lambda c:c['kind']=='EditBox',RENAMED),'ui_edit_pass')
        def save_outcome(b,a,s):
            data,native_ok=native_named(RENAMED);probe,public_ok=public_named(t,'saved_set',RENAMED)
            checks={'selected':s,'native_name':native_ok,'public_name':public_ok,
                'identity_slots_preserved':native_ok and [r[:3]+r[4:] for r in stable(data)['rows']]==
                    [r[:3]+r[4:] for r in saved['rows']],
                'resources_preserved':stable(baseline())==original,
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'equipment_set_save_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'native':data,'public':probe}}
        require(click_case(t,'character.equipment_set_save','Save the edited equipment set.',
            lambda c:c['text']=='Okay',save_outcome),'equipment_set_save_pass')
        t.clean_panels();t.execute({'kind':'chat','value':'/reload'})
        probe,valid=public_named(t,'saved_set_reload',RENAMED);_,native_ok=native_named(RENAMED)
        if not valid or not native_ok:raise RuntimeError('saved set did not persist across reload')
        t.receipt['reload_persistence']={'public':probe,'native_name':native_ok};t.persist()
        open_manager(t,'sets.use');row(t,RENAMED,'sets.use.select')
        t.execute({'kind':'key','value':'b'})
        require(change(t,oracle,item,destination),'equipment_change_pass')
        t.receipt['use_fixture']={'item':item,'destination':destination};t.persist()
        def use_outcome(b,a,s):
            probe,valid=public_named(t,'equipped_set',RENAMED);data,native_ok=native_named(RENAMED)
            checks={'selected':s,'public_set':valid and probe['sets'][0]['equipped'],
                'helmet_restored':oracle.poll().equipment(1)==item and not oracle.slot(*destination)['guid'],
                'native_set':native_ok,'all_resources_restored':stable(baseline())==original,
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'equipment_set_equip_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'native':data,'public':probe}}
        require(click_case(t,'character.equipment_set_equip','Equip the saved set to restore the helmet.',
            lambda c:c['name']=='PaperDollFrameEquipSet',use_outcome),'equipment_set_equip_pass')
        row(t,RENAMED,'sets.delete.hover',True)
        require(click_case(t,'sets.delete.dialog','Delete the disposable equipment set.',
            lambda c:c.get('equipment_set_button')=='delete' and c.get('equipment_set_id')==id,
            lambda b,a,s:{'status':'equipment_set_delete_dialog_pass' if s and 'StaticPopup1' in a['panels'] else
                'client_or_protocol_failure'}),'equipment_set_delete_dialog_pass')
        def delete_outcome(b,a,s):
            data=sets();probe=detail(t,'deleted_set')
            checks={'selected':s,'native_empty':not data['rows'],'public_empty':probe['count']==0 and not probe['sets'],
                'resources_preserved':stable(baseline())==original,
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'equipment_set_delete_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'native':data,'public':probe}}
        require(click_case(t,'character.equipment_set_delete','Confirm deleting the disposable equipment set.',
            lambda c:c['name']=='StaticPopup1Button1',delete_outcome),'equipment_set_delete_pass')
        t.clean_panels();t.execute({'kind':'chat','value':'/reload'})
        if detail(t,'deleted_set_reload')['count'] or sets()['rows']:raise RuntimeError('set deletion did not persist')
    finally:
        oracle.poll()
        if not oracle.equipment(1)['guid'] and oracle.slot(*destination)==item:
            t.clean_panels()
            for key in ['c','b']:t.execute({'kind':'key','value':key})
            require(change(t,oracle,item,destination,True),'equipment_change_pass')
        t.clean_panels()
        # Reload initializes the stock character frame collapsed. Record this
        # display boundary rather than silently asserting arbitrary UI state.
        t.receipt['native_after']={'native':stable(baseline()),'sets':stable(sets())}
        t.receipt['native_resources_preserved']=t.receipt['native_after']['native']==original;t.persist()
        if not t.receipt['native_resources_preserved']:raise RuntimeError('equipment-set roundtrip did not restore native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.source);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
