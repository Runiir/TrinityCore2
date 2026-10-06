"""Recover the retained Imp after one closed, unexecuted health staging failure."""
import argparse,copy,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_owned_melee_health import HealthPresence
from .interaction_pet_spell import restore_spell
from .interaction_pet_react_modes import mode,whole_restore
from .interaction_pet_summon import SummonOracle,summon_checks
from .interaction_pet_command_probe import read
from .interaction_pet_target import pair
from .interaction_spellbook_navigation import wire_known
from .interaction_ground_movement import position
from .interaction_macros import require
from .observation.inventory import Inventory


def eligible(d,t,hashes):
    checks=d.get('restoration_checks',{})
    missing={'persisted_assist','owned_pet','public_assist','public_pet_bar'}
    if (d.get('completed') is not False or not d.get('finished_at') or
        d.get('failure')!='RuntimeError: native pet reaction-mode restoration differs' or
        d.get('actor')!=t.fixture or t.fixture.get('guid')!=5 or d.get('runtime')!=t.receipt['runtime'] or
        [s.get('sha256') for s in d.get('sources',[])]!=hashes or
        len(checks)!=17 or {k for k,v in checks.items() if not v}!=missing or
        len(d.get('protected_checks',{}))!=6 or not all(d['protected_checks'].values()) or
        [c['id'] for c in d.get('cases',[])]!=['fixture.health_pet_passive','fixture.moveto_restore.follow'] or
        d['cases'][0].get('status')!='owned_native_react_mode_pass' or
        not all(d['cases'][0]['oracle']['checks'].values()) or
        d.get('attack_fixture_restoration',{}).get('position')!=d.get('original_position') or
        len(d['attack_fixture_restoration'].get('temporary_teleports_removed',[]))!=2 or
        d.get('custom_script_permission')!='blocked_by_user' or d.get('softTargetInteract')!=SCRIPT_BOUNDARY):
        raise RuntimeError('closed absent-pet-only failed health staging differs')
    return d


def run(t,preparation,entry,source):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session'];e=entry_source(t,entry,session,preparation)
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence') or source.is_symlink():
        raise ValueError('requires the private closed failed staging')
    d=eligible(json.loads(source.read_text()),t,[lab.sha256(p) for p in (preparation,entry)])
    if d['native_session']!=session or position(5)!=d['original_position']:raise RuntimeError('failed staging session or restored pose differs')
    t.receipt.update(baseline=copy.deepcopy(d['baseline']),native_session=session,
        original_failure={'path':str(source),'sha256':lab.sha256(source)},attack_replayed=False,qualification_added=False);t.persist()
    o=HealthPresence(session,5,e['started_at']).poll();summon=SummonOracle(session,5,e['started_at']).poll()
    absent=read(t,'health_recovery_absence');o.poll();summon.poll()
    absence=not o.present() and pair(o.player,'UNIT_FIELD_SUMMON')==0 and not absent['probe'].get('pet_guid')
    if not absence or 688 not in wire_known(t,session):raise RuntimeError('requires native/public absence and native-known Summon Imp')
    old_guid=o.pet['guid'] if o.pet else 0;since=time.time()
    def outcome(before,after,selected):
        summon.poll();checks,packets=summon_checks(summon,since,old_guid,d['baseline']['pet'],selected,absence)
        checks['ui_clean']=not after.get('lua_errors') and not after.get('blocked_actions')
        return {'status':'owned_retained_summon_recovery_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':packets}}
    require(t.step('fixture.health_retained_imp_recovery','Restore the retained Imp through normal native-known Summon Imp.',
        {'summon':{'kind':'chat','value':'/cast Summon Imp'}},outcome,diagnostic_action='summon',
        await_state=lambda state:summon.poll().present() and not state.get('player_cast',{}).get('active')),
        'owned_retained_summon_recovery_pass')
    o.poll();mode(t,o,3,'fixture.health_assist_recovery');restore_spell(t,o,d['original_spell'])
    whole_restore(t,o,Inventory(lab.ROOT,session,5).poll(),old,d['baseline'])
    t.receipt.update(completed=True,phase='owned_melee_health_staging_restored',qualified_scope=
        'Ordinary retained Imp recovery and full original actor restoration only. The failed staging remains excluded; no Attack replay or damage qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','source','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.source)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','restoration_checks')}),flush=True)
