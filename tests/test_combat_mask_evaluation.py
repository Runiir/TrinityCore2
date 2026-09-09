"""Passive cache provenance serializer behavior and exhaustive writer wiring audit."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / 'src/server/game/Bots'


def test_cached_mask_evaluation_context_changes_only_on_evaluation(tmp_path):
    source = tmp_path / 'mask.cpp'
    source.write_text(r'''
#include "Bots/BotCombatMaskEvaluation.h"
#include <iostream>
struct Guid {unsigned value; unsigned GetCounter()const{return value;}};
struct Actor {unsigned guid=30008,entry=0; Guid GetGUID()const{return {guid};}
 unsigned GetEntry()const{return entry;} unsigned GetMapId()const{return 669;}
 unsigned GetInstanceId()const{return 33;}};
struct Cohort {std::string Id="cohort\"\n";unsigned AttemptId=7;
 struct {unsigned WipeGeneration=2;} Raid;
 struct {std::string ValidationRouteNodeId="magmaw";} Config;};
struct Party {unsigned ValidationRouteGeneration=4;};
int main(){
 Actor actor,head;head.guid=76;head.entry=42347;Cohort cohort;Party party;
 std::string const mask=R"({"schema":"bot_valid_action_mask_v2","profile":{"snapshot_generation":7},"profile_source":"database","role_goal":"damage","role_saturation_state":{},"observation":{"power":123},"actions":[{"spell_id":30108,"target_guid":76,"score":5,"valid":true}]})";
 auto evaluation=BotCombatMaskEvaluation::Context(1788917243000ULL,&actor,&head,cohort,party,"ResolveProfileCombatAction");
 std::string cached=BotCombatMaskEvaluation::Append(mask,evaluation,R"({"movement_compatible_only":false,"excluded_spell_id":0})");
 std::cout<<mask<<'\n'<<cached<<'\n';
 // A later read and changed live target do not reevaluate or re-stamp the cache.
 head.guid=215;head.entry=41620;party.ValidationRouteGeneration=5;
 std::cout<<cached<<'\n';
 evaluation=BotCombatMaskEvaluation::Context(1788917259000ULL,&actor,&head,cohort,party,"SelectHealSpell");
 cached=BotCombatMaskEvaluation::Append(mask,evaluation,R"({"instant_only":true})");
 std::cout<<cached<<'\n';
 // A fallback is not a real evaluation and is not passed to Append.
 std::cout<<"{}\n";
}
''')
    binary = tmp_path / 'mask'
    subprocess.run(['g++', '-std=c++17', '-I', str(ROOT / 'src/server/game'), str(source), '-o', str(binary)], check=True)
    original, first, retained, refreshed, fallback = map(json.loads, subprocess.check_output([str(binary)], text=True).splitlines())
    assert first == retained
    assert {k: v for k, v in first.items() if k != 'evaluation'} == original
    assert {k: v for k, v in refreshed.items() if k != 'evaluation'} == original
    assert first['evaluation'] == {
        'started_at_ms': 1788917243000, 'selector': 'ResolveProfileCombatAction',
        'actor_guid': 30008, 'target_guid': 76, 'target_entry': 42347,
        'scope': {'cohort_id': 'cohort"\n', 'attempt_id': 7, 'wipe_generation': 2,
                  'route_generation': 4, 'node_id': 'magmaw', 'map_id': 669, 'instance_id': 33},
        'selector_filters': {'movement_compatible_only': False, 'excluded_spell_id': 0},
    }
    assert refreshed['evaluation']['started_at_ms'] == 1788917259000
    assert refreshed['evaluation']['target_guid'] == 215
    assert refreshed['evaluation']['scope']['route_generation'] == 5
    assert refreshed['evaluation']['selector'] == 'SelectHealSpell'
    assert refreshed['evaluation']['selector_filters'] == {'instant_only': True}
    assert 'evaluation' not in fallback  # timestamp unavailable, never current


def test_all_real_cached_mask_writers_capture_context_before_candidates():
    writers = {}
    for path in BOTS.glob('*.cpp'):
        source = path.read_text()
        if 'LastCombatMaskByBot[botKey] =' in source:
            writers[path.name] = source
    assert set(writers) == {f'BotWorldPopulationMgrCombat{x}.cpp' for x in ('Resolver', 'Support', 'Spell')}
    for source in writers.values():
        assert source.count('LastCombatMaskByBot[botKey] =') == 1
        assert source.index('BotCombatMaskEvaluation::Context(') < source.index('::BuildCandidates(bot, target, profile)')
        assert 'LastCombatMaskByBot[botKey] = BotCombatMaskEvaluation::Append(' in source
        assert 'roleGoal.c_str(), saturation.ToJson().c_str()), maskEvaluation,' in source
    resolver = writers['BotWorldPopulationMgrCombatResolver.cpp']
    for name in ('requestedHostileCount', 'hostileCount', 'densityOnly', 'excludedSpellId', 'areaOnly',
                 'selfCenteredOnly', 'forbidArea', 'allowMultidot', 'hostileTargetOnly',
                 'movementCompatibleOnly', 'specTagOverride'):
        assert name in resolver[resolver.index('std::ostringstream maskFilters;'):]
    assert 'instantOnly ?' in writers['BotWorldPopulationMgrCombatSupport.cpp']
    # Fallback/read sites retain unknown timestamps; this is a wiring audit,
    # not an assertion that a cached mask belongs to a later combat attempt.
    for name in ('BotWorldPopulationMgrEventRecording.cpp', 'BotWorldPopulationMgrCombatLog.cpp'):
        assert 'BotCombatMaskEvaluation::' not in (BOTS / name).read_text()
