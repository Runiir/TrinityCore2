"""Static checks for the Atramedes native script split and its audited fixes.

boss_atramedes.cpp was 1,141 lines; it is split by concern into the creature
AIs (boss_atramedes.cpp), the spell/aura scripts (boss_atramedes_spells.cpp)
and the shared identifiers (boss_atramedes_shared.h). These tests pin that no
registration or DB binding was lost and that each audited defect stays fixed.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
BOSS = SCRIPTS / "boss_atramedes.cpp"
SPELLS = SCRIPTS / "boss_atramedes_spells.cpp"
SHARED = SCRIPTS / "boss_atramedes_shared.h"
LOADER = ROOT / "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp"
TDB = ROOT / "data/TDB_full_434.22011_2022_01_09/TDB_full_world_434.22011_2022_01_09.sql"

CREATURE_AIS = {
    "boss_atramedes",
    "npc_atramedes_ancient_dwarven_shield",
    "npc_atramedes_lord_victor_nefarius",
    "npc_atramedes_obnoxious_fiend",
    "npc_atramedes_reverberating_flame",
}
# spell_script_names bindings for the encounter (TDB 434.22011 and the
# historical custom update pack): every bound name must stay registered.
BOUND_SPELL_SCRIPTS = {
    "spell_atramedes_modulation",
    "spell_atramedes_roaring_flame_breath_reverse_cast",
    "spell_atramedes_roaring_flame_breath",
    "spell_atramedes_roaring_flame_breath_fire_periodic",
    "spell_atramedes_resonating_clash_ground",
    "spell_atramedes_resonating_clash_air",
    "spell_atramedes_resonating_clash",
    "spell_atramedes_sound_bar",
    "spell_atramedes_noisy",
    "spell_atramedes_vertigo",
    "spell_atramedes_sonic_flames",
    "spell_atramedes_devastation_trigger",
    "spell_atramedes_sonic_breath",
    "spell_atramedes_destroy_shield",
    "spell_atramedes_pestered",
    "spell_atramedes_apply_vehicle_periodic",
}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    raise AssertionError(f"unterminated: {signature}")


def test_split_files_stay_below_the_module_size_limit() -> None:
    for path in (BOSS, SPELLS, SHARED):
        assert len(text(path).splitlines()) < 1000, path.name


def test_every_script_is_still_registered_once() -> None:
    boss, spells = text(BOSS), text(SPELLS)
    for ai in CREATURE_AIS:
        assert boss.count(f"RegisterBlackwingDescentCreatureAI({ai});") == 1, ai
    registered = set(re.findall(r"RegisterSpellScript\((\w+)\);", spells))
    registered |= set(re.findall(r"RegisterSpellAndAuraScriptPair\((\w+),", spells))
    assert registered == BOUND_SPELL_SCRIPTS
    # The loader only knows AddSC_boss_atramedes; it chains the spell file.
    assert "void AddSC_boss_atramedes();" in text(LOADER)
    assert "AddSC_boss_atramedes_spells" not in text(LOADER)
    assert "void AddSC_boss_atramedes_spells();" in boss
    assert "    AddSC_boss_atramedes_spells();" in function_body(boss, "void AddSC_boss_atramedes()")
    assert "void AddSC_boss_atramedes_spells()" in spells


def test_database_bindings_match_registered_names() -> None:
    if not TDB.exists():
        return
    dump = TDB.read_text(encoding="utf-8", errors="replace")
    bound = set(re.findall(r"\(\d+,'(spell_atramedes_\w+)'\)", dump))
    assert bound and bound <= BOUND_SPELL_SCRIPTS
    ais = set(re.findall(r"'(boss_atramedes|npc_atramedes_\w+)'", dump))
    assert ais <= CREATURE_AIS


def test_player_sound_bar_is_cleared_on_evade_and_death() -> None:
    boss, shared = text(BOSS), text(SHARED)
    assert re.search(r"SPELL_SOUND_BAR_PLAYER\s*=\s*88824", shared)
    cleanup = function_body(boss, "void RemoveEncounterSoundFromPlayers()")
    assert "DoRemoveAurasDueToSpellOnPlayers(SPELL_SOUND_BAR_PLAYER)" in cleanup
    assert "DoRemoveAurasDueToSpellOnPlayers(SPELL_NOISY)" in cleanup
    assert "RemoveEncounterSoundFromPlayers();" in function_body(boss, "void EnterEvadeMode(")
    assert "RemoveEncounterSoundFromPlayers();" in function_body(boss, "void JustDied(")


def test_native_mechanic_timers_are_published_from_the_event_map() -> None:
    body = function_body(text(BOSS), "uint32 GetTimeUntilEncounterMechanic(uint32 spellId) const override")
    for spell, event in (("SPELL_SEARING_FLAME", "EVENT_SEARING_FLAME"),
                         ("SPELL_SONIC_BREATH", "EVENT_SONIC_BREATH"),
                         ("SPELL_TAKE_OFF_ANIM_KIT", "EVENT_LIFTOFF")):
        assert f"case {spell}:" in body and event in body
    assert "events.IsInPhase(PHASE_GROUND)" in body
    assert "events.GetTimeUntilEvent(eventId)" in body
    assert "dueAt <= events.GetTimer()" in body


def test_landing_removes_the_air_sonar_trigger() -> None:
    boss = text(BOSS)
    land = boss[boss.index("case EVENT_LAND:"):boss.index("case EVENT_REENGAGE_PLAYERS:")]
    assert "GetSpellIdForDifficulty(SPELL_SONAR_PULSE_TRIGGER, me)" in land
    assert "SPELL_SONAR_PULSE_PERIODIC_TRIGGER" not in land


def test_intro_vertigo_asks_the_boss_ai_not_the_instance() -> None:
    spells, boss = text(SPELLS), text(BOSS)
    vertigo = function_body(spells, "void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)\n    {\n        Unit* target = GetTarget();\n        target->CastSpell")
    assert "atramedes->AI()->GetData(DATA_IS_IN_INTRO_FLIGHT)" in vertigo
    assert "instance->GetData(DATA_IS_IN_INTRO_PHASE)" not in spells
    getter = function_body(boss, "uint32 GetData(uint32 type) const override")
    assert "case DATA_IS_IN_INTRO_FLIGHT:" in getter
    assert "me->HasReactState(REACT_PASSIVE)" in getter


def test_redirected_roaring_flame_restarts_at_initial_speed() -> None:
    boss, shared = text(BOSS), text(SHARED)
    assert re.search(r"SPELL_BUILDING_SPEED_EFFECT\s*=\s*78218", shared)
    inform = boss[boss.index("case POINT_DWARVEN_SHIELD:"):]
    inform = inform[:inform.index("_lastUsedDwarvenShieldUserGUID = ObjectGuid::Empty;")]
    assert "DoCastSelf(SPELL_SONIC_FLAMES);" in inform
    assert "GetSpellIdForDifficulty(SPELL_BUILDING_SPEED_EFFECT, me)" in inform
    assert inform.index("RemoveAurasDueToSpell") < inform.index("trackTarget(target)")


def test_unchanged_native_schedule_is_preserved() -> None:
    engage = function_body(text(BOSS), "void JustEngagedWith(Unit* who) override")
    for event, delay in (("EVENT_SONAR_PULSE", "14s + 500ms"), ("EVENT_MODULATION", "13s"),
                         ("EVENT_SEARING_FLAME", "46s"), ("EVENT_SONIC_BREATH", "24s"),
                         ("EVENT_LIFTOFF", "1min + 31s")):
        assert f"events.ScheduleEvent({event}, {delay}, 0, PHASE_GROUND);" in engage
