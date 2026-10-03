"""Ordinary equipped-item and learned-glyph hovers with native identity checks."""
import argparse,json,re,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import command,controls,point
from .interaction_observation import read_page
from .interaction_macros import require,edit_case
from .interaction_archaeology_projects import native,dbc
from .interaction_talents import native_state,glyph_detail
from .interaction_glyph_learn import spells,LEARNED
from .interaction_glyph_apply import open_glyphs,GLYPH,AURA


def items(ids):
    path=lab.ROOT/'data/dbc/enUS/Item-sparse.db2';body=path.read_bytes()
    header=struct.unpack_from('<4s11I',body);magic,count,fields,width,size=header[:5]
    if magic!=b'WDB2' or (fields,width,header[6])!=(133,532,15595):
        raise RuntimeError('unexpected native Item-sparse catalog layout/build')
    start=48+(header[9]-header[8]+1)*6
    if len(body)!=start+count*width+size:raise RuntimeError('native Item-sparse index/data boundary differs')
    strings=body[start+count*width:];out={}
    for i in range(count):
        row=struct.unpack_from('<133I',body,start+i*width)
        if row[0] not in ids:continue
        if not 0<=row[99]<size:raise RuntimeError('native item display string is invalid')
        name=strings[row[99]:].split(b'\0',1)[0].decode()
        out[row[0]]={'id':row[0],'name':name,'inventory_type':row[9],'item_level':row[12]}
    if set(out)!=set(ids):raise RuntimeError('equipped item identities are absent from native catalog')
    return out,lab.sha256(path)


def baseline():
    return {'archaeology_inventory_money':native(),'talents_glyphs':native_state(),'known_spells':spells()}


def tooltip(t,label):
    try:
        state,frame=read_page(t,label,'tooltip','/tcui tooltip')
        t.receipt.setdefault('tooltip_details',{})[label]={'state':state,'frame':frame};t.persist()
        return state['tooltip_probe']
    finally:command(t,'/tcui state')


def hover(t,case_id,control,title,item=None):
    def outcome(b,a,s):
        probe=tooltip(t,case_id.replace('.','_'));lines=probe.get('lines') or []
        text=lines[0].get('left','') if lines else ''
        text=re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',text)
        checks={'visible':probe['visible'],'title':text==title,'owner':probe.get('owner')==control['name'],
            'native_preserved':baseline()==t.tooltip_baseline,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        if item:
            match=re.search(r'\|Hitem:(\d+)',probe.get('item_link',''))
            checks.update(item_name=probe.get('item_name')==title,item_id=bool(match and int(match[1])==item))
        return {'status':'stock_tooltip_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'expected_title':title,'expected_item':item,'public':probe}}
    require(t.step(case_id,'Inspect the ordinary '+title+' tooltip.',
        {'hover':{'kind':'hover','value':point(control),'description':'Move the owned pointer over '+control['name']+'.'}},
        outcome,diagnostic_action='hover'),'stock_tooltip_pass')


def suite(t,family):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned primary warrior')
    actors.session_entry(t.fixture);t.clean_panels();t.tooltip_baseline=baseline()
    t.receipt['baseline']=t.tooltip_baseline;t.persist()
    original_search=None
    try:
        if family=='equipment':
            slots=[('CharacterHeadSlot',0),('CharacterBackSlot',14),('CharacterMainHandSlot',15)]
            selected={name:next(r for r in t.tooltip_baseline['archaeology_inventory_money']['inventory']['items']
                if r[0]==1 and r[1]==0 and r[2]==slot) for name,slot in slots}
            names,digest=items([row[4] for row in selected.values()])
            t.receipt['item_contracts']={'items':names,'catalog_sha256':digest,'slots':selected};t.persist()
            require(t.step('character.tooltip_open','Open the character equipment panel.',
                {'open':{'kind':'key','value':'c','description':'Press C for character equipment.'}},
                lambda b,a,s:{'status':'character_open_pass' if 'CharacterFrame' in a['panels'] else
                    'client_or_protocol_failure'},diagnostic_action='open'),'character_open_pass')
            for name,slot in slots:
                rows=[c for c in controls(t) if c['name']==name]
                if len(rows)!=1:raise RuntimeError('equipped tooltip control is absent/ambiguous: '+name)
                entry=selected[name][4];hover(t,'character.equipment_tooltip.'+name,rows[0],names[entry]['name'],entry)
        else:
            if not any(r[0]==LEARNED and r[1:]==(1,0) for r in t.tooltip_baseline['known_spells']):
                raise RuntimeError('Battle glyph must already be learned normally')
            props,_=dbc('GlyphProperties',4);prop=next(r for r in props if r[0]==GLYPH)
            if prop[1]!=AURA:raise RuntimeError('native Battle glyph aura contract differs')
            rows,text=dbc('Spell',48);title=next(text(r[21]) for r in rows if r[0]==AURA)
            open_glyphs(t);probe=glyph_detail(t,'glyph_tooltip_before');original_search=probe.get('search') or ''
            require(edit_case(t,'glyphs.tooltip_search','Find the learned Battle glyph.',
                lambda c:c['name']=='GlyphFrameSearchBox','Battle'),'ui_edit_pass')
            probe=glyph_detail(t,'glyph_tooltip_catalog');matches=[r for r in probe['rows'] if r.get('id')==GLYPH and r.get('known')]
            rows=[c for c in controls(t) if c['name'].startswith('GlyphFrameScrollFrameButton') and c['text']=='Battle']
            if len(matches)!=1 or len(rows)!=1:raise RuntimeError('one visible learned Battle glyph is required')
            t.receipt['glyph_contract']={'id':GLYPH,'aura':AURA,'learned_spell':LEARNED,'title':title};t.persist()
            hover(t,'talents.glyph_tooltip',rows[0],title)
    finally:
        if original_search is not None:
            require(edit_case(t,'glyphs.tooltip_search_restore','Restore the original glyph search.',
                lambda c:c['name']=='GlyphFrameSearchBox',original_search),'ui_edit_pass')
        t.clean_panels();t.receipt['native_after']=baseline();t.receipt['native_preserved']=t.receipt['native_after']==t.tooltip_baseline;t.persist()
        if not t.receipt['native_preserved']:raise RuntimeError('read-only tooltips changed native state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--family',choices=['equipment','glyph'],required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.family);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
