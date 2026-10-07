"""Join the owned ability outcome to its complete archived cleanup boundary."""
from pathlib import Path
from . import lab_runtime as lab
from .primary_throw_evidence import verify,require,closed


def proof(data,digests,packets):
    names={'entry':'primary_clean_combat_entry01','stage':'primary_faced_throw_stage01',
        'cast':'primary_faced_throw_native01','log':'primary_stock_damage_log_open03',
        'restore':'primary_stock_damage_log_restore01','park':'primary_combat_final_park01'}
    rows={k:data[v+'/episode.json'] for k,v in names.items()}
    e=rows['cast'];stage=rows['stage'];entry=rows['entry']
    outcome=verify(e,stage,entry)
    directory=Path(e['source']['path']).parent.parent
    require(directory.parent==lab.ROOT/'evidence','owned archive directory differs')

    def link(ref,key):
        require(ref.get('path')==str(directory/key) and ref.get('sha256')==digests.get(key),
            'archived source/frame digest differs: '+key)

    link(e['source'],names['stage']+'/episode.json')
    link(stage['source'],names['entry']+'/episode.json')
    link(e['review'],names['stage']+'/review.json')
    reviewed=data[names['stage']+'/review.json']
    link(reviewed['source'],names['stage']+'/episode.json')
    require(reviewed.get('reviewed') is True and reviewed.get('target_visible') is True and
        reviewed.get('control')=='primary_throw' and reviewed['frame']==stage['frame']==e['review']['frame'],
        'fresh visually reviewed owned target differs')
    require(0<=e['started_at']-stage['finished_at']<110,
        'ability did not start within the reviewed capture lifetime')
    frame=stage['frame'];monitor=frame['monitor'];isolation=monitor['input_isolation']
    require(monitor['second_monitor_verified'] is True and monitor['monitor']['name']=='HDMI-1' and
        isolation['actor']=='primary' and isolation['display']==':2' and
        isolation['host_activation_sent'] is False,'owned second-monitor input boundary differs')
    require(digests[names['stage']+'/'+frame['file']]==frame['sha256'],
        'reviewed image differs from actual archive')
    fixture_key=names['stage']+'/primary_throw_facing_fixture.json'
    link(e['pose_fixture'],fixture_key);link(stage['pose_fixture'],fixture_key)
    fixture=data[fixture_key];restored=e['facing_restoration'];base=stage['baseline']
    require(fixture['actor_guid']==1 and fixture['native']==e['runtime']['worldserver'] and
        fixture['before']==base['position']==restored['original']==restored['restored'] and
        fixture['landing']==stage['combat_position'] and
        fixture['landing'][:3]==base['position'][:3] and fixture['landing'][4]==base['position'][4] and
        len(fixture['rows'])==2 and [r[-1] for r in fixture['rows']]==
        ['TC442PrimaryThrowRestore','TC442PrimaryThrowFacing'] and
        restored['removed']==[r[0] for r in fixture['rows']] and restored['native_unchanged'] is True and
        data[names['cast']+'/primary_facing_restoration.json']==restored,
        'complete exact user-facing fixture restoration differs')
    require(all(row[1:4]==base['position'][:3] and row[5]==base['position'][4]
        for row in fixture['rows']) and fixture['rows'][0][4]==base['position'][3] and
        fixture['rows'][1][4]==fixture['landing'][3],
        'owned native fixture coordinates/facing differ')
    for key,count in (('log',5),('restore',5),('park',7)):
        row=rows[key];closed(row,'checks',count)
        require(row['actor']==e['actor'] and row['runtime']==e['runtime'] and
            row['custom_script_permission']=='blocked_by_user' and row['model'] is None,
            'closure actor/runtime/script/model boundary differs')
    link(rows['log']['source'],names['entry']+'/episode.json')
    link(rows['restore']['source'],names['log']+'/episode.json')
    link(rows['park']['source'],names['cast']+'/episode.json')
    require(stage['baseline']==e['baseline']==rows['park']['baseline'] and
        rows['park']['parked_native']['online']==0 and
        e['finished_at']<rows['log']['started_at']<rows['log']['finished_at']<
        rows['restore']['started_at']<rows['restore']['finished_at']<rows['park']['started_at'],
        'whole normal parking and original saved-state boundary differs')
    log=rows['log']['public'];original=e['public_combat_log_before']
    require(log['selected']==2 and log['visible'] and log['saved_settings']==original['saved_settings']==
        rows['restore']['public']['saved_settings'] and rows['restore']['public']['selected']==1,
        'stock combat tab/filter restoration differs')
    text=[v['text'] for v in log.get('recent_messages',[]) if not v.get('truncated') and
        'Hspell:57755:0:SPELL_DAMAGE' in v.get('text','') and
        'Hunit:Player-1-00000001:Harnessone' in v.get('text','') and
        'Parched Buzzard' in v.get('text','')]
    net=outcome['damage']-outcome['overkill']
    require(len(text)==1 and format(net,',') in text[0] and
        format(outcome['overkill'],',')+' Overkill' in text[0] and 'Physical' in text[0],
        'native-matching stock damage/overkill line absent')
    deploy=data['spell_damage_bridge_deploy01/deployment.json']
    require(deploy['completed'] is True and deploy['native_unchanged'] is True and
        deploy['native']==e['runtime']['worldserver'] and
        deploy['client_lifetimes']['primary']==e['runtime']['client'],
        'accepted bridge deployment/native/client lineage differs')
    for key in ('entry','stage','cast'):
        row=rows[key]
        require(row['custom_script_permission']=='blocked_by_user' and row['model'] is None,
            'ability script/model boundary differs')
    from .review_native_feedback_checkpoint import packet_key
    require(all(packet_key(p) in packets for p in e['packets']),
        'owned outcome packet absent from actual archive tracking')
    return dict(outcome,stock_damage_text=True,original_general_restored=True,
        exact_facing_restored=True,temporary_rows_removed=True,primary_offline=True,
        native_unchanged=True,existing_client_lifetime_preserved=True,scripts_blocked=True)
