"""Compile the production UpdateAI with EventMap; stub actors and spell execution only."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BOSS = ROOT / 'src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_magmaw.cpp'


def body(source, signature):
    start = source.index('{', source.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def test_overdue_cast_waits_without_losing_phase_event(tmp_path):
    source = BOSS.read_text()
    enums = '\n'.join('enum ' + name + ' ' + body(source, 'enum ' + name) + ';'
                      for name in ('Events', 'Phases', 'Texts', 'BodyParts', 'EncounterFramePriorities'))
    unit = r'''
#include "EventMap.h"
#include "boss_magmaw_shared.h"
#include <cassert>
#include <vector>
using namespace BlackwingDescent::Magmaw;
uint32 urand(uint32 min, uint32) { return min; }
using ObjectGuid = uint64;
constexpr int UNIT_STATE_CASTING=1, REACT_PASSIVE=0, REACT_AGGRESSIVE=1,
 DATA_PREPARE_MASSIVE_CRASH_AND_GET_TARGET_GUID=1, ENCOUNTER_FRAME_ENGAGE=1,
 UNIT_FIELD_FLAGS=1, UNIT_FLAG_NOT_SELECTABLE=1, SELECT_TARGET_RANDOM=0;
struct Creature {
 bool casting=false; bool selectable=false;
 bool HasUnitState(int) { return casting; }
 Creature* GetVictim() { return this; }
 bool IsWithinMeleeRange(Creature*) { return true; }
 void AttackStop() {} void SetReactState(int) {} void ReleaseSpellFocus(void*,bool) {}
 void SetFacingToObject(Creature*,bool) {} void CastSpell(Creature*,int,bool) {}
 void RemoveFlag(int,int) { selectable=true; }
};
struct Instance {
 ObjectGuid GetGuidData(int) { return 0; }
 void SendEncounterUnit(int,Creature*,int) {}
};
namespace ObjectAccessor { Creature* GetCreature(Creature&,ObjectGuid) { return nullptr; } }
int NonTankTargetSelector(Creature*) { return 0; }
struct Base { virtual void UpdateAI(uint32)=0; };
'''
    unit += enums
    unit += r'''
struct Boss : Base {
 Creature actor, head; Creature* me=&actor; Instance inst; Instance* instance=&inst;
 EventMap events; unsigned _magmaProjectileCount=0; bool _headEngaged=false;
 std::vector<int> submitted, rejected;
 Boss() { events.SetPhase(PHASE_COMBAT); }
 bool UpdateVictim() { return true; }
 Creature* SelectTarget(int,int,int) { return me; }
 Creature* GetBodyPart(BodyParts) { return &head; }
 void Talk(int) {} void DoMeleeAttackIfReady() {}
 void DoCastAOE(int spell) {
   if (me->casting) { rejected.push_back(spell); return; }
   submitted.push_back(spell);
   if (spell==SPELL_LAVA_SPEW) me->casting=true;
 }
 void DoCast(int spell) { DoCastAOE(spell); }
 void DoCastSelf(int spell) { DoCastAOE(spell); }
 void UpdateAI(uint32 diff) override
'''
    unit += body(source, 'void UpdateAI(uint32 diff) override') + '\n};\n'
    unit += r'''
int main() {
 Boss b;
 b.events.ScheduleEvent(EVENT_LAVA_SPEW, 1ms, 0, PHASE_COMBAT);
 b.events.ScheduleEvent(EVENT_MANGLE, 2ms, 0, PHASE_COMBAT);
 b.UpdateAI(10); // Both overdue. Spew starts a native cast.
 assert(b.submitted.size()==1 && b.rejected.empty());
 assert(b.events.GetNextEventTime(EVENT_MANGLE)==2);
 b.UpdateAI(100); // Still casting: deadline remains queued.
 assert(b.submitted.size()==1 && b.rejected.empty());
 b.me->casting=false;
 b.UpdateAI(1); // Finish unlocks Mangle; phase cancellation runs now.
 assert(b.submitted.size()==2 && b.submitted.back()==SPELL_MANGLE_TARGETING);
 assert(b.rejected.empty());
 assert(b.events.GetTimeUntilEvent(EVENT_PREPARE_MASSIVE_CRASH)==3500);
 // Impale's ongoing cast must not suppress the scheduled head exposure.
 Boss h; h.events.SetPhase(PHASE_IMPALED); h.me->casting=true;
 h.events.ScheduleEvent(EVENT_SHOW_HEAD, 1ms, 0, PHASE_IMPALED);
 h.UpdateAI(1); assert(h.head.selectable && h._headEngaged);
 // Instant projectiles do not acquire an invented global cast-spacing delay.
 Boss i;
 i.events.ScheduleEvent(EVENT_MAGMA_PROJECTILE, 1ms, 0, PHASE_COMBAT);
 i.events.ScheduleEvent(EVENT_MANGLE, 2ms, 0, PHASE_COMBAT);
 i.UpdateAI(10); assert(i.submitted.size()==2 && i.rejected.empty());
}
'''
    cpp = tmp_path / 'queue.cpp'
    cpp.write_text(unit)
    exe = tmp_path / 'queue'
    subprocess.run(['g++', '-std=c++17', '-I'+str(ROOT/'src/common'),
                    '-I'+str(ROOT/'src/common/Utilities'), '-I'+str(BOSS.parent),
                    str(cpp), str(ROOT/'src/common/Utilities/EventMap.cpp'), '-o', str(exe)],
                   check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
