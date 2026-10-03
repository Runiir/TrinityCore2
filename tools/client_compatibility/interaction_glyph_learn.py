"""Learn Glyph of Battle from a staged book using an ordinary bag right-click."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_crafting import fixture_command
from .interaction_fixture_permissions import item_fixture_permission
from .interaction_inventory_moves import slot_control
from .interaction_operations import click_case,point
from .interaction_macros import require
from .interaction_trade import inventory
from .interaction_talents import native_state,glyph_detail
from .observation.inventory import Inventory
from .observation.journal import entries

BOOK=43395
LEARNED=58276


def spells():
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT spell,active,disabled FROM client442_characters.character_spell WHERE guid=1 ORDER BY spell')
        return q.fetchall()


def cleanup(t,source):
    previous=json.loads(source.read_text());baseline=previous['baseline']
    normalize=lambda x:json.loads(json.dumps(x))
    if (not previous.get('finished_at') or previous.get('completed') or
            previous['actor']!=t.fixture or not previous.get('book_fixture')):
        raise RuntimeError('glyph cleanup requires a closed failed owned book-use episode')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    native=previous['book_fixture']['native'];public=previous['book_fixture']['public']
    if (oracle.count(BOOK)!=1 or oracle.slot(public['bag'],public['slot'])!=native or
            normalize(spells())!=baseline['spells'] or normalize(native_state())!=baseline['talents']):
        raise RuntimeError('unused glyph book or unrelated player baseline changed')
    t.receipt['cleanup_source']={'file':str(source),'sha256':lab.sha256(source)};t.persist()
    t.clean_panels()
    with item_fixture_permission(t):
        fixture_command(t,'/cleartarget','remove only the unused owned glyph book fixture')
        fixture_command(t,f'.additem {BOOK} -1','restore the exact unused glyph book from the failed probe')
    t.receipt['restoration']={'inventory_money_restored':normalize(inventory())==baseline['inventory_money'],
        'native_spells_restored':normalize(spells())==baseline['spells'],
        'talents_glyphs_restored':normalize(native_state())==baseline['talents'],'book_absent':oracle.poll().count(BOOK)==0}
    t.persist()
    if not all(t.receipt['restoration'].values()):raise RuntimeError('failed glyph book fixture cleanup differs from baseline')


def suite(t):
    session=actors.session_entry(t.fixture)['session'];t.clean_panels()
    oracle=Inventory(lab.ROOT,session,1).poll();items=inventory();known=spells();talents=native_state()
    if oracle.count(BOOK) or any(r[0]==LEARNED for r in known):
        raise RuntimeError('glyph learning requires no pre-existing book or learned Battle glyph')
    catalog=lab.ROOT/'data/dbc/enUS/Item-sparse.db2'
    digest=lab.sha256(catalog)
    if digest!='bd21d2a012c4a983dc3179de84d63abd1cfcd1f7063d0785426d75636dd24c06':
        raise RuntimeError('pinned native glyph book catalog changed')
    t.receipt['baseline']={'inventory_money':items,'spells':known,'talents':talents,
        'item_catalog_sha256':digest,'book':BOOK,'learned_spell':LEARNED};t.persist()
    try:
        with item_fixture_permission(t):
            fixture_command(t,'/cleartarget','stage the book only on the owned actor')
            fixture_command(t,f'.additem {BOOK} 1','one disposable glyph book, not learned-spell credit')
        if oracle.poll().count(BOOK)!=1:raise RuntimeError('native glyph book fixture did not appear')
        t.execute({'kind':'key','value':'b'});state,frame=t.observe('glyph_book_prepared')
        shown=[r for r in state.get('bag_items',[]) if r['id']==BOOK and r['count']==1]
        if len(shown)!=1:raise RuntimeError('glyph book is absent or ambiguous in the public bags')
        row=shown[0];control=slot_control(t,row['bag'],row['slot']);native=oracle.slot(row['bag'],row['slot'])
        if not control or native['id']!=BOOK:raise RuntimeError('public glyph book position disagrees with native inventory')
        t.receipt['book_fixture']={'public':row,'native':native,'frame':frame,'control':control};t.persist()
        started=time.time()
        def outcome(b,a,s):
            deadline=time.monotonic()+12
            while oracle.poll().count(BOOK) and time.monotonic()<deadline:time.sleep(.25)
            now=spells();added=[r for r in now if r not in known];unchanged=[r for r in now if r[0]!=LEARNED]==list(known)
            packets=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('session')==session and
                p.get('time',0)>=started and p.get('name') in ['CMSG_USE_ITEM','CMSG_CAST_SPELL',
                    'SMSG_SPELL_START','SMSG_SPELL_GO','SMSG_CAST_FAILED','SMSG_LEARNED_SPELL','SMSG_LEARNED_SPELLS']]
            passed=s=='use' and oracle.count(BOOK)==0 and len(added)==1 and added[0][0]==LEARNED and unchanged
            t.receipt['earned_glyph']={'native_spells':now,'added':added,'book_remaining':oracle.count(BOOK),'passed':passed}
            t.persist()
            return {'status':'glyph_learn_pass' if passed else 'client_or_protocol_failure',
                'oracle':{'book_consumed':oracle.count(BOOK)==0,'native_spell_diff':added,
                    'unrelated_spells_unchanged':unchanged,'packets':packets,'public_errors':a.get('errors')}}
        require(t.step('glyphs.learn_book','Learn Glyph of Battle from its book.',
            {'use':{'kind':'click','value':point(control),'button':3,'description':'Right-click the observed Glyph of Battle book.'}},
            outcome,diagnostic_action='use'),'glyph_learn_pass')
        t.clean_panels();t.execute({'kind':'key','value':'n'})
        require(click_case(t,'glyphs.learned_open','Open glyphs.',lambda c:c['name']=='PlayerTalentFrameTab3',
            lambda b,a,s:{'status':'glyph_panel_pass' if s and a.get('talent_probe',{}).get('selected')==3 else
                'client_or_protocol_failure'}),'glyph_panel_pass')
        data=glyph_detail(t,'learned_catalog');rows=list(data['rows'])
        for page in range(2,(data['total']+11)//12+1):rows.extend(glyph_detail(t,'learned_catalog_'+str(page),page)['rows'])
        battle=[r for r in rows if r.get('name')=='Battle' and r.get('id')==483]
        passed=len(battle)==1 and battle[0].get('known') is True
        t.receipt['public_learned_oracle']={'rows':battle,'passed':passed};t.persist()
        if not passed:raise RuntimeError('learned native glyph is absent from the public known catalog')
    finally:
        t.clean_panels();remaining=oracle.poll().count(BOOK)
        if remaining:
            if remaining!=1:raise RuntimeError('glyph book fixture has an unexpected quantity')
            with item_fixture_permission(t):
                fixture_command(t,'/cleartarget','remove only the unused owned glyph book fixture')
                fixture_command(t,f'.additem {BOOK} -1','remove only the unused disposable glyph book')
        now=spells();preserved=[r for r in now if r[0]!=LEARNED]==list(known)
        t.receipt['restoration']={'inventory_money_restored':inventory()==items,'talents_glyphs_unchanged':native_state()==talents,
            'unrelated_spells_unchanged':preserved,'earned_learning_preserved':True};t.persist()
        if not all(t.receipt['restoration'].values()):raise RuntimeError('glyph learning fixture changed unrelated player state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cleanup-episode',type=Path);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:
        cleanup(t,a.cleanup_episode) if a.cleanup_episode else suite(t)
        t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
