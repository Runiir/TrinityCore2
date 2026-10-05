"""Laya controls the visible journal; measured currency spending confirms solves."""
import time
from . import runtime
from .observe import observe
from .farm_actions import click_choice
from .dig_policy import SolveBatches


def run(folder, batches=None, *, race_id=None):
    folder.mkdir(parents=True,exist_ok=False)
    batches=batches or SolveBatches()
    receipt={'started_at':time.time(),'solves':[],'steps':[],'finished':False}
    def record():runtime.write(folder/'batch.json',receipt)
    def click(row,path,goal,expected):
        result=click_choice(folder/f"ui_{len(receipt['steps']):03d}",row,path,goal,expected)
        receipt['steps'].append(result);record()
        if not result['executed']:raise RuntimeError('Laya waited during a ready solve batch')
        return result['after']
    row=observe(folder/'before.png')
    if race_id is not None:batches.active_races.add(race_id)
    race=next((r for r in row['archaeology']['races'] if (race_id is None or r['index']==race_id) and batches.next_project(r)),None)
    if not race:return {'finished':True,'solves':[]}
    try:
        if row['farm_ui']['journal']['visible']:
            row=click(row,['journal','controls'],'Close journal',{'kind':'close'})
        row=click(row,['canopic'],'Open the archaeology Journal',{'label':'Journal'})
        visible=next(r for r in row['farm_ui']['journal']['races'] if r['race']==race['index'])
        row=click(row,['journal','races'],f"Open the {visible['label']} current artifact",{'race':race['index']})
        for i in range(12):
            current=next(r for r in row['archaeology']['races'] if r['index']==race['index'])
            project=batches.next_project(current)
            if not project:break
            j=row['farm_ui']['journal']
            if j['race']!=race['index'] or j['project']['spell']!=current['project_spell']:
                raise RuntimeError('journal selection disagrees with current race project')
            for stone in range(1,project['keystones']+1):
                target=next(s for s in j['keystones'] if s['index']==stone)
                if not target['added']:
                    row=click(row,['journal','keystones'],f'Add keystone in socket {stone}',{'index':stone})
                    j=row['farm_ui']['journal']
                    if not next(s for s in j['keystones'] if s['index']==stone)['added']:
                        raise RuntimeError('keystone input did not fill the selected socket')
            if not j['project']['can_solve']:raise RuntimeError('selected project is not affordable')
            before=row
            row=click(row,['journal','solve'],'Solve current artifact',{'kind':'solve'})
            confirmed=False
            for attempt in range(40):
                time.sleep(.3)
                row=observe(folder/f'solve_{i:02d}_wait.png')
                new=next(r for r in row['archaeology']['races'] if r['index']==race['index'])
                if not row['archaeology']['casting'] and new['fragments']<current['fragments']:
                    if current['fragments']-new['fragments']!=project['fragments_required']:
                        raise RuntimeError('solve currency spending differs from accepted keystones')
                    receipt['solves'].append({'before':current,'after':new,'project':project,'observed_at':row['observed_at']})
                    record();confirmed=True;break
            if not confirmed:raise RuntimeError('solve did not produce measured fragment spending')
        else:raise RuntimeError('solve batch exceeded finite available-project bound')
        row=click(row,['journal','controls'],'Close journal',{'kind':'close'})
        receipt.update(finished=True,after=row,active_races=sorted(batches.active_races))
    except Exception as error:
        receipt['failure']=f'{type(error).__name__}: {error}'
    receipt['finished_at']=time.time();record()
    return receipt


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    result=run(parser.parse_args().output)
    print(json.dumps({'finished':result['finished'],'solves':len(result['solves']),'failure':result.get('failure')}))
