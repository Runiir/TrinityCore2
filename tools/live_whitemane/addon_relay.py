"""Decode only the own addon's self-addressed public telemetry. No chat export."""
import base64
import json
import struct
import time
from . import snapshot
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.observation.telemetry import decode_packet, checksum, PACKET

PREFIX=b'WMLF1'
LIVE=struct.Struct('>2sHHIIIH')


def movement_packet(data):
    if len(data)!=PACKET.size+LIVE.size:raise ValueError('relay movement length changed')
    movement=decode_packet(data[:PACKET.size])
    magic,flags,instance,north,west,height,check=LIVE.unpack_from(data,PACKET.size)
    if magic!=b'W1' or flags & ~511 or checksum(data[:-2])!=check:
        raise ValueError('relay movement extension failed checksum or layout')
    live={name:bool(flags&mask) for name,mask in [('mounted',1),('flying',2),('casting',4),
        ('loot_open',8),('falling',16),('swimming',32),('can_survey',256)]}
    live['world']={'instance':instance,'north':north/100-100000,'west':west/100-100000} if flags&64 else None
    live['altitude_yards']=height/100-100000 if flags&128 else None
    live['grounded']=not (live['flying'] or live['falling'] or live['swimming'])
    movement['live_archaeology']=live
    return movement


def targeted(payload,player=None):
    r=Reader(payload);prefix_size=r.bits(5);text_size=r.bits(8);logged=r.bits(1)
    try:r.unpack('i');prefix=r.raw(prefix_size);text=r.raw(text_size)
    except ValueError as error:
        raise ValueError(f'addon parameters truncated: bytes={len(payload)} prefix={prefix_size} text={text_size}') from error
    if prefix!=PREFIX:return None
    if logged:raise ValueError('relay must not enter chat logging')
    try:channel=r.guid();recipient=r.guid();r.unpack('I')
    except ValueError as error:
        raise ValueError(f'own relay recipient GUID fields truncated: bytes={len(payload)} position={r.pos}') from error
    # This owned 60895 client uses nine-bit dynamic target-name lengths.
    # Seven-bit parsing reports name=1/channel=96 with only eight bytes left;
    # nine-bit parsing restores the exact self name and packet boundary.
    name_size=r.bits(9);channel_size=r.bits(9)
    try:
        name=r.raw(name_size).rstrip(b'\0') if name_size>1 else b''
        channel_name=r.raw(channel_size).rstrip(b'\0') if channel_size>1 else b''
    except ValueError as error:
        raise ValueError(f'own relay recipient names truncated: name={name_size} channel={channel_size} remaining={len(payload)-r.pos}') from error
    r.end()
    named_self=name.split(b'-')[0]==b'Runiir'
    guid_self=player is not None and recipient==player
    if channel!=(0,0) or channel_name or (name and not named_self) or not (named_self or guid_self):
        raise ValueError('relay is not self-addressed to Runiir')
    if recipient!=(0,0) and (player is None or recipient!=player):
        raise ValueError('relay recipient is not the owned character')
    return text.decode('ascii')


class Assembler:
    def __init__(self):self.pending={};self.channels={};self.rejected=0

    def packet(self,text,at):
        kind,sequence,part,total,payload=text.split('|',4)
        sequence,part,total=map(int,(sequence,part,total))
        if kind not in ('M','A','U','F') or not 0<=sequence<2**32 or not 1<=part<=total<=120 or len(payload)>200:
            raise ValueError('relay fragment exceeds public telemetry bounds')
        self.pending={k:v for k,v in self.pending.items() if at-v['at']<15}
        key=(kind,sequence)
        if key not in self.pending and len(self.pending)>=8:
            del self.pending[min(self.pending,key=lambda k:self.pending[k]['at'])]
        job=self.pending.setdefault(key,{'at':at,'total':total,'parts':{}})
        if job['total']!=total or (part in job['parts'] and job['parts'][part]!=payload):
            raise ValueError('relay fragments disagree')
        job['parts'][part]=payload
        if len(job['parts'])!=total:return False
        value=base64.b64decode(''.join(job['parts'][i] for i in range(1,total+1)),validate=True)
        del self.pending[key]
        if len(value)>16384:raise ValueError('relay message exceeds public UI capacity')
        if kind=='M':value=movement_packet(value)
        elif kind=='A':value=snapshot.decode(value)
        else:
            value=json.loads(value)
            if not isinstance(value,dict) or value.get('observer_error'):raise ValueError('relay public UI is unavailable')
        old=self.channels.get(kind)
        if old and not 0<(sequence-old['sequence'])%2**32<2**31:return False
        self.channels[kind]={'sequence':sequence,'observed_at':job['at'],'value':value}
        return True

    def state(self,runtime,reader):
        return {'runtime':runtime,'reader_pid':reader['pid'],'reader_start_ticks':reader['start_ticks'],
            'source':'normal_public_addon_api_self_addressed_relay','channels':self.channels}


def observation(owner,root,now=None):
    """Verify fresh own-process public facts and a fully received UI generation."""
    from .runtime import proc_start
    now=time.time() if now is None else now
    state=json.loads((root/'run/addon_state.json').read_text())
    feed=json.loads((root/'run/bearing_reader.json').read_text())
    if (state['runtime']!=owner or feed['status']!='ready' or state['reader_pid']!=feed['pid']
            or state['reader_start_ticks']!=feed['start_ticks'] or proc_start(feed['pid'])!=feed['start_ticks']):
        raise ValueError('direct addon relay is not the current owned reader')
    channels=state['channels']
    for kind,limit in [('M',.75),('A',2),('F',2)]:
        if kind not in channels or not 0<=now-channels[kind]['observed_at']<=limit:
            raise ValueError('direct addon relay has stale '+kind+' facts')
    movement=dict(channels['M']['value']);archaeology=dict(channels['A']['value'])
    skew=(movement['client_uptime_ms']-archaeology['client_uptime_ms']+2**31)%2**32-2**31
    if abs(skew)>1500:
        raise ValueError('direct movement and archaeology generations disagree')
    archaeology.update(movement.pop('live_archaeology'))
    ui=None;fast=channels['F']['value'];slow=channels.get('U')
    if slow and slow['sequence']==fast.get('ui_version'):
        ui={**slow['value'],**fast,'sequence':slow['sequence'],'source':state['source']}
    movement['source']=state['source']
    return {'observed_at':now,'runtime':owner,'movement':movement,'archaeology':archaeology,
        'farm_ui':ui,'farm_ui_error':None if ui else 'waiting for complete UI generation',
        'source':state['source'],'frame':None,'server':'Whitemane live realm',
        'channel_ages':{key:now-value['observed_at'] for key,value in channels.items()},'owned_pose':None}


def main():
    import argparse
    from . import runtime
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true')
    args=parser.parse_args()
    runtime.monitor();owner=runtime.owned_process()
    if owner is None:raise RuntimeError('owned client is absent')
    row=observation(owner,runtime.ROOT)
    if row['farm_ui'] is None:raise RuntimeError('wait for a complete public UI generation')
    if args.activate:
        runtime.write(runtime.ROOT/'run/observation_mode.json',{'transport':'addon_relay',
            'activated_at':time.time(),'runtime':owner,'reader_pid':json.loads(
                (runtime.ROOT/'run/bearing_reader.json').read_text())['pid']})
    print(json.dumps({'source':row['source'],'channel_ages':row['channel_ages'],
        'runtime_pid':owner['pid'],'screenshots_required':False,'activated':args.activate}))


if __name__=='__main__':main()
