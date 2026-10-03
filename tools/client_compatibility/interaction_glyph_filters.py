"""Exercise stock learned/unlearned glyph filters without mutating the character."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_glyph_apply import open_glyphs
from .interaction_glyph_learn import spells
from .interaction_talents import native_state,glyph_detail
from .interaction_trade import inventory
from .interaction_operations import click_case
from .interaction_macros import require

FLAGS={'known':8,'unknown':16}
LABELS={'known':'Used','unknown':'Unavailable'}


def catalog(t,label):
    probe=glyph_detail(t,label);rows=list(probe['rows'])
    for page in range(2,(probe['total']+11)//12+1):
        data=glyph_detail(t,label+'_'+str(page),page)
        if data['total']!=probe['total']:raise RuntimeError('glyph catalog changed while being observed')
        rows.extend(data['rows'])
    if len(rows)!=probe['total']:raise RuntimeError('incomplete glyph filter catalog')
    return {'rows':rows,'flags':{r['value']:r['active'] for r in probe['filters']},'total':probe['total']}


def menu(t,label):
    state,_=t.observe('menu_precheck_'+label)
    if 'ContextMenu' in state['panels']:return
    require(click_case(t,'glyphs.filter_menu.'+label,'Open the glyph filter menu.',
        lambda c:c['text'] in ['All Glyphs','Used','Unavailable','None'],
        lambda b,a,s:{'status':'glyph_filter_menu_pass' if s and 'ContextMenu' in a['panels'] else
            'client_or_protocol_failure'}),'glyph_filter_menu_pass')


def change(t,kind,expected,label,baseline):
    menu(t,label)
    def outcome(b,a,s):
        # Diagnostics only read public flags/catalog; all changes use the stock
        # menu checkbox. Checking native state is reserved for final restoration.
        probe=catalog(t,'filter_result_'+label)
        actual=[r for r in probe['rows'] if r.get('id')]
        wanted=[r for r in baseline['rows'] if r.get('id') and
            (bool(r['known']) and probe['flags'][8] or not r['known'] and probe['flags'][16])]
        comparable=lambda rows:[{k:r[k] for k in ['id','name','type','known']} for r in rows]
        # Filtering rebuilds the catalog indexes. Compare the glyph identities,
        # names, types and learned flags in order, not their pre-filter indexes.
        matches=comparable(actual)==comparable(wanted) and probe['flags'][FLAGS[kind]]==expected
        t.receipt.setdefault('filter_oracles',{})[label]={'public':probe,'expected_glyph_ids':[r['id'] for r in wanted],
            'passed':matches};t.persist()
        return {'status':'glyph_filter_pass' if s and matches else 'client_or_protocol_failure',
            'oracle':t.receipt['filter_oracles'][label]}
    require(click_case(t,'glyphs.filter_'+kind+'.'+label,
        ('Show' if expected else 'Hide')+' '+('learned' if kind=='known' else 'unlearned')+' glyphs.',
        lambda c:c['text']==LABELS[kind],outcome),'glyph_filter_pass')
    state,_=t.observe('filter_menu_settled_'+label)
    if 'ContextMenu' in state['panels']:
        t.execute({'kind':'key','value':'Escape','description':'Dismiss only the still-visible filter menu.'})


def suite(t):
    t.clean_panels();items,known,talents=inventory(),spells(),native_state()
    t.receipt['baseline']={'inventory_money':items,'spells':known,'talents':talents};t.persist()
    baseline=None
    try:
        open_glyphs(t);baseline=catalog(t,'complete_catalog')
        glyphs=[r for r in baseline['rows'] if r.get('id')]
        if (len(glyphs)!=34 or sum(bool(r['known']) for r in glyphs)!=1 or
            not all(baseline['flags'].values())):
            raise RuntimeError('requires the full warrior catalog with only Battle learned and all filters enabled')
        t.receipt['filter_baseline']=baseline;t.persist()
        change(t,'unknown',False,'known_only',baseline)
        change(t,'unknown',True,'unknown_restore',baseline)
        change(t,'known',False,'unknown_only',baseline)
        change(t,'known',True,'known_restore',baseline)
    finally:
        if baseline:
            current=catalog(t,'restoration_check')
            for kind,flag in FLAGS.items():
                if current['flags'][flag]!=baseline['flags'][flag]:
                    change(t,kind,baseline['flags'][flag],'cleanup_'+kind,baseline)
                    current=catalog(t,'cleanup_check_'+kind)
            t.receipt['filter_restoration']={'catalog_flags_restored':current==baseline};t.persist()
            if current!=baseline:raise RuntimeError('glyph filter catalog differs after restoration')
        t.clean_panels()
        t.receipt['restoration']={'inventory_money_unchanged':inventory()==items,
            'learned_spells_unchanged':spells()==known,'talents_glyphs_unchanged':native_state()==talents};t.persist()
        if not all(t.receipt['restoration'].values()):raise RuntimeError('glyph filters mutated unrelated character state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
