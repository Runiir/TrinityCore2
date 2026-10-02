"""Public model collision complements the navigation mesh's ground surfaces."""
import json
import shlex
import subprocess
from functools import lru_cache
from . import lab_runtime as lab


def binary():
    source=lab.REPO/'tools/client_compatibility/collision_probe.cpp';target=lab.ROOT/'bin/collision_probe'
    if not target.exists() or target.stat().st_mtime<source.stat().st_mtime:
        commands=json.loads((lab.ROOT/'build/compile_commands.json').read_text())
        entry=next(row for row in commands if row['file'].endswith('/VMapManager2.cpp'))
        command=shlex.split(entry['command']);args=[a for a in command[1:] if a.startswith(('-I','-D','-std='))]
        build=lab.ROOT/'build'
        subprocess.run([command[0],*args,'-O2',str(source),str(build/'src/common/libcommon.a'),
            str(build/'dep/g3dlite/libg3dlib.a'),str(build/'dep/fmt/libfmt.a'),
            '-lboost_filesystem','-lboost_program_options','-lboost_thread','-lboost_chrono',
            '-lboost_regex','-lssl','-lcrypto','-lz','-ldl','-pthread','-o',str(target)],check=True)
    return target


def column(map_id,position):
    return _column(map_id,*[round(v,3) for v in position[:3]])


@lru_cache(maxsize=2048)
def _column(map_id,x,y,z):
    result=subprocess.run([str(binary()),str(lab.BASE/'data/vmaps'),str(map_id),*map(str,[x,y,z])],
        capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError('public model collision: '+result.stderr.strip())
    return json.loads(result.stdout)


def supporting_surface(map_id,position):
    from . import terrain_geometry
    terrain=terrain_geometry.height(map_id,position);models=column(map_id,position)
    heights=[h for h in [terrain,models['collision_height']] if h is not None and h>-100000]
    return {'terrain_height':terrain,'model_collision_height':models['collision_height'],
        'highest_surface':max(heights) if heights else None,
        'source':'public raw MAPS terrain and static VMAP model collision'}


def clear_body_segment(map_id,start,end):
    for height in [.5,1.7]:
        a=[start[0],start[1],start[2]+height];b=[end[0],end[1],end[2]+height]
        result=subprocess.run([str(binary()),str(lab.BASE/'data/vmaps'),str(map_id),'--segment',
            *map(str,a),*map(str,b)],capture_output=True,text=True,timeout=10)
        if result.returncode:raise RuntimeError('public body collision: '+result.stderr.strip())
        if not json.loads(result.stdout)['clear']:return False
    return True
