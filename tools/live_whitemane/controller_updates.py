"""Load controller fixes between completed actions and defer UI reload until idle."""
import ast
import hashlib
import importlib
import sys
import time
from pathlib import Path
from . import runtime,action_queue,pending_find

COMPONENTS=('guide','camera_steering','camera_navigation','fast_waypoint','smooth_move',
    'flight','combat_target','combat','dig_context','dig_decisions','pickup_intent',
    'dig_feedback','dig_session','farm_policy','recovery','interact','survey_find','pending_find',
    'world_facts','farm_graph','swim_vertical','clearance','terrain_context','inputs','portal','taxi','ground_jump','controller_updates','interaction_search')


class SourceUpdates:
    def __init__(self):
        self.loaded={};self.pending={}
        for name in COMPONENTS:
            module=sys.modules.get(__package__+'.'+name)
            if module:self.loaded[name]=self.source(module)[1]

    @staticmethod
    def source(module):
        source=Path(module.__file__).read_bytes()
        return source,hashlib.sha256(source).hexdigest()

    def refresh(self):
        if action_queue._active.locked():return []
        modules={name:sys.modules.get(__package__+'.'+name) for name in COMPONENTS}
        sources={name:self.source(module) for name,module in modules.items() if module}
        changed=set();trees={}
        for name,(source,digest) in sources.items():
            if name not in self.loaded:self.loaded[name]=digest
            if digest==self.loaded[name]:self.pending.pop(name,None);continue
            if self.pending.get(name)!=digest:self.pending[name]=digest;continue
            # A half-written file stays out of the running controller.
            try:trees[name]=ast.parse(source);compile(source,modules[name].__file__,'exec')
            except SyntaxError:continue
            changed.add(name)
        if not changed:return []
        dependencies={}
        for name,(source,_) in sources.items():
            try:
                tree=trees.get(name) or ast.parse(source)
                compile(source,modules[name].__file__,'exec')
            except SyntaxError:return []
            dependencies[name]=set()
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom) and node.level==1:
                    dependencies[name].update([node.module.split('.')[0]] if node.module
                        else [item.name for item in node.names])
        affected=set(changed)
        while True:
            added={name for name,deps in dependencies.items() if deps&affected}-affected
            if not added:break
            affected.update(added)
        order=[];visiting=set()
        def append(name):
            if name in order or name in visiting:return
            visiting.add(name)
            for dep in sorted(dependencies[name]&affected):append(dep)
            visiting.remove(name);order.append(name)
        for name in COMPONENTS:
            if name in affected:append(name)
        for name in order:
            importlib.invalidate_caches();importlib.reload(modules[name])
            self.loaded[name]=sources[name][1];self.pending.pop(name,None)
        runtime.write(runtime.ROOT/'run/controller_source_updates.json',{
            'at':time.time(),'modules':order,'loaded_sha256':self.loaded,
            'boundary':'between completed farm actions','active_client_commands':0})
        return order


def matches_expected(actual,expected):
    return isinstance(actual,dict) and all(
        matches_expected(actual.get(key),value) if isinstance(value,dict)
        else key in actual and actual[key]==value
        for key,value in expected.items())


def upgrade_bound_callbacks():
    """Update the startup callback retained by this process's active farm frame."""
    updated=0
    for frame in sys._current_frames().values():
        while frame:
            if (frame.f_code.co_name=='run' and
                    Path(frame.f_code.co_filename).resolve()==runtime.REPO/'tools/live_whitemane/farm_loop.py'):
                callback=frame.f_locals.get('apply_addon_request')
                if callback and callback is not apply_addon_request and callback.__module__==__name__:
                    callback.__code__=apply_addon_request.__code__;updated+=1
            frame=frame.f_back
    return updated


def apply_addon_request(folder,row):
    path=runtime.ROOT/'run/addon_reload_request.json'
    if not path.exists():return False
    import json
    request=json.loads(path.read_text());ui=row.get('farm_ui') or {}
    expected=request.get('expected',{'combat_facts_schema':'observed_attackers_v1'})
    if matches_expected(ui,expected):
        request.update(completed=True,confirmed_at=time.time())
        runtime.write(Path(request['receipt']),request);path.unlink();return False
    a,m=row['archaeology'],row['movement']
    if (m['in_combat'] or m['dead'] or not m['in_world'] or m.get('speed',0)>0
            or any(a.get(k) for k in ('flying','falling','casting')) or pending_find.load(row)
            or time.time()-request.get('last_attempt',0)<10):return False
    request['last_attempt']=time.time();runtime.write(path,request)
    from .farm_actions import command_choice
    try:
        request['selection']=command_choice(folder/'addon_update',row,'/reload',
            request.get('goal','Load installed facts identifying mobs attacking this player'),
            request.get('label','Reload the installed attacker observation telemetry'))
    except RuntimeError as error:
        request['retry_reason']=str(error)
        runtime.write(Path(request['receipt']),request);return False
    runtime.write(Path(request['receipt']),request)
    return request['selection']['executed']
