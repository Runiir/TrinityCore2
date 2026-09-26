"""Round 3 raid class rotations, scoped to raids.

Round 2 BWD 10N starved four canonical DPS rotations (Beast Mastery enemy
ceilings, Retribution Holy Power generators, Demonology self-cast rows,
Assassination Vendetta cap) and looped Demonology Drain Life. The fixes are
raid-only (user decision, 2026-09-25): accepted Stonecore canaries and Phase 8
calibrations must stay exactly reproducible. So there are no world-DB
migrations; BotRaidRotationOverrides applies the row changes to the resolver's
copy of the profile only in raid scope, and the resolver's nominal melee reach
and healer-owned health recovery use the same scope.
"""
from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path

import pytest

from tests.combat_resolver_source import combat_resolver_source

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "sql/custom/world"
BOTS = ROOT / "src/server/game/Bots"
DBC = ROOT / "data/dbc/enUS"
RESOLVER = BOTS / "BotWorldPopulationMgrCombatResolver.cpp"
ADMISSION = BOTS / "BotWorldPopulationMgrCombatResolverAdmission.cpp"
OVERRIDES = BOTS / "BotRaidRotationOverrides.h"
RESERVATION = BOTS / "BotWorldPopulationMgrRaidCooldownReservation.h"
INCLUDES = ["-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common")]

FIELDS = ("spell", "category", "tags", "damage", "bucket", "sort", "min_enemies", "max_enemies",
          "melee", "ranged", "selector", "min_range", "max_range")

# (class, spec, role) -> rows as the world DB holds them after every earlier
# migration (2026_07_18_00 coverage, the Retribution 2026_07_20_05/27_01/
# 08_17_10, Demonology 2026_07_25_0x and rogue 2026_08_17_01 migrations), plus
# scope probes: other specs, a tank role, and rows whose DB value differs from
# the one an override expects.
PROFILES = {
    (3, "beast_mastery_hunter", "dps"): [
        (1978, "dot", "serpent_sting,dot", 0.86, 1, 10, 1, 1, 0, 1, "enemy", 5, 35),
        (34026, "spender", "kill_command,pet_primary", 1.00, 1, 20, 1, 1, 0, 1, "enemy", 5, 35),
        (53351, "execute", "kill_shot,execute", 1.00, 1, 30, 1, 1, 0, 1, "enemy", 5, 35),
        (3044, "spender", "arcane_shot,focus_dump", 0.82, 3, 40, 1, 1, 0, 1, "enemy", 5, 35),
        (77767, "resource_generator", "cobra_shot,focus_builder", 0.74, 4, 50, 1, 1, 0, 1, "enemy", 5, 35),
        (2643, "aoe", "multi_shot,aoe", 0.88, 2, 60, 3, 0, 0, 1, "enemy", 5, 35),
        (19577, "stun_cc", "intimidation,pet_control", 0.30, 3, 70, 1, 1, 0, 1, "enemy", 5, 35),
    ],
    (3, "marksmanship", "dps"): [
        (3044, "spender", "arcane_shot,focus_dump", 0.82, 3, 40, 1, 1, 0, 1, "enemy", 5, 35),
    ],
    (2, "retribution_paladin", "dps"): [
        (96231, "interrupt", "rebuke,interrupt", 0.15, 1, 10, 1, 1, 1, 0, "enemy", 0, 5),
        (35395, "resource_generator", "crusader_strike,holy_power", 0.94, 1, 20, 1, 1, 1, 0, "enemy", 0, 5),
        (85256, "spender", "templars_verdict,holy_power,holy_power_3", 1.05, 0, 30, 1, 1, 1, 0, "enemy", 0, 5),
        (20271, "builder", "judgement,ranged_filler", 0.82, 2, 40, 1, 1, 0, 0, "enemy", 0, 30),
        (879, "spender", "exorcism,proc", 0.88, 2, 50, 1, 1, 0, 0, "enemy", 0, 30),
        (24275, "execute", "hammer_of_wrath,execute", 1.00, 1, 60, 1, 1, 0, 0, "enemy", 0, 30),
        (53385, "aoe", "divine_storm,aoe", 0.90, 2, 70, 4, 0, 1, 0, "enemy", 0, 5),
        (84963, "offensive_cooldown", "inquisition,self,buff,holy_power_3", 1.08, 0, 2, 1, 0, 0, 0, "self", 0, 0),
        (31884, "offensive_cooldown", "avenging_wrath,self,offensive_cooldown", 1.00, 0, 3, 1, 0, 0, 0, "self", 0, 0),
    ],
    (2, "retribution_paladin", "tank"): [
        (35395, "resource_generator", "crusader_strike,holy_power", 0.94, 1, 20, 1, 1, 1, 0, "enemy", 0, 5),
    ],
    (9, "demonology_warlock", "dps"): [
        (18540, "offensive_cooldown", "summon_doomguard,guardian,pinned_apl", 1.20, 0, 15, 1, 1, 0, 1, "enemy", 5, 18),
        (47897, "spender", "shadowflame,short_range,pinned_apl", 1.05, 1, 55, 1, 0, 0, 0, "enemy", 0, 8),
        (348, "dot", "immolate,dot", 0.90, 1, 30, 1, 1, 0, 1, "enemy", 0, 18),
        (172, "dot", "corruption,dot", 0.86, 2, 40, 1, 1, 0, 1, "enemy", 0, 18),
        (603, "dot", "bane_of_doom,dot,pinned_apl", 0.98, 1, 25, 1, 1, 0, 1, "enemy", 5, 18),
        (71521, "spender", "hand_of_guldan,primary", 1.00, 1, 50, 1, 1, 0, 1, "enemy", 0, 18),
        (74434, "offensive_cooldown", "soulburn,soul_fire_setup,pinned_apl", 1.05, 1, 17, 1, 1, 0, 0, "self", 0, 0),
        (6353, "offensive_cooldown", "soul_fire,soulburn_consumer,improved_soul_fire,pinned_apl", 1.10, 1, 18, 1, 1, 0, 1, "enemy", 5, 18),
        (6353, "execute", "soul_fire,decimation", 0.94, 2, 60, 1, 1, 0, 1, "enemy", 0, 18),
        (689, "resource_generator", "drain_life,health_recovery,resource_fallback,pinned_apl", 0.20, 0, 66, 1, 0, 0, 1, "enemy", 5, 18),
        (1949, "aoe", "hellfire,aoe", 0.86, 2, 80, 3, 0, 0, 0, "self", 0, 10),
        (29722, "builder", "incinerate,filler,pinned_apl", 0.82, 4, 75, 1, 0, 0, 1, "enemy", 5, 18),
    ],
    (9, "affliction_warlock", "dps"): [
        (18540, "offensive_cooldown", "summon_doomguard,guardian,pinned_apl", 1.20, 0, 5, 1, 0, 0, 0, "self", 0, 0),
        (348, "dot", "immolate,dot", 0.90, 1, 30, 1, 1, 0, 1, "enemy", 0, 35),
    ],
    (4, "assassination_rogue", "dps"): [
        (79140, "offensive_cooldown", "vendetta,target,burst", 1.05, 1, 20, 1, 0, 1, 0, "enemy", 0, 5),
        (1329, "builder", "mutilate,primary_builder,combo_builder", 1.00, 5, 80, 1, 0, 1, 0, "enemy", 0, 5),
        (1766, "interrupt", "kick,interrupt", 0.15, 0, 10, 1, 0, 1, 0, "enemy", 0, 5),
    ],
    (4, "combat_rogue", "dps"): [
        (51690, "offensive_cooldown", "killing_spree,burst", 1.00, 1, 20, 1, 0, 1, 0, "enemy", 0, 5),
    ],
}

# Rows whose DB value differs from the one an override expects are untouched:
# a later world-DB change wins over the raid override.
DRIFTED = {
    (3, "beast_mastery_hunter", "dps"): [
        (77767, "resource_generator", "cobra_shot,focus_builder", 0.74, 4, 50, 1, 3, 0, 1, "enemy", 5, 35),
    ],
    (9, "demonology_warlock", "dps"): [
        (18540, "offensive_cooldown", "summon_doomguard,guardian", 1.20, 0, 15, 1, 0, 0, 0, "self", 0, 0),
    ],
    (4, "assassination_rogue", "dps"): [
        (79140, "offensive_cooldown", "vendetta,target,burst", 1.05, 1, 20, 1, 0, 1, 0, "enemy", 0, 8),
    ],
}

SCOPE_TAG = "raid_rotation_20260926"
EXPECTED = {
    ("beast_mastery_hunter", 1978): {"max_enemies": (1, 0)},
    ("beast_mastery_hunter", 34026): {"max_enemies": (1, 0)},
    ("beast_mastery_hunter", 53351): {"max_enemies": (1, 0)},
    ("beast_mastery_hunter", 3044): {"max_enemies": (1, 2)},
    ("beast_mastery_hunter", 77767): {"max_enemies": (1, 0)},
    ("retribution_paladin", 35395): {"max_enemies": (1, 0)},
    ("retribution_paladin", 85256): {"max_enemies": (1, 0)},
    ("retribution_paladin", 20271): {"max_enemies": (1, 0)},
    ("retribution_paladin", 879): {"max_enemies": (1, 0)},
    ("retribution_paladin", 24275): {"max_enemies": (1, 0)},
    ("retribution_paladin", 53385): {"selector": ("enemy", "self"), "max_range": (5.0, 8.0),
                                     "bucket": (2, 1), "sort": (70, 19), "damage": (0.9, 1.0)},
    # Inquisition keeps its category; only the reservation exemption tag.
    ("retribution_paladin", 84963): {},
    ("demonology_warlock", 18540): {"selector": ("enemy", "self"), "min_range": (5.0, 0.0),
                                    "max_range": (18.0, 0.0), "ranged": (1, 0), "max_enemies": (1, 0)},
    ("demonology_warlock", 47897): {"selector": ("enemy", "self")},
    ("demonology_warlock", 348): {"max_enemies": (1, 2)},
    ("demonology_warlock", 172): {"max_enemies": (1, 2)},
    ("demonology_warlock", 603): {"max_enemies": (1, 2)},
    ("demonology_warlock", 71521): {"max_enemies": (1, 2)},
    ("demonology_warlock", 74434): {"max_enemies": (1, 2)},
    ("demonology_warlock", 6353): {"max_enemies": (1, 2)},
    ("assassination_rogue", 79140): {"max_range": (5.0, 0.0)},
}


def _category(name: str) -> str:
    return "BotCombatActionCategory::" + "".join(part.title() for part in name.split("_"))


def _row(spell: tuple) -> str:
    (spell_id, category, tags, damage, bucket, sort, min_enemies, max_enemies,
     melee, ranged, selector, min_range, max_range) = spell
    return (f'{{BotActionProfileSpell s;s.SpellId={spell_id};s.Category={_category(category)};'
            f's.MechanicTags="{tags}";s.DamageWeight={float(damage)}f;s.PriorityBucket={bucket};'
            f's.SortOrder={sort};s.MinEnemies={min_enemies};s.MaxEnemies={max_enemies};'
            f's.RequiresMeleeRange={"true" if melee else "false"};'
            f's.RequiresRangedRange={"true" if ranged else "false"};s.TargetSelector="{selector}";'
            f's.MinRange={float(min_range)}f;s.MaxRange={float(max_range)}f;p.Spells.push_back(s);}}')


def _run_overrides(tmp_path: Path, profiles: dict) -> list[dict]:
    blocks = []
    for (class_id, spec, role), spells in profiles.items():
        rows = "".join(_row(spell) for spell in spells)
        blocks.append(f'{{BotClassSpecActionProfile p;p.ClassId={class_id};p.SpecTag="{spec}";'
                      f'p.Role="{role}";{rows}run(p);}}')
    source = tmp_path / "overrides.cpp"
    source.write_text(r'''
#include "Bots/BotRaidRotationOverrides.h"
#include <cstdio>
void dump(char const* phase, BotClassSpecActionProfile const& p, unsigned changed) {
    for (BotActionProfileSpell const& s : p.Spells)
        std::printf("%s|%s|%s|%u|%u|%u|%.2f|%u|%u|%u|%u|%d|%d|%s|%.2f|%.2f\n", phase,
            p.SpecTag.c_str(), p.Role.c_str(), changed, s.SpellId,
            unsigned(s.Category), double(s.DamageWeight),
            unsigned(s.PriorityBucket), unsigned(s.SortOrder), unsigned(s.MinEnemies),
            unsigned(s.MaxEnemies), int(s.RequiresMeleeRange), int(s.RequiresRangedRange),
            s.TargetSelector.c_str(), double(s.MinRange), double(s.MaxRange));
    for (BotActionProfileSpell const& s : p.Spells)
        std::printf("tags|%s|%s|%s|%u|%s\n", phase, p.SpecTag.c_str(), p.Role.c_str(), s.SpellId,
            s.MechanicTags.c_str());
}
void run(BotClassSpecActionProfile p) {
    dump("before", p, 0);
    unsigned const first = BotRaidRotationOverrides::Apply(p);
    dump("after", p, first);
    unsigned const second = BotRaidRotationOverrides::Apply(p);
    std::printf("second|%s|%s|%u\n", p.SpecTag.c_str(), p.Role.c_str(), second);
}
int main() {
''' + "\n".join(blocks) + "\n}\n")
    binary = tmp_path / "overrides"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
                    str(source), "-o", str(binary)], check=True)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout.splitlines()


def _parse(lines: list[str]):
    rows = {"before": [], "after": []}
    tags = {"before": [], "after": []}
    second = {}
    for line in lines:
        parts = line.split("|")
        if parts[0] in rows:
            (_, spec, role, changed, spell, category, damage, bucket, sort, min_e, max_e,
             melee, ranged, selector, min_r, max_r) = parts
            rows[parts[0]].append({"spec": spec, "role": role, "changed": int(changed), "spell": int(spell),
                                   "category": category, "damage": float(damage), "bucket": int(bucket),
                                   "sort": int(sort), "min_enemies": int(min_e), "max_enemies": int(max_e),
                                   "melee": int(melee), "ranged": int(ranged), "selector": selector,
                                   "min_range": float(min_r), "max_range": float(max_r)})
        elif parts[0] == "tags":
            tags[parts[1]].append((parts[2], parts[3], int(parts[4]), parts[5]))
        elif parts[0] == "second":
            second[(parts[1], parts[2])] = int(parts[3])
    return rows, tags, second


def test_raid_overrides_change_exactly_the_starved_rows(tmp_path: Path) -> None:
    rows, tags, second = _parse(_run_overrides(tmp_path, PROFILES))
    before, after = rows["before"], rows["after"]
    assert len(before) == len(after) == sum(len(spells) for spells in PROFILES.values())
    changes = {}
    for old, new in zip(before, after):
        diff = {key: (old[key], new[key]) for key in old if key not in ("changed",) and old[key] != new[key]}
        if diff or (old["spec"], old["spell"]) in EXPECTED and old["role"] == "dps":
            changes.setdefault((old["spec"], old["spell"]), diff)
    # Only canonical raid DPS profiles change; categories never change.
    assert changes == {key: value for key, value in EXPECTED.items()}
    assert all(old["category"] == new["category"] for old, new in zip(before, after))
    # Tags: every touched row carries the scope tag; Inquisition also the
    # reservation exemption; untouched rows keep their tags byte for byte.
    assert len(tags["before"]) == len(tags["after"]) == len(before)
    for (spec, role, spell, old_tags), (_, _, _, new_tags) in zip(tags["before"], tags["after"]):
        if role != "dps" or (spec, spell) not in EXPECTED:
            assert new_tags == old_tags, (spec, role, spell)
        elif spell == 84963:
            assert new_tags == old_tags + ",raid_reservation_exempt," + SCOPE_TAG
        else:
            assert new_tags == old_tags + "," + SCOPE_TAG, (spec, spell)
    counts = {(row["spec"], row["role"]): row["changed"] for row in after}
    assert counts[("beast_mastery_hunter", "dps")] == 5
    assert counts[("retribution_paladin", "dps")] == 7
    assert counts[("demonology_warlock", "dps")] == 9
    assert counts[("assassination_rogue", "dps")] == 1
    for key in (("marksmanship", "dps"), ("retribution_paladin", "tank"),
                ("affliction_warlock", "dps"), ("combat_rogue", "dps")):
        assert counts[key] == 0, key
    # Idempotent: a second Apply on an overridden profile changes nothing.
    assert set(second.values()) == {0}


def test_a_changed_db_row_wins_over_the_raid_override(tmp_path: Path) -> None:
    rows, _tags, _second = _parse(_run_overrides(tmp_path, DRIFTED))
    assert rows["before"] == [dict(row, changed=0) for row in rows["before"]]
    for old, new in zip(rows["before"], rows["after"]):
        assert {key: value for key, value in old.items() if key != "changed"} == \
            {key: value for key, value in new.items() if key != "changed"}
        assert new["changed"] == 0


def test_resolver_applies_raid_fixes_only_in_raid_scope() -> None:
    resolver = combat_resolver_source()
    assert '#include "Bots/BotRaidRotationOverrides.h"' in resolver
    scope = ("    bool const raidRotationScope = Cohort().Raid.RaidInstance\n"
             "        && bot->GetMap() && bot->GetMap()->IsRaid();\n"
             "    if (raidRotationScope)\n"
             "        BotRaidRotationOverrides::Apply(profile);\n")
    assert scope in resolver
    # The overrides run right after the DB profile is built, before any use.
    built = resolver.index("        : BotClassSpecActionProfileStore::Build(bot, role.c_str());")
    assert built < resolver.index(scope) < resolver.index("BuildCandidates(bot, target, profile")
    # Exactly one Apply call site in the whole server.
    callers = [path for path in (ROOT / "src").rglob("*.cpp")
               if "BotRaidRotationOverrides::Apply(" in path.read_text(errors="replace")]
    assert callers == [RESOLVER]
    # The nominal melee reach: raid scope and an exact 5 yd cap only.
    helper = resolver[resolver.index("    auto effectiveSpellMaxRange ="):]
    helper = helper[:helper.index("\n    };") + 7]
    assert "[bot, target, raidRotationScope]" in helper
    assert ("&& (candidate.Profile.MaxRange <= 0.0f\n"
            "                || (raidRotationScope\n"
            "                    && candidate.Profile.MaxRange == NOMINAL_MELEE_RANGE)))") in helper
    assert "<= NOMINAL_MELEE_RANGE" not in resolver
    # Drain Life: the healer-owned recovery gate uses the same scope.
    assert "BotRaidHealthRecoveryGate::Holds(raidRotationScope," in resolver
    # Five round 3 uses, plus the round 4 canonical Survival scope (round 4 test).
    assert resolver.count("raidRotationScope") == 6


def test_no_world_db_rotation_row_changes_this_round() -> None:
    for name in ("2026_09_26_10_beast_mastery_raid_enemy_ceilings.sql",
                 "2026_09_26_11_retribution_raid_holy_power_generators.sql",
                 "2026_09_26_12_demonology_raid_doomguard_and_targets.sql",
                 "2026_09_26_13_assassination_vendetta_native_range.sql"):
        assert not (WORLD / name).exists(), name
    for path in WORLD.glob("*.sql"):
        text = path.read_text(errors="replace")
        for tag in (SCOPE_TAG, "raid_reservation_exempt", "bm_raid_enemy_ceiling_20260926",
                    "ret_raid_holy_power_20260926", "demo_raid_targets_20260926",
                    "vendetta_native_range_20260926"):
            assert tag not in text, (path.name, tag)


def test_reservation_exempts_only_the_override_tag(tmp_path: Path) -> None:
    reservation = RESERVATION.read_text()
    assert 'ReservationExemptTag = "raid_reservation_exempt"' in reservation
    assert "HasTag(candidate.MechanicTags, ReservationExemptTag)" in reservation
    # Only the raid overrides add the tag; no other source mentions it.
    mentions = sorted(path.name for path in (ROOT / "src").rglob("*")
                      if path.suffix in (".h", ".cpp")
                      and "ReservationExemptTag" in path.read_text(errors="replace"))
    assert mentions == ["BotRaidRotationOverrides.h", "BotWorldPopulationMgrRaidCooldownReservation.h"]
    source = tmp_path / "reservation.cpp"
    source.write_text(r'''
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include <cassert>
#include <string>
int main() {
    using namespace BotRaidCooldownReservation;
    RouteContext trash{true, true, false, false, "trash", "trash_cluster", ""};
    RouteContext dungeon{true, false, false, false, "trash", "trash_cluster", ""};
    RouteContext bossCombat{true, true, true, false, "boss", "boss", "combat"};
    auto const cooldown = BotCombatActionCategory::OffensiveCooldown;
    std::string const inquisition = "inquisition,self,buff,holy_power_3";
    std::string const exempt = inquisition + ",raid_reservation_exempt,raid_rotation_20260926";
    assert(std::string(ReservationReason(trash, {cooldown, inquisition})) == "raid_offensive_cooldown_reserved");
    assert(ReservationReason(trash, {cooldown, exempt}) == nullptr);
    assert(std::string(ReservationReason(trash, {cooldown, "avenging_wrath,self,offensive_cooldown"}))
        == "raid_offensive_cooldown_reserved");
    assert(ReservationReason(dungeon, {cooldown, inquisition}) == nullptr);
    assert(ReservationReason(bossCombat, {cooldown, inquisition}) == nullptr);
    // A substring is not the tag.
    assert(std::string(ReservationReason(trash, {cooldown, "raid_reservation_exempted"}))
        == "raid_offensive_cooldown_reserved");
}
''')
    binary = tmp_path / "reservation"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_override_pre_state_matches_the_world_db_migrations() -> None:
    coverage = (WORLD / "2026_07_18_00_all_spec_rotation_profile_coverage.sql").read_text()
    bm = [line for line in coverage.splitlines() if "'beast_mastery_hunter' AND `role`='dps'), " in line]
    # Column order: ..., priority_bucket, min_enemies, max_enemies, max_target_health_pct, ...
    for spell in (1978, 34026, 53351, 3044, 77767):
        row = next(line for line in bm if f", {spell}, " in line)
        assert ", 1, 1, 1.00, 0, 0, 1, 'enemy'" in row or ", 1, 1, 0.20, 0, 0, 1, 'enemy'" in row, spell
    ret = [line for line in coverage.splitlines() if "'retribution_paladin' AND `role`='dps'), " in line]
    for spell in (35395, 85256, 20271, 879, 24275):
        row = next(line for line in ret if f", {spell}, " in line)
        assert ", 1, 1, 1.00, " in row or ", 1, 1, 0.20, " in row, spell
    alignment = (WORLD / "2026_08_17_10_phase8_melee_apl_alignment.sql").read_text()
    assert "SET a.`min_enemies` = 4" in alignment and "a.`spell_id` = 53385" in alignment
    burst = (WORLD / "2026_07_25_12_phase8_demonology_melee_burst.sql").read_text()
    assert "`action`.`max_range` = 18.0" in burst
    affliction = (WORLD / "2026_09_13_02_affliction_doomguard.sql").read_text()
    assert "`target_selector` = 'self'" in affliction and "`requires_ranged_range` = 0" in affliction
    shadowflame = (WORLD / "2026_08_16_03_affliction_shadowflame_self_centered.sql").read_text()
    assert "`action`.`target_selector` = 'self'" in shadowflame and "`action`.`max_range` = 8" in shadowflame


def _spell_ranges(spell_ids: set[int]) -> dict[int, tuple[int, float, int]]:
    def load(name: str):
        blob = (DBC / name).read_bytes()
        count, _fields, size, _strings = struct.unpack_from("<4I", blob, 4)
        return count, size, blob[20:20 + count * size]

    count, size, records = load("SpellRange.dbc")
    ranges = {}
    for index in range(count):
        record = records[index * size:(index + 1) * size]
        range_id, _min_hostile, _min_friendly, max_hostile, _max_friendly, flags = struct.unpack_from(
            "<IffffI", record, 0)
        ranges[range_id] = (max_hostile, flags)
    count, size, records = load("Spell.dbc")
    found = {}
    for index in range(count):
        record = records[index * size:(index + 1) * size]
        spell_id = struct.unpack_from("<I", record, 0)[0]
        if spell_id in spell_ids:
            range_index = struct.unpack_from("<I", record, 15 * 4)[0]
            found[spell_id] = (range_index, *ranges[range_index])
    return found


def test_native_range_facts_behind_the_overrides() -> None:
    if not (DBC / "Spell.dbc").is_file():
        pytest.skip("client DBCs not hydrated")
    facts = _spell_ranges({18540, 47897, 53385, 79140, 1329})
    # Self-cast (SpellRange 1, 0 yd): Summon Doomguard, Shadowflame, Divine Storm.
    for spell in (18540, 47897, 53385):
        assert facts[spell][:2] == (1, 0.0), spell
    # Vendetta is a 30 yd non-melee spell; Mutilate is SPELL_RANGE_MELEE.
    assert facts[79140][:2] == (4, 30.0) and not facts[79140][2] & 1
    assert facts[1329][0] == 2 and facts[1329][2] & 1


def test_raid_health_recovery_gate_is_healer_owned_and_emergency_only(tmp_path: Path) -> None:
    source = tmp_path / "gate.cpp"
    source.write_text(r'''
#include "BotRaidHealthRecoveryGate.h"
#include <cassert>
#include <string>
int main() {
    using namespace BotRaidHealthRecoveryGate;
    int probes = 0;
    auto healer = [&probes]() { ++probes; return true; };
    auto noHealer = [&probes]() { ++probes; return false; };
    // Raid, tagged Drain Life, 60% health, a living healer: held.
    assert(Holds(true, true, 0.60f, healer));
    // Emergency health, no healer, outside raid scope or an untagged row: released.
    assert(!Holds(true, true, 0.35f, healer));
    assert(!Holds(true, true, 0.20f, healer));
    assert(!Holds(true, true, 0.60f, noHealer));
    assert(!Holds(false, true, 0.60f, healer));
    assert(!Holds(true, false, 0.60f, healer));
    // The group walk only happens for a tagged raid row above the floor.
    assert(probes == 2);
    assert(std::string(HealthRecoveryTag) == "health_recovery");
    assert(std::string(RejectReason) == "raid_healer_owned_health_recovery");
}
''')
    binary = tmp_path / "gate"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(BOTS),
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_resolver_applies_the_health_recovery_gate_after_the_profile_health_gate() -> None:
    resolver = combat_resolver_source()
    assert '#include "Bots/BotRaidHealthRecoveryGate.h"' in ADMISSION.read_text()
    profile_gate = resolver.index('candidate.RejectReason = "self_health_gate";')
    raid_gate = resolver.index("BotRaidHealthRecoveryGate::Holds(raidRotationScope,")
    assert profile_gate < raid_gate < resolver.index("float distance = selfCenteredHostileAction")
    gate = resolver[raid_gate:resolver.index("continue;", raid_gate)]
    assert "BotRaidHealthRecoveryGate::HealthRecoveryTag" in gate
    assert "selfHealthPct, livingGroupHealer" in gate
    assert "candidate.RejectReason = BotRaidHealthRecoveryGate::RejectReason;" in gate
    probe = resolver[resolver.index("auto livingGroupHealer"):resolver.index("bool const targetActivelyCasting")]
    assert 'std::string(GetDungeonRole(member)) == "healer"' in probe
    assert "member != bot" in probe and "member->IsAlive()" in probe and "member->IsInMap(bot)" in probe
    # The Demonology Drain Life row is the only DPS health_recovery row.
    rows = [statement for path in WORLD.glob("*.sql")
            for statement in path.read_text().split(";") if "health_recovery" in statement]
    assert rows and all("demonology_warlock" in statement for statement in rows)
