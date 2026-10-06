"""Target the observed owned Imp and compare its health and optional mana."""
import argparse,json,re,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_macros import require
from .interaction_owned_class_fixture import prepared,origin_checks,saved,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import Cursor
from .world.native_objects import records
from .world.objects import INDEX
from .world.gameobjects import modern_guid
from .world.buffer import Reader
from .interaction_operations import click_case
from .interaction_spellbook_navigation import detail


def pair(fields,name):
    i=INDEX[name];return fields.get(i,0)|(fields.get(i+1,0)<<32)


class PetOracle:
    def __init__(self,session,owner,started):
        self.cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
        self.session,self.owner,self.started=session,owner,started
        self.player={};self.pet=None;self.requests=[]

    def poll(self):
        for p in self.cursor.poll():
            if p.get('session')!=self.session or p.get('time',0)<self.started:continue
            if p.get('name')=='CMSG_SET_SELECTION':self.requests.append(p)
            if p.get('direction')!='from_native' or p.get('name')!='SMSG_UPDATE_OBJECT':continue
            for r in records(bytes.fromhex(p['body'])):
                fields=r.get('fields',{})
                if r.get('guid')==self.owner:self.player.update(fields)
                if r.get('kind')==3 and r['guid']>>52==0xf14 and pair(fields,'UNIT_FIELD_SUMMONEDBY')==self.owner:
                    if self.pet and self.pet['guid']!=r['guid']:raise RuntimeError('ambiguous owned pet creation')
                    self.pet=r
                elif self.pet and r.get('guid')==self.pet['guid']:
                    self.pet['fields'].update(fields)
                if self.pet and r.get('update_type')==3 and self.pet['guid'] in r.get('removed',[]):
                    raise RuntimeError('owned pet left visibility during the trial')
        return self

    def selected(self):return pair(self.player,'UNIT_FIELD_TARGET')


def source(t,probe,session,entry):
    p=closed(probe)
    if (p.get('phase')!='native_pet_public_comparison' or p.get('actor')!=t.fixture or
        p.get('runtime')!=t.receipt['runtime'] or p.get('source',{}).get('sha256')!=lab.sha256(entry) or
        p.get('public_pet',{}).get('exists') is not True or not p.get('native_resources_preserved') or
        set(p.get('origin_checks',{}))!={'original_character','original_saved_rows','native_worldserver'} or
        not all(p['origin_checks'].values()) or not re.fullmatch('[A-Za-z]{1,24}',p['public_pet'].get('name',''))):
        raise RuntimeError('requires the closed same-entry public owned pet probe')
    return p


def power_checks(oracle,state,public,expected):
    pet=oracle.pet;fields=pet['fields'] if pet else {}
    native={'power':fields.get(INDEX['UNIT_FIELD_POWER1'],0),
        'max_power':fields.get(INDEX['UNIT_FIELD_MAXPOWER1'],0),
        'power_type':fields.get(INDEX['UNIT_FIELD_BYTES_0'],0)>>24&255}
    checks={'native_target':bool(pet and oracle.selected()==pet['guid']),
        'owned_pet':bool(pet and pair(fields,'UNIT_FIELD_SUMMONEDBY')==oracle.owner and
            pair(oracle.player,'UNIT_FIELD_SUMMON')==pet['guid']),
        'public_target':state['target'].get('guid')==expected,
        'public_pet':public.get('exists') is True and public.get('guid')==expected,
        'mana_type':INDEX['UNIT_FIELD_BYTES_0'] in fields and native['power_type']==0 and public.get('power_type')==0,
        'power':0<native['power']<=native['max_power'] and
            all(type(public.get(k)) is int and public[k]==v for k,v in native.items()),
        'visible_target':state['target'].get('visible') is True,
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    return checks,native


def read_power(t,oracle,expected):
    require(click_case(t,'fixture.pet_power.book_open','Open the observed stock spellbook for passive mana readings.',
        lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'spellbook_open_pass' if s and
            'SpellBookFrame' in a['panels'] and not a.get('lua_errors') and not a.get('blocked_actions') else
            'client_or_protocol_failure'}),'spellbook_open_pass')
    probe=detail(t,'owned_pet_power');snapshot=t.receipt['spellbook_details']['owned_pet_power']
    if snapshot['state'].get('observer_version')!=129:
        raise RuntimeError('requires passive pet-power observer129')
    oracle.poll();checks,native=power_checks(oracle,snapshot['state'],probe['pet'],expected)
    row={'id':'pets.pet_power','time':time.time(),'status':'native_owned_pet_power_pass' if all(checks.values()) else
        'client_or_protocol_failure','input_sent':False,'scope':'Read mana of the selected owned Imp.',
        'after':snapshot['state'],'after_frame':snapshot['frame'],
        'oracle':{'checks':checks,'native':native,'public':probe['pet']}}
    t.receipt['cases'].append(row);t.persist();require(row,'native_owned_pet_power_pass')


def suite(t,preparation,entry,probe,power=False):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);p=source(t,probe,session,entry)
    oracle=PetOracle(session,t.fixture['guid'],e['started_at']).poll()
    items=Inventory(lab.ROOT,session,t.fixture['guid']).poll();pet=oracle.pet
    if (not pet or pet['guid']>>32&0xfffff!=416 or pair(oracle.player,'UNIT_FIELD_SUMMON')!=pet['guid'] or
        pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'],0)!=1 or oracle.selected()!=0 or
        resources(items)!=e['resources'] or saved(t.fixture['guid'])!=e['entered_saved']):
        raise RuntimeError('owned pet identity or original empty selection differs')
    guid=pet['guid'];expected=f"Pet-0-1-{pet['map']}-0-{guid>>32&0xfffff}-{guid&0xffffffff:010X}"
    if p['public_pet']['guid']!=expected:raise RuntimeError('native and public pet GUIDs differ')
    t.receipt.update(sources=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (entry,probe)],
        native_session=session,native_pet=pet,public_pet=p['public_pet'],
        qualified_scope='Ordinary exact-name targeting and selected owned Imp health'+(' and mana' if power else '')+
            ' only; no pet command or pet-tab qualification.')
    t.persist();before,_=t.observe('pet_target_baseline')
    if before['target']['exists']:raise RuntimeError('public original selection is not empty')
    try:
        since=time.time()
        def outcome(b,a,selected):
            oracle.poll();requests=[r for r in oracle.requests if r['time']>=since]
            modern=[]
            for r in requests:
                if r['direction']=='from_client':
                    reader=Reader(bytes.fromhex(r['body']));modern.append(reader.guid());reader.end()
            checks={'ordinary_input':selected=='target','public_target':a['target'].get('guid')==expected,
                'public_name':a['target'].get('name')==p['public_pet']['name'],
                'native_target':oracle.selected()==guid,
                'owned_pet':pair(pet['fields'],'UNIT_FIELD_SUMMONEDBY')==t.fixture['guid'] and pair(oracle.player,'UNIT_FIELD_SUMMON')==guid,
                'modern_request':modern_guid(guid,pet['map']) in modern,
                'native_request':any(r['direction']=='to_native' and r['body']==struct.pack('<Q',guid).hex() for r in requests),
                'position':b['world_position']==a['world_position'],
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'native_owned_pet_target_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'native_target':oracle.selected()}}
        require(t.step('pets.pet_target','Target the visible owned pet by its observed name.',
            {'target':{'kind':'chat','value':'/targetexact '+p['public_pet']['name'],'description':'Use the stock exact-name target command.'}},
            outcome,diagnostic_action='target',await_state=lambda a:a['target'].get('guid')==expected),
            'native_owned_pet_target_pass')
        state,frame=t.observe('owned_pet_health');oracle.poll();fields=pet['fields']
        native={'health':fields.get(INDEX['UNIT_FIELD_HEALTH'],0),'max_health':fields.get(INDEX['UNIT_FIELD_MAXHEALTH'],0)}
        checks={'native_target':oracle.selected()==guid,'public_target':state['target'].get('guid')==expected,
            'health':0<native['health']<=native['max_health'] and all(state['target'].get(k)==v for k,v in native.items()),
            'visible_target':state['target'].get('visible') is True,
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        row={'id':'pets.pet_health','time':time.time(),'status':'native_owned_pet_health_pass' if all(checks.values()) else
            'client_or_protocol_failure','input_sent':False,'scope':'Read health of the selected owned pet.',
            'after':state,'after_frame':frame,'oracle':{'checks':checks,'native':native}}
        t.receipt['cases'].append(row);t.persist();require(row,'native_owned_pet_health_pass')
        if power:read_power(t,oracle,expected)
    finally:
        state,_=t.observe('pet_cleanup_before')
        if state['target'].get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        t.clean_panels();state,frame=t.observe('pet_cleanup_complete');oracle.poll()
        checks=origin_checks(old);checks.update(empty_selection=oracle.selected()==0 and not state['target']['exists'],
            resources=resources(items)==e['resources'],saved_rows=saved(t.fixture['guid'])==e['entered_saved'],
            position=state['world_position']==before['world_position'],
            panels_closed=not state.get('panels') and not state.get('bags'),
            ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'))
        t.receipt.update(restoration_checks=checks,restored_frame=frame);t.persist()
        if not all(checks.values()):raise RuntimeError('owned pet targeting restoration differs')
    t.receipt.update(completed=True,phase='owned_pet_target_health_power_complete' if power else 'owned_pet_target_health_complete')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','probe','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--power',action='store_true',help='Read owned Imp mana with passive observer129')
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.probe,a.power)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
