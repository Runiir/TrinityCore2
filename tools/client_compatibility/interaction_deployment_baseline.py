"""Carry a failed owned client's verified baseline into a bridge recovery."""
import json,re
from . import lab_runtime as lab
from .interaction_talents import native_state
from .interaction_trade import inventory
from .interaction_glyph_learn import spells


def unavailable_primary(t,source,native,bridge):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='recovery.json':
        raise ValueError('require an owned closed client-recovery receipt')
    run=json.loads(source.read_text());episode_path=source.parent/'reentry/episode.json'
    episode=json.loads(episode_path.read_text())
    if (not run.get('finished_at') or run.get('completed') or not episode.get('finished_at') or
            episode.get('completed') or episode['actor']!=t.fixture):
        raise RuntimeError('recovery source must be a closed failed reentry for this actor')
    identity=lambda row:{key:row[key] for key in ['pid','start_ticks']}
    if (run['before']['worldserver']!=identity(native) or run['before']['modern_world']!=identity(bridge) or
            identity(episode['runtime']['client'])!=identity(lab.owned_process('client'))):
        raise RuntimeError('unavailable actor or server lifetime differs from the recovery source')
    actual={'inventory':inventory(),'talents':native_state(),'spells':spells()}
    if json.loads(json.dumps(actual))!=run['native_baseline']:
        raise RuntimeError('native recovery baseline changed before deployment')
    label=run['source']
    if not re.fullmatch('[A-Za-z0-9_]+',label):raise ValueError('invalid baseline batch member')
    observed_path=source.parent.parent/label/'primary/episode.json'
    observed=json.loads(observed_path.read_text())
    if observed['actor']!=t.fixture or not observed.get('finished_at'):
        raise RuntimeError('previous public baseline belongs to another actor or open trial')
    state=observed['observer_before']['state']
    if state['guid']!=t.guid:raise RuntimeError('previous public baseline GUID differs')
    t.receipt.update(native_baseline_verified=True,public_precheck_deferred=True,
        recovery_source={'file':str(source),'sha256':lab.sha256(source)},
        public_baseline_source={'file':str(observed_path),'sha256':lab.sha256(observed_path)},
        failure='Client is at a verified failed-reentry lobby; current public checks deferred until reconnect.')
    t.persist()
    return {key:state.get(key) for key in ['guid','money','equipment','group','raid_profile']}


def unavailable_scout(t,source,inventory_source,native,bridge):
    source=source.resolve();inventory_source=inventory_source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='deployment.json':
        raise ValueError('require an owned scout recovery deployment')
    run=json.loads(source.read_text());episode_path=source.parent/'scout_after/episode.json'
    episode=json.loads(episode_path.read_text())
    identity=lambda row:{key:row[key] for key in ['pid','start_ticks']}
    if (not run.get('recovery_source') or not episode.get('finished_at') or episode.get('completed') or
            episode['actor']!=t.fixture or identity(run['native'])!=identity(native) or
            identity(run['after'])!=identity(bridge) or
            identity(episode['runtime']['client'])!=identity(lab.owned_process('client'))):
        raise RuntimeError('scout recovery does not bind the current failed actor and servers')
    if not inventory_source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('inventory source must belong to this private lab')
    shared=json.loads(inventory_source.read_text())
    if (not shared.get('finished_at') or shared['before']['worldserver']!=identity(native) or
            shared['before']['modern_world']!=identity(bridge) or
            json.loads(json.dumps(inventory()))!=shared['native_baseline']['inventory']):
        raise RuntimeError('both-character inventory/money baseline changed')
    baseline=run['baselines']['scout']
    if baseline['guid']!=t.guid:raise RuntimeError('scout public baseline GUID differs')
    t.receipt.update(public_precheck_deferred=True,inventory_money_verified=True,
        recovery_source={'file':str(source),'sha256':lab.sha256(source)},
        inventory_source={'file':str(inventory_source),'sha256':lab.sha256(inventory_source)},
        failure='Client failed reentry; previous public baseline is deferred until reconnect.')
    t.persist();return baseline
