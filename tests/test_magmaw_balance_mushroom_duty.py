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


def _compile_and_run(tmp_path: Path, name: str, body: str) -> None:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(body, encoding="utf-8")
    result = subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-Isrc/server/game", "-Isrc/common", str(source), "-o", str(binary)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    run = subprocess.run([str(binary)], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_ground_selector_uses_live_ring_parasite_and_fails_closed(tmp_path: Path):
    _compile_and_run(tmp_path, "magmaw_balance_ground_selector", r"""
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
#include <cassert>
#include <cmath>
#include <vector>

using Duty = BotEncounter::MagmawBalanceMushroomDuty;

// Two engaged companions inside the six-yard envelope of the ring anchor.
// They carry no actor line of sight, so they add density but can never be
// selected as the anchor themselves.
static std::vector<Duty::GroundCandidate> WithCompanions(
    std::vector<Duty::GroundCandidate> candidates, Duty::GroundCandidate anchor)
{
    for (int i = 0; i != 2; ++i)
    {
        Duty::GroundCandidate companion = anchor;
        companion.ParasiteGuid = 900 + i;
        companion.ParasiteX = anchor.GroundX + (i ? 1.0f : -1.0f);
        companion.ParasiteY = anchor.GroundY + 1.0f;
        companion.ParasiteZ = anchor.GroundZ;
        companion.GroundX = companion.ParasiteX;
        companion.GroundY = companion.ParasiteY;
        companion.ParasiteToGroundDistance = 0.0f;
        companion.ActorLineOfSight = false;
        candidates.push_back(companion);
    }
    return candidates;
}

int main()
{
    Duty::GroundPoint point;

    // Parasites occupy the observed seven-yard ring.  The projected floor
    // point stays directly below one live engaged parasite and is inside the
    // child spell's native six-yard three-dimensional envelope.
    Duty::GroundCandidate ring;
    ring.ParasiteGuid = 22;
    ring.ParasiteX = 7.0f;
    ring.ParasiteY = 0.0f;
    ring.ParasiteZ = 5.5f;
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
    assert(Duty::SelectGroundPoint(WithCompanions({ring}, ring), 6.0f, point));
    assert(point.ParasiteGuid == 22);
    assert(point.X == 7.0f && point.Y == 0.0f && point.Z == 0.0f);
    assert(point.ParasiteHits == 3);

    // A lower-guid high-Z or otherwise invalid projection cannot win over a
    // lawful candidate, and a high-Z-only set fails closed.
    Duty::GroundCandidate highZ = ring;
    highZ.ParasiteGuid = 1;
    highZ.ParasiteZ = 9.0f;
    highZ.ParasiteToGroundDistance = 9.0f;
    assert(Duty::SelectGroundPoint(WithCompanions({highZ, ring}, ring), 6.0f, point));
    assert(point.ParasiteGuid == 22);
    highZ.GroundProjectionValid = false;
    assert(!Duty::SelectGroundPoint(WithCompanions({highZ}, highZ), 6.0f, point));

    // Discovery radius is not cast authority: an actor-range or destination
    // LOS failure is rejected before it can preempt the ordinary rotation.
    Duty::GroundCandidate actorRange = ring;
    actorRange.ParasiteGuid = 2;
    actorRange.ActorRangeValid = false;
    assert(Duty::SelectGroundPoint(WithCompanions({actorRange, ring}, ring), 6.0f, point));
    assert(point.ParasiteGuid == 22);
    Duty::GroundCandidate actorLos = ring;
    actorLos.ParasiteGuid = 3;
    actorLos.ActorLineOfSight = false;
    assert(Duty::SelectGroundPoint(WithCompanions({actorLos, ring}, ring), 6.0f, point));
    assert(point.ParasiteGuid == 22);
    actorRange.ActorLineOfSight = false;
    assert(!Duty::SelectGroundPoint(WithCompanions({actorRange}, actorRange), 6.0f, point));

    // Dead, non-attackable, or non-engaged parasites are never lawful; no
    // parasite at all also leaves ordinary rotation available.
    Duty::GroundCandidate dead = ring;
    dead.Live = false;
    assert(!Duty::SelectGroundPoint(WithCompanions({dead}, dead), 6.0f, point));
    Duty::GroundCandidate illegal = ring;
    illegal.Attackable = false;
    assert(!Duty::SelectGroundPoint(WithCompanions({illegal}, illegal), 6.0f, point));
    Duty::GroundCandidate unengaged = ring;
    unengaged.Engaged = false;
    assert(!Duty::SelectGroundPoint(WithCompanions({unengaged}, unengaged), 6.0f, point));
    assert(!Duty::SelectGroundPoint({}, 6.0f, point));

    // Candidate order is not an authority: equal lawful observations choose
    // the stable lower GUID.
    Duty::GroundCandidate tie = ring;
    tie.ParasiteGuid = 11;
    assert(Duty::SelectGroundPoint(WithCompanions({ring, tie}, ring), 6.0f, point));
    assert(point.ParasiteGuid == 11);
}
""")


def test_placement_requires_three_parasites_in_native_radius(tmp_path: Path):
    """DPS-066: 1-2 parasites refuse placement, 3 allow it, densest wins."""
    _compile_and_run(tmp_path, "magmaw_balance_placement_threshold", r"""
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
#include <cassert>
#include <vector>

using Duty = BotEncounter::MagmawBalanceMushroomDuty;

static Duty::GroundCandidate Parasite(uint64 guid, float x, float y,
    bool anchor = true)
{
    Duty::GroundCandidate candidate;
    candidate.ParasiteGuid = guid;
    candidate.ParasiteX = candidate.GroundX = x;
    candidate.ParasiteY = candidate.GroundY = y;
    candidate.ParasiteZ = candidate.GroundZ = 210.0f;
    candidate.ParasiteToGroundDistance = 0.0f;
    candidate.ActorToGroundDistance = 25.0f;
    candidate.Live = candidate.Attackable = candidate.Engaged = true;
    candidate.GroundProjectionValid = true;
    candidate.ActorRangeValid = true;
    candidate.ActorLineOfSight = anchor;
    return candidate;
}

int main()
{
    static_assert(Duty::RequiredParasiteHits == 3, "DPS-066 threshold");
    float const radius = 6.0f;  // native 78777 TargetB radius (SpellRadius 29)
    Duty::GroundPoint point;
    uint32 hits = 99;

    // One lone parasite in range: the historical single-parasite third set.
    assert(!Duty::SelectGroundPoint({Parasite(1, 0, 0)}, radius, point, &hits));
    assert(hits == 1);

    // Two parasites inside the radius are still refused and reported.
    std::vector<Duty::GroundCandidate> two{Parasite(1, 0, 0), Parasite(2, 3, 0)};
    assert(!Duty::SelectGroundPoint(two, radius, point, &hits));
    assert(hits == 2);

    // A third parasite outside the radius of every anchor does not qualify.
    std::vector<Duty::GroundCandidate> spread = two;
    spread.push_back(Parasite(3, 20, 0));
    assert(!Duty::SelectGroundPoint(spread, radius, point, &hits));
    assert(hits == 2);

    // Three inside the radius of one lawful anchor allow placement there.
    std::vector<Duty::GroundCandidate> three = two;
    three.push_back(Parasite(3, 0, 5.9f));
    assert(Duty::SelectGroundPoint(three, radius, point, &hits));
    assert(hits == 3 && point.ParasiteHits == 3);
    assert(point.ParasiteGuid == 1 && point.X == 0.0f && point.Y == 0.0f);

    // The radius is three-dimensional, as in the native area search.
    std::vector<Duty::GroundCandidate> raised = two;
    Duty::GroundCandidate above = Parasite(3, 0, 1);
    above.ParasiteZ = 216.5f;
    raised.push_back(above);
    assert(!Duty::SelectGroundPoint(raised, radius, point, &hits));

    // Dead, non-attackable or unengaged parasites add no density.
    for (int invalid = 0; invalid != 3; ++invalid)
    {
        std::vector<Duty::GroundCandidate> weak = two;
        Duty::GroundCandidate extra = Parasite(3, 1, 1, false);
        if (invalid == 0) extra.Live = false;
        if (invalid == 1) extra.Attackable = false;
        if (invalid == 2) extra.Engaged = false;
        weak.push_back(extra);
        assert(!Duty::SelectGroundPoint(weak, radius, point));
    }
    // A companion without actor LOS still counts as a hit, not as an anchor.
    std::vector<Duty::GroundCandidate> blockedCompanion = two;
    blockedCompanion.push_back(Parasite(3, 1, 1, false));
    assert(Duty::SelectGroundPoint(blockedCompanion, radius, point));
    assert(point.ParasiteGuid != 3);

    // The densest lawful anchor wins before distance or GUID ordering.
    std::vector<Duty::GroundCandidate> clusters{
        Parasite(1, 0, 0), Parasite(2, 2, 0), Parasite(3, 0, 2),
        Parasite(10, 40, 0), Parasite(11, 42, 0), Parasite(12, 40, 2),
        Parasite(13, 41, 1)};
    assert(Duty::SelectGroundPoint(clusters, radius, point, &hits));
    assert(hits == 4 && point.ParasiteHits == 4);
    assert(point.ParasiteGuid >= 10);

    // Invalid native radius still fails closed.
    assert(!Duty::SelectGroundPoint(three, 0.0f, point, &hits) && hits == 0);
}
""")


def test_detonation_counts_native_hits_and_salvages_ending_wave(tmp_path: Path):
    """DPS-066: 3 owned-mushroom hits detonate; a dying wave forces it."""
    _compile_and_run(tmp_path, "magmaw_balance_detonation_threshold", r"""
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
#include <cassert>
#include <cmath>
#include <vector>

using Duty = BotEncounter::MagmawBalanceMushroomDuty;

int main()
{
    float const radius = 6.0f;
    std::vector<Duty::Point3> const mushrooms{
        {0, 0, 210}, {1, 0, 210}, {30, 0, 210}};

    // The historical 2-hit detonation: one parasite under two mushrooms.
    std::vector<Duty::Point3> one{{0.5f, 0, 210}};
    assert(Duty::CountDetonationHits(mushrooms, one, radius) == 2);
    // Four live parasites remain elsewhere: not a wave ending, so hold.
    assert(!Duty::DetonationWorthwhile(3, 2, 4));
    assert(!Duty::DetonationWorthwhile(3, 2, 3));

    // Three native damage events from the owned set allow Detonate.
    std::vector<Duty::Point3> three{{0.5f, 0, 210}, {30, 1, 210}};
    assert(Duty::CountDetonationHits(mushrooms, three, radius) == 3);
    assert(Duty::DetonationWorthwhile(3, 3, 5));
    std::vector<Duty::Point3> pack{{0, 1, 210}, {1, 1, 210}, {0.5f, -1, 210}};
    assert(Duty::CountDetonationHits(mushrooms, pack, radius) == 6);
    assert(Duty::DetonationWorthwhile(3, 6, 8));

    // Wave ending: fewer live parasites than the threshold remain, so the
    // placed set is detonated on whatever it still hits instead of wasting it.
    assert(Duty::WaveEnding(2) && Duty::WaveEnding(1) && Duty::WaveEnding(0));
    assert(!Duty::WaveEnding(3));
    assert(Duty::DetonationWorthwhile(3, 1, 2));
    assert(Duty::DetonationWorthwhile(3, 2, 1));
    // Nothing in range is never a detonation, even when the wave ends.
    assert(!Duty::DetonationWorthwhile(3, 0, 0));
    assert(!Duty::DetonationWorthwhile(3, 0, 5));
    // An incomplete set never detonates (unchanged set-size rule).
    assert(!Duty::DetonationWorthwhile(2, 6, 5));
    assert(!Duty::DetonationWorthwhile(2, 1, 1));

    // Radius is three-dimensional and invalid geometry fails closed.
    std::vector<Duty::Point3> raised{{0, 0, 216.5f}};
    assert(Duty::CountDetonationHits({{0, 0, 210}}, raised, radius) == 0);
    std::vector<Duty::Point3> edge{{6, 0, 210}};
    assert(Duty::CountDetonationHits({{0, 0, 210}}, edge, radius) == 1);
    assert(Duty::CountDetonationHits(mushrooms, pack, 0.0f) == 0);
    assert(Duty::CountDetonationHits(mushrooms, pack, NAN) == 0);
    std::vector<Duty::Point3> invalid{{NAN, 0, 210}};
    assert(Duty::CountDetonationHits(mushrooms, invalid, radius) == 0);
}
""")


def test_runtime_observation_wires_thresholds_into_the_duty():
    duty_source = DUTY_SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    observe = duty_source[duty_source.index("MagmawBalanceMushroomState ObserveMagmawBalanceMushroomState("):]
    observe = observe[:observe.index("\n}\n")]
    # Placement and submission share the same thresholded selector.
    assert "SelectMagmawBalanceMushroomGroundPoint(\n        bot, point, &state.GroundParasiteHits)" in observe
    assert "SelectMagmawBalanceMushroomGroundPoint(bot, point))" in duty_source
    # Detonation readiness is the pure rule over native hits and live wave size.
    assert "MagmawBalanceMushroomDuty::DetonationWorthwhile(" in observe
    assert "state.OwnedMushroomHasNativeRangeCandidate = detonation.Hits > 0;" in observe
    detonation = duty_source[duty_source.index("bool IsMagmawBalanceMushroomDetonation("):]
    detonation = detonation[:detonation.index("\n}\n")]
    assert "state.DetonationReady" in detonation
    assert "Duty::CountDetonationHits(mushroomPositions," in duty_source
    assert "&observed.LiveParasites" in duty_source
    # The radius stays the native runtime value of the Detonate payload.
    assert "WildMushroomDamageSpellId" in duty_source
    assert "CalcRadius(" in duty_source
    assert "RequiredParasiteHits = 3;" in header
    assert "Wild Mushroom: Detonate 88751" in header
    assert "magmaw_mushroom_parasite_density_below_threshold" in duty_source
    assert "magmaw_mushroom_parasite_hits_below_threshold" in duty_source
    # Existing safety rules stay in the lawful anchor predicate.
    for rule in ("candidate.ActorRangeValid", "candidate.ActorLineOfSight",
                 "candidate.GroundProjectionValid", "candidate.Engaged"):
        assert rule in header


def test_pinned_dbc_detonate_payload_radius():
    import hashlib
    import struct
    import pytest

    effect_path = ROOT / "data/dbc/enUS/SpellEffect.dbc"
    radius_path = ROOT / "data/dbc/enUS/SpellRadius.dbc"
    if not effect_path.exists() or not radius_path.exists():
        pytest.skip("local 4.3.4 DBC extraction is not present")

    def dbc(path: Path):
        data = path.read_bytes()
        _, records, fields, size, _ = struct.unpack("<4s4I", data[:20])
        return ([data[20 + i * size:20 + (i + 1) * size] for i in range(records)],
                fields, hashlib.sha256(data).hexdigest())

    effects, fields, effect_sha = dbc(effect_path)
    radii, _, radius_sha = dbc(radius_path)
    assert effect_sha == "e3d9a470bbcb5cea4e3f2947911a908b816cc60e6ffeb9f70b4cfb123bad6252"
    assert radius_sha == "7f72b397dd4463761e2d83253ad92ce64a7aef769698846ba6174e37b5642af1"
    radius = {}
    for row in radii:
        entry, minimum, _, maximum = struct.unpack("<Ifff", row[:16])
        radius[entry] = (minimum, maximum)
    by_spell = {}
    for row in effects:
        values = struct.unpack(f"<{fields}I", row[:fields * 4])
        # SpellEffectEntry: 1 Effect, 15/16 radius indexes, 22/23 targets,
        # 24 SpellID, 25 EffectIndex.
        by_spell.setdefault(values[24], {})[values[25]] = values
    detonate = by_spell[88751]
    assert set(detonate) == {0}
    # Detonate is a caster-targeted dummy with no radius of its own.
    assert detonate[0][1] == 3 and detonate[0][22] == 1
    assert detonate[0][15] == 0 and detonate[0][16] == 0
    damage = by_spell[78777][0]
    assert damage[1] == 2 and damage[22] == 87 and damage[23] == 16
    assert damage[15] == 0 and damage[16] == 29
    assert radius[29] == (6.0, 6.0)


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
