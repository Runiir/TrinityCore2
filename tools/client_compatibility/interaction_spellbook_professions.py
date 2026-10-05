"""Check stock profession rendering against native skills with ordinary tab clicks."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_spellbook_navigation import detail,known,wire_known,navigate
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory

SKILLS={171,197,794,356,185,129}


def skills(guid):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT skill,value,max FROM client442_characters.character_skills WHERE guid=%s ORDER BY skill',(guid,))
        return [list(row) for row in q.fetchall()]


def checks(probe,native,learned):
    rows=probe.get('professions') or []
    trained=[r for r in rows if r.get('index')]
    expected={r[0]:(r[1],r[2]) for r in native if r[0] in SKILLS}
    clean=lambda s:re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',s or '').strip()
    valid={'visible':probe['visible'],'profession_book':probe['book_type']==probe['book_types']['profession'],
        'six_stock_slots':len(rows)==6 and [r['slot'] for r in rows]==list(range(1,7)),
        'native_catalog':{r['api']['skill'] for r in trained}==set(expected)}
    for row in rows:
        prefix=row['frame'];rendered=row.get('rendered',{});api=row.get('api')
        valid[prefix+'.visible']=row['visible']
        if api:
            rank,maximum=expected.get(api['skill'],(None,None));modifier=api.get('modifier') or 0
            ranks=[rank,modifier,maximum] if modifier>0 else [rank,maximum]
            valid[prefix+'.native_rank']=(api['rank'],api['max_rank'])==(rank,maximum)
            valid[prefix+'.rendered_name']=clean(rendered.get('name'))==clean(api['name']) and bool(api['name'])
            valid[prefix+'.rendered_rank']=[int(v) for v in re.findall(r'\d+',rendered.get('rank_text') or '')]==ranks
            valid[prefix+'.bar']=rendered.get('bar_visible') and rendered.get('bar_value')==rank and rendered.get('bar_max')==maximum
            valid[prefix+'.skill']=rendered.get('skill')==api['skill']
            valid[prefix+'.buttons']=len(row.get('buttons',[]))==min(api['count'],2) and all(
                b.get('id') in learned and b.get('known') is True and clean(b.get('name'))==clean(b.get('shown_name'))
                for b in row.get('buttons',[]))
        else:
            valid[prefix+'.untrained']=not rendered.get('bar_visible') and rendered.get('missing_header_visible') and rendered.get('missing_text_visible') and not row.get('buttons')
    return valid


def suite(t,after_tab=None):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();original=resources(oracle);persisted=known(t.fixture['guid']);native=skills(t.fixture['guid'])
    learned=wire_known(t,session);layout=None
    t.receipt.update(native_session=session,baseline=original,native_skills=native,native_persisted_spells=persisted,
        qualified_scope='Stock profession tab, six trained skill ranks/names/buttons or untrained placeholders only; recipe crafting/learning/unlearning remain open')
    t.persist()
    try:
        require(click_case(t,'spellbook.professions.open','Open the observed stock spellbook.',
            lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'spellbook_open_pass' if s and
                'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda a:'SpellBookFrame' in a['panels']),'spellbook_open_pass')
        layout=detail(t,'profession_layout_baseline');t.receipt['book_layout_baseline']=layout;t.persist()
        def outcome(b,a,s):
            probe=detail(t,'profession_tab',book_type=layout['book_types']['profession']);valid=checks(probe,native,learned)
            valid.update(selected=s,ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
            return {'status':'profession_tab_pass' if all(valid.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':valid,'probe':probe}}
        require(click_case(t,'spellbook.professions_tab','Inspect the stock profession tab.',
            lambda c:c['name']=='SpellBookFrameTabButton2',outcome),'profession_tab_pass')
        if after_tab is not None:after_tab(t)
    finally:
        try:
            if layout:
                current=detail(t,'profession_restore_before')
                if not current['visible']:raise RuntimeError('profession cleanup requires the visible owned spellbook')
                if current['book_type']!=layout['book_type']:
                    tab='SpellBookFrameTabButton'+('1' if layout['book_type']==layout['book_types']['spell'] else '2')
                    require(click_case(t,'spellbook.professions.restore_book','Return to the original spellbook tab.',
                        lambda c:c['name']==tab,lambda b,a,s:{'status':'spellbook_restore_pass' if s and
                            detail(t,'profession_restore_book',book_type=layout['book_type'])['book_type']==layout['book_type'] else 'client_or_protocol_failure'}),'spellbook_restore_pass')
                    current=detail(t,'profession_restore_category')
                if current['skill_line']!=layout['skill_line']:
                    require(navigate(t,learned,'spellbook.professions.restore_line','SpellBookSkillLineTab'+str(layout['skill_line']),
                        line=layout['skill_line'],check_content=False),'spellbook_navigation_pass')
                after=detail(t,'profession_layout_restored')
                t.receipt['book_layout_restored']=all(after.get(k)==layout.get(k) for k in ['book_type','skill_line','pages','page'])
                if not t.receipt['book_layout_restored']:raise RuntimeError('original spellbook layout did not restore')
        finally:
            try:t.clean_panels()
            finally:
                t.receipt.update(native_after=resources(oracle),native_skills_after=skills(t.fixture['guid']),
                    native_persisted_spells_after=known(t.fixture['guid']))
                t.receipt['native_resources_preserved']=t.receipt['native_after']==original and t.receipt['native_skills_after']==native and t.receipt['native_persisted_spells_after']==persisted
                t.persist()
                if not t.receipt['native_resources_preserved']:raise RuntimeError('profession tab changed native inventory/money/skills/spells')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
