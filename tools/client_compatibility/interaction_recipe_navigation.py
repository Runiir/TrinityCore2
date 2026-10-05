"""Move the ordinary recipe scrollbar using observed geometry and rendered row IDs."""
import math
from .interaction_observation import read_page
from .interaction_operations import command,point
from .interaction_control_target import target
from .interaction_macros import require


def detail(t,label):
    try:
        state,frame=read_page(t,label,'recipes','/tcui recipes')
        probe=state['recipe_probe']
        t.receipt.setdefault('recipe_viewports',[]).append({'label':label,'frame':frame,'probe':probe});t.persist()
        if state.get('observer_version',0)<106 or not probe.get('visible'):
            raise RuntimeError('requires the owned visible recipe viewport observer106')
        return probe
    finally:command(t,'/tcui state')


def drag_points(probe,offset):
    slider=probe['slider'];count=probe['count']
    values=[slider[k] for k in ('low','high','value','track_top','track_bottom')]+list(slider['thumb'].values())
    if (count<=8 or not 0<=offset<=count-8 or any(not math.isfinite(v) for v in values) or
        not slider['low']<=slider['value']<=slider['high'] or slider['high']<=slider['low'] or
        not 0<=slider['track_top']<slider['track_bottom']<=65535 or
        any(not 0<=v<=65535 for v in slider['thumb'].values())):
        raise RuntimeError('recipe scrollbar geometry or requested offset is invalid')
    start=point(slider['thumb']);ratio=offset/(count-8)
    y=(slider['track_top']+(slider['track_bottom']-slider['track_top'])*ratio)/65535*720
    # Drag slightly past endpoints so integer input pixels clamp to exact bounds.
    y=math.floor(y)-3 if ratio==0 else math.ceil(y)+3 if ratio==1 else round(y)
    end=[start[0],y]
    if not 0<=y<720:raise RuntimeError('recipe thumb drag exceeds the owned viewport')
    return start,end


def scroll_to(t,offset,label,visible_index=None):
    before=detail(t,label+'_before');start,end=drag_points(before,offset)
    def outcome(b,a,s):
        after=detail(t,label+'_after')
        checks={'ordinary_drag':s=='drag','same_catalog':after['count']==before['count'],
            'offset':after['offset']==offset if offset in (0,before['count']-8) else abs(after['offset']-offset)<=4,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        if visible_index is not None:checks['wanted_row_visible']=any(r['index']==visible_index for r in after['rows'])
        return {'status':'recipe_viewport_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'before':before,'after':after,'requested_offset':offset}}
    require(t.step(label,'Move the observed stock recipe scrollbar thumb.',
        {'drag':{'kind':'drag','start':start,'end':end,'duration':1.5}},outcome,diagnostic_action='drag'),
        'recipe_viewport_pass')


def select_original(t,baseline):
    probe=detail(t,'recipe_unfiltered_selection_guard');wanted=baseline['recipe_selection']
    if probe['count']!=baseline['recipe_count']:raise RuntimeError('original unfiltered catalog differs')
    scroll_to(t,max(0,min(wanted-4,probe['count']-8)),'fixture.reveal_original_recipe',visible_index=wanted)
    probe=detail(t,'recipe_original_row_guard')
    rows=[r for r in probe['rows'] if r['index']==wanted]
    if len(rows)!=1:raise RuntimeError('original recipe row is not uniquely visible')
    control=target(t,'fixture.select_unfiltered_original_recipe',lambda c:c['name']==rows[0]['button'] and
        c['text'].strip()==baseline['selected_recipe']['name'])
    require(t.step('fixture.select_unfiltered_original_recipe','Select the original recipe in the unfiltered list.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},
        lambda b,a,s:{'status':'recipe_selection_restored' if s=='click' and
            a.get('recipe_selection')==wanted and a.get('selected_recipe')==baseline['selected_recipe'] else
            'client_or_protocol_failure'},diagnostic_action='click',await_state=lambda a:a.get('recipe_selection')==wanted),
        'recipe_selection_restored')
    scroll_to(t,0,'fixture.restore_recipe_viewport')
