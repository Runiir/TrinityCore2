"""Restore only the exact pending helmet relocation from a failed combat trial."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_equipment import change
from .interaction_equipment_set_roundtrip import open_character,restore_display,stable
from .interaction_tooltips import baseline
from .interaction_macros import require
from .observation.inventory import Inventory


def pending(source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
        raise ValueError('require an owned failed combat episode')
    old=json.loads(source.read_text())
    if (not old.get('finished_at') or old.get('completed') or old.get('native_resources_preserved') or
        old['actor']['guid']!=1 or not old.get('helmet_fixture')):
        raise RuntimeError('requires a closed failed primary helmet mutation')
    item=old['helmet_fixture']['item'];destination=old['helmet_fixture']['destination']
    if destination[0]!=0 or not 1<=destination[1]<=16 or item['count']!=1:
        raise RuntimeError('only one helmet in the owned backpack can be restored')
    changed=stable(old['baseline']);rows=changed['archaeology_inventory_money']['inventory']['items']
    match=[r for r in rows if r[:3]==[1,0,0] and r[3]==item['guid']&0xffffffff and r[4]==item['id'] and r[5]==1]
    if len(match)!=1:raise RuntimeError('original native helmet row is not exact')
    match[0][2]=22+destination[1];rows.sort(key=lambda r:tuple(r[:3]))
    if changed!=old['native_after'] or stable(baseline())!=changed:
        raise RuntimeError('native state differs by more than the exact pending helmet relocation')
    return source,old,changed


def unavailable(t,source,native,bridge):
    source,old,changed=pending(source)
    if (old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or
        old['runtime']['worldserver']!=native or old['runtime']['modern_world']!=bridge):
        raise RuntimeError('pending helmet source does not bind these actor/server/client lifetimes')
    rows=[r for r in old['cases'] if r['id']=='character.unequip']
    if len(rows)!=1 or not rows[0]['oracle']['native_matches'] or rows[0]['oracle']['visible_matches']:
        raise RuntimeError('source does not prove a native relocation with stale client slots')
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],1).poll()
    public=old['cases'][0]['before']
    if public['guid']!=t.guid:raise RuntimeError('original public actor differs')
    result={key:public.get(key) for key in ['guid','money','equipment','group','raid_profile']}
    result['equipment']=[oracle.equipment(i)['id'] for i in range(1,20)]
    t.receipt.update(combat_source={'file':str(source),'sha256':lab.sha256(source)},
        pending_native_baseline=changed,pending_native_equipment=result['equipment'],public_precheck_deferred=True,
        failure='Failed sparse update left stale client slots; reconnect must match the exact pending native helmet fixture.')
    t.persist();return result


def suite(t,source,deployment):
    source,old,changed=pending(source);deployment=deployment.resolve()
    if not deployment.is_relative_to(lab.ROOT/'evidence') or deployment.name!='deployment.json':
        raise ValueError('require an owned bridge deployment')
    run=json.loads(deployment.read_text());pre=json.loads((deployment.parent/'primary_before/episode.json').read_text())
    if (not run.get('completed') or not run.get('native_unchanged') or old['actor']!=t.fixture or
        run['native']!=old['runtime']['worldserver'] or run['native']!=t.receipt['runtime']['worldserver'] or
        run['after']!=t.receipt['runtime']['modern_world'] or
        pre.get('combat_source')!={'file':str(source),'sha256':lab.sha256(source)}):
        raise RuntimeError('recovery does not bind the corrected deployment and exact pending source')
    t.receipt.update(source=pre['combat_source'],deployment={'file':str(deployment),'sha256':lab.sha256(deployment)},
        baseline=changed,qualified_scope='Source fixture restoration only; no feature qualification.');t.persist()
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],1).poll()
    item=old['helmet_fixture']['item'];destination=old['helmet_fixture']['destination']
    if oracle.equipment(1)['guid'] or oracle.slot(*destination)!=item:
        raise RuntimeError('pending native helmet is not in the exact backpack slot')
    try:
        open_character(t,'combat.recovery');t.execute({'kind':'key','value':'b'})
        require(change(t,oracle,item,destination,True),'equipment_change_pass')
    finally:
        try:restore_display(t,old['display_baseline']['collapsed'])
        finally:
            t.receipt['native_after']=stable(baseline());t.receipt['native_resources_preserved']=t.receipt['native_after']==old['baseline'];t.persist()
            if not t.receipt['native_resources_preserved']:raise RuntimeError('original full combat fixture remains unrestored')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--deployment',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.source,a.deployment);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
