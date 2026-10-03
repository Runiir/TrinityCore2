"""Restore only a disposable, auto-accepted quest in the isolated primary fixture."""
import time
from . import lab_runtime as lab
from .interaction_crafting import fixture_command
from .interaction_fixture_permissions import quest_fixture_permission
from .interaction_trade import inventory

QUEST=28766


def quest_state(guid):
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT * FROM client442_characters.character_queststatus WHERE guid=%s ORDER BY quest',(guid,))
        active=[dict(zip([x[0] for x in q.description],row)) for row in q.fetchall()]
        q.execute('SELECT * FROM client442_characters.character_queststatus_rewarded WHERE guid=%s ORDER BY quest',(guid,))
        rewarded=[dict(zip([x[0] for x in q.description],row)) for row in q.fetchall()]
    return {'active':active,'rewarded':rewarded}


def restore_autoaccepted(trial,baseline,quest=QUEST):
    if quest not in [QUEST,52]:raise ValueError('quest cleanup requires a bounded registered trial quest')
    if (trial.fixture['account_id'],trial.fixture['guid'],trial.fixture['character_name'])!=(1,1,'Harnessone'):
        raise RuntimeError('quest restoration requires the isolated primary actor')
    before=quest_state(1)
    if before==baseline:return
    extra=[row for row in before['active'] if row['quest']==quest]
    remaining={**before,'active':[row for row in before['active'] if row['quest']!=quest]}
    # Quest 52 has no source items. A failed full-objective trial may already
    # be complete but unrewarded; removing it is fixture cleanup, never proof.
    allowed=[3,1] if quest==52 else [3]
    if len(extra)!=1 or extra[0]['status'] not in allowed or remaining!=baseline:
        raise RuntimeError('unexpected quest mutation; preserving state for diagnosis')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT StartItem FROM client442_world.quest_template WHERE ID=%s',(quest,))
        if q.fetchall()!=((0,),):raise RuntimeError('quest source items require a separate restoration contract')
    items=inventory();trial.clean_panels()
    record={'source':'code_fixture_cleanup','quest':quest,'before':before,'baseline':baseline,
        'target_actor':1,'inventory_money_before':items}
    trial.receipt['quest_fixture_cleanup']=record;trial.persist()
    try:
        fixture_command(trial,'/targetexact Harnessone','remove only the owned disposable auto-accepted quest')
        state,frame=trial.observe('quest_cleanup_self_target')
        record['target_frame']=frame;trial.persist()
        if state.get('target',{}).get('guid')!=trial.guid:raise RuntimeError('quest cleanup target is not the owned actor')
        with quest_fixture_permission(trial):
            fixture_command(trial,f'.quest remove {quest}','restore only the quest introduced by the failed compatibility trial')
        after=quest_state(1);record['after']=after;record['inventory_money_restored']=inventory()==items
        record['restored']=after==baseline and record['inventory_money_restored'];trial.persist()
        if not record['restored']:raise RuntimeError('quest fixture restoration did not match the original state')
    finally:
        fixture_command(trial,'/cleartarget','clear the temporary self target')
