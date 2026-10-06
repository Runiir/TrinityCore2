"""Bound this farm's hot data and memory; offload only closed public evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from . import runtime

MIB=2**20
DEFAULTS={'soft_disk_mib':64,'hard_disk_mib':256,'minimum_free_disk_mib':2048,
    'controller_rss_mib':512,'reader_rss_mib':128,'observer_rss_mib':128,'model_rss_mib':3072,
    'model_vram_mib':3584,'minimum_free_host_memory_mib':1024,
    'poll_seconds':5,'loop_history':16,'dig_history':40,'movement_history':40,
    'action_log_mib':1}
_cached_root=None
_checked_at=0
_last_failures=[]


class ResourceLimit(RuntimeError):pass


def limits():
    path=runtime.ROOT/'run/resource_limits.json'
    return {**DEFAULTS,**json.loads(path.read_text())} if path.exists() else None


def enable():
    config=json.loads((runtime.REPO/'experiments/configs/client_harness/whitemane_farm_loop_v1.json').read_text())
    values={**DEFAULTS,**config.get('resource_limits',{})}
    runtime.write(runtime.ROOT/'run/resource_limits.json',values)
    return values


def rss(pid):
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])/1024
    raise ResourceLimit('owned process RSS is unavailable')


def register_model(pid):
    command=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    if not {b'tools.live_whitemane.model',b'tools.live_whitemane.vision_model'}.intersection(command):
        raise ResourceLimit('model process is not the owned live model service')
    runtime.write(runtime.ROOT/'run/model_service.json',{'pid':pid,'start_ticks':runtime.proc_start(pid)})


def tree_bytes(root):
    # Inspect sizes only; never open launcher/account logs.
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())


def snapshot(values):
    result={'at':time.time(),'hot_bytes':tree_bytes(runtime.ROOT),
        'free_disk_bytes':shutil.disk_usage(runtime.ROOT).free,'controller_rss_mib':rss(os.getpid())}
    for name,file in [('reader','bearing_reader.json'),('model','model_service.json'),('observer','state_observer.json')]:
        path=runtime.ROOT/'run'/file
        if not path.exists():continue
        process=json.loads(path.read_text())
        if name=='reader' and process.get('status')!='ready':continue
        if name=='observer' and process.get('status')!='running':continue
        try:
            if runtime.proc_start(process['pid'])!=process['start_ticks']:
                raise ResourceLimit(name+' process identity changed')
        except FileNotFoundError:raise ResourceLimit(name+' process is absent') from None
        result[name+'_rss_mib']=rss(process['pid'])
        if name=='model':
            query=subprocess.run(['nvidia-smi','--query-compute-apps=pid,used_memory',
                '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2,check=True)
            result['model_vram_mib']=sum(float(row.split(',')[1]) for row in query.stdout.splitlines()
                if row.split(',')[0].strip()==str(process['pid']))
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):result['free_host_memory_mib']=int(line.split()[1])/1024
    failures=[]
    for field in ('controller_rss_mib','reader_rss_mib','observer_rss_mib','model_rss_mib','model_vram_mib'):
        if result.get(field,0)>values[field]:failures.append(f'{field}={result[field]:.1f} exceeds {values[field]}')
    if result['hot_bytes']>=values['hard_disk_mib']*MIB:failures.append('owned hot data reached the disk limit')
    if result['free_disk_bytes']<values['minimum_free_disk_mib']*MIB:failures.append('free disk is below the reserve')
    if result['free_host_memory_mib']<values['minimum_free_host_memory_mib']:
        failures.append('free host memory is below the reserve')
    result['limits']=values;result['failures']=failures
    return result


def check(force=False):
    global _cached_root,_checked_at,_last_failures
    values=limits()
    if values is None:return
    now=time.monotonic()
    if not force and _cached_root==runtime.ROOT and now-_checked_at<values['poll_seconds']:
        if _last_failures:raise ResourceLimit('; '.join(_last_failures))
        return
    result=snapshot(values)
    runtime.write(runtime.ROOT/'run/resource_usage.json',result)
    _cached_root=runtime.ROOT;_checked_at=now;_last_failures=result['failures']
    if result['failures']:raise ResourceLimit('; '.join(result['failures']))
    return result


def trim_session(session,kind):
    values=limits() or DEFAULTS
    # Retain a monotonic index even after old receipts leave the hot history.
    session['next_step_index']=max(session.get('next_step_index',0),
        max((s.get('index',i)+1 for i,s in enumerate(session['steps'])),default=0))
    session['steps']=session['steps'][-values[kind+'_history']:]
    if 'runs' in session:session['runs']=session['runs'][-8:]


def append_action(receipt):
    values=limits() or DEFAULTS
    path=runtime.ROOT/'evidence/actions.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size>=values['action_log_mib']*MIB:
        path.rename(path.with_name(f'actions_closed_{time.time_ns()}.jsonl'))
    with path.open('a') as out:out.write(json.dumps(receipt)+'\n')


def prune_verified(checkpoint,object_meta,*,keep_json=False):
    """Called only after remote status proved the exact archive hash exists."""
    freed=0;removed=0;changed=[]
    for item in checkpoint['manifest']:
        path=(runtime.ROOT/item['path']).resolve()
        if not path.is_relative_to(runtime.ROOT/'evidence'):raise ResourceLimit('invalid prune manifest path')
        if keep_json and path.suffix!='.png':continue
        if not path.exists():continue
        if path.stat().st_size!=item['bytes'] or path.stat().st_mtime_ns!=item['mtime_ns']:
            changed.append(item['path']);continue
        with path.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
        if digest!=item['sha256']:changed.append(item['path']);continue
        freed+=path.stat().st_size;path.unlink();removed+=1
    archive=Path(checkpoint['archive']);freed+=archive.stat().st_size;archive.unlink()
    cache=subprocess.check_output(['dvc','cache','dir'],cwd=runtime.REPO,text=True).strip()
    digest=object_meta['md5'];object_path=Path(cache)/'files/md5'/digest[:2]/digest[2:]
    if object_path.exists():freed+=object_path.stat().st_size;object_path.unlink()
    # Empty closed directories carry no resume state.
    for directory in sorted((runtime.ROOT/'evidence').rglob('*'),reverse=True):
        if directory.is_dir():
            try:directory.rmdir()
            except OSError:pass
    return {'freed_bytes':freed,'removed_files':removed,'changed_files_preserved':changed,
        'remote_md5':digest,'remote_verified':True}


def offload(roots,*,label=None,keep_json=False):
    # The controller's lean auth environment does not carry DVC/DVCLive.
    # Run checkpointing in the repository's tracked pixi environment.
    request=runtime.ROOT/'run/offload_request.json'
    runtime.write(request,{'roots':[str(p) for p in roots],'label':label,'keep_json':keep_json})
    result=subprocess.run(['pixi','run','python','-m','tools.live_whitemane.resources',
        '--offload',str(request)],cwd=runtime.REPO,capture_output=True,text=True,timeout=600,check=True)
    return json.loads(result.stdout.splitlines()[-1])


def offload_worker(roots,*,label=None,keep_json=False):
    """Inputs must already be released. A failed push preserves all evidence."""
    from .checkpoint import checkpoint_closed
    import yaml
    label=label or f'auto_{time.time_ns()}'
    receipt=checkpoint_closed(label,roots,{'resources/closed_roots':len(roots)},
        {'automatic_offload':True,'gameplay_acceptance':False})
    archive=Path(receipt['archive']);target=str(archive.relative_to(runtime.REPO))
    pointer=target+'.dvc'
    def run(*args):
        return subprocess.run(args,cwd=runtime.REPO,capture_output=True,text=True,timeout=180,check=True)
    run('dvc','add',target)
    # Only this archive is pushed; never collect or delete another worker's data.
    run('dvc','push',pointer)
    status=json.loads(run('dvc','status','--cloud','--json',pointer).stdout)
    if status:raise ResourceLimit('closed evidence remote did not confirm sync')
    metadata=yaml.safe_load((runtime.REPO/pointer).read_text())['outs'][0]
    run('git','add','--',pointer,str(archive.parent.relative_to(runtime.REPO)/'.gitignore'))
    run('git','commit','-m',f'Checkpoint closed Whitemane evidence {label}','--',pointer,
        str(archive.parent.relative_to(runtime.REPO)/'.gitignore'))
    result=prune_verified(receipt,metadata,keep_json=keep_json)
    result.update(label=label,pointer=pointer,closed_roots=len(roots))
    runtime.write(runtime.ROOT/'run/last_offload.json',result)
    return result


def phase_boundary(output,session):
    values=limits() or DEFAULTS
    result=check(force=True)
    if result is None or result['hot_bytes']<values['soft_disk_mib']*MIB:return
    active=Path(session['dig_output']).resolve() if session.get('dig_output') else None
    # Leave the latest two phases and dig decisions available for diagnosis.
    candidates=sorted(output.glob('step_*'))[:-2]
    roots=[p for p in candidates if not active or not active.is_relative_to(p.resolve())]
    if active:roots+=sorted(active.glob('step_*'))[:-2]
    roots+=sorted((runtime.ROOT/'evidence').glob('actions_closed_*.jsonl'))
    if not roots:return
    offload(roots)
    check(force=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offload',type=Path,required=True)
    args=parser.parse_args();request=json.loads(args.offload.read_text())
    request['roots']=[Path(p) for p in request['roots']]
    print(json.dumps(offload_worker(**request)))
