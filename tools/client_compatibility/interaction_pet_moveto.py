"""Complete one reviewed stock Move To, prove native motion and restore the whole fixture."""
import argparse,copy,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY,reviewed,character,pets,saved
from .interaction_retained_class_fixture import closed
from . import interaction_pet_moveto_capture as capture
from .interaction_pet_commands import eligibility
from .interaction_pet_command_probe import read,expected_guid,follow_row
from .interaction_pet_target import pair,retained_imp
from .interaction_pet_dismiss import vitals
from .interaction_pet_spell import SpellPresence,pet_vitals,restore_spell
from .pet_spell_evidence import buffs
from .pet_command_evidence import range_state
from .pet_moveto_evidence import request_checks,motion_checks
from .pet_movement_evidence import movement_pairs
from .interaction_ground_movement import position
from .interaction_macros import require
from .observation.journal import entries,latest


def finish(t,preparation,entry,reticle,review_path):
    old,e,base,inventory,identity=eligibility(t,preparation,entry)
    d=capture.source(closed(reticle),t,[lab.sha256(p.resolve()) for p in (preparation,entry)])
    o=SpellPresence(base.session,5,base.started).poll()
    t.receipt.update(baseline=copy.deepcopy(d['baseline']),reticle_source={'path':str(reticle.resolve()),
        'sha256':lab.sha256(reticle)},qualification_added=False);t.persist()
    original=None
    try:
        checked=reviewed(t,review_path,'owned_pet_move_to_ground')
        capture.ground_review(d,checked,lab.sha256(reticle))
        state,frame=t.observe('moveto_pending_native_ground');o.poll()
        if (state.get('spell_targeting') is not d['reticle_state']['spell_targeting'] or
            o.session!=d.get('native_session') or not o.present() or o.pet['guid']!=d['native_pet']['guid'] or
            pair(o.player,'UNIT_FIELD_TARGET')!=0 or vitals(o)!=d['baseline']['vitals']):
            raise RuntimeError('reviewed current owned Move To cursor or native fixture differs')
        original={'auras':copy.deepcopy(o.auras),'public_buffs':buffs(state),'pet_vitals':pet_vitals(o)}
        if 6307 in original['public_buffs'] or any(r['spell']==6307 for r in original['auras'].values()):
            raise RuntimeError('requires the original owned fixture without Blood Pact')
        t.receipt['spell_baseline']={**original,'frame':frame,'native_pet':copy.deepcopy(o.pet)}
        input_pet=copy.deepcopy(o.pet);since=time.time();t.receipt['moveto_ground_started_at']=since;t.persist()
        def outcome(b,a,s):
            sample=read(t,'moveto_native_ground_outcome');state,frame=t.observe('moveto_native_scene');o.poll()
            until=time.time();packets=list(entries(lab.ROOT/'evidence/world_packets.jsonl'))
            checks,requests=request_checks(packets,o.session,since,until,input_pet)
            paths=movement_pairs(packets,o.session,input_pet['guid'],input_pet['map'],since,until)
            checks.update(motion_checks(paths,requests))
            rejection=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==o.session and
                since<=r.get('time',0)<=until and r.get('event')=='pet_action_translation_rejected')
            row,point=capture.button(sample['probe'],o.pet);follow=follow_row(sample['probe'])
            checks.update(no_translation_rejection=rejection is None,
                same_owned_pet=o.present() and o.pet['guid']==input_pet['guid'],
                public_owned_pet=sample['probe'].get('pet_guid')==expected_guid(input_pet),
                public_move_to_selected=row.get('active') is True,
                public_follow_clear=bool(follow and follow.get('active') is False),
                public_pet_near=range_state(sample['probe'],True),
                public_pet_visible=sample['probe'].get('pet_visible') is True,
                public_idle=sample['probe'].get('pet_speed')==sample['probe'].get('player_speed')==0,
                owner_vitals=vitals(o)==d['baseline']['vitals'],position=position(5)==d['baseline']['position'],
                saved=saved(5)==d['baseline']['saved'],money=character(5,2)['money']==d['baseline']['money'],
                saved_pet_identity=all(retained_imp(t.fixture,pets(5))[k]==v for k,v in d['baseline']['pet'].items()),
                ui_clean=sample['ui_clean'])
            return {'status':'owned_native_pet_moveto_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'movement_pairs':paths,'rejection':rejection,
                    'public':sample,'state':state,'frame':frame,'native_pet':copy.deepcopy(o.pet),
                    'pet_coordinates_available':False}}
        require(t.step('pets.command_move_to','Complete one reviewed stock pet destination and require delivered native movement.',
            {'ground':{'kind':'click','value':checked['point'],'hold':.4}},outcome,diagnostic_action='ground'),
            'owned_native_pet_moveto_pass')
        readback_since=time.time();t.execute({'kind':'chat','value':'/reload'})
        sample=read(t,'moveto_native_catalog_readback');o.poll()
        catalogs=[c for c in o.catalogs if c['guid']==input_pet['guid'] and c['packet']['time']>=readback_since]
        row,_=capture.button(sample['probe'],o.pet);follow=follow_row(sample['probe'])
        checks={'fresh_native_move_to_catalog':bool(catalogs) and catalogs[-1]['command']==4 and catalogs[-1]['react']==3,
            'public_move_to_readback':row.get('active') is True,
            'public_follow_clear':bool(follow and follow.get('active') is False),
            'same_owned_pet':o.present() and o.pet['guid']==input_pet['guid'],
            'public_owned_pet':sample['probe'].get('pet_guid')==expected_guid(input_pet),
            'saved':saved(5)==d['baseline']['saved'],'owner_vitals':vitals(o)==d['baseline']['vitals'],
            'position':position(5)==d['baseline']['position'],'ui_clean':sample['ui_clean']}
        t.receipt['moveto_readback']={'checks':checks,'catalogs':catalogs,'public':sample};t.persist()
        if not all(checks.values()):raise RuntimeError('fresh native/public Move To readback differs')
    finally:
        capture.restore(t,o,inventory,old,before_whole=(lambda:restore_spell(t,o,original)) if original else None)
    t.receipt.update(completed=True,phase='owned_native_pet_moveto_complete',qualified_scope=
        'One owned retained Imp, observed stock Move To and separately reviewed ground destination, exact native '
        'command and delivered path to that destination, fresh native/public command readback, then ordinary '
        'Follow, Assist, aura/vitals and whole original-state restoration. Public pet coordinates are unavailable.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('preparation','entry','reticle','review','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:finish(t,a.preparation,a.entry,a.reticle,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
