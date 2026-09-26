"""Round 5 class item 1: the canonical druid keeps the major armor debuff on the boss.

The round 5 buff audit (raid_buff_coverage) found no canonical action profile
that applies Faerie Fire, Expose Armor or Sunder Armor. BotRaidMajorArmor.h
adds one Faerie Fire row to the canonical druid (Balance DPS or Feral tank)
through BotRaidRotationOverrides::ApplyCanonical, and the resolver admission
gates it: a boss in combat, only while the debuff or an equivalent at full
strength is missing or about to expire, never a range-recovery movement.
Stonecore, the Phase 8 calibrations and the legacy Magmaw roster (druid 30001
is Balance) keep their rows and decisions.
"""
from __future__ import annotations

import json
import re
import struct
import subprocess
from pathlib import Path

import pytest

from tests.combat_resolver_source import combat_resolver_source

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
HEADER = BOTS / "BotRaidMajorArmor.h"
ADMISSION = BOTS / "BotWorldPopulationMgrCombatResolverAdmission.cpp"
DBC = ROOT / "data/dbc/enUS"
INCLUDES = ["-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common")]
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
LEGACY_SHARDS = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
TRAINERS = ROOT / "dataset/world_knowledge/trainers.jsonl"


def _run(tmp_path: Path, name: str, program: str) -> str:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
                    str(source), "-o", str(binary)], check=True)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def _constant(name: str) -> int:
    match = re.search(rf"inline constexpr uint(?:8|32) {name} = (\d+);", HEADER.read_text())
    assert match, name
    return int(match.group(1))


def _table(name: str) -> dict[int, tuple[int, ...]]:
    blob = (DBC / name).read_bytes()
    count, fields, size, _strings = struct.unpack_from("<4I", blob, 4)
    records = blob[20:20 + count * size]
    rows = {}
    for index in range(count):
        values = struct.unpack_from(f"<{fields}I", records, index * size)
        rows[values[0]] = values
    return rows


def _effects() -> dict[int, list[tuple[int, int, int, int]]]:
    blob = (DBC / "SpellEffect.dbc").read_bytes()
    count, fields, size, _strings = struct.unpack_from("<4I", blob, 4)
    records = blob[20:20 + count * size]
    effects: dict[int, list[tuple[int, int, int, int]]] = {}
    for index in range(count):
        values = struct.unpack_from(f"<{fields}I", records, index * size)
        base = struct.unpack_from("<i", records, index * size + 5 * 4)[0]
        # SpellEffectEntry: Effect 1, EffectAura 3, BasePoints 5, TriggerSpell 21, SpellID 24.
        effects.setdefault(values[24], []).append((values[1], values[3], base, values[21]))
    return effects


def test_faerie_fire_and_equivalents_match_the_434_dbc() -> None:
    needed = ("Spell.dbc", "SpellEffect.dbc", "SpellAuraOptions.dbc", "SpellDuration.dbc",
              "SpellCooldowns.dbc", "SpellRange.dbc")
    if not all((DBC / name).is_file() for name in needed):
        pytest.skip("client DBCs not hydrated")
    spells = _table("Spell.dbc")
    effects = _effects()
    stacks = {key: row[1] for key, row in _table("SpellAuraOptions.dbc").items()}
    durations = {key: row[1] for key, row in _table("SpellDuration.dbc").items()}
    recovery = {key: row[2] for key, row in _table("SpellCooldowns.dbc").items()}
    ranges = {key: struct.unpack("<f", struct.pack("<I", row[3]))[0]
              for key, row in _table("SpellRange.dbc").items()}

    # Spell.dbc: AttributesEx3 4, DurationIndex 13, RangeIndex 15,
    # SpellAuraOptionsId 32, SpellCooldownsId 37.
    def fact(spell_id: int) -> dict[str, float]:
        row = spells[spell_id]
        return {"ex3": row[4], "duration": durations.get(row[13], 0), "range": ranges.get(row[15], 0.0),
                "stacks": stacks.get(row[32], 0), "recovery": recovery.get(row[37], 0)}

    aura = _constant("FaerieFireAuraId")
    for spell_id, name in ((770, "FaerieFireSpellId"), (16857, "FaerieFireFeralSpellId")):
        assert _constant(name) == spell_id
        # SPELL_EFFECT_TRIGGER_SPELL 64 casts the shared debuff.
        assert (64, 0, -4, aura) in effects[spell_id]
    assert fact(770)["recovery"] == 0 and fact(770)["range"] == 35.0
    assert fact(16857)["recovery"] == 6000 and fact(16857)["range"] == 30.0

    debuff = fact(aura)
    assert aura == 91565
    assert debuff["duration"] == 300000 and debuff["stacks"] == _constant("FullStacks") == 3
    # SPELL_AURA_MOD_RESISTANCE_PCT 101 on armor: -4% per stack.
    assert (6, 101, -4, 0) in effects[aura]
    # No SPELL_ATTR3_DOT_STACKING_RULE (0x80): the druid's casts share one aura.
    assert not debuff["ex3"] & 0x80
    assert _constant("RefreshBelowMs") < debuff["duration"]

    assert _constant("ExposeArmorAuraId") == 8647
    assert (6, 101, -12, 0) in effects[8647]
    for name, spell_id in (("SunderArmorAuraId", 58567), ("CorrosiveSpitAuraId", 95466),
                           ("TearArmorAuraId", 95467)):
        assert _constant(name) == spell_id
        assert (6, 101, -4, 0) in effects[spell_id]
        assert fact(spell_id)["stacks"] == 3 and fact(spell_id)["duration"] == 30000


def test_upkeep_need_observation_and_admission_truth_table(tmp_path: Path) -> None:
    out = _run(tmp_path, "need", r'''
#include "Bots/BotRaidMajorArmor.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
struct FakeAura {
    uint8 stacks; int32 duration;
    uint8 GetStackAmount() const { return stacks; }
    int32 GetDuration() const { return duration; }
};
struct FakeCreature {
    bool dungeonBoss = false, worldBoss = false;
    bool IsDungeonBoss() const { return dungeonBoss; }
    bool isWorldBoss() const { return worldBoss; }
};
struct FakeUnit {
    std::map<uint32, FakeAura> auras; FakeCreature const* creature = nullptr; bool combat = true;
    FakeAura const* GetAura(uint32 id) const { auto it = auras.find(id); return it == auras.end() ? nullptr : &it->second; }
    FakeCreature const* ToCreature() const { return creature; }
    bool IsInCombat() const { return combat; }
};
namespace A = BotRaidMajorArmor;
bool need(uint8 ff, int32 ms, bool expose = false, uint8 equivalent = 0) {
    A::Observation o; o.FaerieFireStacks = ff; o.FaerieFireRemainingMs = ms;
    o.ExposeArmor = expose; o.StackingEquivalentStacks = equivalent;
    return A::Needed(o);
}
bool same(char const* a, char const* b) { return a == b || (a && b && !std::strcmp(a, b)); }
int main() {
    assert(A::IsUpkeepSpell(770) && A::IsUpkeepSpell(16857));
    assert(!A::IsUpkeepSpell(91565) && !A::IsUpkeepSpell(8647) && !A::IsUpkeepSpell(0));
    // Stacks first, then the refresh window; an equivalent at full strength covers it.
    assert(need(0, 0) && need(1, 290000) && need(2, 290000));
    assert(!need(3, 290000) && !need(3, 30000) && need(3, 29999) && need(3, 0));
    assert(!need(3, -1));                    // no expiry
    assert(!need(0, 0, true) && !need(2, 5000, true));
    assert(!need(0, 0, false, 3) && need(0, 0, false, 2) && need(1, 5000, false, 2));

    FakeCreature boss; boss.dungeonBoss = true;
    FakeCreature construct; construct.worldBoss = true;  // Omnotron constructs, Exposed Head
    FakeCreature trash;
    FakeUnit target; target.creature = &boss;
    A::Observation o = A::Observe(target);
    assert(o.FaerieFireStacks == 0 && !o.ExposeArmor && o.StackingEquivalentStacks == 0);
    target.auras[91565] = {2, 250000};
    target.auras[58567] = {1, 20000};
    target.auras[95467] = {3, 20000};
    o = A::Observe(target);
    assert(o.FaerieFireStacks == 2 && o.FaerieFireRemainingMs == 250000 && o.StackingEquivalentStacks == 3);
    assert(same(A::AdmissionRejection(&target, ""), A::CoveredReason));
    target.auras.erase(95467);
    assert(A::AdmissionRejection(&target, "") == nullptr);
    // A needed cast keeps its ordinary reason (cooldown, resource) but never
    // becomes the range-recovery movement.
    assert(same(A::AdmissionRejection(&target, "insufficient_resource"), nullptr));
    assert(same(A::AdmissionRejection(&target, "out_of_range"), A::OutOfRangeReason));
    target.auras[91565] = {3, 250000};
    assert(same(A::AdmissionRejection(&target, "out_of_range"), A::CoveredReason));
    target.auras[91565] = {3, 12000};
    assert(A::AdmissionRejection(&target, "") == nullptr);
    target.auras[8647] = {0, 20000};
    assert(same(A::AdmissionRejection(&target, ""), A::CoveredReason));

    FakeUnit bare; bare.creature = &construct;
    assert(A::AdmissionRejection(&bare, "") == nullptr);
    bare.combat = false;
    assert(same(A::AdmissionRejection(&bare, ""), A::NotEngagedReason));
    FakeUnit add; add.creature = &trash;
    assert(same(A::AdmissionRejection(&add, ""), A::NotBossReason));
    FakeUnit player;  // ToCreature() == nullptr
    assert(same(A::AdmissionRejection(&player, ""), A::NotBossReason));
    assert(same(A::AdmissionRejection(static_cast<FakeUnit const*>(nullptr), ""), A::NotBossReason));
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_apply_canonical_adds_one_faerie_fire_row_to_the_canonical_druid(tmp_path: Path) -> None:
    out = _run(tmp_path, "rows", r'''
#include "Bots/BotRaidRotationOverrides.h"
#include <cassert>
#include <cstdio>
#include <string>
BotActionProfileSpell row(uint32 id, uint8 bucket, uint16 sort) {
    BotActionProfileSpell s; s.SpellId = id; s.PriorityBucket = bucket; s.SortOrder = sort; return s;
}
BotClassSpecActionProfile druid(char const* spec, char const* role, uint8 cls = 11) {
    BotClassSpecActionProfile p; p.ClassId = cls; p.SpecTag = spec; p.Role = role;
    p.Spells = { row(8921, 1, 10), row(78674, 1, 30), row(2912, 3, 60) };
    return p;
}
int main() {
    auto balance = druid("balance_druid", "dps");
    // Raid scope alone (legacy Magmaw druid 30001 is Balance) adds nothing.
    assert(BotRaidRotationOverrides::Apply(balance) == 0 && balance.Spells.size() == 3);
    assert(BotRaidRotationOverrides::ApplyCanonical(balance) == 1 && balance.Spells.size() == 4);
    BotActionProfileSpell const& ff = balance.Spells.back();
    assert(ff.SpellId == 770 && ff.Category == BotCombatActionCategory::Debuff);
    assert(ff.MechanicTags == "faerie_fire,major_armor_debuff,raid_major_armor,canonical_raid_rotation_20260926");
    assert(ff.PriorityBucket == 1 && ff.SortOrder == 38 && ff.TargetSelector == "enemy");
    assert(ff.DamageWeight > 0.89f && ff.DamageWeight < 0.91f && ff.ThreatWeight == 0.0f);
    assert(ff.MaxRange == 0.0f && ff.MinRange == 0.0f && ff.MaintainAuraId == 0);
    assert(ff.MinEnemies == 1 && ff.MaxEnemies == 0 && !ff.RequiresMeleeRange && !ff.RequiresRangedRange);
    assert(BotRaidRotationOverrides::ApplyCanonical(balance) == 0 && balance.Spells.size() == 4);

    auto feral = druid("feral_druid_tank", "tank");
    assert(BotRaidRotationOverrides::ApplyCanonical(feral) == 1);
    BotActionProfileSpell const& fff = feral.Spells.back();
    assert(fff.SpellId == 16857 && fff.Category == BotCombatActionCategory::Debuff);
    assert(fff.MechanicTags == "faerie_fire_feral,major_armor_debuff,threat,raid_major_armor,canonical_raid_rotation_20260926");
    assert(fff.PriorityBucket == 1 && fff.SortOrder == 35 && fff.ThreatWeight == 1.0f);
    assert(fff.MaxRange == 0.0f && fff.RequiredShapeshiftForm == 5); // FORM_BEAR
    assert(ff.RequiredShapeshiftForm == 0);

    // A world-DB row for the spell wins; no duplicate, no retag.
    auto owned = druid("balance_druid", "dps");
    owned.Spells.push_back(row(770, 4, 90));
    assert(BotRaidRotationOverrides::ApplyCanonical(owned) == 0 && owned.Spells.size() == 4);
    assert(owned.Spells.back().MechanicTags.empty());

    for (auto other : { druid("restoration_druid", "healer"), druid("feral_druid_dps", "dps"),
                        druid("balance_druid", "tank"), druid("feral_druid_tank", "dps"),
                        druid("balance_druid", "dps", 7) })
    {
        assert(BotRaidRotationOverrides::ApplyCanonical(other) == 0);
        assert(other.Spells.size() == 3);
    }
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_admission_gates_the_tagged_rows_before_range_recovery() -> None:
    admission = ADMISSION.read_text(encoding="utf-8")
    assert '#include "Bots/BotRaidMajorArmor.h"' in admission
    gate = ("        if (raidRotationScope && BotRaidMajorArmor::IsUpkeepSpell(candidate.SpellId))\n"
            "            if (char const* majorArmorReason = BotRaidMajorArmor::AdmissionRejection(\n"
            "                    target, candidate.RejectReason))\n"
            "            {\n"
            "                candidate.RejectReason = majorArmorReason;\n"
            "                continue;\n"
            "            }\n")
    assert admission.count(gate) == 1
    # Before every ordinary gate that could admit it, and before the block
    # that turns an out_of_range candidate into the range-recovery action.
    position = admission.index(gate)
    # After the calibration prepull exclusion, outside the exclusion slices
    # that the Bane and self-provided-potion tests compile.
    assert admission.index('candidate.RejectReason = "reference_prepull_action_excluded";') < position
    for later in ("BotRaidCooldownReservation::ReservationReason(",
                  'candidate.RejectReason == "out_of_range"',
                  "bestRangeRecovery = &candidate;",
                  "bestMagmawMushroomPlacement = &candidate;"):
        assert position < admission.index(later), later
    # The spliced resolver (what the other resolver tests read) carries it too.
    resolver_source = combat_resolver_source()
    assert gate in resolver_source
    # Typed key: the gate adds no mechanic-tag runtime gate (the phase 4
    # rotation contract keeps tags descriptive; round 3's health-recovery
    # gate is the fourth, the contract expects three).
    assert resolver_source.count("hasMechanicTag(candidate.Profile.MechanicTags") == 4
    assert "BotRaidMajorArmor::Tag" not in admission
    # Magmaw mushroom actions still preempt the ordinary best, so the
    # Balance druid's parasite duty outranks the upkeep row.
    resolver = (BOTS / "BotWorldPopulationMgrCombatResolver.cpp").read_text(encoding="utf-8")
    selection = resolver[resolver.index("    if (bestInterrupt)\n        best = bestInterrupt;"):]
    assert selection.index("bestMagmawMushroomDetonation") < selection.index("bestRangeRecovery")
    assert "ApplyCanonical(profile);" in resolver
    for path in (HEADER, ADMISSION, BOTS / "BotRaidRotationOverrides.h"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path


def test_every_canonical_bwd_shard_has_the_druid_and_legacy_magmaw_is_protected() -> None:
    composition = json.loads(COMPOSITION.read_text(encoding="utf-8"))
    specs = [boss["spec_selection"]["druid"] for boss in composition["bosses"]]
    specs.append(composition["full_raid"]["spec_selection"]["druid"])
    # The druid covers every shard, so the rogue keeps its combo points
    # (Expose Armor 8647 is the fallback that is not needed).
    assert specs and set(specs) <= {"balance_druid", "feral_druid_tank"}
    assert {"balance_druid", "feral_druid_tank"} <= set(specs)

    roster = {}

    def walk(node):
        if isinstance(node, dict):
            guid = node.get("character_guid")
            if isinstance(guid, int) and 30001 <= guid <= 30010:
                roster[guid] = node.get("class_spec")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(LEGACY_SHARDS.read_text(encoding="utf-8")))
    # The legacy accepted Magmaw druid is Balance: raid scope alone would
    # change it, so the rows are canonical-scope only.
    assert roster[30001] == "balance_druid"


def test_the_canonical_druid_spellbook_holds_its_faerie_fire_in_every_shard() -> None:
    """The provisioned spellbook, not trainability.

    BuildCandidates rejects a row whose spell the bot does not know
    (unknown_requested_spell), so the upkeep needs 770 in the druid's Balance
    talent group and 16857 in its Feral group. The plan is built from the
    composition config through the tool (raid_shard_scenarios.build_plan),
    not read from a generated plan.json; each group is checked as the active
    one, which covers the live group of every shard. It fails closed rather
    than skipping when the client DBCs or the DVC plan inputs are absent.
    """
    import copy

    from tools.raid_program.raid_loadout_spells import loadout_known_spells
    from tools.raid_program.raid_shard_scenarios import build_plan

    inputs = (DBC / "SkillLineAbility.dbc", DBC / "SpellEffect.dbc", TRAINERS)
    absent = [str(path.relative_to(ROOT)) for path in inputs if not path.is_file()]
    assert not absent, f"extract the client DBCs and dvc pull the plan inputs: {absent}"
    required = {"balance_druid": 770, "feral_druid_tank": 16857}
    plan = build_plan(COMPOSITION)
    druids = [(shard["cohort_id"], bot) for shard in plan["shards"] for bot in shard["bots"]
              if bot["character_key"] == "druid"]
    assert len(druids) == len(plan["shards"]) and druids
    missing = []
    live_specs = set()
    for cohort, bot in druids:
        groups = bot["loadout"]["groups"]
        assert sorted(group["class_spec"] for group in groups) == sorted(required), cohort
        live_specs.add(groups[int(bot["loadout"]["active_talent_group"])]["class_spec"])
        for index, group in enumerate(groups):
            view = copy.deepcopy(bot)
            view["loadout"]["active_talent_group"] = index
            known = set(loadout_known_spells(view, DBC, trainers_path=TRAINERS)["known_spell_ids"])
            if required[group["class_spec"]] not in known:
                missing.append((cohort, group["class_spec"], required[group["class_spec"]]))
    assert live_specs == set(required)
    assert not missing, missing
