"""Read both stock talent and glyph panels without allocating or removing anything."""
import argparse,json,time
from pathlib import Path
from PIL import Image
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,command
from .interaction_bridge_deploy import shot
from .interaction_macros import require,edit_case
from .interaction_trade import inventory
from .observation.interactions import decode_image
from .interaction_observation import read_page


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
        state,frame=read_page(t,label,'talents','/tcui talents')
        record={'state':state,'frame':frame};t.receipt.setdefault('detail',{})[label]=record;t.persist()
        return state['talent_probe']
    finally:command(t,'/tcui state')


def glyph_detail(t,label,page=1):
    try:
        state,frame=read_page(t,label,'glyphs','/tcui glyphs '+str(page),
            ready=lambda s:s.get('glyph_probe',{}).get('page')==page)
        t.receipt.setdefault('glyph_detail',{})[label]={'state':state,'frame':frame};t.persist()
        return state['glyph_probe']
    finally:command(t,'/tcui state')


def suite(t,learned_arms=False):
    actors.session_entry(t.fixture);t.clean_panels();before=native_state();items=inventory()
    expected_tree=['746','0'] if learned_arms else ['0','0']
    expected_talents=((80976,0),) if learned_arms else ()
    if (before['character'][0].split()!=expected_tree or before['character'][1:]!=(1,0) or
            before['talents']!=expected_talents or any(any(r[2:]) for r in before['glyphs'])):
        raise RuntimeError('requires the registered unallocated primary warrior fixture')
    t.receipt['baseline']={'talents':before,'inventory_money':items};t.persist()
    try:
        require(t.step('talents.open_repaired','Open the talents and glyph window.',
            {'open':{'kind':'key','value':'n','description':'Press the installed N binding.'}},
            lambda b,a,s:{'status':'talents_open_pass' if 'PlayerTalentFrame' in a['panels'] and
                a.get('talent_probe',{}).get('groups')==1 and a['talent_probe'].get('unspent')==41-int(learned_arms) and not a.get('lua_errors') else
                'client_or_protocol_failure','oracle':{'public':a.get('talent_probe'),'native':before}},diagnostic_action='open',
            await_state=lambda s:'PlayerTalentFrame' in s['panels']),'talents_open_pass')
        state,_=t.observe('talent_selected_tab')
        if state.get('talent_probe',{}).get('selected')==1:
            # Stock tabs disable their already-selected button. Read this panel
            # directly rather than treating its disabled tab as a failure.
            t.receipt['talent_tab_already_selected']=True;t.persist()
        else:
            require(click_case(t,'talents.select_talent_panel','View the three warrior specializations.',
                lambda c:c['name']=='PlayerTalentFrameTab1' and c['text']=='Talents',
                lambda b,a,s:{'status':'talent_panel_pass' if s and a.get('talent_probe',{}).get('selected')==1 else
                    'client_or_protocol_failure'}),'talent_panel_pass')
        probe=detail(t,'talent_details')
        if [(r.get('id'),r.get('name'),r.get('count')) for r in probe['tabs']]!=[(746,'Arms',20),(815,'Fury',21),(845,'Protection',20)]:
            raise RuntimeError('public warrior talent catalogs differ from pinned native/client tables')
        if [r.get('spent') for r in probe['tabs']]!=[int(learned_arms),0,0]:
            raise RuntimeError('public per-tree totals differ from native learned talents')
        require(click_case(t,'talents.glyph_open_repaired','Open the glyph socket panel.',
            lambda c:c['name']=='PlayerTalentFrameTab3' and c['text']=='Glyphs',
            lambda b,a,s:{'status':'glyph_panel_pass' if s and a.get('talent_probe',{}).get('selected')==3 and not a.get('lua_errors') else
                'client_or_protocol_failure'}),'glyph_panel_pass')
        probe=detail(t,'glyph_details')
        glyphs=probe['glyphs'];enabled=len(glyphs)==9 and all(r.get('enabled') and r.get('type') in [1,2,3] for r in glyphs)
        types={kind:sum(r.get('type')==kind for r in glyphs) for kind in [1,2,3]}
        if not enabled or types!={1:3,2:3,3:3}:raise RuntimeError('nine enabled Prime/Major/Minor glyph socket types are missing')
        # Stock 60895 XML places Major sockets at 1/4/6, Minor at 2/3/5
        # and Prime at 7/8/9. Counts alone hide incorrectly reused DB2 IDs.
        socket_types=[r.get('type') for r in glyphs]
        if socket_types!=[2,3,3,2,3,2,1,1,1]:raise RuntimeError('glyph types do not match the stock socket positions')
        t.receipt['glyph_oracle']={'nine_enabled':enabled,'three_of_each_type':types,
            'socket_positions':socket_types,'native_glyphs_unchanged':native_state()==before}
        t.persist()
        if learned_arms:
            initial=glyph_detail(t,'glyph_catalog');total=initial['total']
            if type(total)is not int or not 3<=total<=500:raise RuntimeError('glyph catalog exceeds bounded review')
            rows=list(initial['rows'])
            for page in range(2,(total+11)//12+1):
                data=glyph_detail(t,'glyph_catalog_'+str(page),page)
                if data['total']!=total:raise RuntimeError('glyph catalog changed while reading')
                rows.extend(data['rows'])
            if len(rows)!=total or len({r['index'] for r in rows})!=total:
                raise RuntimeError('glyph catalog observation is incomplete')
            t.receipt['glyph_catalog_oracle']={'rows':rows,'total':total,'passed':True};t.persist()
            require(edit_case(t,'glyphs.search','Search the normal glyph catalog for Battle.',
                lambda c:c['name']=='GlyphFrameSearchBox','Battle'),'ui_edit_pass')
            searched=glyph_detail(t,'glyph_search')
            matching=[r for r in searched['rows'] if r.get('name')!='header']
            if searched.get('search')!='Battle' or not matching or any('battle' not in r.get('name','').lower() for r in matching):
                raise RuntimeError('glyph search does not match the public filtered catalog')
            t.receipt['glyph_search_oracle']={'public':searched,'passed':True};t.persist()
            require(edit_case(t,'glyphs.clear_search','Clear the glyph search.',
                lambda c:c['name']=='GlyphFrameSearchBox',''),'ui_edit_pass')
            cleared=glyph_detail(t,'glyph_search_cleared')
            # Stock OnEditFocusLost restores the localized SEARCH placeholder.
            # Reading diagnostics through chat causes that normal focus change.
            if (cleared['total']!=total or cleared.get('search') not in ['',initial.get('search')] or
                    cleared['rows']!=initial['rows']):raise RuntimeError('glyph search did not restore the catalog')
        require(t.step('talents.close_repaired','Close the talents and glyph panel.',
            {'close':{'kind':'key','value':'Escape','description':'Close the stock talent window with Escape.'}},
            lambda b,a,s:{'status':'talents_close_pass' if 'PlayerTalentFrame' not in a['panels'] else 'client_or_protocol_failure'},
            diagnostic_action='close'),'talents_close_pass')
    finally:
        t.clean_panels();t.receipt['restoration']={'talents_unchanged':native_state()==before,'inventory_money_unchanged':inventory()==items};t.persist()
        if not all(t.receipt['restoration'].values()):raise RuntimeError('talent read fixture mutated native player state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--learned-arms',action='store_true');a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t,a.learned_arms);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=str(e)
    finally:t.receipt['finished_at']=time.time();t.persist();print({'completed':t.receipt['completed'],'failure':t.receipt['failure']})
