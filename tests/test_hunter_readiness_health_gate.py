import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / 'src/server/game/Bots'


def test_readiness_uses_hostile_health_in_actual_selection_branches(tmp_path):
    header = (BOT/'BotClassSpecActionProfile.h').read_text()
    definitions = header[header.index('struct BotActionProfileSpell'):header.index('struct BotActionCandidate')]
    functions = []
    for index, name in enumerate(('BotWorldPopulationMgrCombatSpell.cpp', 'BotWorldPopulationMgrCombatResolver.cpp')):
        source = (BOT/name).read_text()
        begin = source.index('float targetHealthPct = UnitHealthPct(actionTarget);')
        branch = source[begin:source.index('float selfHealthPct = UnitHealthPct(bot);', begin)]
        functions.append(f'''bool select{index}(BotActionProfileSpell profile, Unit* target) {{
            Candidate candidate{{profile}}; Unit self{{1.0f}}; Unit* actionTarget=&self;
            for(int once=0;once<1;++once) {{ {branch} return true; }} return false;
        }}''')
    controller = (BOT/'BotControllerCombat.cpp').read_text()
    begin = controller.index('if (state.TargetHpPct < candidate.Profile.MinTargetHealthPct')
    end = controller.index('if (state.SelfHpPct', begin)
    functions.append('bool select2(BotActionProfileSpell profile, Unit* target) { '
        'Candidate candidate{profile}; State state{UnitHealthPct(target), {target == nullptr}}; '
        'for(int once=0;once<1;++once) {' + controller[begin:end] +
        'return true;} return false;}')
    producer = (BOT/'BotClassSpecActionProfileCandidates.cpp').read_text()
    begin = producer.index('MeetsHostileTargetHealthGate(')
    end = producer.index('\n            candidate.RejectReason', begin)
    call = producer[begin:end][:-1]  # strip the surrounding if's closing parenthesis
    functions.append('bool produce(BotActionProfileSpell spell, Unit* target) { return ' + call + '; }')
    source = tmp_path/'gate.cpp'
    source.write_text('''#include <cmath>
#include <string>
#include <limits>
#include <cassert>
using uint32=unsigned; using uint16=unsigned short; using uint8=unsigned char;
enum class BotCombatActionCategory { Builder };
''' + definitions + '''
struct Unit { float health; float GetHealth(){return health;} float GetMaxHealth(){return 1;} };
struct Guid { bool empty; bool IsEmpty(){return empty;} };
struct State { float TargetHpPct; Guid TargetGuid; };
float UnitHealthPct(Unit* unit){return unit ? unit->health : 0.0f;}
struct Candidate { BotActionProfileSpell Profile; std::string RejectReason; };
''' + '\n'.join(functions) + '''
int main(){
 BotActionProfileSpell spell; spell.TargetSelector="self";
 spell.MaxTargetHealthPct=1.0f; spell.MaxHostileTargetHealthPct=.90f;
 Unit enemy{.90f};
 assert(select2(spell,&enemy)); assert(!select2(spell,nullptr));
 assert(produce(spell,&enemy)); assert(!produce(spell,nullptr));
 enemy.health=.90001f; assert(!select2(spell,&enemy)); assert(!produce(spell,&enemy)); enemy.health=.90f;
 for(auto select : {select0,select1}) {
  assert(select(spell,&enemy));
  enemy.health=.90001f; assert(!select(spell,&enemy)); enemy.health=.90f;
  assert(!select(spell,nullptr));
  auto old=spell; old.MaxTargetHealthPct=.90f; old.MaxHostileTargetHealthPct=0;
  assert(!select(old,&enemy)); // Historical self-health counterexample.
 }
 spell.MaxHostileTargetHealthPct=0; assert(MeetsHostileTargetHealthGate(spell,0,false));
 spell.MinHostileTargetHealthPct=.25f;
 assert(!MeetsHostileTargetHealthGate(spell,.25f,true));
 assert(MeetsHostileTargetHealthGate(spell,.25001f,true));
 assert(!MeetsHostileTargetHealthGate(spell,0,false));
 spell.MaxHostileTargetHealthPct=.2f; assert(!ValidHostileTargetHealthRange(spell));
 spell.MaxHostileTargetHealthPct=1.1f; assert(!ValidHostileTargetHealthRange(spell));
 spell.MaxHostileTargetHealthPct=-.1f; assert(!ValidHostileTargetHealthRange(spell));
 spell.MaxHostileTargetHealthPct=std::numeric_limits<float>::quiet_NaN();
 assert(!ValidHostileTargetHealthRange(spell));
}
''')
    binary = tmp_path/'gate'
    subprocess.run(['c++','-std=c++17',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)


def test_max_hostile_gate_is_appended_bound_exported_and_all_callers_supply_presence():
    db = (BOT/'BotClassSpecActionProfileDb.cpp').read_text()
    query = db[db.index('"SELECT p.id'):db.index('"FROM bot_rotation_profile p')]
    columns = re.findall(r'\b[pa]\.([a-z_]+)',query)
    assert columns[76:81] == ['min_hostile_target_health_pct','required_self_aura_charges',
        'max_self_aura_charges','min_owned_target_aura_remaining_ms','max_hostile_target_health_pct']
    assert 'spell.MaxHostileTargetHealthPct = fields[80].GetFloat();' in db
    assert 'ValidHostileTargetHealthRange(spell)' in db
    assert 'spell.MaxHostileTargetHealthPct' in db[db.index('std::string SnapshotPayload'):db.index('std::shared_ptr<DbRotationSnapshot> Load')]
    assert '\\"max_hostile_target_health_pct\\":' in db
    assert 'state.TargetHpPct, !state.TargetGuid.IsEmpty()' in (BOT/'BotControllerCombat.cpp').read_text()
    assert ': 0.0f, target != nullptr)' in (BOT/'BotClassSpecActionProfileCandidates.cpp').read_text()
    for name in ('build_phase4_rotation_contract.py','review_rotation_mechanics.py'):
        assert '"max_hostile_target_health_pct"' in (ROOT/'tools/bot_ml'/name).read_text()


def test_readiness_migration_changes_only_exact_self_targeted_sequence_row():
    name='2026_09_09_00_hunter_readiness_hostile_health_gate'
    forward=(ROOT/'sql/custom/world'/f'{name}.sql').read_text()
    rollback=(ROOT/'sql/custom/rollback/world'/f'{name}_rollback.sql').read_text()
    for sql in (forward,rollback):
        for predicate in ("`profile`.`class_id` = 3", "`profile`.`spec_tag` = 'marksmanship'",
                          "`profile`.`role` = 'dps'", "`action`.`spell_id` = 23989",
                          "`action`.`mechanic_tags` = 'readiness,apl_strict_sequence'",
                          "`action`.`target_selector` = 'self'"):
            assert predicate in sql
        assert 'sort_order' not in sql and 'priority_bucket' not in sql
    assert '`max_target_health_pct` = 1.00' in forward
    assert '`max_hostile_target_health_pct` = 0.90' in forward
    assert '`max_target_health_pct` = 0.90' in rollback
    assert rollback.index('UPDATE') < rollback.index('DROP COLUMN')
