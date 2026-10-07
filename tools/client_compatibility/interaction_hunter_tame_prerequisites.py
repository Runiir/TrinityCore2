"""Read current native tameable Wolf spawns for the owned Hunter; no mutation."""
import argparse,json,subprocess,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_bridge_deploy import identity
from .interaction_owned_class_fixture import character,pets
from .interaction_spellbook_navigation import known


def read(output):
    output=output.resolve()
    if not output.is_relative_to(lab.ROOT/'evidence') or output.exists():raise ValueError('requires a new owned evidence output')
    fixture=actors.load();native=identity('worldserver');owner=character(6,2)
    if (fixture['guid'],fixture['class'],fixture['level'],owner['online'])!=(6,3,10,1):
        raise RuntimeError('requires the current online owned level10 Hunter')
    keys=('guid','id','name','map','position_x','position_y','position_z','orientation',
        'minlevel','maxlevel','type','type_flags','family','faction','unit_flags','MovementType')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
            't.minlevel,t.maxlevel,t.type,t.type_flags,t.family,t.faction,t.unit_flags,c.MovementType '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id '
            'WHERE c.map=%s AND c.id=299 ORDER BY POW(c.position_x-%s,2)+POW(c.position_y-%s,2) LIMIT5',
            (owner['map'],owner['position_x'],owner['position_y']))
        rows=[dict(zip(keys,row)) for row in q.fetchall()]
    spells=[r[0] for r in known(6)]
    if not rows or rows[0]['guid']!=280666 or 1515 not in spells or identity('worldserver')!=native:
        raise RuntimeError('current native target, Tame1515 or server lifetime differs')
    lab.private_write(output,json.dumps({'schema':'client442_owned_tame_prerequisite_recon_v1',
        'observed_at':time.time(),'native':native,'owner':6,'owner_native':owner,'pets':pets(6),
        'known_spells':spells,'nearest_existing_wolves':rows,'input_sent':False,'qualification_added':False,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip()},indent=2)+'\n')
    print(json.dumps({'owner':6,'nearest_wolf':rows[0]['guid'],'existing_spawns':len(rows),'input_sent':False}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('scout'):read(a.output)
