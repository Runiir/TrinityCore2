"""Archive closed player-interaction evidence with DVCLive and push it to DVC."""
import argparse
import hashlib
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from dvclive import Live
from . import lab_runtime as lab
from .observation.journal import entries

SAFE_BODY_NAMES={
    'CMSG_MAIL_TAKE_ITEM','CMSG_MAIL_TAKE_MONEY',
    'CMSG_MAIL_MARK_AS_READ','CMSG_MAIL_DELETE','SMSG_SEND_MAIL_RESULT','SMSG_MAIL_COMMAND_RESULT',
    'CMSG_MAIL_GET_LIST','CMSG_GET_MAIL_LIST','SMSG_MAIL_LIST_RESULT','SMSG_SHOW_MAILBOX',
    'CMSG_QUERY_NEXT_MAIL_TIME','MSG_QUERY_NEXT_MAIL_TIME','SMSG_MAIL_QUERY_NEXT_TIME_RESULT',
    'SMSG_RECEIVED_MAIL','SMSG_NOTIFY_RECEIVED_MAIL',
    'CMSG_LIST_INVENTORY','SMSG_VENDOR_INVENTORY',
    'CMSG_REPAIR_ITEM','CMSG_TRAINER_LIST','CMSG_TRAINER_BUY_SPELL',
    'SMSG_TRAINER_LIST','SMSG_TRAINER_BUY_FAILED','SMSG_TRAINER_BUY_SUCCEEDED',
    'SMSG_LEARNED_SPELL','SMSG_LEARNED_SPELLS',
    'CMSG_QUERY_QUEST_INFO','SMSG_QUERY_QUEST_INFO_RESPONSE','CMSG_QUEST_GIVER_HELLO','CMSG_QUEST_GIVER_QUERY_QUEST',
    'SMSG_QUEST_QUERY_RESPONSE',
    'CMSG_QUEST_GIVER_ACCEPT_QUEST','CMSG_QUEST_LOG_REMOVE_QUEST',
    'SMSG_QUEST_GIVER_QUEST_DETAILS','SMSG_QUEST_GIVER_QUEST_LIST_MESSAGE',
    'CMSG_BUY_ITEM','SMSG_BUY_ITEM','SMSG_BUY_SUCCEEDED','SMSG_BUY_FAILED','SMSG_ITEM_PUSH_RESULT',
    'CMSG_SELL_ITEM','SMSG_SELL_ITEM','SMSG_SELL_RESPONSE','CMSG_BUY_BACK_ITEM','CMSG_BUYBACK_ITEM',
    'CMSG_BANKER_ACTIVATE','SMSG_SHOW_BANK','SMSG_NPC_INTERACTION_OPEN_RESULT',
    'CMSG_AUTOBANK_ITEM','CMSG_AUTOSTORE_BANK_ITEM','CMSG_CLOSE_INTERACTION',
    'CMSG_INSPECT','SMSG_INSPECT_TALENT','SMSG_INSPECT_RESULT',
    'CMSG_INITIATE_TRADE','CMSG_BEGIN_TRADE','CMSG_CANCEL_TRADE','CMSG_ACCEPT_TRADE','CMSG_BUSY_TRADE',
    'CMSG_IGNORE_TRADE','CMSG_UNACCEPT_TRADE','CMSG_SET_TRADE_GOLD','CMSG_SET_TRADE_ITEM','CMSG_CLEAR_TRADE_ITEM',
    'SMSG_TRADE_STATUS','SMSG_TRADE_UPDATED',
    'CMSG_QUERY_GUILD_INFO','CMSG_GUILD_QUERY','CMSG_GUILD_GET_ROSTER',
    'CMSG_GUILD_INVITE_BY_NAME','CMSG_GUILD_INVITE','SMSG_GUILD_INVITE',
    'CMSG_ACCEPT_GUILD_INVITE','CMSG_GUILD_ACCEPT','CMSG_GUILD_DECLINE_INVITATION','CMSG_GUILD_DECLINE',
    'CMSG_CHAT_MESSAGE_SAY','CMSG_CHAT_MESSAGE_YELL','CMSG_CHAT_MESSAGE_PARTY','CMSG_CHAT_MESSAGE_RAID',
    'CMSG_CHAT_MESSAGE_RAID_WARNING','CMSG_CHAT_MESSAGE_WHISPER','CMSG_CHAT_MESSAGE_EMOTE',
    'CMSG_MESSAGECHAT_SAY','CMSG_MESSAGECHAT_YELL','CMSG_MESSAGECHAT_PARTY','CMSG_MESSAGECHAT_RAID',
    'CMSG_MESSAGECHAT_RAID_WARNING','CMSG_MESSAGECHAT_WHISPER','CMSG_MESSAGECHAT_EMOTE','SMSG_CHAT','SMSG_MESSAGECHAT',
    'SMSG_DESTROY_OBJECT','SMSG_SEND_KNOWN_SPELLS','SMSG_UPDATE_ACTION_BUTTONS',
    'CMSG_LOG_DISCONNECT','CMSG_LOGOUT_REQUEST','CMSG_LOGOUT_CANCEL','SMSG_LOGOUT_RESPONSE','SMSG_LOGOUT_COMPLETE','SMSG_LOGOUT_CANCEL_ACK',
    'CMSG_ENUM_CHARACTERS','SMSG_ENUM_CHARACTERS_RESULT','CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD',
    'CMSG_SWAP_INV_ITEM','CMSG_SWAP_ITEM','CMSG_SPLIT_ITEM','CMSG_AUTO_EQUIP_ITEM','CMSG_AUTOEQUIP_ITEM',
    'CMSG_AUTO_EQUIP_ITEM_SLOT','CMSG_AUTOEQUIP_ITEM_SLOT','CMSG_AUTO_STORE_BAG_ITEM','CMSG_AUTOSTORE_BAG_ITEM','SMSG_INVENTORY_CHANGE_FAILURE',
    'CMSG_CAST_SPELL','SMSG_SPELL_PREPARE','SMSG_SPELL_START','SMSG_SPELL_GO','SMSG_CAST_FAILED',
    'CMSG_CLEAR_RAID_MARKER','SMSG_RAID_MARKERS_CHANGED','SMSG_UPDATE_OBJECT',
    'CMSG_SEND_CONTACT_LIST','CMSG_CONTACT_LIST','CMSG_ADD_FRIEND','CMSG_DEL_FRIEND',
    'CMSG_SET_CONTACT_NOTES','CMSG_ADD_IGNORE','CMSG_DEL_IGNORE','SMSG_CONTACT_LIST','SMSG_FRIEND_STATUS',
    'CMSG_QUERY_PLAYER_NAMES','SMSG_QUERY_PLAYER_NAMES_RESPONSE','CMSG_QUERY_REALM_NAME','SMSG_REALM_QUERY_RESPONSE',
    'CMSG_PARTY_INVITE','CMSG_PARTY_INVITE_RESPONSE','CMSG_PARTY_UNINVITE','CMSG_LEAVE_GROUP',
    'CMSG_GROUP_DISBAND','CMSG_CONVERT_RAID','CMSG_GROUP_RAID_CONVERT','CMSG_SET_PARTY_LEADER',
    'CMSG_GROUP_SET_LEADER','CMSG_GROUP_UNINVITE_GUID','SMSG_PARTY_UPDATE','SMSG_PARTY_INVITE',
    'SMSG_PARTY_COMMAND_RESULT','SMSG_GROUP_DECLINE','CMSG_DO_READY_CHECK','CMSG_READY_CHECK_RESPONSE',
    'MSG_RAID_READY_CHECK','MSG_RAID_READY_CHECK_CONFIRM','SMSG_READY_CHECK_STARTED','SMSG_READY_CHECK_RESPONSE',
    'SMSG_READY_CHECK_COMPLETED','SMSG_INITIALIZE_FACTIONS','SMSG_SET_FACTION_STANDING',
    'CMSG_REQUEST_PARTY_MEMBER_STATS','SMSG_PARTY_MEMBER_FULL_STATE','SMSG_PARTY_MEMBER_STATE',
    'CMSG_SAVE_CUF_PROFILES','SMSG_LOAD_CUF_PROFILES',
    'CMSG_SET_EVERYONE_IS_ASSISTANT','CMSG_SET_ASSISTANT_LEADER','CMSG_GROUP_ASSISTANT_LEADER',
    'CMSG_INITIATE_ROLE_POLL','CMSG_ROLE_POLL_BEGIN','CMSG_SET_ROLE','SMSG_ROLE_POLL_BEGIN','SMSG_ROLE_POLL_INFORM','SMSG_ROLE_CHANGED_INFORM',
    'SMSG_SET_FACTION_VISIBLE','CMSG_SET_FACTION_AT_WAR','CMSG_SET_FACTION_NOT_AT_WAR',
    'CMSG_SET_FACTION_INACTIVE','CMSG_SET_WATCHED_FACTION','CMSG_SET_ACTION_BUTTON',
    'SMSG_ALL_ACHIEVEMENT_DATA','SMSG_CRITERIA_UPDATE','SMSG_ACHIEVEMENT_EARNED'}


def checkpoint(directory,name):
    directory=directory.resolve()
    if directory.parent!=lab.ROOT/'evidence' or not re.fullmatch(r'[A-Za-z0-9_]+',name):
        raise ValueError('checkpoint requires a named private lab evidence directory')
    if subprocess.check_output(['git','status','--porcelain'],cwd=lab.REPO,text=True):
        raise RuntimeError('commit experiment code/configuration before checkpointing')
    episodes=[]
    for path in sorted(directory.rglob('episode.json')):
        run=json.loads(path.read_text())
        if not run.get('finished_at'):raise RuntimeError('open interaction run: '+str(path))
        episodes.append((path,run))
    for path in directory.rglob('cohort.json'):
        if not json.loads(path.read_text()).get('finished_at'):raise RuntimeError('open cohort: '+str(path))
    if not episodes:raise RuntimeError('no closed interaction episodes')
    since=min(r['started_at'] for _,r in episodes)
    cases=[c for _,r in episodes for c in r['cases']]
    counts=Counter(c['status'] for c in cases)
    native=lab.owned_process('worldserver');before=json.loads((directory/'native_server_before.json').read_text())
    if (native['pid'],native['start_ticks'])!=(before['pid'],before['start_ticks']):
        raise RuntimeError('native server identity changed during this experiment')
    target=lab.REPO/'artifacts/client_harness'/(name+'.tar.gz');pointer=str(target.relative_to(lab.REPO))+'.dvc'
    if target.exists() or (lab.REPO/pointer).exists():raise RuntimeError('checkpoint name already exists')
    metadata={'schema':'client442_interaction_checkpoint_v1','since':since,'counts':dict(counts),
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'native_worldserver':native,'native_worldserver_restarted':False,
        'native_binary_sha256':lab.sha256(lab.ROOT/'bin/worldserver'),
        'bridge_build':json.loads((lab.ROOT/'build/native_bridge/build_receipt.json').read_text()),
        'runs':[{'path':str(p.relative_to(lab.ROOT)),'completed':r['completed'],'failure':r['failure'],
            'controller':r['controller'],'model':r['model'],'revision':r['revision']} for p,r in episodes],
        'limits':['Panel visibility passes do not qualify panel contents or mutations.',
            'The base text-only Laya selects bounded input candidates; this is not open-ended screenshot autonomy.',
            'Counts include historical failures and retries; they are not unique qualified feature counts.',
            'The 891-operation plan and 275-binding catalog remain broader than the completed trials.'],
        'excluded':['credentials','authentication bodies','account-cache bodies','DB contents','Wine/CASC caches']}
    paths=[directory,lab.ROOT/'reference/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2',lab.ROOT/'reference/ui-442',
        lab.ROOT/'build/native_bridge/build_receipt.json',lab.ROOT/'build/native_bridge_asan/build_receipt.json',
        lab.ROOT/'build/native_bridge/client442_bridge',lab.ROOT/'build/native_bridge/bridge_codec']
    manifest=[]
    for path in paths:
        for file in sorted(path.rglob('*')) if path.is_dir() else [path]:
            if not file.is_file():continue
            if file.is_symlink() or any(x in file.parts for x in ['secrets','WTF','wineprefix','Cache']):
                raise RuntimeError('inadmissible artifact path')
            manifest.append({'path':str(file.relative_to(lab.ROOT)),'bytes':file.stat().st_size,'sha256':lab.sha256(file)})
    metadata['files']=manifest
    with tempfile.TemporaryDirectory(dir=lab.ROOT/'run') as folder:
        folder=Path(folder)
        for source,label in [(lab.ROOT/'logs/modern_world.jsonl','events.jsonl'),(lab.ROOT/'evidence/world_packets.jsonl','packets.jsonl')]:
            with (folder/label).open('w') as output:
                for row in entries(source):
                    if row.get('time',0)<since:continue
                    if 'body' in row and row.get('name') not in SAFE_BODY_NAMES:continue
                    output.write(json.dumps(row,separators=(',',':'))+'\n')
        (folder/'checkpoint.json').write_text(json.dumps(metadata,indent=2)+'\n')
        with Live(dir=str(folder/'live'),save_dvc_exp=False,dvcyaml=False,report=None) as live:
            live.log_param('code_commit',metadata['code_commit']);live.log_param('controller','attributed_interaction_trials')
            live.log_metric('closed_runs',len(episodes));live.log_metric('model_choices_executed',sum(bool(c.get('response')) and 'selected' in c for c in cases))
            for status,count in counts.items():live.log_metric('case_status/'+status,count)
            live.log_metric('native_worldserver_restarts',0);live.log_metric('whole_game_qualified',0);live.next_step()
        with tarfile.open(target,'w:gz',compresslevel=3) as archive:
            for path in paths:
                if path.exists():archive.add(path,arcname=str(path.relative_to(lab.ROOT)))
            archive.add(folder,arcname='tracking')
    relative=str(target.relative_to(lab.REPO))
    with tarfile.open(target,'r:gz') as archive:
        for record in manifest:
            with archive.extractfile(record['path']) as file:
                digest=hashlib.file_digest(file,'sha256').hexdigest()
            if digest!=record['sha256']:raise RuntimeError('checkpoint archive hash mismatch: '+record['path'])
    for command in [['dvc','add',relative],['dvc','status',pointer],['dvc','push',pointer]]:
        subprocess.run(command,cwd=lab.REPO,check=True)
    cloud=json.loads(subprocess.check_output(['dvc','status','--cloud','--json',pointer],cwd=lab.REPO,text=True))
    if cloud:raise RuntimeError('checkpoint is not synchronized with the DVC remote')
    lab.private_write(directory/'checkpoint_receipt.json',json.dumps({'file':relative,'sha256':lab.sha256(target),
        'bytes':target.stat().st_size,'cloud_verified':True,'file_manifest':manifest},indent=2)+'\n')
    print(json.dumps({'pointer':pointer,'bytes':target.stat().st_size,'sha256':lab.sha256(target)}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--name',required=True)
    a=p.parse_args();checkpoint(a.directory,a.name)


if __name__=='__main__':main()
