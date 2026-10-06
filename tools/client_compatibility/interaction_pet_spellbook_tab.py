"""Open the stock trained-Imp spellbook and match its contents to the native catalog."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,SCRIPT_BOUNDARY
from .interaction_pet_control_training import protected
from .interaction_pet_target import PetOracle,pair,source,retained_imp
from .interaction_pet_training_disconnect import catalog
from .interaction_spellbook_pet_recon import entry_source
from .interaction_spellbook_navigation import detail
from .interaction_spellbook_recon import resources
from .interaction_operations import click_case
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.buffer import Reader
from .world.gameobjects import modern_guid
from .world.objects import INDEX


def modern_catalog(body):
    r=Reader(bytes.fromhex(body));guid=r.guid()
    family,spec,duration,command,flags,react=r.unpack('HHIBBB');buttons=list(r.unpack('10I'))
    count,cooldowns,history=r.unpack('3I')
    if count>255 or cooldowns>255 or history:raise RuntimeError('modern pet catalog exceeds native shape')
    actions=list(r.unpack('I'*count));cooldown_rows=[list(r.unpack('iiifH')) for _ in range(cooldowns)];r.end()
    return dict(guid=list(guid),family=family,spec=spec,duration=duration,command=command,flags=flags,
        react=react,buttons=buttons,actions=actions,cooldowns=cooldown_rows)


def catalog_checks(native,modern,guid,map_id):
    types={0:0,1:1,6:6,7:7,0x81:0x101,0xc1:0x181}
    def actions_equal(left,right):
        return len(left)==len(right) and all((a&0xffffff)==(b&0x7fffff) and
            types.get(a>>24)==b>>23 for a,b in zip(left,right))
    return {'owned_guid':native['guid']==guid and modern['guid']==list(modern_guid(guid,map_id)),
        'modes':all(native[k]==modern[k] for k in ['family','duration','command','flags','react']) and modern['spec']==0,
        'buttons':actions_equal(native['buttons'],modern['buttons']),
        'known_actions':actions_equal(native['actions'],modern['actions']),
        'cooldowns':len(native['cooldowns'])==len(modern['cooldowns']) and all(
            [n[0],n[2],n[3],1.0,n[1]]==m for n,m in zip(native['cooldowns'],modern['cooldowns']))}


def suite(t,preparation,entry,probe):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);p=source(t,probe,session,entry)
    retained=retained_imp(t.fixture,old['retained_class_pets'])
    if t.fixture['guid']!=5 or not p.get('native_control_demon_known') or [80388,1,0] not in e['entered_saved']['spells']:
        raise RuntimeError('requires the normally trained eligible control fixture')
    owner=PetOracle(session,5,e['started_at']).poll();pet=owner.pet
    if (not pet or pair(pet['fields'],'UNIT_FIELD_SUMMONEDBY')!=5 or
        pair(owner.player,'UNIT_FIELD_SUMMON')!=pet['guid'] or
        pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=retained['id']):
        raise RuntimeError('native catalog owner links differ')
    packets=[r for r in entries(lab.ROOT/'evidence/world_packets.jsonl') if r.get('session')==session and
        e['started_at']<=r.get('time',0)<=e['finished_at'] and r.get('name') in
        ['SMSG_PET_SPELLS','SMSG_PET_SPELLS_MESSAGE']]
    native=[r for r in packets if r['direction']=='from_native' and r['name']=='SMSG_PET_SPELLS']
    modern=[r for r in packets if r['direction']=='to_client' and r['name']=='SMSG_PET_SPELLS_MESSAGE']
    if len(native)!=1 or len(modern)!=1:raise RuntimeError('requires one native and public entry pet catalog')
    n=catalog(native[0]['body']);m=modern_catalog(modern[0]['body']);checks=catalog_checks(n,m,pet['guid'],pet['map'])
    if not all(checks.values()):raise RuntimeError('native and modern owned pet catalogs differ')
    inventory=Inventory(lab.ROOT,session,5).poll()
    if resources(inventory)!=e['resources'] or saved(5)!=e['entered_saved']:
        raise RuntimeError('original trained entry state changed')
    t.receipt.update(sources=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (entry,probe)],
        native_session=session,native_owned_pet=pet,catalog_packets=packets,native_catalog=n,
        modern_catalog=m,catalog_checks=checks,qualified_scope='Normal Pet spellbook tab and exact native-known spell contents only.')
    t.persist();t.clean_panels()
    try:
        require(click_case(t,'fixture.pet_tab.open','Open the stock spellbook.',lambda c:c['name']=='SpellbookMicroButton',
            lambda b,a,s:{'status':'spellbook_open_pass' if s and 'SpellBookFrame' in a['panels'] else
                'client_or_protocol_failure'}),'spellbook_open_pass')
        require(click_case(t,'spellbook.pet_tab','Open the observed Pet spellbook tab.',
            lambda c:c['name']=='SpellBookFrameTabButton3' and c['text']=='Pet',
            lambda b,a,s:{'status':'pet_tab_selected_pass' if s and 'SpellBookFrame' in a['panels'] else
                'client_or_protocol_failure'}),'pet_tab_selected_pass')
        book=detail(t,'owned_pet_tab');state,frame=t.observe('owned_pet_tab_contents')
        ids=sorted(a&0xffffff for a in n['actions'])
        public=sorted(r.get('api_id') for r in book.get('rows',[]) if type(r.get('api_id')) is int)
        checks={'pet_book':book.get('book_type')==book.get('book_types',{}).get('pet'),
            'owned_pet':book.get('pet',{}).get('guid')==p['public_pet']['guid'],
            'exact_native_spells':public==ids,'known_named_rows':all(r.get('known') is True and r.get('name') and
                r.get('shown_name')==r.get('name') for r in book.get('rows',[])),
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt.update(pet_book=book,pet_tab_checks=checks,pet_tab_frame=frame);t.persist()
        if not all(checks.values()):raise RuntimeError('stock pet spellbook contents differ from native catalog')
    finally:
        t.clean_panels();state,frame=t.observe('pet_tab_restored')
        checks=protected(old);checks.update(resources=resources(inventory)==e['resources'],
            saved_rows=saved(5)==e['entered_saved'],panels_closed=not state.get('panels') and not state.get('bags'),
            ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'))
        t.receipt.update(restoration_checks=checks,restored_frame=frame);t.persist()
        if not all(checks.values()):raise RuntimeError('stock pet tab original restoration differs')
    t.receipt.update(completed=True,phase='owned_pet_spellbook_tab_complete')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['preparation','entry','probe','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.probe)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure','catalog_checks','pet_tab_checks','restoration_checks']}),flush=True)
