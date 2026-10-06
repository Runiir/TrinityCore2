"""Capture one stock pet ground request, then restore ordinary Follow and Assist."""
import argparse,copy,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY,reviewed
from .interaction_retained_class_fixture import closed
from .interaction_pet_commands import eligibility,PET_KEYS
from .interaction_pet_command_probe import read,expected_guid,follow_row
from .interaction_pet_target import pair,retained_imp
from .interaction_pet_dismiss import vitals
from .interaction_pet_follow_capture import follow_request
from .interaction_pet_react_modes import public_bar,mode,whole_restore
from .interaction_spellbook_recon import resources
from .interaction_ground_movement import position
from .interaction_sit_stand import pose,afk
from .interaction_owned_class_fixture import character,pets
from .interaction_macros import require
from .pet_command_evidence import command_checks
from .observation.journal import entries,latest
from .world.gameobjects import modern_guid


def button(probe,pet):
    if probe.get('owner_guid')!='Player-1-00000005' or probe.get('pet_guid')!=expected_guid(pet):
        raise RuntimeError('Move To requires the current owned public Imp')
    rows=[r for r in probe.get('actions',[]) if r.get('slot')==3 and r.get('name')=='PET_ACTION_MOVE_TO']
    if len(rows)!=1:raise RuntimeError('observed stock Move To button is absent or ambiguous')
    row=rows[0];frame=row.get('frame',{})
    if (row.get('available') is not True or row.get('is_token') is not True or
        frame.get('button')!='PetActionButton3' or
        not all(frame.get(k) is True for k in ('available','visible','enabled')) or
        any(type(frame.get(k)) is not int or not 0<=frame[k]<65535 for k in ('x','y'))):
        raise RuntimeError('stock Move To button geometry or availability differs')
    return row,[round(frame['x']/65535*1280),round(frame['y']/65535*720)]


def packets(o,since):
    names={'CMSG_PET_ACTION','CMSG_PET_ABANDON','CMSG_PET_SET_ACTION','CMSG_CAST_SPELL'}
    return [p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('session')==o.session
        and since<=p.get('time',0)<=time.time() and p.get('name') in names]


def restore(t,o,inventory,old):
    t.clean_panels();since=time.time()
    def followed(b,a,s):
        o.poll();sample=read(t,'moveto_follow_restored');checks=command_checks(packets(o,since),o.pet,1)
        row=follow_row(sample['probe'])
        checks.update(public_follow=bool(row and row.get('active')),current_owned_pet=o.present(),
            public_owned_pet=sample['probe'].get('pet_guid')==expected_guid(o.pet),ui_clean=sample['ui_clean'])
        return {'status':'owned_native_follow_cleanup_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'requests':packets(o,since),'public':sample}}
    try:
        require(t.step('fixture.moveto_restore.follow','Restore the stock Follow command through its captured native route.',
            {'follow':{'kind':'chat','value':'/petfollow'}},followed,diagnostic_action='follow'),
            'owned_native_follow_cleanup_pass')
        mode(t,o,3,'fixture.pet_assist_restore')
    finally:whole_restore(t,o,inventory,old,t.receipt['baseline'])


def begin(t,preparation,entry):
    old,e,o,inventory,identity=eligibility(t,preparation,entry);t.clean_panels()
    sample=read(t,'moveto_stock_baseline');row,point=button(sample['probe'],o.pet)
    if row.get('usable') is not True or sample['probe'].get('modified_click') is not False:
        raise RuntimeError('requires observed usable Move To without a modified click')
    state,_=t.observe('moveto_original_scene');catalogs=[c for c in o.catalogs if c['guid']==o.pet['guid']]
    follow=follow_row(sample['probe'])
    if (not sample['ui_clean'] or not catalogs or catalogs[-1]['react']!=3 or catalogs[-1]['command']!=1
        or identity['Reactstate']!=3 or not follow or not follow.get('active') or
        state.get('spell_targeting') is not False):raise RuntimeError('requires original idle Assist/Follow without a target cursor')
    baseline={'resources':resources(inventory),'saved':e['entered_saved'],'position':position(5),'vitals':vitals(o),
        'pet':{k:identity[k] for k in PET_KEYS},'pose':pose(inventory),'afk':afk(inventory),
        'money':character(5,2)['money'],'public_bar':public_bar(sample['probe'])}
    t.receipt.update(baseline=baseline,native_pet=copy.deepcopy(o.pet),native_catalog=catalogs[-1],
        observed_button=row,qualification_added=False);t.persist();since=time.time()
    try:
        def selected(b,a,s):
            # A pet destination cursor can be hidden while the pointer remains
            # over the stock bar. Inspect it over visible ground before judging
            # selection; this hover submits no ground request.
            t.execute({'kind':'hover','value':[875,545]})
            state,frame=t.observe('moveto_ground_reticle')
            o.poll();requests=packets(o,since)
            checks={'stock_targeting_cursor':state.get('spell_targeting') is True,'no_pet_or_owner_command_yet':not requests,
                'current_owned_pet':o.present() and o.pet['guid']==t.receipt['native_pet']['guid'],
                'owner_vitals':vitals(o)==baseline['vitals'],'position':position(5)==baseline['position'],
                'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
            t.receipt.update(reticle_frame=frame,reticle_state=state,
                selection_observation='one stock AnyUp click followed by non-click ground hover');t.persist()
            return {'status':'owned_pet_moveto_reticle_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'ground_state':state,'ground_frame':frame,
                    'qualification_added':False}}
        require(t.step('diagnostic.pet_moveto.reticle','Select the observed stock Move To button once.',
            {'select':{'kind':'click','value':point,'hold':.4}},selected,diagnostic_action='select'),
            'owned_pet_moveto_reticle_pass')
        t.receipt.update(completed=True,phase='await_owned_pet_moveto_ground_review',
            qualified_scope='Stock Move To selection and pending ordinary target cursor only. '
            'Ground input requires a fresh separate source-bound visual review; no gameplay qualification.')
    except Exception:
        restore(t,o,inventory,old);raise


def source(d,t,hashes):
    if (d.get('completed') is not True or not d.get('finished_at') or d.get('failure') is not None or
        d.get('phase')!='await_owned_pet_moveto_ground_review' or d.get('actor')!=t.fixture or
        d.get('runtime')!=t.receipt['runtime'] or [r.get('sha256') for r in d.get('sources',[])]!=hashes or
        d.get('qualification_added') is not False or d.get('custom_script_permission')!='blocked_by_user' or
        d.get('softTargetInteract')!=SCRIPT_BOUNDARY or len(d.get('cases',[]))!=1 or
        d['cases'][0].get('id')!='diagnostic.pet_moveto.reticle' or
        d['cases'][0].get('status')!='owned_pet_moveto_reticle_pass' or
        len(d['cases'][0].get('oracle',{}).get('checks',{}))!=6 or
        not all(d['cases'][0].get('oracle',{}).get('checks',{}).values()) or
        d.get('reticle_state',{}).get('spell_targeting') is not True):
        raise RuntimeError('closed owned Move To reticle source differs')
    return d


def finish(t,preparation,entry,reticle,review_path):
    old,e,o,inventory,identity=eligibility(t,preparation,entry)
    d=source(closed(reticle),t,[lab.sha256(p.resolve()) for p in (preparation,entry)])
    t.receipt.update(baseline=copy.deepcopy(d['baseline']),reticle_source={'path':str(reticle.resolve()),
        'sha256':lab.sha256(reticle)},qualification_added=False);t.persist()
    try:
        checked=reviewed(t,review_path,'owned_pet_move_to_ground')
        state,_=t.observe('moveto_pending_ground');o.poll()
        if (checked.get('reticle_source_sha256')!=lab.sha256(reticle) or
            checked['frame']['sha256']!=d['reticle_frame']['sha256'] or state.get('spell_targeting') is not True or
            o.session!=d.get('native_session') or not o.present() or o.pet['guid']!=d['native_pet']['guid'] or
            pair(o.player,'UNIT_FIELD_TARGET')!=0 or vitals(o)!=d['baseline']['vitals']):
            raise RuntimeError('reviewed current owned Move To cursor or native fixture differs')
        since=time.time();t.receipt['moveto_ground_started_at']=since;t.persist()
        def outcome(b,a,s):
            sample=read(t,'moveto_ground_outcome');state,frame=t.observe('moveto_capture_scene');o.poll()
            requests=packets(o,since);modern=[p for p in requests if p.get('direction')=='from_client']
            native=[p for p in requests if p.get('direction')=='to_native']
            t.receipt['actual_moveto_requests']={'modern':modern,'native':native,'wire_layout_inferred':False};t.persist()
            decoded=follow_request(modern[0]) if len(modern)==1 and modern[0]['name']=='CMSG_PET_ACTION' else None
            rejection=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==o.session and
                r.get('time',0)>=since and r.get('event')=='pet_action_translation_rejected')
            checks={'one_actual_stock_pet_action':len(modern)==1 and modern[0]['name']=='CMSG_PET_ACTION',
                'current_owned_guid':bool(decoded and decoded['guid']==list(modern_guid(o.pet['guid'],o.pet['map']))),
                'finite_ground_destination':bool(decoded and all(math.isfinite(v) for v in decoded['position'])
                    and any(v!=0 for v in decoded['position'])),
                'no_native_command':not native,'healthy_rejection':bool(rejection),
                'targeting_cursor_completed':state.get('spell_targeting') is False,
                'same_owned_pet':o.present() and o.pet['guid']==d['native_pet']['guid'],
                'public_owned_pet':sample['probe'].get('pet_guid')==expected_guid(o.pet),
                'owner_vitals':vitals(o)==d['baseline']['vitals'],'position':position(5)==d['baseline']['position'],
                'public_idle':sample['probe'].get('pet_speed')==sample['probe'].get('player_speed')==0,
                'saved_pet_identity':all(retained_imp(t.fixture,pets(5))[k]==v for k,v in d['baseline']['pet'].items()),
                'ui_clean':sample['ui_clean']}
            return {'status':'owned_pet_moveto_shape_capture_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'decoded':decoded,'rejection':rejection,
                    'public':sample,'state':state,'frame':frame,'native_pet':copy.deepcopy(o.pet),'qualification_added':False}}
        require(t.step('diagnostic.pet_moveto.ground','Complete the reviewed stock Move To cursor with one ordinary ground click.',
            {'ground':{'kind':'click','value':checked['point'],'hold':.4}},outcome,diagnostic_action='ground'),
            'owned_pet_moveto_shape_capture_pass')
    finally:restore(t,o,inventory,old)
    t.receipt.update(completed=True,phase='owned_pet_moveto_capture_complete',qualified_scope=
        'Actual stock Move To ground request and healthy native rejection only, followed by captured native Follow, '
        'Assist and whole original-state restoration. Native movement and pets.command_move_to remain unqualified.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['begin','finish'])
    for n in ('preparation','entry','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--reticle',type=Path);p.add_argument('--review',type=Path);a=p.parse_args()
    if a.action=='finish' and (a.reticle is None or a.review is None):p.error('finish needs closed reticle source and visual review')
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='begin':begin(t,a.preparation,a.entry)
            else:finish(t,a.preparation,a.entry,a.reticle,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
