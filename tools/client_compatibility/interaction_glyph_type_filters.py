"""Collapse and expand the three stock glyph-type headers through mouse inputs."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_glyph_apply import open_glyphs
from .interaction_glyph_filters import catalog
from .interaction_glyph_learn import spells
from .interaction_talents import native_state
from .interaction_trade import inventory
from .interaction_operations import click_case
from .interaction_macros import require

TYPES={'Prime':1,'Major':2,'Minor':4}


def change(t,kind,expected,label,baseline):
    def outcome(b,a,s):
        probe=catalog(t,'type_filter_'+label)
        actual=[r for r in probe['rows'] if r.get('id')]
        wanted=[r for r in baseline['rows'] if r.get('id') and probe['flags'][2**(r['type']-1)] and
            (probe['flags'][8] if r['known'] else probe['flags'][16])]
        comparable=lambda rows:[{k:r[k] for k in ['id','name','type','known']} for r in rows]
        passed=(s and probe['flags'][TYPES[kind]]==expected and comparable(actual)==comparable(wanted) and
            probe['flags'][8]==baseline['flags'][8] and probe['flags'][16]==baseline['flags'][16])
        oracle={'public':probe,'expected_glyph_ids':[r['id'] for r in wanted],'passed':bool(passed)}
        t.receipt.setdefault('type_filter_oracles',{})[label]=oracle;t.persist()
        return {'status':'glyph_type_filter_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
    require(click_case(t,'glyphs.type_'+kind.lower()+'.'+label,
        ('Expand' if expected else 'Collapse')+' the '+kind+' glyph catalog.',
        lambda c:c['name'].startswith('GlyphFrameHeader') and c['text']==kind+' Glyphs',outcome),'glyph_type_filter_pass')


def suite(t):
    t.clean_panels();items,known,talents=inventory(),spells(),native_state()
    t.receipt['baseline']={'inventory_money':items,'spells':known,'talents':talents};t.persist();baseline=None
    try:
        open_glyphs(t);baseline=catalog(t,'type_full_catalog')
        if len([r for r in baseline['rows'] if r.get('id')])!=34 or not all(baseline['flags'].values()):
            raise RuntimeError('requires the full warrior catalog and all five filters enabled')
        t.receipt['filter_baseline']=baseline;t.persist()
        # Collapsing earlier types brings the next ordinary header into view.
        # Reversing that order restores all three without hidden UI mutations.
        for kind in TYPES:change(t,kind,False,kind.lower()+'_collapse',baseline)
        for kind in reversed(TYPES):change(t,kind,True,kind.lower()+'_expand',baseline)
    finally:
        if baseline:
            current=catalog(t,'type_restoration_check')
            if current!=baseline:
                for kind,flag in TYPES.items():
                    if current['flags'][flag]:
                        change(t,kind,False,'cleanup_'+kind.lower()+'_collapse',baseline)
                        current=catalog(t,'cleanup_collapsed_'+kind)
                for kind in reversed(TYPES):
                    change(t,kind,True,'cleanup_'+kind.lower()+'_expand',baseline)
                current=catalog(t,'type_cleanup_restored')
            t.receipt['filter_restoration']={'catalog_flags_restored':current==baseline};t.persist()
            if current!=baseline:raise RuntimeError('glyph type filters did not restore the exact catalog')
        t.clean_panels()
        checks={'inventory_money_unchanged':inventory()==items,'learned_spells_unchanged':spells()==known,
            'talents_glyphs_unchanged':native_state()==talents}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('glyph type filters mutated unrelated character state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
