"""Stream actual single-Tame packet journals without admitting an interaction."""
import argparse,hashlib,json,time
from pathlib import Path
from . import lab_runtime as lab
from .observation.journal import entries
from .world.buffer import Reader,player_high
from .world.objects import native_guid


def require(value,message):
    if not value:raise RuntimeError(message)


def review(directory,output):
    directory=directory.resolve();output=output.resolve()
    require(directory.parent==lab.ROOT/'evidence' and output.parent==directory and not output.exists(),
        'requires a new review in the owned open batch')
    source=directory/'hunter_tame_cast01/episode.json';cast=json.loads(source.read_text())
    entry=json.loads((directory/'hunter_tame_entry01/episode.json').read_text())
    closure=json.loads((directory/'hunter_tame_success_close01/episode.json').read_text())
    require(cast.get('completed') is True and cast.get('failure') is None and
        len(cast.get('capture_checks',{}))==14 and all(cast['capture_checks'].values()) and
        closure.get('completed') is True and closure.get('failure') is None and
        len(closure.get('checks',{}))==20 and all(closure['checks'].values()) and
        cast.get('capture_disarmed') is True and cast.get('qualification_added') is False,
        'requires the whole diagnostic and parked closure')
    since=cast['capture_config']['created_at'];until=cast['finished_at'];session=cast['native_session']
    journal=lab.ROOT/'logs/modern_world.jsonl'
    instances={r['session'] for r in entries(journal) if r.get('event')=='instance_authenticated' and
        r.get('account_id')==2 and entry['started_at']<=r.get('time',0)<=entry['finished_at']}
    require(len(instances)==1,'fresh owned instance is absent or ambiguous')
    raw=[r for r in entries(lab.ROOT/'evidence/owned_tame_request_packets.jsonl') if
        r.get('session')==session and since<=r.get('time',0)<=until]
    require(raw==cast.get('capture_packets'),'actual private channel journal differs')
    expected={('from_native','MSG_CHANNEL_START'),('from_native','MSG_CHANNEL_UPDATE'),
        ('to_client','SMSG_SPELL_CHANNEL_START'),('to_client','SMSG_SPELL_CHANNEL_UPDATE')}
    require(len(raw)==4 and {(r['direction'],r['name']) for r in raw}==expected,
        'requires exactly four actual owned channel payloads')
    names={r['name'] for r in raw}|{'SMSG_PET_ADDED'}
    metadata=[r for r in entries(journal) if r.get('session') in {session}|instances and
        since<=r.get('time',0)<=until and r.get('event') in ('native_packet','modern_packet') and
        r.get('name') in names]
    for packet in raw:
        matches=[r for r in metadata if (r.get('name'),r.get('direction'),r.get('bytes'))==
            (packet['name'],packet['direction'],len(bytes.fromhex(packet['body']))) and
            0<=packet['time']-r['time']<.1]
        require(len(matches)==1,'actual native/modern channel metadata pair differs')
        reader=Reader(bytes.fromhex(packet['body']));native=packet['direction']=='from_native'
        require((native_guid(reader)==6 if native else reader.guid()==(6,player_high())),
            'actual channel owner differs')
        if packet['name'].endswith('START'):
            require(reader.unpack('i')[0]==1515,'actual channel spell differs')
            if not native:require(reader.unpack('I')[0]==238368,'actual channel visual differs')
            require(reader.unpack('I')[0]==10000,'actual channel duration differs')
            require((reader.unpack('BB')==(0,0) if native else reader.bits(1)==reader.bits(1)==0),
                'actual channel optional flags differ')
        else:require(reader.unpack('I')[0]==0,'actual channel did not stop')
        reader.end()
    added=[r for r in metadata if r['name']=='SMSG_PET_ADDED']
    require(len(added)==1 and (added[0]['event'],added[0]['direction'],added[0]['bytes'])==
        ('native_packet','from_native',23),'expected untranslated PetAdded metadata differs')
    samples=cast['public_channel_samples']
    require(len(samples)==8 and all(s['player_channel'].get('active') is True for s in samples[:-1]) and
        samples[-1]['player_channel'].get('active') is False,'actual public channel samples differ')
    events=samples[-1]['player_channel']['events']
    require([e['event'] for e in events]==['UNIT_SPELLCAST_CHANNEL_START','UNIT_SPELLCAST_CHANNEL_STOP'] and
        all(e['spell']==1515 for e in events) and 9.8<events[1]['observed_at']-events[0]['observed_at']<10.2,
        'actual public channel start/stop timing differs')
    for sample in samples:
        frame=sample['frame'];path=source.parent/frame['file'];m=frame['monitor']
        require(path.is_file() and lab.sha256(path)==frame['sha256'] and m['second_monitor_verified'] and
            m['input_isolation']['actor']=='scout' and m['input_isolation']['host_activation_sent'] is False,
            'actual owned channel frame attribution differs')
    lab.private_write(output,json.dumps({'schema':'client442_tame_diagnostic_local_review_v1',
        'reviewed_at':time.time(),'source':{'path':str(source),'sha256':lab.sha256(source)},
        'closure_source':{'path':str(directory/'hunter_tame_success_close01/episode.json'),
            'sha256':lab.sha256(directory/'hunter_tame_success_close01/episode.json')},
        'channel_packets':raw,'channel_metadata':metadata,'physical_instance':next(iter(instances)),
        'public_channel_samples':8,'public_channel_seconds':events[1]['observed_at']-events[0]['observed_at'],
        'new_pet_number':cast['native_pet_after']['fields']['69'],
        'missing':['actual native PetAdded body','modern PetAdded translation/delivery'],
        'inventory_admitted':False,'qualification_added':False,'input_sent':False},indent=2)+'\n')
    print(json.dumps({'completed':True,'actual_channel_packets':4,'metadata_records':len(metadata),
        'qualification_added':False}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();review(a.directory,a.output)
