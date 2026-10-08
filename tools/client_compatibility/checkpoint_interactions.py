"""Archive closed player-interaction evidence with DVCLive and push it to DVC."""
import argparse
import hashlib
from collections import Counter
import json
import math
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from . import lab_runtime as lab
from .observation.journal import entries
from .interaction_metrics import choice_counts
from .native_input.control import verified as verified_input
from .archive_integrity import archive_digest,unchanged_archive
from .hunter_rest_accrual import precision_source

REST_PRECISION_SCHEMA='client442_owned_hunter_readonly_rest_precision_v1'


def checkpoint_runs(episodes,directory):
    """Separate the one known read-only diagnostic from attributed Trial cases."""
    cases=[];runs=[];trials=[]
    for path,run in episodes:
        relative=str(path.relative_to(lab.ROOT))
        if run.get('schema')==REST_PRECISION_SCHEMA:
            fields={'schema','phase','completed','started_at','finished_at','input_sent','mutation_sent',
                'qualification_added','query','row','sources','before','after','checks'}
            if set(run)!=fields:
                raise RuntimeError('readonly rest precision diagnostic fields differ')
            if (not all(type(run[k]) in (int,float) and math.isfinite(run[k]) for k in ('started_at','finished_at')) or
                not 0<run['started_at']<run['finished_at']):
                raise RuntimeError('readonly rest precision diagnostic closed timestamps differ')
            for ref in run['sources']:
                source=Path(ref['path'])
                if source.is_symlink() or not source.resolve().is_relative_to(directory.resolve()):
                    raise RuntimeError('readonly rest precision source is outside the archived batch')
            for key,snapshot in run['before'].items():
                if (set(snapshot)!={'native','saved','pets','inventory'} or
                    snapshot['native'].get('guid')!=int(key) or not isinstance(snapshot['saved'],dict) or
                    not isinstance(snapshot['pets'],list) or not isinstance(snapshot['inventory'],list)):
                    raise RuntimeError('readonly rest precision offline snapshot shape differs')
            checked=precision_source(path,run['sources'][0],run['before']['6']['native'])
            if checked!=run:raise RuntimeError('readonly rest precision receipt changed during checkpoint validation')
            runs.append({'path':relative,'record_kind':'readonly_diagnostic','source_schema':REST_PRECISION_SCHEMA,
                'completed':True,'started_at':run['started_at'],'finished_at':run['finished_at'],
                'input_sent':False,'mutation_sent':False,'qualification_added':False,'operations_admitted':0,
                'cases':[],'checks':run['checks'],'sources':run['sources'],
                'receipt_sha256':lab.sha256(path)})
        else:
            # Preserve required ordinary Trial identity and case fields. Unknown
            # schemas never inherit the diagnostic's missing-field exemption.
            cases.extend(run['cases']);trials.append(run)
            runs.append({'path':relative,'completed':run['completed'],'failure':run['failure'],
                'controller':run['controller'],'model':run['model'],'revision':run['revision']})
    return cases,runs,trials


def tracking_live(**options):
    # Source classification and its tests do not require the publishing-only
    # DVCLive dependency; the actual checkpoint still requires it.
    # These checkpoints publish their exact artifact separately. Automatic
    # experiment saving scans and rewrites unrelated repository stages.
    if options.get('save_dvc_exp', False) is not False:
        raise ValueError('interaction tracking must disable automatic DVC experiment saving')
    options['save_dvc_exp'] = False
    from dvclive import Live
    return Live(**options)

SAFE_BODY_NAMES={
    'CMSG_LOADING_SCREEN_NOTIFY','CMSG_GET_ACCOUNT_CHARACTER_LIST',
    'SMSG_ON_MONSTER_MOVE',
    'SMSG_AURA_UPDATE','SMSG_AURA_UPDATE_ALL',
    'CMSG_CANCEL_AURA','CMSG_PET_CANCEL_AURA',
    'CMSG_PET_ACTION','CMSG_PET_ABANDON','CMSG_PET_SPELL_AUTOCAST','CMSG_PET_SET_ACTION',
    'CMSG_REQUEST_PET_INFO','CMSG_QUERY_PET_NAME','CMSG_PET_NAME_QUERY',
    'MSG_CHANNEL_START','MSG_CHANNEL_UPDATE','SMSG_SPELL_CHANNEL_START','SMSG_SPELL_CHANNEL_UPDATE','SMSG_PET_ADDED',
    'SMSG_PET_NAME_QUERY_RESPONSE','SMSG_QUERY_PET_NAME_RESPONSE','SMSG_PET_SPELLS','SMSG_PET_SPELLS_MESSAGE',
    'CMSG_WHO','SMSG_WHO',
    'CMSG_SAVE_EQUIPMENT_SET','CMSG_DELETE_EQUIPMENT_SET','CMSG_USE_EQUIPMENT_SET',
    'CMSG_EQUIPMENT_SET_SAVE','CMSG_EQUIPMENT_SET_DELETE','CMSG_EQUIPMENT_SET_USE',
    'CMSG_SHOWING_HELM','CMSG_SHOWING_CLOAK',
    'SMSG_EQUIPMENT_SET_LIST','SMSG_EQUIPMENT_SET_SAVED','SMSG_EQUIPMENT_SET_USE_RESULT',
    'SMSG_LOAD_EQUIPMENT_SET','SMSG_EQUIPMENT_SET_ID','SMSG_USE_EQUIPMENT_SET_RESULT',
    'CMSG_REQUEST_RESEARCH_HISTORY','SMSG_SETUP_RESEARCH_HISTORY','SMSG_RESEARCH_COMPLETE',
    'SMSG_SETUP_CURRENCY','SMSG_SET_CURRENCY','CMSG_SET_CURRENCY_FLAGS',
    'CMSG_QUEST_GIVER_STATUS_QUERY','CMSG_QUEST_GIVER_STATUS_MULTIPLE_QUERY','CMSG_QUEST_GIVER_STATUS_TRACKED_QUERY',
    'SMSG_QUEST_GIVER_STATUS','SMSG_QUEST_GIVER_STATUS_MULTIPLE','SMSG_QUEST_UPDATE_ADD_CREDIT','SMSG_QUEST_UPDATE_COMPLETE',
    'SMSG_UPDATE_TALENT_DATA','SMSG_TALENTS_INFO','CMSG_LEARN_TALENT','CMSG_LEARN_PREVIEW_TALENTS','CMSG_SET_PRIMARY_TALENT_TREE',
    'SMSG_ACTIVE_GLYPHS','CMSG_REMOVE_GLYPH',
    'CMSG_AUCTION_HELLO_REQUEST','MSG_AUCTION_HELLO','SMSG_AUCTION_HELLO_RESPONSE',
    'CMSG_AUCTION_LIST_BIDDED_ITEMS','CMSG_AUCTION_LIST_BIDDER_ITEMS','SMSG_AUCTION_BIDDER_LIST_RESULT',
    'SMSG_AUCTION_LIST_BIDDED_ITEMS_RESULT','CMSG_AUCTION_LIST_OWNED_ITEMS','CMSG_AUCTION_LIST_OWNER_ITEMS',
    'SMSG_AUCTION_OWNER_LIST_RESULT','SMSG_AUCTION_LIST_OWNED_ITEMS_RESULT',
    'CMSG_AUCTION_BROWSE_QUERY','CMSG_AUCTION_LIST_ITEMS','SMSG_AUCTION_LIST_RESULT','SMSG_AUCTION_LIST_BUCKETS_RESULT',
    'CMSG_AUCTION_LIST_ITEMS_BY_ITEM_ID','CMSG_AUCTION_LIST_ITEMS_BY_BUCKET_KEY','SMSG_AUCTION_LIST_ITEMS_RESULT',
    'CMSG_AUCTION_SELL_ITEM','CMSG_AUCTION_REMOVE_ITEM','CMSG_AUCTION_PLACE_BID','SMSG_AUCTION_COMMAND_RESULT',
    'CMSG_SEND_MAIL','CMSG_MAIL_RETURN_TO_SENDER',
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
    'CMSG_QUEST_GIVER_COMPLETE_QUEST','CMSG_QUEST_GIVER_REQUEST_REWARD','CMSG_QUEST_GIVER_CHOOSE_REWARD',
    'SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE','SMSG_QUEST_GIVER_QUEST_COMPLETE','SMSG_QUEST_GIVER_REQUEST_ITEMS',
    'SMSG_QUEST_GIVER_QUEST_DETAILS','SMSG_QUEST_GIVER_QUEST_LIST_MESSAGE',
    'CMSG_QUEST_GIVER_STATUS_QUERY','CMSG_QUEST_GIVER_STATUS_MULTIPLE_QUERY',
    'SMSG_QUEST_GIVER_STATUS','SMSG_QUEST_GIVER_STATUS_MULTIPLE',
    'CMSG_QUERY_CREATURE','CMSG_CREATURE_QUERY','SMSG_CREATURE_QUERY_RESPONSE','SMSG_QUERY_CREATURE_RESPONSE',
    'CMSG_QUERY_GAME_OBJECT','CMSG_GAMEOBJECT_QUERY','SMSG_GAMEOBJECT_QUERY_RESPONSE','SMSG_QUERY_GAME_OBJECT_RESPONSE',
    # Public static page text and the owned readable item's identity/position.
    'CMSG_READ_ITEM','SMSG_READ_ITEM_OK','SMSG_READ_ITEM_FAILED','SMSG_READ_ITEM_RESULT_OK','SMSG_READ_ITEM_RESULT_FAILED',
    'CMSG_QUERY_PAGE_TEXT','CMSG_PAGE_TEXT_QUERY','SMSG_PAGE_TEXT_QUERY_RESPONSE','SMSG_QUERY_PAGE_TEXT_RESPONSE',
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
    # Exact disposable channels, empty/fixed public fixture passwords, and
    # at most the two owned roster actors. The bridge checks packet boundaries.
    'CMSG_CHAT_JOIN_CHANNEL','CMSG_JOIN_CHANNEL','CMSG_CHAT_LEAVE_CHANNEL','CMSG_LEAVE_CHANNEL',
    'SMSG_CHANNEL_NOTIFY','SMSG_CHANNEL_NOTIFY_JOINED','SMSG_CHANNEL_NOTIFY_LEFT',
    'CMSG_CHAT_CHANNEL_LIST','CMSG_CHAT_CHANNEL_DISPLAY_LIST','CMSG_CHAT_CHANNEL_OWNER','SMSG_CHANNEL_LIST',
    'CMSG_CHAT_CHANNEL_PASSWORD','SMSG_USERLIST_ADD','SMSG_USERLIST_UPDATE','SMSG_USERLIST_REMOVE',
    'SMSG_DESTROY_OBJECT','SMSG_SEND_KNOWN_SPELLS','SMSG_UPDATE_ACTION_BUTTONS',
    'CMSG_LOG_DISCONNECT','CMSG_LOGOUT_REQUEST','CMSG_LOGOUT_CANCEL','SMSG_LOGOUT_RESPONSE','SMSG_LOGOUT_COMPLETE','SMSG_LOGOUT_CANCEL_ACK',
    'CMSG_ENUM_CHARACTERS','SMSG_ENUM_CHARACTERS_RESULT','CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD',
    'CMSG_SWAP_INV_ITEM','CMSG_SWAP_ITEM','CMSG_SPLIT_ITEM','CMSG_AUTO_EQUIP_ITEM','CMSG_AUTOEQUIP_ITEM',
    'CMSG_AUTO_EQUIP_ITEM_SLOT','CMSG_AUTOEQUIP_ITEM_SLOT','CMSG_AUTO_STORE_BAG_ITEM','CMSG_AUTOSTORE_BAG_ITEM','SMSG_INVENTORY_CHANGE_FAILURE',
    'CMSG_CAST_SPELL','CMSG_CANCEL_CAST','CMSG_USE_ITEM','SMSG_SPELL_PREPARE','SMSG_SPELL_START','SMSG_SPELL_GO','SMSG_CAST_FAILED',
    'SMSG_SPELL_FAILURE','SMSG_SPELL_FAILED_OTHER',
    'CMSG_ATTACK_SWING','CMSG_ATTACK_STOP','SMSG_ATTACK_START','SMSG_ATTACK_STOP',
    'SMSG_ATTACKSWING_NOTINRANGE','SMSG_ATTACKSWING_BADFACING','SMSG_ATTACKSWING_CANT_ATTACK',
    'SMSG_ATTACKSWING_DEADTARGET','SMSG_ATTACK_SWING_ERROR','SMSG_ATTACKER_STATE_UPDATE',
    'SMSG_SPELLNONMELEEDAMAGELOG','SMSG_SPELL_NON_MELEE_DAMAGE_LOG',
    'CMSG_CLEAR_RAID_MARKER','SMSG_RAID_MARKERS_CHANGED','SMSG_UPDATE_OBJECT',
    'CMSG_SEND_CONTACT_LIST','CMSG_CONTACT_LIST','CMSG_ADD_FRIEND','CMSG_DEL_FRIEND',
    'CMSG_SET_CONTACT_NOTES','CMSG_ADD_IGNORE','CMSG_DEL_IGNORE','SMSG_CONTACT_LIST','SMSG_FRIEND_STATUS',
    'CMSG_CHAT_REPORT_IGNORED','CMSG_CHAT_IGNORED',
    'SMSG_GM_MESSAGECHAT',
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
    'SMSG_SET_FACTION_VISIBLE','CMSG_SET_FACTION_AT_WAR','CMSG_SET_FACTION_NOT_AT_WAR','CMSG_SET_FACTION_ATWAR',
    'CMSG_SET_FACTION_INACTIVE','CMSG_SET_WATCHED_FACTION','CMSG_SET_ACTION_BUTTON',
    'CMSG_SET_ACTION_BAR_TOGGLES','CMSG_SET_ACTIONBAR_TOGGLES',
    'CMSG_STAND_STATE_CHANGE','CMSG_STANDSTATECHANGE','SMSG_STAND_STATE_UPDATE','CMSG_SET_SHEATHED',
    'SMSG_ALL_ACHIEVEMENT_DATA','SMSG_CRITERIA_UPDATE','SMSG_ACHIEVEMENT_EARNED'}


def initialize(directory):
    directory=directory.resolve()
    if directory.parent!=lab.ROOT/'evidence' or not re.fullmatch(r'[A-Za-z0-9_]+',directory.name):
        raise ValueError('require a new named private interaction batch')
    native=lab.owned_process('worldserver')
    if not native:raise RuntimeError('owned native worldserver is absent')
    directory.mkdir(mode=0o700,exist_ok=False)
    identity={key:native[key] for key in ['pid','start_ticks']}
    lab.private_write(directory/'native_server_before.json',json.dumps(identity,indent=2)+'\n')
    lab.private_write(directory/'batch.json',json.dumps({'schema':'client442_interaction_batch_v1',
        'started_at':time.time(),'native_worldserver':identity,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip()},indent=2)+'\n')
    print(json.dumps({'directory':str(directory),'native_worldserver':identity}))


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
    cases,runs,trials=checkpoint_runs(episodes,directory)
    plan=json.loads((lab.REPO/'experiments/configs/client_harness/442_interactions_v1.json').read_text())
    counts=Counter(c['status'] for c in cases)
    native=lab.owned_process('worldserver');before=json.loads((directory/'native_server_before.json').read_text())
    if (native['pid'],native['start_ticks'])!=(before['pid'],before['start_ticks']):
        raise RuntimeError('native server identity changed during this experiment')
    target=lab.REPO/'artifacts/client_harness'/(name+'.tar.gz');pointer=str(target.relative_to(lab.REPO))+'.dvc'
    if target.exists() or (lab.REPO/pointer).exists():raise RuntimeError('checkpoint name already exists')
    input_binary,input_build=verified_input()
    metadata={'schema':'client442_interaction_checkpoint_v1','since':since,'counts':dict(counts),
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'native_worldserver':native,'native_worldserver_restarted':False,
        'native_binary_sha256':lab.sha256(lab.ROOT/'bin/worldserver'),
        'bridge_build':json.loads((lab.ROOT/'build/native_bridge/build_receipt.json').read_text()),
        'input_build':input_build,
        'runs':runs,
        'limits':['Panel visibility passes do not qualify panel contents or mutations.',
            'Ordinary Trial controller/model/revision identities are recorded per episode. Read-only diagnostics have no assigned Trial identities or admitted operations. Bounded UI choices do not qualify general learned autonomy.',
            'Counts include historical failures and retries; they are not unique qualified feature counts.',
            f"The {len(plan['cases'])}-operation plan and 275-binding catalog remain broader than the completed trials."],
        'interaction_plan_operations':len(plan['cases']),
        'qualified_fixture_operations':plan.get('qualified_operations',0),
        'excluded':['credentials','authentication bodies','account-cache bodies','DB contents','Wine/CASC caches']}
    paths=[directory,lab.ROOT/'reference/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2',
        lab.ROOT/'reference/28fc3d194b22063ce8e94d2ed7235ca98ca51ef2',lab.ROOT/'reference/ui-442',lab.ROOT/'reference/local-60895',
        lab.ROOT/'build/native_bridge/build_receipt.json',lab.ROOT/'build/native_bridge_asan/build_receipt.json',
        lab.ROOT/'build/native_bridge/client442_bridge',lab.ROOT/'build/native_bridge/bridge_codec',
        lab.ROOT/'build/native_input/build_receipt.json',input_binary,
        lab.ROOT/'bin/worldserver']
    for receipt_path in directory.glob('native_*build*.json'):
        build=json.loads(receipt_path.read_text())
        if build.get('schema')!='client442_native_core_build_v1':continue
        if not build.get('finished_at'):raise RuntimeError('native build is still open')
        if build.get('completed') is not True:continue  # Retain failed receipts; never admit their candidate.
        candidate=lab.ROOT/'build/src/server/worldserver/worldserver'
        if build.get('binary_sha256')!=lab.sha256(candidate):
            raise RuntimeError('closed native build candidate artifact differs')
        if candidate not in paths:paths.append(candidate)
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
        for source,label in [(lab.ROOT/'logs/modern_world.jsonl','events.jsonl'),(lab.ROOT/'evidence/world_packets.jsonl','packets.jsonl'),
                (lab.ROOT/'evidence/owned_pet_abandon_packets.jsonl','owned_pet_abandon_packets.jsonl'),
                (lab.ROOT/'evidence/owned_tame_request_packets.jsonl','owned_tame_request_packets.jsonl'),
                (lab.ROOT/'evidence/owned_entry_request_packets.jsonl','owned_entry_request_packets.jsonl')]:
            if not source.exists() and label in ('owned_pet_abandon_packets.jsonl','owned_tame_request_packets.jsonl',
                    'owned_entry_request_packets.jsonl'):continue
            with (folder/label).open('w') as output:
                for row in entries(source):
                    if row.get('time',0)<since:continue
                    if 'body' in row and row.get('name') not in SAFE_BODY_NAMES:continue
                    output.write(json.dumps(row,separators=(',',':'))+'\n')
        (folder/'checkpoint.json').write_text(json.dumps(metadata,indent=2)+'\n')
        with tracking_live(dir=str(folder/'live'),save_dvc_exp=False,dvcyaml=False,report=None) as live:
            live.log_param('code_commit',metadata['code_commit']);live.log_param('controller','attributed_interaction_trials')
            live.log_metric('closed_runs',len(episodes))
            for metric,count in choice_counts(trials).items():live.log_metric(metric,count)
            live.log_metric('readonly_diagnostic_runs',len(episodes)-len(trials))
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
    verified_sha256=archive_digest(target)
    for command in [['dvc','add',relative],['dvc','status',pointer],['dvc','push',pointer]]:
        subprocess.run(command,cwd=lab.REPO,check=True)
        unchanged_archive(target,verified_sha256)
    cloud=json.loads(subprocess.check_output(['dvc','status','--cloud','--json',pointer],cwd=lab.REPO,text=True))
    if cloud:raise RuntimeError('checkpoint is not synchronized with the DVC remote')
    lab.private_write(directory/'checkpoint_receipt.json',json.dumps({'file':relative,'sha256':verified_sha256,
        'bytes':target.stat().st_size,'cloud_verified':True,'file_manifest':manifest},indent=2)+'\n')
    print(json.dumps({'pointer':pointer,'bytes':target.stat().st_size,'sha256':verified_sha256}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--name')
    p.add_argument('--initialize',action='store_true');a=p.parse_args()
    if a.initialize:
        if a.name:p.error('initialization does not name an archive')
        initialize(a.directory)
    else:
        if not a.name:p.error('checkpoint requires --name')
        checkpoint(a.directory,a.name)


if __name__=='__main__':main()
