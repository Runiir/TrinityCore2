"""Switch stock languages with one temporary owned native language and restore it."""
import argparse,hashlib,json,time
from contextlib import ExitStack
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_control_target import target
from .interaction_operations import point,controls
from .interaction_keybindings_native import suite as native_suite
from .interaction_fixture_permissions import fixture_permission
from .interaction_spellbook_navigation import known
from .interaction_spellbook_professions import skills
from .interaction_targeting import selection,target as select_target
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import Cursor
from .world.objects import INDEX
from .world.buffer import Reader

SPELL=672
LANGUAGE=6
SKILL=111
SKILL_FIELDS=['PLAYER_SKILL_LINEID_0','PLAYER_SKILL_STEP_0','PLAYER_SKILL_RANK_0',
    'PLAYER_SKILL_MAX_RANK_0','PLAYER_SKILL_MODIFIER_0','PLAYER_SKILL_TALENT_0']


def native_skills(oracle):
    fields=oracle.poll().objects[oracle.guid]
    return {name:[fields.get(INDEX[name]+i,0) for i in range(64)] for name in SKILL_FIELDS}


def click(t,label,predicate):
    c=target(t,label+'_control',predicate)
    if not c.get('enabled') or c['kind'] not in ('Button','CheckButton'):
        raise RuntimeError('requires an enabled observed stock button')
    require(t.step(label,'Click the observed stock chat control.',
        {'click':{'kind':'click','value':point(c),'hold':1.2}},
        lambda b,a,s:{'status':'ordinary_stock_click' if s=='click' and not a.get('lua_errors')
            and not a.get('blocked_actions') else 'client_or_protocol_failure'},diagnostic_action='click'),
        'ordinary_stock_click')


def choose(t,id,label):
    probe=detail(t,label+'_choices');rows=probe.get('languages',{})
    matches=[r for r in rows.get('rows',[]) if r['id']==id]
    if not rows.get('available') or len(matches)!=1:raise RuntimeError('language is absent or ambiguous')
    click(t,label+'_menu',lambda c:c['name']=='ChatFrameMenuButton')
    click(t,label+'_submenu',lambda c:c['text']=='Language')
    catalog=controls(t);state,frame=t.observe(label+'_options_rendered')
    t.receipt.setdefault('language_menus',[]).append({'label':label,'controls':catalog,'frame':frame});t.persist()
    click(t,label+'_radio',lambda c:c['text']==matches[0]['name'])
    after=detail(t,label+'_selected')
    t.receipt.setdefault('language_selections',[]).append({'label':label,'expected':id,'public':after});t.persist()
    if after['languages'].get('selected_id')!=id:raise RuntimeError('stock language selection differs')


def request(body,modern):
    r=Reader(bytes.fromhex(body));language,=r.unpack('i');size=r.bits(11 if modern else 9)
    if modern:r.bits(1)
    text=r.raw(size).decode();r.end();return language,text


def response(body,modern):
    r=Reader(bytes.fromhex(body));kind,language=r.unpack('Bi')
    if modern:
        sender=r.guid()[0];r.guid();r.guid();r.guid();r.unpack('IIiHfi')
        sizes=[r.bits(n) for n in [11,11,5,7,12]]
        for _ in range(4):r.bits(1)
        text=[r.raw(n).decode() for n in sizes][-1]
    else:
        sender,=r.unpack('Q');r.unpack('I');r.unpack('Q');size,=r.unpack('I')
        raw=r.raw(size)
        if not raw or raw[-1]!=0:raise ValueError('native message lacks terminator')
        text=raw[:-1].decode();r.unpack('B')
    r.end();return kind,language,sender,text


def send(t,session,id,label):
    token='TC442UI:language_'+str(id)+'_'+hashlib.sha256(str(t.out).encode()).hexdigest()[:8]
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in cursor.poll():pass
    since=time.time()
    def outcome(b,a,s):
        packets=[r for r in cursor.poll() if r.get('session')==session and r.get('time',0)>=since
            and token.encode() in bytes.fromhex(r.get('body',''))]
        checks={'ordinary_say':s=='say','public_echo':any(r.get('event')=='CHAT_MSG_SAY' and
            r.get('text')==token for r in a.get('chat_probes',[])),
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        decoded=[]
        for direction,name,modern,reply in [('from_client','CMSG_CHAT_MESSAGE_SAY',True,False),
            ('to_native','CMSG_MESSAGECHAT_SAY',False,False),('from_native','SMSG_MESSAGECHAT',False,True),
            ('to_client','SMSG_CHAT',True,True)]:
            values=[response(r['body'],modern) if reply else request(r['body'],modern)
                for r in packets if r.get('direction')==direction and r.get('name')==name]
            expected=(1,id,1,token) if reply else (id,token)
            checks[direction+'.exact_language_text']=bool(values) and all(v==expected for v in values)
            decoded.append({'direction':direction,'name':name,'decoded':values,'expected':expected})
        return {'status':'owned_stock_language_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'decoded':decoded,'packets':packets,'token':token}}
    require(t.step(label,'Send the fixed owned Say marker using the selected stock language.',
        {'say':{'kind':'chat','value':'/say '+token}},outcome,diagnostic_action='say'),'owned_stock_language_pass')
    state,frame=t.observe(label+'_rendered')
    t.receipt.setdefault('language_rendered',[]).append({'label':label,'state':state,'frame':frame});t.persist()


def run(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned primary language fixture')
    before=detail(t,'language_original');languages=before.get('languages',{})
    if not languages.get('available') or languages['rows']!=[{'id':7,'name':'Common'}]:
        raise RuntimeError('requires the exact original Common-only fixture')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    original={'spells':known(1),'skills':skills(1),'native_skills':native_skills(oracle),'target':selection(oracle)}
    if any(r[0]==SPELL for r in original['spells']) or any(r[0]==SKILL for r in original['skills']):
        raise RuntimeError('temporary native language already exists')
    if original['target'] not in [0,1,2]:raise RuntimeError('refuses an unrelated target baseline')
    t.receipt.update(language_baseline=before,language_fixture_baseline=original,
        language_fixture={'spell':SPELL,'language':LANGUAGE,'skill':SKILL,'temporary':True});t.persist()
    changed=False
    with ExitStack() as stack:
        stack.enter_context(fixture_permission(t,417));stack.enter_context(fixture_permission(t,429))
        try:
            if selection(oracle)!=1:
                select_target(t,oracle,session,'fixture.language_target_self',
                    {'kind':'chat','value':'/target Harnessone'},1)
            changed=True;t.execute({'kind':'chat','value':'.learn 672'});t.execute({'kind':'chat','value':'.save'})
            trained=detail(t,'language_fixture_trained')
            t.receipt['language_fixture_trained']={'public':trained,'spells':known(1),'skills':skills(1),
                'native_skills':native_skills(oracle)};t.persist()
            if (not any(r['id']==LANGUAGE for r in trained['languages']['rows']) or
                    not any(r[0]==SPELL for r in known(1)) or not any(r[0]==SKILL for r in skills(1))):
                raise RuntimeError('native language fixture did not become available and persist')
            choose(t,LANGUAGE,'chat.language_switch');send(t,session,LANGUAGE,'chat.language_switch')
            choose(t,7,'fixture.language_restore_common');send(t,session,7,'fixture.language_restore_common')
        except BaseException as error:
            t.receipt['language_operation_failure']=f'{type(error).__name__}: {error}';t.persist();raise
        finally:
            t.clean_panels()
            if changed:
                if selection(oracle)!=1:raise RuntimeError('refuses to unlearn on another target')
                t.execute({'kind':'chat','value':'.unlearn 672'});t.execute({'kind':'chat','value':'.save'})
                t.execute({'kind':'chat','value':'/reload'})
            if selection(oracle)!=original['target']:
                name={0:'/cleartarget',1:'/target Harnessone',2:'/target Harnesstwo'}[original['target']]
                select_target(t,oracle,session,'fixture.language_restore_target',{'kind':'chat','value':name},original['target'])
            after=detail(t,'language_restored')
            checks={'original_languages':after['languages']==before['languages'],
                'original_chat_settings':signature(after)==signature(before),'original_channels':after['channels']==before['channels'],
                'original_spells':known(1)==original['spells'],'original_skills':skills(1)==original['skills'],
                'original_native_skills':native_skills(oracle)==original['native_skills'],
                'original_target':selection(oracle)==original['target']}
            t.receipt['language_restoration']={'checks':checks,'public':after};t.persist()
            if not all(checks.values()):raise RuntimeError('original language fixture restoration differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    p.error('UI80 quarantined this live fixture: skill-step learning does not round-trip through spell persistence or unlearn. Implement the source-bound skill lifecycle before another language trial.')
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=run,preserve_settings=False);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
