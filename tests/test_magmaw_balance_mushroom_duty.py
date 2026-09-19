from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
    "Magmaw/BotMagmawBalanceMushroomDuty.h"
)
SQL = ROOT / "sql/custom/world/2026_09_18_01_magmaw_balance_lava_mushrooms.sql"
ROLLBACK_SQL = ROOT / (
    "sql/custom/rollback/world/"
    "2026_09_18_01_magmaw_balance_lava_mushrooms_rollback.sql"
)
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
DUTY_SOURCE = HEADER.with_suffix(".cpp")
DRUID_SPELLS = ROOT / "src/server/scripts/Spells/spell_druid.cpp"
DRUID_MAGMAW_SPELLS = ROOT / "src/server/scripts/Spells/spell_druid_magmaw.cpp"


def test_magmaw_balance_duty_is_closed_and_counted(tmp_path: Path):
    source = tmp_path / "magmaw_balance_mushroom_duty.cpp"
    binary = tmp_path / "magmaw_balance_mushroom_duty"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
#include <cassert>

int main()
{
    using Duty = BotEncounter::MagmawBalanceMushroomDuty;
    assert(Duty::IsActive(true, "bwd.magmaw.encounter", "balance_druid", 41806));
    assert(Duty::IsActive(true, "bwd.magmaw.encounter", "balance_druid", 42321));
    assert(Duty::IsActive(true, "bwd.magmaw.encounter", "balance_druid", 41570, true));
    assert(!Duty::IsActive(true, "bwd.magmaw.encounter", "balance_druid", 41570));
    assert(Duty::PillarOfFlameEntry == 41843);
    assert(!Duty::IsActive(false, "bwd.magmaw.encounter", "balance_druid", 41806));
    assert(!Duty::IsActive(true, "bwd.magmaw.drudges", "balance_druid", 41806));
    assert(!Duty::IsActive(true, "bwd.magmaw.encounter", "fire", 41806));
    assert(!Duty::IsActive(true, "bwd.magmaw.encounter", "balance_druid", 41570));
    assert(Duty::NeedsPlacement(0));
    assert(Duty::NeedsPlacement(2));
    assert(!Duty::NeedsPlacement(3));
    assert(!Duty::ReadyToDetonate(2));
    assert(Duty::ReadyToDetonate(3));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-Isrc/server/game", "-Isrc/common", str(source), "-o", str(binary)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    subprocess.run([str(binary)], cwd=tmp_path, check=True)


def test_ground_selector_uses_live_ring_parasite_and_fails_closed(tmp_path: Path):
    source = tmp_path / "magmaw_balance_ground_selector.cpp"
    binary = tmp_path / "magmaw_balance_ground_selector"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
#include <cassert>
#include <cmath>

int main()
{
    using Duty = BotEncounter::MagmawBalanceMushroomDuty;
    Duty::GroundPoint point;

    // Parasites occupy the observed seven-yard ring.  The projected floor
    // point stays directly below one live engaged parasite and is inside the
    // child spell's native six-yard three-dimensional envelope.
    Duty::GroundCandidate ring;
    ring.ParasiteGuid = 22;
    ring.GroundX = 7.0f;
    ring.GroundY = 0.0f;
    ring.GroundZ = 0.0f;
    ring.ParasiteToGroundDistance = 5.5f;
    ring.ActorToGroundDistance = 7.0f;
    ring.Live = true;
    ring.Attackable = true;
    ring.Engaged = true;
    ring.GroundProjectionValid = true;
    ring.ActorRangeValid = true;
    ring.ActorLineOfSight = true;
    assert(Duty::SelectGroundPoint({ring}, 6.0f, point));
    assert(point.ParasiteGuid == 22);
    assert(point.X == 7.0f && point.Y == 0.0f && point.Z == 0.0f);

    // A lower-guid high-Z or otherwise invalid projection cannot win over a
    // lawful candidate, and a high-Z-only set fails closed.
    Duty::GroundCandidate highZ = ring;
    highZ.ParasiteGuid = 1;
    highZ.ParasiteToGroundDistance = 9.0f;
    assert(Duty::SelectGroundPoint({highZ, ring}, 6.0f, point));
    assert(point.ParasiteGuid == 22);
    highZ.GroundProjectionValid = false;
    assert(!Duty::SelectGroundPoint({highZ}, 6.0f, point));

    // Discovery radius is not cast authority: an actor-range or destination
    // LOS failure is rejected before it can preempt the ordinary rotation.
    Duty::GroundCandidate actorRange = ring;
    actorRange.ParasiteGuid = 2;
    actorRange.ActorRangeValid = false;
    assert(Duty::SelectGroundPoint({actorRange, ring}, 6.0f, point));
    assert(point.ParasiteGuid == 22);
    Duty::GroundCandidate actorLos = ring;
    actorLos.ParasiteGuid = 3;
    actorLos.ActorLineOfSight = false;
    assert(Duty::SelectGroundPoint({actorLos, ring}, 6.0f, point));
    assert(point.ParasiteGuid == 22);
    actorRange.ActorLineOfSight = false;
    assert(!Duty::SelectGroundPoint({actorRange}, 6.0f, point));

    // Dead, non-attackable, or non-engaged parasites are never lawful; no
    // parasite at all also leaves ordinary rotation available.
    Duty::GroundCandidate dead = ring;
    dead.Live = false;
    assert(!Duty::SelectGroundPoint({dead}, 6.0f, point));
    Duty::GroundCandidate illegal = ring;
    illegal.Attackable = false;
    assert(!Duty::SelectGroundPoint({illegal}, 6.0f, point));
    Duty::GroundCandidate unengaged = ring;
    unengaged.Engaged = false;
    assert(!Duty::SelectGroundPoint({unengaged}, 6.0f, point));
    assert(!Duty::SelectGroundPoint({}, 6.0f, point));

    // Candidate order is not an authority: equal lawful observations choose
    // the stable lower GUID.
    Duty::GroundCandidate tie = ring;
    tie.ParasiteGuid = 11;
    assert(Duty::SelectGroundPoint({ring, tie}, 6.0f, point));
    assert(point.ParasiteGuid == 11);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-Isrc/server/game", "-Isrc/common", str(source), "-o", str(binary)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    subprocess.run([str(binary)], cwd=tmp_path, check=True)


def test_sql_and_native_path_keep_the_exception_narrow():
    sql = SQL.read_text(encoding="utf-8")
    rollback_sql = ROLLBACK_SQL.read_text(encoding="utf-8")
    resolver = RESOLVER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    duty_source = DUTY_SOURCE.read_text(encoding="utf-8")
    druid_spells = DRUID_SPELLS.read_text(encoding="utf-8")
    druid_magmaw_spells = DRUID_MAGMAW_SPELLS.read_text(encoding="utf-8")

    assert "target_selector` = 'ground_enemy'" in sql
    assert "requires_ground_target` = 1" in sql
    assert "target_selector` = 'self'" in sql
    assert "magmaw_lava_parasite_add_duty" in sql
    assert "wild_mushroom,prepull,pinned_apl" in rollback_sql
    assert "target_selector` = 'enemy'" in rollback_sql
    assert "NeedsPlacement" in duty_source
    assert "ReadyToDetonate" in duty_source
    assert "WildMushroomDamageSpellId" in duty_source
    assert "CalcRadius(" in duty_source
    assert "SpellTargetIndex::TargetB" in duty_source
    assert "SelectGroundPoint" in duty_source
    assert "GroundTargetAvailable" in duty_source
    assert "GetCreatureListWithEntryInGrid" in duty_source
    assert "IsValidAttackTarget" in duty_source
    assert "IsInCombat" in duty_source
    assert "GetSpellMinRangeForTarget(nullptr, placementSpell)" in duty_source
    assert "GetSpellMaxRangeForTarget(nullptr, placementSpell)" in duty_source
    assert "ActorToGroundDistance" in duty_source
    assert "ActorRangeValid" in duty_source
    assert "ActorLineOfSight" in duty_source
    assert "IsWithinLOS" in duty_source
    assert "OwnedMushroomHasNativeRangeCandidate" in duty_source
    assert "GetAllMinionsByEntry" in duty_source
    assert "livePillarVisible" in duty_source
    assert "state.LivePillarVisible" in duty_source
    assert "bot->FindNearestCreature" in duty_source
    assert "magmaw_lava_spawn_ground_target_unavailable" in resolver
    assert "never fall back to the hostile" in resolver
    assert "MagmawWildMushroomNative event=detonate" in druid_spells
    assert "MagmawWildMushroomNative event=damage_cast" in druid_spells
    assert "caster->CastSpell(\n                    Position{ mushroom->GetPositionX(), mushroom->GetPositionY(), mushroom->GetPositionZ() },\n                    SPELL_DRUID_WILD_MUSHROOM_DAMAGE, true)" in druid_spells
    assert "event=damage_targets" in druid_magmaw_spells
    assert "event=nearby_targets" in druid_magmaw_spells
    assert "probe_radius=12.000 native_radius" in druid_magmaw_spells
    # This hook observes selection; assignments cannot enlarge a player spell.
    assert "MagmawParasiteGroundRadius" not in druid_magmaw_spells
    assert "effectiveRadius" not in druid_magmaw_spells
    assert "Cell::VisitAllObjects" in druid_magmaw_spells
    assert "distance_2d" in druid_magmaw_spells
    assert "CalcRadius(" in druid_magmaw_spells
    assert "SpellTargetIndex::TargetB" in druid_magmaw_spells
    assert "targets.push_back" not in druid_magmaw_spells
    assert "targets.insert" not in druid_magmaw_spells
    assert "targets.remove" not in druid_magmaw_spells
    assert "TARGET_UNIT_DEST_AREA_ENEMY" in druid_magmaw_spells
    assert "spell_dru_wild_mushroom_damage" in sql
    assert "GetHomePosition" not in duty_source
    assert "PillarOfFlameEntry" in duty_source
    assert "FindNearestCreature" in duty_source
    assert "GetHeight" in duty_source
    assert "parasite->GetPositionX()" in duty_source
    assert "parasite->GetPositionY()" in duty_source
    assert "parasite->GetExactDist" in duty_source
    assert "groundX = pillar" not in duty_source
    assert "groundY = pillar" not in duty_source
    assert "groundZ = map->GetHeight" not in duty_source
    assert "GroundTargetX = point.X" in duty_source
    assert "GroundTargetY = point.Y" in duty_source
    assert "GroundTargetZ = point.Z" in duty_source
    assert "VMAP::ModelIgnoreFlags::M2" in duty_source
    assert "AllowMagmawBalanceMushroomSplash" in executor
    assert "prepull_only" in duty_source
