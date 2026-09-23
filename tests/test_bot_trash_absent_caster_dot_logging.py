from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def test_absent_periodic_caster_is_attributed_only_when_unique(tmp_path: Path) -> None:
    # sq1: a Drudge lost 60,742 more health than the combat log recorded,
    # exactly Mgwtanka's Moonfire and Insect Swarm ticks after he died and
    # released.  The native tick then passes no attacker.
    source = tmp_path / "absent_caster.cpp"
    binary = tmp_path / "absent_caster"
    source.write_text(r'''
#include "Bots/BotCombatDamageAttribution.h"
#include <cassert>

using namespace BotCombatDamageAttribution;

int main()
{
    std::uint64_t const tanka = 30001;
    std::uint64_t const other = 30010;
    std::uint64_t const pet = 0xF14022FF00000001ull;

    // No application of the ticking spell: nothing to attribute.
    assert(AbsentPeriodicCaster({}) == 0);
    // The released caster is the only absent player: attribute to it.
    assert(AbsentPeriodicCaster({ { tanka, true, false } }) == tanka);
    // A present caster of the same spell ticked with its own attacker, so
    // the attacker-less tick belongs to the absent one.
    assert(AbsentPeriodicCaster({ { other, true, true }, { tanka, true, false } }) == tanka);
    // Two stacks from one caster are one caster.
    assert(AbsentPeriodicCaster({ { tanka, true, false }, { tanka, true, false } }) == tanka);
    // Two absent players with the same spell cannot be told apart.
    assert(AbsentPeriodicCaster({ { tanka, true, false }, { other, true, false } }) == 0);
    // A despawned pet is not a player caster; it stays unattributed.
    assert(AbsentPeriodicCaster({ { pet, false, false } }) == 0);
    assert(AbsentPeriodicCaster({ { 0, true, false } }) == 0);
}
''', encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "src/server/game"), str(source), "-o", str(binary)],
        check=True, cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_attackerless_periodic_damage_is_logged_for_the_aura_caster() -> None:
    notifications = (BOTS / "BotWorldPopulationMgrCombatNotifications.cpp").read_text()
    notify = notifications[notifications.index("void BotWorldPopulationMgr::NotifyCombatDamage("):]
    notify = notify[:notify.index("\n}\n")]
    # The victim alone scopes an attacker-less tick; only a periodic tick is
    # recovered, every other attacker-less callback stays ignored, and no
    # attacker is dereferenced before the dispatch.
    assert "if (!attacker || !victim)" not in notify
    scope = notify.index("CohortScope scope = ScopeCallbackCohort(attacker, victim);")
    active = notify.index("if (!Cohort().Active || (!damage && !unmitigatedDamage))")
    absent = notify.index("if (!attacker)")
    assert scope < active < absent
    assert "attacker->" not in notify[:absent]
    assert "damageType == uint32(DOT)" in notify[absent:absent + 200]
    assert "NotifyAbsentCasterPeriodicDamage(victim," in notify[absent:absent + 300]
    assert notify.index("return;", absent) < notify.index("CombatOwnerPlayer(attacker)")

    recover = notifications[notifications.index("::NotifyAbsentCasterPeriodicDamage("):]
    assert "victim->GetAppliedAuras().equal_range(spellId)" in recover
    assert "aura->GetCasterGUID()" in recover
    assert "ObjectAccessor::GetUnit(*victim, casterGuid)" in recover
    assert "AbsentPeriodicCaster(candidates)" in recover
    # The ghost is on another map: the caller scoped by the victim, and the
    # caster must be a bot of that cohort; calibration keeps its own books.
    assert "ScopeCallbackCohort(" not in recover
    assert "for (WorldBotState const& state : Party().Bots)" in recover
    assert "CalibrationMetricsByGuid.count(" in recover
    # Another map's thread owns the ghost: nothing reads the player object.
    # Identity comes from the bot's cached state, and the position only from
    # a death on the victim's map and instance.
    assert "GetLoadedBot" not in recover
    assert "IsFriendlyTo" not in recover
    assert "absent.Name = casterState->CombatLogName;" in recover
    assert "absent.Role = casterState->CombatLogRole;" in recover
    assert "absent.ClassId = casterState->CombatLogClassId;" in recover
    assert "casterState->LastDeathMapId == victim->GetMapId()" in recover
    assert "casterState->LastDeathInstanceId == victim->GetInstanceId()" in recover
    assert "absent.Z = casterState->LastDeathZ;" in recover
    # A null actor and source mean the absent caster, so its ticks join its
    # live DoT rows under the same actor guid and spell.
    assert "AddCombatLogAggregate(outgoingPerspective, nullptr, nullptr, victim" in recover
    assert 'AddCombatLogEvent("damage", nullptr, nullptr, victim' in recover
    assert recover.count("&absent") == 3

    combat_log = (BOTS / "BotWorldPopulationMgrCombatLog.cpp").read_text()
    aggregate = combat_log[combat_log.index("::AddCombatLogAggregate("):combat_log.index("::AddCombatLogEvent(")]
    assert "if (!target || (!absentSource && (!actor || !source)))" in aggregate
    assert "if (!absentSource || absentSource->PositionKnown)" in aggregate
    sampled = aggregate[aggregate.index("if (!absentSource || absentSource->PositionKnown)"):]
    sampled = sampled[:sampled.index("CombatLogSecondBucket")]
    for statistic in ("++aggregate.DistanceSamples;", "aggregate.MovingEvents +=",
                      "aggregate.DistanceTotal +=", "aggregate.MinDistance = distance;",
                      "aggregate.MaxDistance ="):
        assert statistic in sampled
    assert "!absentSource && source->isMoving()" in sampled
    event = combat_log[combat_log.index("::AddCombatLogEvent("):]
    event = event[:event.index("\n}\n")]
    assert "else if (absentSource->PositionKnown)" in event
    assert "event.SourcePositionKnown = false;" in event
    absent_branch = event[event.index("else if (absentSource->PositionKnown)"):event.index("event.SourceIsPet")]
    assert "source->" not in absent_branch and "actor->" not in absent_branch

    status = (BOTS / "BotWorldPopulationMgrStatus.cpp").read_text()
    assert 'json << ",\\"source_x\\":null,\\"source_y\\":null,\\"source_z\\":null";' in status
    assert 'json << ",\\"distance\\":null,\\"source_moving\\":null";' in status
    assert "value.DistanceTotal / double(value.DistanceSamples)" in status
    assert "double(value.MovingEvents) / double(value.DistanceSamples)" in status

    state = (BOTS / "BotWorldPopulationMgrBotState.h").read_text()
    for field in ("uint32 LastDeathInstanceId = 0;", "float LastDeathZ = 0.0f;",
                  "std::string CombatLogName;", "std::string CombatLogRole;",
                  "uint8 CombatLogClassId = 0;"):
        assert field in state
    memory = (BOTS / "BotWorldPopulationMgrSpawnMemory.cpp").read_text()
    assert "state.LastDeathInstanceId = bot->GetInstanceId();" in memory
    assert "state.LastDeathZ = bot->GetPositionZ();" in memory
    preparation = (BOTS / "BotWorldPopulationMgrUpdateBotPreparation.cpp").read_text()
    cache = preparation.index("context.State.CombatLogName = context.Bot->GetName();")
    assert "context.Bot->IsAlive() && context.State.CombatLogName.empty()" in preparation[cache - 200:cache]
    # The role reuses the decision's cadence profile, not a second lookup.
    assert "context.State.CombatLogRole = cadenceProfile.Role;" in preparation
    assert "context.State.CombatLogRole = GetDungeonRole(" not in preparation
    # A bot that dies before its first decision still has an identity.
    for creator in ("BotWorldPopulationMgrValidationAdmission.cpp", "BotWorldPopulationMgrPopulation.cpp"):
        text = (BOTS / creator).read_text()
        creation = text[text.index("state.RosterClassSpec = GetBotClassSpec(bot);"):text.index("Party().Bots.push_back(state);")]
        for field in ("state.CombatLogName = bot->GetName();", "state.CombatLogClassId = bot->getClass();",
                      "state.CombatLogRole = GetDungeonRole(bot);"):
            assert field in creation
    # An aggregate with no distance sample has no minimum.
    assert 'json << "null";' in status[status.index('",\\"distance_min\\":"'):]
