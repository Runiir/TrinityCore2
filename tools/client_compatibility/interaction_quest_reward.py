"""Earn and retain quest 52 rewards using ordinary kills and stock quest UI."""
import argparse,json,time
from collections import Counter
from pathlib import Path
from PIL import Image
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_quest_accept import suite as accept_suite,QUEST,TITLE
from .interaction_quest_progress import complete
from .interaction_quest_fixture import quest_state
from .interaction_trade import inventory
from .interaction_macros import require
from .interaction_operations import click_case,command,controls
from .interaction_bridge_deploy import shot
from .observation.interactions import decode_image
from .observation.transport import Observer
from .observation.journal import entries
from .world.buffer import Reader


def detail(t,label):
    try:
        command(t,'/tcui quest_reward');path=t.out/(label+'.png');frame=shot(path)
        with Image.open(path) as image:state=decode_image(image)
        if state.get('mode')!='quest_reward' or state.get('guid')!=t.guid:
            raise RuntimeError('quest reward diagnostic identity mismatch')
        t.receipt.setdefault('reward_details',{})[label]={'state':state,'frame':frame};t.persist()
        return state['quest_reward']
    finally:command(t,'/tcui state')


def totals(items):
    values=Counter()
    for row in items['items']:
        if row[0]==1:values[row[4]]+=row[5]
    return values


def native_offer(body):
    r=Reader(bytes.fromhex(body));giver,quest=r.unpack('QI')
    for _ in range(6):
        end=r.data.index(b'\0',r.pos);r.raw(end-r.pos+1)
    r.unpack('2I');r.unpack('B');r.unpack('2I');count,=r.unpack('I')
    if count>16:raise ValueError('unsupported native offer emotes')
    r.raw(count*8);choices,=r.unpack('I');ids=r.unpack('6I');qty=r.unpack('6I');r.unpack('6I')
    fixed,=r.unpack('I');fixed_ids=r.unpack('4I');fixed_qty=r.unpack('4I');r.unpack('4I')
    money,xp,title,reserved,unused,unused1,unused2,flags=r.unpack('4If3I')
    r.raw((5*3+2+4+4+2)*4);r.end()
    if choices>6 or fixed>4:raise ValueError('unsupported native offer item counts')
    return {'giver':giver,'quest':quest,'money':money,'xp':xp,
        'choices':[{'id':ids[i],'quantity':qty[i],'index':i+1} for i in range(choices)],
        'fixed':[{'id':fixed_ids[i],'quantity':fixed_qty[i],'index':i+1} for i in range(fixed)]}


def packets_since(started,session,name):
    return [p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('time',0)>=started and
        p.get('session')==session and p.get('name')==name]


def reward(t,giver,point_file):
    complete(t,giver);t.clean_panels()
    t.execute({'kind':'chat','value':'/targetexact '+giver.npc[2]})
    state,frame=t.observe('reward_giver_staged');t.receipt['reward_staging']={'state':state,'frame':frame};t.persist()
    deadline=time.monotonic()+60
    while not point_file.is_file() and time.monotonic()<deadline:time.sleep(.2)
    review=json.loads(point_file.read_text());point=review.get('point')
    if (review.get('frame_sha256')!=frame['sha256'] or review.get('guid')!=t.guid or
        not isinstance(point,list) or len(point)!=2 or any(type(v)is not int or not 0<=v<b for v,b in zip(point,[1280,720]))):
        raise RuntimeError('turn-in giver point lacks fresh bounded visual review')
    t.receipt['reward_point_review']=review;t.persist()
    started=time.time();session=Observer(guid=1).poll()['session']
    require(t.step('quests.reward_interact','Speak to Guard Thomas about the completed quest.',
        {'interact':{'kind':'click','value':point,'button':3,'description':'Right-click the freshly reviewed Guard Thomas.'}},
        lambda b,a,s:{'status':'questgiver_open_pass' if s=='interact' and any(p in a['panels'] for p in ['QuestFrame','GossipFrame']) else
            'client_or_protocol_failure','oracle':{'panels':a['panels'],'quest_giver':a.get('quest_giver')}},
        diagnostic_action='interact'),'questgiver_open_pass')
    state,_=t.observe('reward_giver_open')
    if state.get('quest_giver',{}).get('id')!=QUEST:
        require(click_case(t,'quests.reward_select','Select the completed '+TITLE+' quest.',
            lambda c:TITLE in c['text'],
            lambda b,a,s:{'status':'quest_turnin_open_pass' if s and a.get('quest_giver',{}).get('id')==QUEST else
                'client_or_protocol_failure','oracle':{'quest_giver':a.get('quest_giver')}}),'quest_turnin_open_pass')
    probe=detail(t,'reward_offer')
    if not any(f.get('name')=='QuestFrameRewardPanel' and f.get('visible') for f in probe.get('frames',[])):
        require(click_case(t,'quests.reward_continue','Continue to the reward for the completed objectives.',
            lambda c:c['name']=='QuestFrameCompleteButton',
            lambda b,a,s:{'status':'quest_turnin_open_pass' if s and a.get('quest_giver',{}).get('id')==QUEST else
                'client_or_protocol_failure'}),'quest_turnin_open_pass')
        probe=detail(t,'reward_offer_after_continue')
    offers=packets_since(started,session,'SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE')
    native=[p for p in offers if p['direction']=='from_native']
    if not native:raise RuntimeError('ordinary turn-in did not produce an authoritative native reward offer')
    offered=native_offer(native[-1]['body'])
    plain=lambda rows:[(x.get('id'),x.get('quantity')) for x in rows]
    # Some Classic quest UIs do not expose GetRewardXP. Only this level-cap
    # fixture permits its absence, and only when the native offer gives zero.
    xp_available=probe.get('xp') is not None
    xp_agrees=probe.get('xp')==offered['xp'] if xp_available else t.fixture['level']==85 and offered['xp']==0
    agrees=(probe.get('id')==QUEST and probe.get('money')==offered['money'] and xp_agrees and
        plain(probe.get('choices',[]))==plain(offered['choices']) and plain(probe.get('fixed',[]))==plain(offered['fixed']))
    t.receipt['offer_oracle']={'native':offered,'public':probe,'packets':offers,'passed':agrees,
        'public_xp_available':xp_available,'xp_gain_qualification':False};t.persist()
    if not agrees or not 2<=len(offered['choices'])<=6:
        raise RuntimeError('stock reward display disagrees with the native multiple-choice offer')
    chosen=offered['choices'][0];t.receipt['reward_choice_controls']=controls(t);t.persist()
    require(click_case(t,'quests.reward_choice','Choose the first displayed reward.',
        lambda c:c['name']=='QuestInfoItem1' or c['name'].endswith('QuestInfoItem1'),
        lambda b,a,s:{'status':'quest_reward_choice_pass' if s and detail(t,'reward_selected').get('selected')==1 else
            'client_or_protocol_failure'}),'quest_reward_choice_pass')
    before=inventory();t.receipt['reward_inventory_before']=before;t.persist()
    def rewarded(b,a,s):
        samples=[];deadline=time.monotonic()+15
        while True:
            now=quest_state(1);items=inventory();samples.append({'quests':now,'inventory_money':items})
            if any(x['quest']==QUEST for x in now['rewarded']) or time.monotonic()>deadline:break
            time.sleep(.5)
        expected=Counter({chosen['id']:chosen['quantity']})
        for row in offered['fixed']:expected[row['id']]+=row['quantity']
        actual=totals(items);old=totals(before);delta={k:actual[k]-old[k] for k in set(actual)|set(old) if actual[k]!=old[k]}
        money_before=dict(before['money'])[1];money_now=dict(items['money'])[1]
        packets=packets_since(started,session,'SMSG_QUEST_GIVER_QUEST_COMPLETE');completion=[]
        for p in packets:
            r=Reader(bytes.fromhex(p['body']))
            if p['direction']=='from_native':
                talent,skillups,money,xp,quest,skill=r.unpack('2Ii3I');completion.append((quest,xp,money,skill,skillups))
            elif p['direction']=='to_client':completion.append(r.unpack('IIqII'))
        agrees=len(completion)==2 and completion[0]==completion[1] and completion[0][:3]==(QUEST,offered['xp'],offered['money'])
        passed=(s and any(x['quest']==QUEST for x in now['rewarded']) and not any(x['quest']==QUEST for x in now['active']) and
            delta==dict(expected) and money_now-money_before==offered['money'] and a.get('money')==money_now and agrees)
        return {'status':'quest_reward_pass' if passed else 'client_or_protocol_failure',
            'oracle':{'samples':samples,'item_delta':delta,'expected_item_delta':dict(expected),
                'money_delta':money_now-money_before,'public_money':a.get('money'),'packets':packets,
                'completion_values':completion,'native_modern_completion_agrees':agrees,'earned_reward_retained':True}}
    require(click_case(t,'quests.reward_confirm','Complete the quest and receive the chosen reward.',
        lambda c:c['name']=='QuestFrameCompleteQuestButton',rewarded),'quest_reward_pass')
    t.clean_panels();t.execute({'kind':'key','value':'b'});state,frame=t.observe('reward_received_bag')
    now=inventory();new=[r for r in now['items'] if r[0]==1 and r[4] in [chosen['id']]+[x['id'] for x in offered['fixed']]]
    visible=all(r[1]==0 and 23<=r[2]<39 and any(x.get('bag')==0 and x.get('slot')==r[2]-22 and
        x.get('id')==r[4] and x.get('count')==r[5] for x in state.get('bag_items',[])) for r in new)
    t.receipt['received_rewards']={'native':new,'public':state.get('bag_items'),'frame':frame,'passed':visible};t.persist()
    if not new or not visible:raise RuntimeError('earned reward items are absent from the normal backpack observation')
    return 'reward_retained'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--review-point-file',type=Path,required=True);p.add_argument('--reward-point-file',type=Path,required=True);a=p.parse_args()
    if a.review_point_file.exists() or a.reward_point_file.exists():p.error('point reviews must be fresh for their staged frames')
    t=Trial(a.output,controller='code')
    try:
        accept_suite(t,a.review_point_file,False,after_read=lambda t,g:reward(t,g,a.reward_point_file),retain_reward=True,exercise_log=False)
        t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
