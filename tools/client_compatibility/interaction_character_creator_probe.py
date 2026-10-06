"""Inspect the stock character creator on the existing parked scout, then return."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot,identity
from .interaction_parked_bridge import native,review as parked_review


def roster(t):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT guid,name,race,class,gender,level,online FROM client442_characters.characters '
            'WHERE account=%s ORDER BY guid',(t.fixture['account_id'],))
        return [list(row) for row in q.fetchall()]


def source(t,path,stage):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned scout episode')
    old=json.loads(path.read_text())
    if (old.get('completed') is not True or old.get('failure') is not None or not old.get('finished_at') or
        old.get('actor')!=t.fixture or old.get('runtime')!=t.receipt['runtime']):
        raise RuntimeError('closed scout fixture or process lifetime differs')
    baseline=old.get('parked_native') if stage=='open' else old.get('original_parked_native')
    if native(t)!=baseline:raise RuntimeError('original parked scout native row differs')
    if stage=='open' and not old.get('qualified_scope','').startswith('Read-only owned offline scout preflight'):
        raise RuntimeError('creator inspection requires a parked scout preflight')
    if stage=='cancel' and old.get('creator_stage')!='open':
        raise RuntimeError('creator return requires its closed opening receipt')
    frame=old['parked_frame'] if stage=='open' else old['next_screen']
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},original_parked_native=baseline,
        source_frame_sha256=frame['sha256'])
    return old


def control(t,path,episode,stage):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence'):raise ValueError('requires an owned visual review')
    checked=json.loads(path.read_text());frame=checked.get('frame',{});image=path.parent/frame.get('file','')
    current=owned_input.focus();monitor=frame.get('monitor',{});point=checked.get('point',[])
    label=checked.get('control')
    if (checked.get('reviewed') is not True or checked.get('kind')!='character_creator_'+stage or
        checked.get('episode_sha256')!=lab.sha256(episode) or
        not image.resolve().is_relative_to(lab.ROOT/'evidence') or not image.is_file() or
        frame.get('sha256')!=lab.sha256(image) or frame.get('sha256')!=t.receipt['source_frame_sha256'] or
        not 0<=time.time()-image.stat().st_mtime<=120 or
        not monitor.get('second_monitor_verified') or monitor.get('pid')!=t.receipt['runtime']['client']['pid'] or
        monitor.get('input_isolation',{}).get('actor')!='scout' or
        monitor.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid'] or
        len(point)!=2 or any(type(v) is not int for v in point) or
        not (0<=point[0]<1280 and 0<=point[1]<720) or
        label not in (['Create New Character'] if stage=='open' else ['Back','Cancel'])):
        raise RuntimeError('fresh reviewed owned creator control differs')
    if stage=='open':parked_review(t,path,episode,'character_creator_open')
    t.receipt['control_review']={'path':str(path),'sha256':lab.sha256(path),'frame':frame}
    return point


def run(out,path,review_path,stage):
    with actor('scout'):
        t=Trial(out,controller='code')
        try:
            old=source(t,path,stage);point=control(t,review_path,path,stage);before=roster(t)
            if stage=='cancel' and before!=old['original_roster']:
                raise RuntimeError('owned roster changed after creator inspection')
            t.receipt.update(original_roster=before,creator_stage=stage,custom_script_permission='blocked_by_user',
                softTargetInteract={'original':'0','current_stock_disabled':'1','original_restored':False},
                qualified_scope='One reviewed creator lobby input only; next screen requires visual review. '
                    'No character creation, deletion, customization or spellbook qualification.',
                input={'kind':'click','value':point,'hold':1.2},before_frame=shot(t.out/'before.png'))
            t.persist();t.io.click(*point,hold=1.2);time.sleep(12)
            checks={'original_scout_native':native(t)==t.receipt['original_parked_native'],
                'original_roster':roster(t)==before,'native_worldserver':identity('worldserver')==t.receipt['runtime']['worldserver']}
            t.receipt.update(restoration_checks=checks,next_screen=shot(t.out/'next_screen.png'),
                requires_next_screen_review=True);t.persist()
            if not all(checks.values()):raise RuntimeError('creator input changed the original native fixture')
            t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['creator_stage','completed','failure']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['open','cancel'])
    p.add_argument('--source',type=Path,required=True);p.add_argument('--review',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output,a.source,a.review,a.stage)
