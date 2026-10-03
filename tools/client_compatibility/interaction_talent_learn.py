"""Choose Arms and learn one first-tier talent through stock UI; retain it."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,point
from .interaction_macros import require
from .interaction_trade import inventory
from .interaction_talents import native_state,detail
from .observation.transport import Observer
from .observation.journal import entries


def native_talent(talent_id):
    path=lab.ROOT/'data/dbc/enUS/Talent.dbc';data=path.read_bytes()
    magic,count,fields,width,strings=struct.unpack_from('<4s4I',data)
    if magic!=b'WDBC' or fields!=19 or width!=76 or len(data)!=20+count*width+strings:
        raise RuntimeError('native talent catalog schema changed')
    matches=[struct.unpack_from('<19I',data,20+i*width) for i in range(count)
        if struct.unpack_from('<I',data,20+i*width)[0]==talent_id]
    if len(matches)!=1 or matches[0][1]!=746 or matches[0][2]!=0 or not matches[0][4]:
        raise RuntimeError('ordinary request is not one native Arms first-tier talent')
    return matches[0],lab.sha256(path)


def learned(t,start,session,selected):
    requests=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('time',0)>=start and
        p.get('session')==session and p.get('name') in ['CMSG_LEARN_PREVIEW_TALENTS','CMSG_LEARN_TALENT']]
    modern=[p for p in requests if p['direction']=='from_client'];native=[p for p in requests if p['direction']=='to_native']
    valid=len(modern)==len(native)==1;talent_id=None;rank=None;catalog=None;digest=None
    if valid:
        m,n=modern[0],native[0];mb=bytes.fromhex(m['body']);nb=bytes.fromhex(n['body'])
        if m['name']=='CMSG_LEARN_PREVIEW_TALENTS':
            count,tree,talent_id,rank=struct.unpack('<IiII',mb)
            tab,ncount,nid,nrank=struct.unpack('<iIII',nb)
            valid=count==ncount==1 and tree==tab and tree in [-1,0] and (talent_id,rank)==(nid,nrank)
        else:
            talent_id,rank=struct.unpack('<IH',mb);valid=nb==struct.pack('<II',talent_id,rank)
        valid=valid and rank==0
        catalog,digest=native_talent(talent_id)
    state=native_state();probe=detail(t,'learned_talent');ranks=probe.get('ranks',[])
    rank_agrees=any(x[0:3]==selected[0:3] and x[3]==1 for x in ranks)
    passed=(valid and catalog is not None and state['character'][0].split()==['746','0'] and
        state['talents']==((catalog[4],0),) and probe.get('primary')==1 and probe.get('unspent')==40 and rank_agrees)
    return {'status':'talent_learn_pass' if passed else 'client_or_protocol_failure',
        'oracle':{'native':state,'public':probe,'requests':requests,'rank_display_agrees':rank_agrees,
            'native_catalog_row':catalog,'native_catalog_sha256':digest,'earned_talent_retained':True}}


def suite(t):
    actors.session_entry(t.fixture);t.clean_panels();before=native_state();items=inventory()
    if before['character'][0].split()!=['0','0'] or before['character'][1:]!=(1,0) or before['talents']:
        raise RuntimeError('requires the unallocated native primary warrior')
    t.receipt['baseline']={'talents':before,'inventory_money':items};t.persist()
    try:
        require(t.step('talents.learn_open','Open talents.',
            {'open':{'kind':'key','value':'n','description':'Press the installed N talent binding.'}},
            lambda b,a,s:{'status':'talents_open_pass' if s=='open' and 'PlayerTalentFrame' in a['panels'] else
                'client_or_protocol_failure'},diagnostic_action='open'),'talents_open_pass')
        require(click_case(t,'talents.learn_tab','View warrior talents.',
            lambda c:c['name']=='PlayerTalentFrameTab1',
            lambda b,a,s:{'status':'talent_panel_pass' if s and a.get('talent_probe',{}).get('selected')==1 else
                'client_or_protocol_failure'}),'talent_panel_pass')
        initial=detail(t,'before_specialization');preview=initial.get('preview_option')
        if type(preview)is not bool:raise RuntimeError('stock talent preview preference is not observed')
        def chose(b,a,s):
            p=detail(t,'chosen_specialization');native=native_state()
            passed=(s and ((preview and p.get('preview_primary')==1 and native==before) or
                (not preview and p.get('primary')==1 and native['character'][0].split()==['746','0'])))
            return {'status':'talent_specialization_pass' if passed else 'client_or_protocol_failure',
                'oracle':{'public':p,'native':native,'preview_only':preview}}
        require(click_case(t,'talents.choose_arms','Choose Arms for the warrior.',
            lambda c:c['name']=='PlayerTalentFramePanel1SelectTreeButton' and c['text']=='Arms',chose),
            'talent_specialization_pass')
        probe=detail(t,'first_tier_choices');choices=[x for x in probe.get('ranks',[]) if x[0]==1 and x[3]==0 and x[4]>0]
        if not choices:raise RuntimeError('public Arms first-tier choices are absent')
        selected=choices[0];name='PlayerTalentFramePanel1Talent'+str(selected[1]);t.receipt['selected_talent']=selected;t.persist()
        start=time.time();session=Observer(guid=1).poll()['session']
        def picked(b,a,s):
            if not preview:return learned(t,start,session,selected)
            p=detail(t,'preview_talent');passed=s and native_state()==before and p.get('preview_primary')==1 and any(
                x[0:3]==selected[0:3] and x[3]==0 and x[5]==1 for x in p.get('ranks',[]))
            return {'status':'talent_preview_pass' if passed else 'client_or_protocol_failure',
                'oracle':{'public':p,'native_unchanged':native_state()==before}}
        require(click_case(t,'talents.first_point','Allocate one point to '+str(selected[2])+'.',
            lambda c:c['name']==name,picked),'talent_preview_pass' if preview else 'talent_learn_pass')
        if preview:
            require(click_case(t,'talents.learn_preview','Learn the selected specialization and single talent.',
                lambda c:c['name']=='PlayerTalentFrameLearnButton',
                lambda b,a,s:{'status':'talent_confirm_open_pass' if s and any(p.get('which')=='CONFIRM_LEARN_PREVIEW_TALENTS'
                    for p in detail(t,'learn_confirmation').get('popups',[])) else 'client_or_protocol_failure'}),
                'talent_confirm_open_pass')
            require(click_case(t,'talents.confirm_preview','Confirm learning the selected talents.',
                lambda c:c['name']=='StaticPopup1Button1' and c['text']=='Yes',
                lambda b,a,s:learned(t,start,session,selected) if s else {'status':'controller_failure'}),'talent_learn_pass')
        earned=native_state();t.receipt['earned_talent']=earned;t.persist();t.clean_panels()
        t.execute({'kind':'chat','value':'/reload'});t.execute({'kind':'key','value':'n'})
        after=detail(t,'learned_after_reload');retained=native_state()==earned and after.get('primary')==1 and after.get('unspent')==40 and any(
            x[0:3]==selected[0:3] and x[3]==1 for x in after.get('ranks',[]))
        t.receipt['persistence_oracle']={'passed':retained,'public':after,'native':native_state(),
            'scope':'ordinary addon reload; logout/login persistence remains open'};t.persist()
        if not retained:raise RuntimeError('ordinary reload did not retain learned Arms talent')
    finally:
        t.clean_panels();t.receipt['restoration']={'inventory_money_unchanged':inventory()==items,
            'native_talent_after':native_state(),'learned_state_preserved':True};t.persist()
        if not t.receipt['restoration']['inventory_money_unchanged']:raise RuntimeError('talent trial changed inventory or money')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
