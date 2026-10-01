"""BWD 10N program round 2 class rotations, canonical-composition raids only.

Round 1 (label blackwing_descent_10n-r01-553da85c98): the Demonology warlock
held an 18 yd Phase 8 lane and had no instant filler, so on Atramedes it
landed 12-14 casts per kill; Assassination Fan of Knives (disabled in canonical
raids, user decision 2026-09-27: "always a dps loss") targeted the enemy
although it is a self-range spell and never landed; Fire's three-DoT
Combustion window never opened on Maloriak. The accepted Phase 8 calibrations,
Stonecore canaries and the legacy Magmaw 10N scenario must stay exactly
reproducible, so the rows change only through
BotRaidRotationOverrides::ApplyCanonical and the Combustion gate only under
the admission's canonical-raid flag (the Combustion tests cover that gate).
"""
from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest

from tests.combat_resolver_source import ADMISSION

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
WORLD = ROOT / "sql/custom/world"
DBC = ROOT / "data/dbc/enUS"
HEADER = BOTS / "BotRaidCanonicalClassRotation.h"
OVERRIDES = BOTS / "BotRaidRotationOverrides.h"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
LEGACY_SHARDS = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
INCLUDES = ["-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common")]
TAG = "canonical_raid_rotation_20260927"


def _run(tmp_path: Path, name: str, program: str) -> str:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(program)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
                    str(source), "-o", str(binary)], check=True)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


PROGRAM = r'''
#include "Bots/BotRaidRotationOverrides.h"
#include <cassert>
#include <cstdio>
#include <string>
BotActionProfileSpell row(uint32 id, char const* selector, float minRange, float maxRange, char const* tags = "") {
    BotActionProfileSpell s; s.SpellId = id; s.TargetSelector = selector; s.MinRange = minRange;
    s.MaxRange = maxRange; s.MechanicTags = tags; return s;
}
// The live world-DB Demonology rows (profile 287) that carry a range, as the
// resolver sees them in a raid after the round 3 Apply.
BotClassSpecActionProfile demonology(char const* role = "dps", char const* spec = "demonology_warlock", uint8 cls = 9) {
    BotClassSpecActionProfile p; p.ClassId = cls; p.SpecTag = spec; p.Role = role; p.MinRange = 5.0f; p.MaxRange = 18.0f;
    p.Spells = { row(18540, "self", 0, 0, "summon_doomguard"), row(6353, "enemy", 5, 18, "soul_fire,soulburn_consumer"),
                 row(603, "enemy", 5, 18, "bane_of_doom"), row(348, "enemy", 0, 18, "immolate"),
                 row(172, "enemy", 0, 18, "corruption"), row(50589, "self", 0, 18, "immolation_aura"),
                 row(71521, "enemy", 0, 18, "hand_of_guldan"), row(47897, "self", 0, 8, "shadowflame"),
                 row(6353, "enemy", 0, 18, "soul_fire,decimation"), row(1454, "self", 0, 0, "life_tap"),
                 row(689, "enemy", 5, 18, "drain_life,health_recovery"), row(29722, "enemy", 5, 18, "incinerate"),
                 row(1949, "self", 0, 10, "hellfire") };
    p.Spells[10].MaxSelfHealthPct = 0.90f; // Drain Life, the calibration self-heal
    return p;
}
BotClassSpecActionProfile assassination(char const* spec = "assassination_rogue", float fok = 10.0f) {
    BotClassSpecActionProfile p; p.ClassId = 4; p.SpecTag = spec; p.Role = "dps"; p.MaxRange = 5.0f;
    p.Spells = { row(79140, "enemy", 0, 5, "vendetta"), row(1329, "enemy", 0, 5, "mutilate"),
                 row(51723, "enemy", 0, fok, "fan_of_knives,aoe,poison_application") };
    p.Spells[0].RequiresMeleeRange = p.Spells[1].RequiresMeleeRange = true;
    return p;
}
int main() {
    std::string const tag = ",canonical_raid_rotation_20260927";
    auto p = demonology();
    // Raid scope alone never widens the lane (the round 3 rows are already applied).
    auto raidOnly = demonology();
    assert(BotRaidRotationOverrides::Apply(raidOnly) == 0 && raidOnly.MaxRange == 18.0f);
    // Eight enemy rows at the 18 yd lane plus the added Fel Flame row.
    assert(BotRaidRotationOverrides::ApplyCanonical(p) == 9);
    assert(p.MaxRange == 40.0f && p.MinRange == 5.0f);
    auto const base = demonology();
    for (size_t i = 0; i < base.Spells.size(); ++i) {
        BotActionProfileSpell const& before = base.Spells[i];
        BotActionProfileSpell const& after = p.Spells[i];
        bool const widened = before.TargetSelector == "enemy" && before.MaxRange == 18.0f;
        assert(after.MaxRange == (widened ? 0.0f : before.MaxRange)); // 0: native range
        assert(after.MinRange == before.MinRange && after.TargetSelector == before.TargetSelector);
        assert(after.MechanicTags == (widened ? before.MechanicTags + tag : before.MechanicTags));
        // Drain Life is never admitted in a canonical raid; no other health gate moves.
        assert(after.MaxSelfHealthPct == (before.SpellId == 689 ? 0.0f : before.MaxSelfHealthPct));
    }
    assert(p.Spells.size() == base.Spells.size() + 1);
    BotActionProfileSpell const& fel = p.Spells.back();
    assert(fel.SpellId == 77799 && fel.Category == BotCombatActionCategory::Builder);
    assert(fel.MechanicTags == "fel_flame,moving_filler" + tag);
    assert(fel.RequiresMoving && !fel.RequiresStationary && fel.PriorityBucket == 14 && fel.SortOrder == 140);
    assert(fel.DamageWeight > 0.09f && fel.DamageWeight < 0.11f && fel.TargetSelector == "enemy");
    assert(fel.MinRange == 0.0f && fel.MaxRange == 0.0f && fel.MovementDirective == "ranged");
    assert(fel.MinEnemies == 1 && fel.MaxEnemies == 0 && !fel.RequiresRangedRange && !fel.RequiresMeleeRange);
    // Idempotent.
    assert(BotRaidRotationOverrides::ApplyCanonical(p) == 0 && p.Spells.size() == base.Spells.size() + 1);
    // A world-DB Fel Flame row wins; a drifted lane is left alone.
    auto owned = demonology(); owned.Spells.push_back(row(77799, "enemy", 0, 40, "fel_flame"));
    assert(BotRaidRotationOverrides::ApplyCanonical(owned) == 8 && owned.Spells.back().MechanicTags == "fel_flame");
    auto drifted = demonology(); drifted.MaxRange = 20.0f;
    for (auto& s : drifted.Spells) if (s.MaxRange == 18.0f) s.MaxRange = 20.0f;
    // A drifted lane is left alone; Drain Life and Fel Flame still apply.
    assert(BotRaidRotationOverrides::ApplyCanonical(drifted) == 2 && drifted.MaxRange == 20.0f);
    assert(drifted.Spells[10].MaxRange == 20.0f && drifted.Spells[10].MaxSelfHealthPct == 0.0f);
    auto healthDrift = demonology(); healthDrift.Spells[10].MaxSelfHealthPct = 0.60f;
    assert(BotRaidRotationOverrides::ApplyCanonical(healthDrift) == 9);
    assert(healthDrift.Spells[10].MaxSelfHealthPct == 0.60f && healthDrift.Spells[10].MaxRange == 0.0f);
    // Other roles, specs and classes are untouched.
    for (auto other : { demonology("tank"), demonology("dps", "affliction_warlock"),
                        demonology("dps", "demonology_warlock", 8) }) {
        auto const copy = other;
        assert(BotRaidRotationOverrides::ApplyCanonical(other) == 0);
        assert(other.Spells.size() == copy.Spells.size() && other.MaxRange == copy.MaxRange);
    }

    auto rogue = assassination();
    assert(BotRaidRotationOverrides::Apply(rogue) == 1); // round 3 Vendetta only
    assert(rogue.Spells[2].TargetSelector == "enemy");
    // User decision 2026-09-27: Fan of Knives is never used in a canonical
    // raid. Round 4 removes the row (the round 2 self health ceiling still let
    // the range-recovery lane submit it; BotRaidCanonicalAssassination.h);
    // nothing else moves.
    assert(BotRaidRotationOverrides::ApplyCanonical(rogue) == 1);
    assert(rogue.Spells.size() == 2);
    for (auto const& s : rogue.Spells) assert(s.SpellId != 51723);
    assert(rogue.Spells[1].TargetSelector == "enemy" && rogue.Spells[1].MechanicTags == "mutilate");
    assert(rogue.Spells[0].MaxSelfHealthPct == 1.0f && rogue.Spells[1].MaxSelfHealthPct == 1.0f);
    assert(BotRaidRotationOverrides::ApplyCanonical(rogue) == 0);
    auto driftedRogue = assassination("assassination_rogue", 8.0f);
    assert(BotRaidRotationOverrides::ApplyCanonical(driftedRogue) == 0);
    assert(driftedRogue.Spells.size() == 3 && driftedRogue.Spells[2].MaxSelfHealthPct == 1.0f);
    auto combat = assassination("combat_rogue");
    assert(BotRaidRotationOverrides::ApplyCanonical(combat) == 0 && combat.Spells[2].MaxSelfHealthPct == 1.0f);
    // Raid scope alone (legacy rosters) keeps Fan of Knives.
    auto legacyRogue = assassination();
    BotRaidRotationOverrides::Apply(legacyRogue);
    assert(legacyRogue.Spells[2].MaxSelfHealthPct == 1.0f);

    // Elemental Mastery: one self offensive-cooldown row, canonical only.
    BotClassSpecActionProfile elemental; elemental.ClassId = 7; elemental.SpecTag = "elemental_shaman";
    elemental.Spells = { row(51505, "enemy", 0, 0, "lava_burst"), row(403, "enemy", 0, 0, "lightning_bolt") };
    auto legacyScope = elemental;
    assert(BotRaidRotationOverrides::Apply(legacyScope) == 0 && legacyScope.Spells.size() == 2);
    assert(BotRaidRotationOverrides::ApplyCanonical(elemental) == 1 && elemental.Spells.size() == 3);
    BotActionProfileSpell const& em = elemental.Spells.back();
    assert(em.SpellId == 16166 && em.Category == BotCombatActionCategory::OffensiveCooldown);
    assert(em.TargetSelector == "self" && em.PriorityBucket == 1 && em.SortOrder == 12 && em.MaxEnemies == 0);
    assert(em.MechanicTags == "elemental_mastery,self,burst" + tag && em.MaxRange == 0.0f);
    assert(BotRaidRotationOverrides::ApplyCanonical(elemental) == 0 && elemental.Spells.size() == 3);
    auto restoration = legacyScope; restoration.SpecTag = "restoration_shaman"; restoration.Role = "healer";
    assert(BotRaidRotationOverrides::ApplyCanonical(restoration) == 0);
    std::puts("ok");
}
'''


def test_canonical_class_rows_change_exactly_the_evidenced_rows(tmp_path: Path) -> None:
    assert _run(tmp_path, "rows", PROGRAM).strip() == "ok"


def test_rows_change_only_through_apply_canonical() -> None:
    overrides = OVERRIDES.read_text(encoding="utf-8")
    assert '#include "Bots/BotRaidCanonicalClassRotation.h"' in overrides
    apply_raid = overrides[overrides.index("inline uint32 Apply(BotClassSpecActionProfile& profile)"):
                           overrides.index("inline constexpr char const* CanonicalScopeTag")]
    canonical = overrides[overrides.index("inline uint32 ApplyCanonical(BotClassSpecActionProfile& profile)"):]
    assert "BotRaidCanonicalClassRotation" not in apply_raid
    assert canonical.count("BotRaidCanonicalClassRotation::Apply(profile,") == 1
    callers = sorted(path.name for path in (ROOT / "src").rglob("*")
                     if path.suffix in (".h", ".cpp")
                     and "BotRaidCanonicalClassRotation::" in path.read_text(errors="replace"))
    assert callers == ["BotRaidRotationOverrides.h"]
    # No world-DB migration this round: the calibration rows stay as they are.
    for path in WORLD.glob("*.sql"):
        assert TAG not in path.read_text(errors="replace"), path.name
    for path in (HEADER, OVERRIDES, ADMISSION):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path


def test_override_pre_state_matches_the_world_db_migrations() -> None:
    burst = (WORLD / "2026_07_25_12_phase8_demonology_melee_burst.sql").read_text()
    assert "`max_range` = 18.0" in burst and "`action`.`max_range` = 18.0" in burst
    assert "(`action`.`target_selector` = 'enemy' OR `action`.`spell_id` = 50589)" in burst
    affliction = (WORLD / "2026_09_12_02_affliction_moving_fel_flame.sql").read_text()
    assert "SELECT `p`.`id`, 140, 77799, 'builder', 'fel_flame,moving_filler_20260912',\n       0.10, 14, 1, 0, 'enemy', 'ranged', 'none', 0, 40, 1" in affliction
    assert "`p`.`spec_tag` = 'affliction_warlock'" in affliction
    fok = (WORLD / "2026_07_21_02_phase8_assassination_qualification.sql").read_text()
    assert " 90, 51723, 'aoe', 'fan_of_knives,aoe,poison_application'," in fok
    assert "'enemy', 'melee', 'melee', 0, 10, 0, 0.00, 0, 0, 0, 0, '');" in fok


def test_scope_protects_the_legacy_and_calibration_rosters() -> None:
    specs = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("character_guid"), int) and node.get("class_spec"):
                specs.add((node["character_guid"], node["class_spec"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(LEGACY_SHARDS.read_text(encoding="utf-8")))
    legacy = {spec for _guid, spec in specs}
    # The legacy rosters carry Fire mages (Magmaw 30006/30007) and Assassination
    # rogues, so these fixes are canonical-only; no legacy Demonology exists.
    assert "fire_mage" in legacy and "assassination_rogue" in legacy
    assert "demonology_warlock" not in legacy
    assert {spec for guid, spec in specs if 30001 <= guid <= 30010} >= {"fire_mage"}


def test_canonical_warlock_declares_fel_flame() -> None:
    composition = json.loads(COMPOSITION.read_text(encoding="utf-8"))
    warlock = next(row for row in composition["characters"] if row["character_key"] == "warlock")
    assert warlock["specs"] == ["demonology_warlock"] and warlock["spells"] == [77799]
    manifest = json.loads((ROOT / "experiments/configs/cata_434_action_profiles.json").read_text())
    # The action profile manifest (shared with calibration) is unchanged: the
    # Demonology spellbook there still lacks Fel Flame; Affliction has it.
    assert 77799 not in manifest["action_profile_spells_by_spec"]["demonology_warlock"]
    assert 77799 in manifest["action_profile_spells_by_spec"]["affliction_warlock"]


def test_canonical_warlock_spellbook_learns_fel_flame_natively() -> None:
    gear = ROOT / "dataset/validation_gear_profiles/profiles.json"
    if not gear.is_file() or not (DBC / "Item-sparse.db2").is_file():
        pytest.skip("DVC gear profiles or client DBCs not hydrated")
    from tests.test_raid_shard_plan import _plan
    from tools.raid_program.raid_loadout_spells import loadout_known_spells
    from tools.raid_program.raid_loadout_sql import prepare_config

    scenario_id = "blackwing_descent_10n_atramedes_c0_diagnostic"
    config = prepare_config(_plan(), gear, DBC, [scenario_id])
    scenario = next(row for row in config["scenarios"] if row["id"] == scenario_id)
    warlock = next(bot for bot in scenario["bots"] if bot["character_key"] == "warlock")
    # raid_loadout_spells refuses a declared spell the race and class cannot learn.
    assert 77799 in loadout_known_spells(warlock, DBC)["known_spell_ids"]


def _spell_ranges(spell_ids: set[int]) -> dict[int, tuple[int, float]]:
    def load(name: str):
        blob = (DBC / name).read_bytes()
        count, _fields, size, _strings = struct.unpack_from("<4I", blob, 4)
        return count, size, blob[20:20 + count * size]

    count, size, records = load("SpellRange.dbc")
    ranges = {}
    for index in range(count):
        record = records[index * size:(index + 1) * size]
        range_id, _min_hostile, _min_friendly, max_hostile = struct.unpack_from("<Iffff", record, 0)[:4]
        ranges[range_id] = max_hostile
    count, size, records = load("Spell.dbc")
    found = {}
    for index in range(count):
        record = records[index * size:(index + 1) * size]
        spell_id = struct.unpack_from("<I", record, 0)[0]
        if spell_id in spell_ids:
            range_index = struct.unpack_from("<I", record, 15 * 4)[0]
            found[spell_id] = (range_index, ranges[range_index])
    return found


def test_native_range_facts_behind_the_rows() -> None:
    if not (DBC / "Spell.dbc").is_file():
        pytest.skip("client DBCs not hydrated")
    facts = _spell_ranges({51723, 16166, 77799, 29722, 348, 172, 603, 71521, 6353, 689})
    # Fan of Knives (disabled, not retargeted) and Elemental Mastery are
    # self-cast (SpellRange 1, 0 yd).
    assert facts[51723] == (1, 0.0) and facts[16166] == (1, 0.0)
    # Fel Flame and every Demonology row that falls back to native range are
    # 40 yd spells: the profile lane (40 yd) matches them.
    for spell in (77799, 29722, 348, 172, 603, 71521, 6353, 689):
        assert facts[spell][1] == 40.0, (spell, facts[spell])


def test_combustion_patience_waits_for_a_strong_ignite_within_the_budget(tmp_path: Path) -> None:
    out = _run(tmp_path, "patience", r'''
#include "Bots/BotRaidFireCombustionPatience.h"
#include <cassert>
#include <cstdio>
#include <string>
int main() {
    using namespace BotRaidFireCombustionPatience;
    static_assert(StrongIgniteTick == 40000 && PatienceMs == 15000 && StaleGapMs == 10000);
    // A strong Ignite is admitted at once.
    assert(Ready(1, 40000, 1000));
    // A weak (10k+) Ignite waits until the window has been open 15 s.
    assert(!Ready(2, 27000, 1000));
    assert(!Ready(2, 30000, 9000));
    assert(!Ready(2, 39999, 15999));
    assert(Ready(2, 12000, 16000));
    // A gap longer than any cast restarts the clock (Combustion was cast, or
    // the window closed): the next cooldown waits again.
    assert(!Ready(2, 30000, 16000 + 120000));
    assert(Ready(2, 45000, 16000 + 120001));
    // Gaps up to 10 s (a Fireball, an Evocation channel) keep the clock.
    assert(!Ready(3, 20000, 0 + 1));
    assert(!Ready(3, 20000, 10001));
    assert(Ready(3, 20000, 20000));
    // Each mage has its own clock; a clock that runs backwards restarts.
    assert(!Ready(4, 20000, 20000));
    assert(!Ready(3, 20000, 5000));
    std::string reason = WaitReason;
    assert(reason == "combustion_ignite_patience");
    // Waits reports the rejection only while waiting.
    std::string rejection;
    assert(!Waits(5, StrongIgniteTick, rejection) && rejection.empty());
    assert(Waits(6, 12000, rejection) && rejection == "combustion_ignite_patience");
    assert(CanonicalScope(true, "blackwing_descent_10n_maloriak_c0_diagnostic"));
    assert(!CanonicalScope(true, "blackwing_descent_10n_magmaw_diagnostic"));
    assert(!CanonicalScope(false, "blackwing_descent_10n_maloriak_c0_diagnostic"));
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_admission_binds_the_patience_to_the_canonical_combustion_gate() -> None:
    admission = ADMISSION.read_text(encoding="utf-8")
    assert '#include "Bots/BotRaidFireCombustionPatience.h"' in admission
    header = (BOTS / "BotRaidFireCombustionPatience.h").read_text(encoding="utf-8")
    assert "return raidRotationScope && BotCanonicalRaidScope::IsCanonicalCompositionScenario(scenarioId);" in header
    gate = admission[admission.index("        if (bot->getClass() == CLASS_MAGE && candidate.SpellId == 11129)"):
                     admission.index("        if (candidate.Profile.RequiresInterruptibleTarget")]
    # The legacy window is checked first and unchanged outside canonical raids;
    # the patience only runs after it passed, and only in a canonical raid.
    assert gate.index('"combustion_dot_window_not_ready"') < gate.index("BotRaidFireCombustionPatience::Waits(")
    assert "if (canonicalRaidScope && BotRaidFireCombustionPatience::Waits(" in gate
    assert gate.count("canonicalRaidScope") == 2
    callers = sorted(path.name for path in (ROOT / "src").rglob("*")
                     if path.suffix in (".h", ".cpp")
                     and "BotRaidFireCombustionPatience::" in path.read_text(errors="replace"))
    assert callers == ["BotWorldPopulationMgrCombatResolverAdmission.cpp"]
