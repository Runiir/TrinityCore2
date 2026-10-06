"""Inspect the normally controlled owned Hunter pet without changing its state."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import protected
from .interaction_hunter_training import prior
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_dismiss import Presence
from .interaction_pet_target import PetOracle
from .interaction_pet_training_disconnect import catalog
from .interaction_pet_spellbook_tab import modern_catalog,catalog_checks
from .interaction_pet_command_probe import read as commands,expected_guid
from .interaction_spellbook_navigation import detail
from .interaction_actionbar_pages import detail as bar_detail
from .interaction_spellbook_recon import resources
from .interaction_operations import click_case,controls,point
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX


def starting_wolf(rows,owner):
    return owner==6 and len(rows)==1 and tuple(rows[0].get(k) for k in
        ('id','entry','owner','CreatedBySpell','PetType','level','name','renamed','slot'))==(
            4,42717,6,79597,1,10,'Wolf',0,0)


def saved_pet_unchanged(before,after,now):
    """Native Player::SaveToDB saves the pet and advances only its save clock."""
    if len(before)!=1 or len(after)!=1 or set(before[0])!=set(after[0]):return False
    b,a=before[0],after[0]
    return (type(b.get('savetime')) is int and type(a.get('savetime')) is int and
        0<b['savetime']<=a['savetime']<=now and
        {k:v for k,v in b.items() if k!='savetime'}=={k:v for k,v in a.items() if k!='savetime'})


def pet_frame_menu(t,oracle,expected):
    """Inspect the owned pet frame's menu, whose actions differ from TargetFrame."""
    bar=bar_detail(t,'hunter_pet_hit_rectangle',lambda p:bool(p.get('targeting',{}).get('pet_frame')))
    control=bar['targeting']['pet_frame'];xy=point(control)
    if (control.get('name')!='PetFrame' or control.get('unit')!='pet' or control.get('guid')!=expected or
        control.get('visible') is not True or control.get('enabled') is not True or
        control.get('point_basis')!='hit_rectangle_center' or
        any(type(control.get(k)) is not int or not 0<control[k]<65535 for k in ('x','y'))):
        raise RuntimeError('observed pet frame point differs')
    def outcome(before,after,selected):
        oracle.poll()
        checks={'ordinary_right_click':selected=='open','stock_context_menu':'ContextMenu' in after.get('panels',[]),
            'public_target':after.get('target',{}).get('guid')==expected,
            'native_target':oracle.selected()==oracle.pet['guid'],
            'position':before['world_position']==after['world_position'],
            'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
        return {'status':'hunter_pet_frame_menu_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'pet_frame':control,'qualification_added':False}}
    require(t.step('diagnostic.hunter_pet_frame_menu','Inspect the owned Hunter stock pet frame menu.',
        {'open':{'kind':'click','value':xy,'button':3,'hold':.4,
            'description':'Right-click the observed owned PetFrame once.'}},outcome,diagnostic_action='open',
        await_state=lambda a:'ContextMenu' in a.get('panels',[])),'hunter_pet_frame_menu_pass')
    state,frame=t.observe('hunter_pet_frame_menu');rows=controls(t)
    menu_checks={'owned_menu_title':any(c.get('kind')=='MenuItem' and c.get('text')=='Wolf' for c in rows),
        'player_menu_absent':not any(c.get('text')=='Harnesshunt' for c in rows),
        'stock_rename_visible':any(c.get('text')=='Rename' and c.get('enabled') is True for c in rows)}
    t.receipt.update(pet_menu={'state':state,'frame':frame,'controls':rows,'source_control':control,
        'checks':menu_checks});t.persist()
    if not all(menu_checks.values()):raise RuntimeError('owned Hunter pet rename menu differs')


def catalog_pair(session,since,pet):
    packets=[r for r in entries(lab.ROOT/'evidence/world_packets.jsonl') if r.get('session')==session and
        r.get('time',0)>=since and r.get('name') in ('SMSG_PET_SPELLS','SMSG_PET_SPELLS_MESSAGE')]
    native=[p for p in packets if p['direction']=='from_native' and p['name']=='SMSG_PET_SPELLS' and
        len(bytes.fromhex(p['body']))>=8 and struct.unpack_from('<Q',bytes.fromhex(p['body']))[0]==pet['guid']]
    if not native:raise RuntimeError('normally controlled Hunter native catalog absent')
    packet=native[-1];n=catalog(packet['body'])
    delivered=[]
    for p in packets:
        if p['direction']!='to_client' or p['name']!='SMSG_PET_SPELLS_MESSAGE' or p['time']<packet['time']:continue
        m=modern_catalog(p['body']);checks=catalog_checks(n,m,pet['guid'],pet['map'])
        if all(checks.values()):delivered.append((p,m,checks))
    if len(delivered)!=1:raise RuntimeError('requires one exact attributable Hunter catalog delivery')
    return {'native_packet':packet,'client_packet':delivered[0][0],
        'native':n,'modern':delivered[0][1],'checks':delivered[0][2]}


def suite(t,preparation,entry,trained,menu):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    if (t.fixture['guid'],t.fixture['character_name'],t.fixture['class'],t.fixture['level'])!=(6,'Harnesshunt',3,10):
        raise RuntimeError('requires the normally trained exact Hunter')
    e=entry_source(t,entry,session,preparation);learned=prior(t,trained,session,'control_pet_trained')
    if not all(learned.get('purchase_checks',{}).values()) or len(learned.get('purchase_checks',{}))!=9:
        raise RuntimeError('requires the whole normally paid Control Pet purchase')
    since=min(p['time'] for p in e['login_packets']);o=Presence(session,6,since).poll()
    retained=pets(6);inv=Inventory(lab.ROOT,session,6).poll()
    if (not starting_wolf(retained,6) or not o.present() or o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=4 or
        resources(inv)!=learned['after'] or saved(6)['spells']!=[[1515,1,0],[79682,1,0]]):
        raise RuntimeError('retained starting Wolf or normally purchased Hunter resources differ')
    initial,initial_frame=t.observe('hunter_pet_baseline');before=resources(inv);before_saved=saved(6)
    t.receipt.update(native_session=session,sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in
        (entry,trained)],native_pet=o.pet,retained_pet=retained,baseline_frame=initial_frame,
        qualified_scope='Owned Hunter pet catalog/menu reconnaissance only; no new interaction qualification.')
    try:
        t.clean_panels()
        require(click_case(t,'hunter.pet_book','Open the stock book for passive Hunter pet state.',
            lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'hunter_pet_book_pass' if s and
                'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'}),'hunter_pet_book_pass')
        book=detail(t,'hunter_pet_public');t.clean_panels();bar=commands(t,'hunter_pet_commands')
        o.poll();pair=catalog_pair(session,learned['purchase_started_at'],o.pet);guid=expected_guid(o.pet)
        p=book['pet'];actions=bar['probe'].get('actions',[])
        checks={'owned_public_pet':p.get('exists') is True and p.get('guid')==guid and p.get('name')=='Wolf',
            'owned_public_commands':bar['probe'].get('pet_guid')==guid and bar['probe'].get('owner_guid')==t.guid,
            'ten_readable_actions':len(actions)==10 and all(r.get('available') for r in actions),
            'visible_attack':any(r.get('name')=='PET_ACTION_ATTACK' and r.get('frame',{}).get('visible') for r in actions),
            'exact_catalog_delivery':all(pair['checks'].values()),'ui_clean':bar['ui_clean']}
        t.receipt.update(public_pet=p,public_commands=bar['probe'],catalog_pair=pair,checks=checks);t.persist()
        if not all(checks.values()):raise RuntimeError('public controlled Hunter pet differs')
        if menu:
            t.execute({'kind':'chat','value':'/target pet'});state,_=t.observe('hunter_pet_targeted')
            oracle=PetOracle(session,6,since).poll()
            if state.get('target',{}).get('guid')!=guid or oracle.selected()!=o.pet['guid']:
                raise RuntimeError('stock pet target is not the owned Wolf')
            pet_frame_menu(t,oracle,guid)
    finally:
        t.clean_panels()
        target=initial.get('target',{})
        if target.get('name')=='Benjamin Foxworthy':t.execute({'kind':'chat','value':'/targetexact Benjamin Foxworthy'})
        elif not target.get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        else:raise RuntimeError('Hunter pet recon baseline target cannot be restored normally')
        state,frame=t.observe('hunter_pet_restored');o.poll();inv.poll()
        restored_pets=pets(6)
        checks={'resources':resources(inv)==before,'saved_rows':saved(6)==before_saved,
            'retained_pet':saved_pet_unchanged(retained,restored_pets,time.time()),
            'position':state['world_position']==initial['world_position'],
            'selection':state.get('target',{}).get('guid')==initial.get('target',{}).get('guid'),
            'panels_closed':not state.get('panels'),'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),
            'pet_still_present':o.present(),**protected(old)}
        t.receipt.update(restoration_checks=checks,restored_frame=frame,protected_checks=protected(old),
            restored_pets=restored_pets,pet_save_clock={'before':retained[0]['savetime'],
                'after':restored_pets[0]['savetime'],
                'native_sources':['src/server/game/Entities/Player/Player.cpp:19324',
                    'src/server/game/Entities/Pet/PetPersistence.cpp:374']});t.persist()
        if not all(checks.values()):raise RuntimeError('Hunter pet reconnaissance restoration differs')
    t.receipt.update(completed=True,phase='hunter_pet_menu_recon' if menu else 'hunter_pet_catalog_recon')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','trained','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--menu',action='store_true');a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.trained,a.menu)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase')}),flush=True)
