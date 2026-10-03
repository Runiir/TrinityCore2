"""Read both stock talent and glyph panels without allocating or removing anything."""
import argparse,json,time
from pathlib import Path
from PIL import Image
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,command
from .interaction_bridge_deploy import shot
from .interaction_macros import require
from .interaction_trade import inventory
from .observation.interactions import decode_image


def native_state():
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT talentTree,talentGroupsCount,activeTalentGroup FROM client442_characters.characters WHERE guid=1')
        character=q.fetchone()
        q.execute('SELECT spell,talentGroup FROM client442_characters.character_talent WHERE guid=1 ORDER BY talentGroup,spell')
        talents=q.fetchall()
        q.execute('SELECT * FROM client442_characters.character_glyphs WHERE guid=1 ORDER BY talentGroup');glyphs=q.fetchall()
    return {'character':character,'talents':talents,'glyphs':glyphs}


def detail(t,label):
    try:
        command(t,'/tcui talents');p=t.out/(label+'.png');frame=shot(p);state=decode_image(Image.open(p))
        if state.get('mode')!='talents' or state.get('guid')!=t.guid:raise RuntimeError('talent diagnostic page identity mismatch')
        record={'state':state,'frame':frame};t.receipt.setdefault('detail',{})[label]=record;t.persist()
        return state['talent_probe']
    finally:command(t,'/tcui state')


def suite(t):
    actors.session_entry(t.fixture);t.clean_panels();before=native_state();items=inventory()
    if before['character']!=('0 0',1,0) or before['talents'] or any(any(r[2:]) for r in before['glyphs']):
        raise RuntimeError('requires the registered unallocated primary warrior fixture')
    t.receipt['baseline']={'talents':before,'inventory_money':items};t.persist()
    try:
        require(t.step('talents.open_repaired','Open the talents and glyph window.',
            {'open':{'kind':'key','value':'n','description':'Press the installed N binding.'}},
            lambda b,a,s:{'status':'talents_open_pass' if 'PlayerTalentFrame' in a['panels'] and
                a.get('talent_probe',{}).get('groups')==1 and a['talent_probe'].get('unspent')==41 and not a.get('lua_errors') else
                'client_or_protocol_failure','oracle':{'public':a.get('talent_probe'),'native':before}},diagnostic_action='open'),'talents_open_pass')
        require(click_case(t,'talents.select_talent_panel','View the three warrior specializations.',
            lambda c:c['name']=='PlayerTalentFrameTab1' and c['text']=='Talents',
            lambda b,a,s:{'status':'talent_panel_pass' if s and a.get('talent_probe',{}).get('selected')==1 else
                'client_or_protocol_failure'}),'talent_panel_pass')
        probe=detail(t,'talent_details')
        if [(r.get('id'),r.get('name'),r.get('count')) for r in probe['tabs']]!=[(746,'Arms',20),(815,'Fury',21),(845,'Protection',20)]:
            raise RuntimeError('public warrior talent catalogs differ from pinned native/client tables')
        require(click_case(t,'talents.glyph_open_repaired','Open the glyph socket panel.',
            lambda c:c['name']=='PlayerTalentFrameTab3' and c['text']=='Glyphs',
            lambda b,a,s:{'status':'glyph_panel_pass' if s and a.get('talent_probe',{}).get('selected')==3 and not a.get('lua_errors') else
                'client_or_protocol_failure'}),'glyph_panel_pass')
        probe=detail(t,'glyph_details')
        glyphs=probe['glyphs'];enabled=len(glyphs)==9 and all(r.get('enabled') and r.get('type') in [1,2,3] for r in glyphs)
        types={kind:sum(r.get('type')==kind for r in glyphs) for kind in [1,2,3]}
        if not enabled or types!={1:3,2:3,3:3}:raise RuntimeError('nine enabled Prime/Major/Minor glyph socket types are missing')
        t.receipt['glyph_oracle']={'nine_enabled':enabled,'three_of_each_type':types,'native_glyphs_unchanged':native_state()==before}
        t.persist()
        require(t.step('talents.close_repaired','Close the talents and glyph panel.',
            {'close':{'kind':'key','value':'Escape','description':'Close the stock talent window with Escape.'}},
            lambda b,a,s:{'status':'talents_close_pass' if 'PlayerTalentFrame' not in a['panels'] else 'client_or_protocol_failure'},
            diagnostic_action='close'),'talents_close_pass')
    finally:
        t.clean_panels();t.receipt['restoration']={'talents_unchanged':native_state()==before,'inventory_money_unchanged':inventory()==items};t.persist()
        if not all(t.receipt['restoration'].values()):raise RuntimeError('talent read fixture mutated native player state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=str(e)
    finally:t.receipt['finished_at']=time.time();t.persist();print({'completed':t.receipt['completed'],'failure':t.receipt['failure']})
