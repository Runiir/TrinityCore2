"""BWD 10N round 4: cross-boss healer and class-rotation repairs.

Evidence (label blackwing_descent_10n-r03-a3864fcf6d, Maloriak batch cd3009
combat log, and the round 4 Omnotron/Maloriak/Chimaeron/Nefarian/Magmaw
handoffs):

* Generic raid heal: the target was the lowest member anywhere, with no range
  or line-of-sight test, so an out-of-range lowest ally blocked every heal
  (Discipline priest idle 242.0-259.1 s while the Feral at 34-9% stood 56 yd
  away and five allies at 45-51% stood within 20 yd).
* Assassination: Slice and Dice recast 10 times against 6 Envenoms per kill;
  no Envenom refreshed Slice and Dice (Cut to the Chase). Fan of Knives still
  submitted 8 times through the range-recovery lane despite the user rule.
* Demonology: Hellfire admitted by the enemies around the target and never
  stopped; the Felguard followed only owner spell casts.
* Healer mana: no heartbeat readout.

Every behavior change is canonical-composition raid scope only, so Stonecore,
the Phase 8 calibrations and the legacy Magmaw b5 shard keep their decisions.
"""
from __future__ import annotations

import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
INCLUDES = [flag for path in ("src/server/game", "src/server/game/Entities/Object", "src/common",
                              "src/common/Utilities", "src/common/Logging", "src/common/Debugging")
            for flag in ("-I", str(ROOT / path))]


def _run(tmp_path: Path, name: str, program: str, extra_includes: tuple[Path, ...] = ()) -> str:
    # extra_includes come first, so a scratch copy of a header can shadow the checkout's
    # (used to prove a regression fails against the pre-fix behaviour).
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(program)
    shadow = [flag for path in extra_includes for flag in ("-I", str(path))]
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *shadow, *INCLUDES,
                    str(source), "-o", str(binary)], check=True)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def _source(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


HEAL_TRIAGE = r'''
#include "Bots/BotRaidHealTriage.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using namespace BotRaidHealTriage;
std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }
Member m(uint64 guid, float hp, bool inRange, bool tank = false, bool attacked = false, bool alive = true) {
    Member x; x.Guid = guid; x.HealthPct = hp; x.InRange = inRange; x.Tank = tank;
    x.UnderAttack = attacked; x.Alive = alive; return x;
}
int main() {
    auto allLos = [](uint64) { return true; };
    // r03 cd3009 243-259 s: the Feral off-tank (2) is lowest but 56 yd away;
    // five allies at 45-51% are in range. The legacy rule picked the Feral.
    std::vector<Member> maloriak = { m(1, 61, true, true), m(2, 34, false, true, true),
        m(4, 45, true), m(6, 47, true), m(7, 50, true), m(8, 47, true), m(9, 51, true) };
    assert(LegacyLowest(maloriak)->Guid == 2);
    auto pick = Select(maloriak, allLos);
    assert(pick && pick->Guid == 4 && pick->Reachable && pick->HealthPct == 45.0f);
    // A tank under attack counts 10 points lower: 55% tank before a 50% dps,
    // but not before a 44% dps; an idle tank has no bonus.
    std::vector<Member> tank = { m(1, 55, true, true, true), m(5, 50, true) };
    assert(Select(tank, allLos)->Guid == 1);
    tank.push_back(m(6, 44, true));
    assert(Select(tank, allLos)->Guid == 6);
    std::vector<Member> idle = { m(1, 55, true, true, false), m(5, 50, true) };
    assert(Select(idle, allLos)->Guid == 5);
    // LOS is asked only for injured in-range members, most urgent first, and
    // stops at the first that passes.
    std::vector<uint64> asked;
    auto blocked4 = [&asked](uint64 guid) { asked.push_back(guid); return guid != 4; };
    pick = Select(maloriak, blocked4);
    assert(pick->Guid == 6 && asked.size() == 2 && asked[0] == 4 && asked[1] == 6);
    // Nobody reachable: the legacy target, flagged unreachable.
    std::vector<Member> far = { m(1, 80, false), m(2, 30, false), m(3, 99, true) };
    pick = Select(far, allLos);
    assert(pick && pick->Guid == 2 && !pick->Reachable);
    auto noLos = [](uint64) { return false; };
    assert(Select(maloriak, noLos)->Guid == 2 && !Select(maloriak, noLos)->Reachable);
    // Healthy raid (>= 94%) or only dead injured members: no target.
    std::vector<Member> healthy = { m(1, 94, true), m(2, 100, true), m(3, 10, true, false, false, false) };
    assert(!Select(healthy, allLos) && !LegacyLowest(healthy));
    std::puts("ok");
}
'''


def test_heal_triage_takes_the_most_endangered_reachable_ally(tmp_path: Path) -> None:
    assert _run(tmp_path, "heal_triage", HEAL_TRIAGE).strip() == "ok"


HEAL_TRIAGE_BOARD = r'''
#include "Bots/BotRaidHealTriage.h"
#include <cassert>
#include <cstdio>
#include <string>
using namespace BotEncounter;
using namespace BotRaidHealTriage;
std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

static ObjectGuid Bot(uint32 slot) { return ObjectGuid(HighGuid::Player, 30500 + slot); }
static ActorSnapshot Ally(uint32 slot, char const* role, float hp) {
    ActorSnapshot a; a.Guid = Bot(slot); a.Kind = ActorKind::Player; a.Role = role;
    a.HealthPct = hp; a.Alive = true; return a;
}
// Nefarian's animated bone warrior (41918): a summoned hostile that attacks `victim`.
static ActorSnapshot Warrior(uint32 counter, ObjectGuid victim) {
    ActorSnapshot a; a.Guid = ObjectGuid(HighGuid::Unit, 41918, counter); a.Entry = 41918;
    a.Kind = ActorKind::Summon; a.Alive = a.Attackable = a.Selectable = true;
    a.HealthPct = 100.0f; a.VictimGuid = victim; return a;
}
// The reviewer's board: a Feral tank at 58% and a reachable DPS at 51%.
static Blackboard Board() {
    Blackboard board;
    board.Players = { Ally(1, "tank", 58.0f), Ally(2, "dps", 51.0f), Ally(3, "healer", 100.0f) };
    return board;
}
template <typename InRange>
static uint64 PickIn(Blackboard const& board, InRange inRange) {
    auto choice = SelectFromBoard(board, inRange, [](uint64) { return true; });
    return choice ? choice->Guid : 0;
}
static uint64 Pick(Blackboard const& board) {
    return PickIn(board, [](ObjectGuid) { return true; });
}
int main() {
    uint64 const tank = Bot(1).GetRawValue();
    uint64 const dps = Bot(2).GetRawValue();
    // Nobody attacks the tank: 58% is not more urgent than the DPS at 51%.
    { auto b = Board(); assert(Pick(b) == dps); }
    // The bone warriors attack the Feral tank: 58 - 10 = 48 beats 51, though
    // the tank is only in board.Summons (the legacy hostile scan missed it).
    { auto b = Board(); b.Summons.push_back(Warrior(1, Bot(1)));
      assert(IsAttackedByHostile(b, Bot(1)) && !IsAttackedByHostile(b, Bot(2)));
      assert(Pick(b) == tank); }
    // Several warriors, or the warrior among the boss's other summons: still the tank.
    { auto b = Board(); b.Summons.push_back(Warrior(1, Bot(2))); b.Summons.push_back(Warrior(2, Bot(1)));
      assert(Pick(b) == tank); }
    // Ordinary hostiles keep working.
    { auto b = Board(); ActorSnapshot boss = Warrior(1, Bot(1)); boss.Kind = ActorKind::Hostile;
      b.Hostiles.push_back(boss); assert(Pick(b) == tank); }
    // A summon that cannot attack the tank does not count: dead, a collapsed
    // (unselectable, unattackable) warrior, a friendly or non-attackable summon
    // and a bot's own pet (kind Pet), even when it names the tank as victim.
    { auto b = Board(); auto w = Warrior(1, Bot(1)); w.Alive = false; b.Summons.push_back(w);
      assert(!IsAttackedByHostile(b, Bot(1)) && Pick(b) == dps); }
    { auto b = Board(); auto w = Warrior(1, Bot(1)); w.Attackable = w.Selectable = false;
      b.Summons.push_back(w); assert(!IsAttackedByHostile(b, Bot(1)) && Pick(b) == dps); }
    { auto b = Board(); auto w = Warrior(1, Bot(1)); w.Kind = ActorKind::Pet; b.Summons.push_back(w);
      assert(!IsAttackedByHostile(b, Bot(1)) && Pick(b) == dps); }
    // A summon with no victim, or attacking another ally, does not mark the tank.
    { auto b = Board(); b.Summons.push_back(Warrior(1, ObjectGuid()));
      b.Summons.push_back(Warrior(2, Bot(3))); assert(Pick(b) == dps); }
    // Only a tank gets the bonus: a DPS under attack by a summon stays at its health.
    { auto b = Board(); b.Players[1].HealthPct = 55.0f; b.Players.push_back(Ally(4, "dps", 53.0f));
      b.Summons.push_back(Warrior(1, Bot(2))); assert(Pick(b) == Bot(4).GetRawValue()); }
    // Range still rules: an attacked tank out of heal range is not chosen.
    { auto b = Board(); b.Summons.push_back(Warrior(1, Bot(1)));
      assert(PickIn(b, [](ObjectGuid guid) { return guid != Bot(1); }) == dps); }
    // A play cohort's human tank (ExternalPlayers) is weighed the same way.
    { Blackboard b; b.Players = { Ally(2, "dps", 51.0f) }; b.ExternalPlayers = { Ally(1, "tank", 58.0f) };
      assert(Pick(b) == dps); b.Summons.push_back(Warrior(1, Bot(1))); assert(Pick(b) == tank); }
    std::puts("ok");
}
'''


def test_tank_under_attack_by_hostile_summons_is_weighted(tmp_path: Path) -> None:
    assert _run(tmp_path, "heal_triage_board", HEAL_TRIAGE_BOARD).strip() == "ok"


def test_generic_raid_heal_uses_triage_only_in_canonical_raids() -> None:
    candidates = _source("BotWorldPopulationMgrUpdateBotKernelCandidates.cpp")
    live = _source("BotRaidHealTriageLive.h")
    support = candidates.index('support.Key = "raid.support.heal."')
    selection = candidates[candidates.rindex("ObjectGuid healTargetGuid =", 0, support):support]
    triage = selection.index("BotRaidHealTriage::SelectForHealer(context.Bot, *Cohort().EncounterSnapshot)")
    scope = selection.index("BotCanonicalRaidScope::IsCanonicalRaid(")
    assert "Cohort().Raid.RaidInstance, Cohort().Config.ValidationRouteScenarioId))" in selection[scope:]
    # Encounter priority targets first, then the canonical triage, then the
    # unchanged legacy lowest-member loop for every other scope.
    assert selection.index("AdaptiveMaloriakPriorityHealTargetGuid") < scope < triage
    legacy = selection.index("for (BotEncounter::ActorSnapshot const& member : *members)")
    assert triage < legacy
    assert "if (member.Alive && member.HealthPct < lowestHealth)" in selection[legacy:]
    assert "healTargetGuid.IsEmpty() && BotCanonicalRaidScope::IsCanonicalRaid(" in selection
    # Native range, then native LOS for ranked candidates only; the snapshot walk
    # (and the attackers of a tank) is the pure, tested part.
    assert "healer->IsWithinDistInMap(unit, HealRangeYards)" in live
    assert "healer->IsWithinLOSInMap(unit)" in live
    assert "return SelectFromBoard(board," in live
    pure = _source("BotRaidHealTriage.h")
    assert "member.UnderAttack = IsAttackedByHostile(board, actor.Guid);" in pure
    assert "hostile.Alive && hostile.VictimGuid == victim" in pure
    assert '#include "Bots/BotRaidHealTriageLive.h"' in candidates


ASSASSINATION = r'''
#include "Bots/BotRaidRotationOverrides.h"
#include <cassert>
#include <cstdio>
#include <string>
using namespace BotRaidCanonicalAssassination;
// The live world-DB Assassination rows (2026_07_21_02 + 2026_07_22_03 +
// 2026_08_17_01 + 2026_07_28_01), as the resolver loads them.
BotActionProfileSpell row(uint32 id, BotCombatActionCategory cat, char const* tags, uint8 bucket, uint32 sort,
    char const* selector, float maxRange) {
    BotActionProfileSpell s; s.SpellId = id; s.Category = cat; s.MechanicTags = tags; s.PriorityBucket = bucket;
    s.SortOrder = sort; s.TargetSelector = selector; s.MaxRange = maxRange; s.MinEnemies = 1; return s;
}
BotClassSpecActionProfile assassination(char const* spec = "assassination_rogue") {
    BotClassSpecActionProfile p; p.ClassId = 4; p.SpecTag = spec; p.Role = "dps"; p.MaxRange = 5.0f;
    auto snd = row(5171, BotCombatActionCategory::Buff, "slice_and_dice,self,haste,initial_finisher", 2, 40, "self", 0);
    snd.ForbiddenSelfAura = 5171; snd.MinComboPoints = 1;
    auto rupture = row(1943, BotCombatActionCategory::Dot, "rupture,owned_bleed,venomous_wounds,maintain_owned_aura", 3, 50, "enemy", 5);
    rupture.MaintainAuraId = 1943; rupture.RefreshAuraBelowMs = 2000; rupture.MinComboPoints = 4; rupture.RequiresMeleeRange = true;
    auto envenom = row(32645, BotCombatActionCategory::Spender, "envenom,primary_finisher,cut_to_the_chase", 4, 70, "enemy", 5);
    envenom.MinComboPoints = 4; envenom.RequiresMeleeRange = true; envenom.DamageWeight = 1.10f;
    auto mutilate = row(1329, BotCombatActionCategory::Builder, "mutilate,primary_builder,combo_builder", 5, 80, "enemy", 5);
    mutilate.MaxComboPoints = 3; mutilate.RequiresMeleeRange = true;
    auto fok = row(51723, BotCombatActionCategory::Aoe, "fan_of_knives,aoe,poison_application", 9, 90, "enemy", 10);
    fok.MinEnemies = 2; fok.MinPrimaryPowerPct = 0.85f;
    auto cold = row(14177, BotCombatActionCategory::OffensiveCooldown, "cold_blood,self,next_finisher", 1, 30, "self", 0);
    cold.MinComboPoints = 5; cold.MaxComboPoints = 5;
    p.Spells = { cold, snd, rupture, envenom, mutilate, fok };
    return p;
}
// The profile gates the rows use, as EvaluateCompiledConditions and the
// admission read them, and the resolver's bucket-first choice.
struct State { uint8 cp; int sndMs; int ruptureMs; }; // -1: aura absent
uint32 choose(BotClassSpecActionProfile const& p, State s) {
    BotActionProfileSpell const* best = nullptr;
    for (auto const& r : p.Spells) {
        if (r.SpellId == 14177 || r.SpellId == 51723) continue; // off-GCD / energy-gated extras
        if (r.RequiredSelfAura == 5171 && s.sndMs < 0) continue;
        if (r.ForbiddenSelfAura == 5171 && s.sndMs >= 0) continue;
        if (r.RequiredSelfAura == 5171 && r.MaxSelfAuraRemainingMs && s.sndMs > int(r.MaxSelfAuraRemainingMs)) continue;
        if (r.MaintainAuraId == 1943 && s.ruptureMs >= 0 && s.ruptureMs > int(r.RefreshAuraBelowMs)) continue;
        if (s.cp < r.MinComboPoints || (r.MaxComboPoints && s.cp > r.MaxComboPoints)) continue;
        if (r.SpellId != 1329 && s.cp == 0) continue; // finishers need points
        if (!best || r.PriorityBucket < best->PriorityBucket
            || (r.PriorityBucket == best->PriorityBucket && r.SortOrder < best->SortOrder)) best = &r;
    }
    return best ? best->SpellId : 0;
}
int main() {
    std::string const tag = ",canonical_raid_rotation_20260927";
    auto legacy = assassination();
    // Raid scope alone (legacy BWD rosters, Vendetta only) keeps every row.
    BotRaidRotationOverrides::Apply(legacy);
    assert(legacy.Spells.size() == 6);
    auto before = assassination();
    auto p = assassination();
    assert(BotRaidRotationOverrides::ApplyCanonical(p) == 2); // FoK removed, refresh added
    assert(p.Spells.size() == 6);
    for (auto const& r : p.Spells) assert(r.SpellId != 51723);
    auto const& refresh = p.Spells.back();
    assert(refresh.SpellId == 32645 && refresh.Category == BotCombatActionCategory::Spender);
    assert(refresh.MechanicTags == std::string("envenom,slice_and_dice_refresh,cut_to_the_chase") + tag);
    assert(refresh.PriorityBucket == 2 && refresh.SortOrder == 45);
    assert(refresh.MinComboPoints == 2 && refresh.MaxComboPoints == 0);
    assert(refresh.RequiredSelfAura == 5171 && refresh.MaxSelfAuraRemainingMs == 3000 && !refresh.ForbiddenSelfAura);
    assert(refresh.TargetSelector == "enemy" && refresh.RequiresMeleeRange && refresh.MaxRange == 5.0f);
    assert(refresh.DamageWeight > 1.09f && refresh.DamageWeight < 1.11f);
    // The pinned rows are otherwise unchanged.
    for (size_t i = 0; i < 5; ++i) {
        assert(p.Spells[i].SpellId == before.Spells[i].SpellId);
        assert(p.Spells[i].MechanicTags == before.Spells[i].MechanicTags);
        assert(p.Spells[i].MinComboPoints == before.Spells[i].MinComboPoints);
        assert(p.Spells[i].PriorityBucket == before.Spells[i].PriorityBucket);
    }
    assert(BotRaidRotationOverrides::ApplyCanonical(p) == 0 && p.Spells.size() == 6);
    auto combat = assassination("combat_rogue");
    assert(BotRaidRotationOverrides::ApplyCanonical(combat) == 0 && combat.Spells.size() == 6);

    // The Assassination standard, pinned rows (before) against canonical rows.
    // Slice and Dice at 2.5 s with 2 points: before, Mutilate and the buff falls
    // off (then a short Slice and Dice eats the points); now Envenom refreshes it.
    assert(choose(before, {2, 2500, 12000}) == 1329);
    assert(choose(p, {2, 2500, 12000}) == 32645);
    // With 4 points and Slice and Dice at 2 s it still refreshes first.
    assert(choose(p, {4, 2000, 12000}) == 32645);
    // Slice and Dice down: cast it (opener or lost buff).
    assert(choose(p, {1, -1, 12000}) == 5171 && choose(before, {1, -1, 12000}) == 5171);
    // Buff up: Rupture missing or below 2 s at 4+ points first.
    assert(choose(p, {4, 10000, -1}) == 1943 && choose(p, {5, 10000, 1500}) == 1943);
    // Buff and Rupture up: Envenom at 4-5, Mutilate below 4.
    assert(choose(p, {4, 10000, 9000}) == 32645 && choose(p, {5, 10000, 9000}) == 32645);
    assert(choose(p, {3, 10000, 9000}) == 1329 && choose(p, {0, 10000, 9000}) == 1329);
    // One point with Slice and Dice at 2.5 s: build, do not spend.
    assert(choose(p, {1, 2500, 9000}) == 1329);
    std::puts("ok");
}
'''


def test_canonical_assassination_refreshes_slice_and_dice_and_never_fans(tmp_path: Path) -> None:
    assert _run(tmp_path, "assassination", ASSASSINATION).strip() == "ok"


def test_assassination_rows_come_only_through_apply_canonical() -> None:
    rotation = _source("BotRaidCanonicalClassRotation.h")
    overrides = _source("BotRaidRotationOverrides.h")
    assert "BotRaidCanonicalAssassination::Apply(profile, tag)" in rotation
    assert "DisableFanOfKnives" not in rotation
    raid_only = overrides[overrides.index("inline uint32 Apply(BotClassSpecActionProfile& profile)"):
                          overrides.index("inline constexpr char const* CanonicalScopeTag")]
    assert "BotRaidCanonical" not in raid_only
    callers = sorted(path.name for path in (ROOT / "src").rglob("*")
                     if path.suffix in (".h", ".cpp")
                     and "BotRaidCanonicalAssassination::" in path.read_text(errors="replace"))
    assert callers == ["BotRaidCanonicalClassRotation.h"]
    # The canonical rogue has Cut to the Chase (51667), which makes Envenom
    # refresh Slice and Dice.
    targets = (ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json").read_text()
    start = targets.index('"spec_target_id": "assassination_rogue"')
    assert '"spell_id": 51667' in targets[start:start + 3000]


HELLFIRE = r'''
#include "Bots/BotRaidDemonologyHellfire.h"
#include <cassert>
#include <cstdio>
using namespace BotRaidDemonologyHellfire;
int main() {
    assert(Hellfire == 1949 && Radius == 10.0f);
    // Start needs three engaged enemies around the warlock itself.
    assert(!StartAllowed(0) && !StartAllowed(2) && StartAllowed(3) && StartAllowed(7));
    // Stop once fewer than two remain; only Hellfire is ever stopped.
    assert(ShouldStop(1949, 0) && ShouldStop(1949, 1));
    assert(!ShouldStop(1949, 2) && !ShouldStop(1949, 5));
    assert(!ShouldStop(689, 0) && !ShouldStop(0, 0));
    // No start can be stopped at once: every admitted start keeps the channel.
    for (uint32 n = 0; n < 10; ++n)
        assert(!(StartAllowed(n) && ShouldStop(1949, n)));
    std::puts("ok");
}
'''


def test_hellfire_start_and_stop_thresholds(tmp_path: Path) -> None:
    assert _run(tmp_path, "hellfire", HELLFIRE).strip() == "ok"


HELLFIRE_GEOMETRY = r'''
#include "Bots/BotRaidDemonologyHellfire.h"
#include <cassert>
#include <cstdio>
#include <vector>
using namespace BotRaidDemonologyHellfire;
float Position::NormalizeOrientation(float o) { return o; }

// The size-aware rule the count used before (WorldObject::IsWithinDistInMap:
// 3D centre distance below the radius plus both combat reaches).
static bool SizeAware(Position const& warlock, Position const& enemy, float warlockReach, float enemyReach) {
    return warlock.IsInDist(&enemy, Radius + warlockReach + enemyReach);
}
// What the start gate and the keep test count: enemies the damage spell hits.
static uint32 Count(Position const& warlock, std::vector<Position> const& enemies) {
    uint32 n = 0;
    for (Position const& enemy : enemies) if (InDamageArea(warlock, enemy)) ++n;
    return n;
}
int main() {
    assert(DamageSpell == 5857 && Radius == 10.0f);
    Position const warlock(100.0f, 200.0f, 50.0f);
    // Reviewer case: three engaged adds 12 yd away with 1.5 yd combat reaches.
    // The size-aware rule admitted them (12 < 10 + 1.5 + 1.5); the damage spell
    // hits none of them, so Hellfire neither starts nor keeps running.
    std::vector<Position> far = { Position(112.0f, 200.0f, 50.0f), Position(100.0f, 188.0f, 50.0f),
                                  Position(100.0f + 8.4853f, 200.0f + 8.4853f, 50.0f) };
    for (Position const& enemy : far) {
        assert(SizeAware(warlock, enemy, 1.5f, 1.5f));
        assert(!InDamageArea(warlock, enemy));
    }
    assert(Count(warlock, far) == 0);
    assert(!StartAllowed(Count(warlock, far)));     // no start
    assert(ShouldStop(Hellfire, Count(warlock, far))); // no keep: a running channel is cancelled
    // The same pack at 9 yd is inside: it starts and the channel keeps.
    std::vector<Position> near = { Position(109.0f, 200.0f, 50.0f), Position(100.0f, 191.0f, 50.0f),
                                   Position(91.0f, 200.0f, 50.0f) };
    assert(Count(warlock, near) == 3 && StartAllowed(3) && !ShouldStop(Hellfire, 3));
    // Two of three inside keep it (but cannot start it): the 3/2 hysteresis.
    std::vector<Position> two = { near[0], near[1], far[0] };
    assert(Count(warlock, two) == 2 && !StartAllowed(2) && !ShouldStop(Hellfire, 2));
    // The boundary is a strict 2D centre distance: 10 yd out, just under in.
    assert(!InDamageArea(warlock, Position(110.0f, 200.0f, 50.0f)));
    assert(InDamageArea(warlock, Position(109.99f, 200.0f, 50.0f)));
    // A cylinder: a height difference up to the radius, no further, whatever the
    // 2D distance. A 3D sphere would disagree (the point 9 yd away and 9 yd up
    // is 12.7 yd from the warlock, yet inside the cylinder).
    assert(InDamageArea(warlock, Position(105.0f, 200.0f, 60.0f)));
    assert(!InDamageArea(warlock, Position(105.0f, 200.0f, 60.5f)));
    assert(!InDamageArea(warlock, Position(100.0f, 200.0f, 39.5f)));
    assert(InDamageArea(warlock, Position(109.0f, 200.0f, 59.0f)));
    std::puts("ok");
}
'''


def test_hellfire_counts_only_enemies_in_the_native_damage_cylinder(tmp_path: Path) -> None:
    assert _run(tmp_path, "hellfire_geometry", HELLFIRE_GEOMETRY).strip() == "ok"


def _dbc_row(name: str, key: int, column: int = 0, also: tuple[int, int] | None = None) -> tuple[int, ...]:
    path = ROOT / "data/dbc/enUS" / name
    if not path.exists():
        pytest.skip(f"{name} is not extracted in this checkout")
    data = path.read_bytes()
    magic, records, fields, size, _ = struct.unpack_from("<4s4I", data, 0)
    assert magic == b"WDBC"
    for index in range(records):
        offset = 20 + index * size
        if struct.unpack_from("<I", data, offset + 4 * column)[0] != key:
            continue
        row = struct.unpack_from(f"<{fields}I", data, offset)
        if also is None or row[also[0]] == also[1]:
            return row
    raise AssertionError(f"{name}: no row {key}")


def test_hellfire_damage_spell_geometry_matches_the_native_data() -> None:
    # The damage spell the channel triggers is 5857 (effect 0 of Hellfire 1949).
    assert _dbc_row("SpellEffect.dbc", 1949, column=24, also=(25, 0))[21] == 5857
    spell = _dbc_row("Spell.dbc", 5857)
    effect = _dbc_row("SpellEffect.dbc", 5857, column=24, also=(25, 0))
    # TargetA DEST_CASTER (18), TargetB UNIT_DEST_AREA_ENEMY (16): the enemies come from
    # an area search around the warlock's own position.
    assert (effect[22], effect[23]) == (18, 16)
    # TargetB radius (EffectRadiusMaxIndex) 13 is 10 yd flat.
    radius = _dbc_row("SpellRadius.dbc", effect[16])
    assert struct.unpack("<3f", struct.pack("<3I", *radius[1:4])) == (10.0, 0.0, 10.0)
    # No combat-reach term: SPELL_ATTR5_TREAT_AS_AREA_EFFECT (0x8000, AttributesEx5) is unset
    # and the family is Warlock (5), not generic.
    assert not spell[6] & 0x8000
    assert _dbc_row("SpellClassOptions.dbc", spell[36])[5] == 5
    # The native check is the cylinder InDamageArea mirrors.
    native = (ROOT / "src/server/game/Spells/Spell.cpp").read_text(encoding="utf-8", errors="replace")
    assert ("_caster->IsUnit() && _spellInfo->HasAttribute(SPELL_ATTR5_TREAT_AS_AREA_EFFECT) "
            "&& _spellInfo->SpellFamilyName != SPELLFAMILY_GENERIC") in native
    assert ("target->IsWithinDist2d(_position, _range + hitboxSum) && std::abs(target->GetPositionZ() "
            "- _position->GetPositionZ()) <= (_range + hitboxSum)") in native
    shared = (ROOT / "src/server/shared/SharedDefines.h").read_text(encoding="utf-8", errors="replace")
    assert "SPELL_ATTR5_TREAT_AS_AREA_EFFECT                                = 0x00008000" in shared


def test_hellfire_start_and_keep_share_the_native_geometry_count() -> None:
    live = _source("BotRaidDemonologyHellfireLive.h")
    count = live[live.index("inline uint32 CountEngagedEnemiesInRadius"):
                 live.index("// The start gate")]
    # The native damage-spell cylinder, not a size-aware reach (IsWithinDistInMap
    # adds both combat reaches: 12 yd away with 1.5 yd reaches counted).
    assert "InDamageArea(*warlock, *unit)" in count
    assert "IsWithinDistInMap" not in live
    assert "warlock->IsInMap(unit) && warlock->IsInPhase(unit)" in count
    # One count feeds the start pre-rejection and the stop (keep) candidate.
    start = live[live.index("inline void RejectStartsWithoutPack"):]
    assert "enemies = CountEngagedEnemiesInRadius(warlock);" in start
    assert "if (!StartAllowed(uint32(enemies)))" in start
    pet = _source("BotWorldPopulationMgrAfflictionPetCombat.cpp")
    keep = pet[pet.index("void SubmitCanonicalHellfireStopCandidate("):pet.index("// The warlock pet and channel")]
    assert "BotRaidDemonologyHellfire::ShouldStop(" in keep
    assert "BotRaidDemonologyHellfire::CountEngagedEnemiesInRadius(bot)" in keep
    header = _source("BotRaidDemonologyHellfire.h")
    assert "enemy.IsInDist2d(&warlock, Radius)" in header
    assert "std::abs(enemy.GetPositionZ() - warlock.GetPositionZ()) <= Radius" in header


def test_hellfire_and_felguard_rules_are_canonical_demonology_only() -> None:
    resolver = _source("BotWorldPopulationMgrCombatResolver.cpp")
    build = resolver.index("BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile, potionHealthOwner);")
    gate = resolver[build:resolver.index("BotRaidDemonologyHellfire::RejectStartsWithoutPack(bot, candidates);", build)]
    assert 'profile.SpecTag == "demonology_warlock" && bot->GetMap() && bot->GetMap()->IsRaid()' in gate
    assert "BotCanonicalRaidScope::IsCanonicalRaid(Cohort().Raid.RaidInstance," in gate
    # Outside the potion-owner window the potion test compiles, before admission.
    assert gate.index("BotRaidCooldownReservation::RouteContext const cooldownRoute") < gate.index(
        'profile.SpecTag == "demonology_warlock"')
    assert resolver.index("RejectStartsWithoutPack(bot, candidates);") < resolver.index(
        "AdmitProfileCombatCandidates(admission);")
    live = _source("BotRaidDemonologyHellfireLive.h")
    assert "if (!StartAllowed(uint32(enemies)))\n            candidate.RejectReason = StartRejectReason;" in live
    # The admission module itself is untouched (its narrowness and pins hold).
    assert "Hellfire" not in _source("BotWorldPopulationMgrCombatResolverAdmission.cpp")
    pet = _source("BotWorldPopulationMgrAfflictionPetCombat.cpp")
    scope = pet[pet.index("bool const canonicalDemonology ="):pet.index("ObjectGuid const petTargetGuid")]
    assert 'profile.SpecTag == "demonology_warlock"' in scope
    assert "BotCanonicalRaidScope::IsCanonicalRaid(Cohort().Raid.RaidInstance," in scope
    assert "context.Bot->GetMap()->IsRaid()" in scope
    assert "if (canonicalDemonology)\n        SubmitCanonicalHellfireStopCandidate(" in scope
    # Affliction keeps its every-scope candidate; Demonology joins only canonical.
    assert '(profile.SpecTag != "affliction_warlock" && !canonicalDemonology)' in scope
    # A protected or next-encounter target is never handed to the Felguard.
    assert "IsImmediateNextValidationRouteEncounterMember(creature)" in scope
    assert "BotRaidAreaAuthority::IsProtectedEncounterTarget(" in scope
    stop = pet[pet.index("void SubmitCanonicalHellfireStopCandidate("):pet.index("// The warlock pet and channel")]
    assert "RequiredResources" not in stop  # claims no lane
    assert "bot->InterruptSpell(CURRENT_CHANNELED_SPELL);" in stop
    assert "CastSpell" not in stop


HEALER_MANA = r'''
#include "Bots/BotRaidHealerManaStatus.h"
#include <cassert>
#include <cstdio>
#include <string>
using namespace BotRaidHealerManaStatus;
int main() {
    assert(JsonField({}).empty());
    Row paladin; paladin.Guid = 11004005; paladin.Name = "Bwmalnbe"; paladin.ClassSpec = "holy_paladin";
    paladin.Present = true; paladin.Alive = true; paladin.Mana = 23456; paladin.MaxMana = 100000;
    Row priest; priest.Guid = 11004007; priest.Name = "Bw\"x"; priest.ClassSpec = "discipline_priest";
    std::string const json = JsonField({ paladin, priest });
    std::string const expected = ",\"healer_mana\":{\"schema\":\"raid_healer_mana_v1\",\"members\":["
        "{\"guid\":11004005,\"name\":\"Bwmalnbe\",\"class_spec\":\"holy_paladin\",\"present\":true,"
        "\"alive\":true,\"mana\":23456,\"max_mana\":100000,\"mana_pct\":23.5},"
        "{\"guid\":11004007,\"name\":\"Bw\\\"x\",\"class_spec\":\"discipline_priest\",\"present\":false,"
        "\"alive\":false,\"mana\":0,\"max_mana\":0,\"mana_pct\":0.0}]}";
    if (json != expected) { std::puts(json.c_str()); return 1; }
    std::puts("ok");
}
'''


def test_healer_mana_field_is_additive(tmp_path: Path) -> None:
    assert _run(tmp_path, "healer_mana", HEALER_MANA).strip() == "ok"


def test_healer_mana_is_written_only_for_canonical_raids() -> None:
    source = _source("BotWorldPopulationMgrRaidConsumablesJson.cpp")
    tail = source[source.index('raid.ValidationPrepullCheckpoint.ToJson() << "}";'):]
    scope = tail.index("if (!BotCanonicalRaidScope::IsCanonicalRaid(raid.RaidInstance,")
    assert tail.index("return;", scope) < tail.index("json << BotRaidHealerManaStatus::JsonField(healers);")
    assert 'if (slot.Role != "healer")' in tail
    # The status writer itself is untouched: the field rides the existing call.
    runtime = _source("BotWorldPopulationMgrRaidRuntime.cpp")
    assert "healer_mana" not in runtime
    assert runtime.count("AppendRaidPrepullConsumablesJson(json);") == 1


def test_changed_sources_stay_below_the_module_size_limit() -> None:
    for name in ("BotWorldPopulationMgrUpdateBotKernelCandidates.cpp",
                 "BotWorldPopulationMgrCombatResolver.cpp",
                 "BotWorldPopulationMgrAfflictionPetCombat.cpp",
                 "BotWorldPopulationMgrRaidConsumablesJson.cpp",
                 "BotRaidCanonicalClassRotation.h", "BotRaidCanonicalAssassination.h",
                 "BotRaidHealTriage.h", "BotRaidHealTriageLive.h",
                 "BotRaidDemonologyHellfire.h", "BotRaidDemonologyHellfireLive.h",
                 "BotRaidHealerManaStatus.h"):
        assert len(_source(name).splitlines()) < 1000, name
