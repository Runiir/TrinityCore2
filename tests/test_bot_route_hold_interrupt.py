"""Route holds interrupt only offensive casts on composition raid rows.

Round 4 r04 traces (113,713 entries in all 102 replies): the route's hold and
reject branches called InterruptNonMeleeSpells(false) at the start of every
tick, while the route candidate claimed only movement, so the healers' Support
heal candidate started a heal that the next tick killed. The Atramedes healers
prepared 953 cast-time heals and 860 failed (SPELL_FAILED_INTERRUPTED, never
moving); after the wipe the paladin landed 1 of 415 and the priest 0 of 353.
771 of the 778 post-wipe failures came from the boss-node rejection of
undeclared trash (boss_route_target_not_declared, Mongrel 46083 and Drakonid
Slayer 42802).

On composition raid rows (a raid instance, row field composition_recovery) the
rejection (TrashThreatControl and TankFocusAssist) and the pending-pull healer
anchor (GroupHeal) interrupt only offensive casts, and the DPS threat-gate
hold owns the cast lanes for its tick. Stonecore, legacy Magmaw and calibration
keep the blanket interrupt.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def _source(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


def _code(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _block(source: str, start: int) -> str:
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError("unterminated block")


def _namespace(name: str, namespace: str) -> str:
    source = _source(name)
    return _block(source, source.index(f"namespace {namespace}\n{{"))


def _run(tmp_path: Path, program: str) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


PURE = r'''
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)

struct Node { std::string NodeId; bool CompositionRecovery = false; };
struct CohortConfig { bool ValidationRouteEnable = true; std::string ValidationRouteNodeId; };
struct CohortRaid { bool RaidInstance = true; };
struct Cohort { CohortConfig Config; CohortRaid Raid; };
struct Party { std::size_t ValidationRouteManifestIndex = 0; std::vector<Node> ValidationRouteManifest; };
'''


def test_offensive_cast_and_scope_decisions(tmp_path: Path) -> None:
    program = PURE + _namespace("BotRouteHoldInterrupt.h", "BotRouteHoldInterrupt") + r'''
int main()
{
    using namespace BotRouteHoldInterrupt;
    CHECK(!IsOffensiveCast(true, false, true));    // Flash of Light on the tank
    CHECK(!IsOffensiveCast(true, false, false));   // a harmful-flagged spell on an ally (not attackable)
    CHECK(IsOffensiveCast(true, true, false));     // Smite on the Mongrel
    CHECK(IsOffensiveCast(true, true, true));      // any cast on an attackable unit
    CHECK(!IsOffensiveCast(false, false, true));   // Holy Radiance, Tranquility (no unit target)
    CHECK(IsOffensiveCast(false, false, false));   // Blizzard, Hurricane (no unit target)

    // Scope: the active node of a composition row in a raid instance only.
    Cohort cohort;
    cohort.Config.ValidationRouteNodeId = "bwd.atramedes.encounter";
    Party party;
    party.ValidationRouteManifest = { { "bwd.atramedes.encounter", true } };
    CHECK(OffensiveOnlyScope(cohort, party));
    Cohort stonecore = cohort;
    stonecore.Raid.RaidInstance = false;           // a dungeon
    CHECK(!OffensiveOnlyScope(stonecore, party));
    Party legacy = party;
    legacy.ValidationRouteManifest[0].CompositionRecovery = false;   // legacy Magmaw rows
    CHECK(!OffensiveOnlyScope(cohort, legacy));
    Cohort calibration = cohort;
    calibration.Config.ValidationRouteEnable = false;
    CHECK(!OffensiveOnlyScope(calibration, party));
    Cohort otherNode = cohort;
    otherNode.Config.ValidationRouteNodeId = "bwd.atramedes.regroup";
    CHECK(!OffensiveOnlyScope(otherNode, party));
    Party past = party;
    past.ValidationRouteManifestIndex = 1;
    CHECK(!OffensiveOnlyScope(cohort, past));
    return failures ? 1 : 0;
}
'''
    _run(tmp_path, program)


SERVER_STUBS = r'''
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include <algorithm>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)

struct ObjectGuid
{
    uint64 raw = 0;
    bool player = false;
    bool IsEmpty() const { return raw == 0; }
    bool IsPlayer() const { return player; }
    bool operator==(ObjectGuid const& other) const { return raw == other.raw; }
};
struct Map { };
Map g_map;
struct Unit;
struct Creature;
struct Player;
struct WorldObject
{
    ObjectGuid guid;
    virtual ~WorldObject() = default;
    ObjectGuid GetGUID() const { return guid; }
    Map* FindMap() const { return &g_map; }
    float GetVisibilityRange() const { return 100.0f; }
    Unit* ToUnit();
};
struct SpellInfo
{
    uint32 Id = 0;
    bool positive = false;
    bool IsPositive() const { return positive; }
};
enum CurrentSpellTypes { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL, CURRENT_AUTOREPEAT_SPELL, CURRENT_MAX_SPELL };
struct Spell;
struct Unit : WorldObject
{
    bool hostile = false;
    Spell* current[CURRENT_MAX_SPELL] = {};
    std::vector<int> interrupted;
    bool blanket = false;
    Spell* GetCurrentSpell(CurrentSpellTypes type) const { return current[type]; }
    bool IsValidAttackTarget(Unit const* target) const { return target->hostile != hostile; }
    void InterruptSpell(CurrentSpellTypes type, bool, bool) { interrupted.push_back(type); current[type] = nullptr; }
    void InterruptNonMeleeSpells(bool)
    {
        blanket = true;
        for (int type = 0; type < CURRENT_MAX_SPELL; ++type)
            if (current[type])
                InterruptSpell(CurrentSpellTypes(type), false, true);
    }
};
struct Creature : Unit { };
struct Player : Unit { };
Unit* WorldObject::ToUnit() { return static_cast<Unit*>(this); }

std::vector<Unit*> g_world;
namespace ObjectAccessor
{
Unit* GetUnit(WorldObject const&, ObjectGuid const& guid)
{
    for (Unit* unit : g_world)
        if (unit->guid.raw == guid.raw)
            return unit;
    return nullptr;
}
Player* FindConnectedPlayer(ObjectGuid const&) { return nullptr; }
}
template <class T> struct GridReference { T* source; T* GetSource() const { return source; } };
template <class T> struct GridRefManager
{
    std::vector<GridReference<T>> refs;
    using iterator = typename std::vector<GridReference<T>>::iterator;
    iterator begin() { return refs.begin(); }
    iterator end() { return refs.end(); }
};
struct Cell
{
    template <class Visitor>
    static void VisitAllObjects(WorldObject const*, Visitor& visitor, float)
    {
        GridRefManager<Creature> none;
        visitor.Visit(none);
    }
};
struct SpellCastTargets
{
    WorldObject* m_objectTarget = nullptr;
    ObjectGuid m_objectTargetGUID;
    WorldObject* GetObjectTarget() const { return m_objectTarget; }
    ObjectGuid GetUnitTargetGUID() const { return m_objectTargetGUID; }
};
struct Spell
{
    WorldObject* caster = nullptr;
    SpellInfo const* info = nullptr;
    SpellCastTargets m_targets;
    WorldObject* GetCaster() const { return caster; }
    SpellInfo const* GetSpellInfo() const { return info; }
};
'''


def test_heal_survives_the_boss_node_rejection_and_offense_is_interrupted(tmp_path: Path) -> None:
    program = (SERVER_STUBS + _namespace("BotSpellCastTarget.h", "BotSpellCastTarget")
               + _namespace("BotRouteHoldInterrupt.h", "BotRouteHoldInterrupt")
               + _namespace("BotRouteHoldInterruptServer.h", "BotRouteHoldInterrupt") + r'''
Spell* Cast(Unit* caster, Unit* target, SpellInfo const* info)
{
    Spell* spell = new Spell();
    spell->caster = caster;
    spell->info = info;
    if (target)
    {
        spell->m_targets.m_objectTarget = target;
        spell->m_targets.m_objectTargetGUID = target->guid;
    }
    return spell;
}

int main()
{
    using namespace BotRouteHoldInterrupt;
    Player priest; priest.guid = { 11007009, true };
    Player tank; tank.guid = { 11007001, true };
    Creature mongrel; mongrel.guid = { 250120, false }; mongrel.hostile = true;
    g_world = { &priest, &tank, &mongrel };
    SpellInfo flashHeal{ 2061, true }, smite{ 585, false }, holyNova{ 15237, true }, penance{ 47540, false };

    // Round 4 Atramedes: the priest is mid-Flash Heal on the tank when the
    // boss-node rejection fires on the Mongrel. Composition row: it survives.
    priest.current[CURRENT_GENERIC_SPELL] = Cast(&priest, &tank, &flashHeal);
    InterruptForRouteHold(&priest, true);
    CHECK(priest.current[CURRENT_GENERIC_SPELL] && priest.interrupted.empty() && !priest.blanket);
    // A self-cast and a targetless positive spell survive too.
    priest.current[CURRENT_GENERIC_SPELL] = Cast(&priest, &priest, &flashHeal);
    priest.current[CURRENT_CHANNELED_SPELL] = Cast(&priest, nullptr, &holyNova);
    CHECK(!InterruptOffensiveCasts(&priest));
    // An offensive cast (Smite on the Mongrel) and an offensive channel
    // (Penance on it) are interrupted; so is an auto-repeat shot.
    priest.current[CURRENT_GENERIC_SPELL] = Cast(&priest, &mongrel, &smite);
    priest.current[CURRENT_CHANNELED_SPELL] = Cast(&priest, &mongrel, &penance);
    priest.current[CURRENT_AUTOREPEAT_SPELL] = Cast(&priest, &mongrel, &smite);
    InterruptForRouteHold(&priest, true);
    CHECK(!priest.current[CURRENT_GENERIC_SPELL] && !priest.current[CURRENT_CHANNELED_SPELL]
        && !priest.current[CURRENT_AUTOREPEAT_SPELL] && priest.interrupted.size() == 3);
    // A channeled heal on an ally survives while the offensive cast stops.
    priest.interrupted.clear();
    priest.current[CURRENT_GENERIC_SPELL] = Cast(&priest, &mongrel, &smite);
    priest.current[CURRENT_CHANNELED_SPELL] = Cast(&priest, &tank, &penance);
    InterruptForRouteHold(&priest, true);
    CHECK(!priest.current[CURRENT_GENERIC_SPELL] && priest.current[CURRENT_CHANNELED_SPELL]);

    // Outside the scope (Stonecore, legacy Magmaw, calibration): the blanket
    // interrupt, exactly as before, even for the heal.
    Player druid; druid.guid = { 11001005, true };
    g_world.push_back(&druid);
    druid.current[CURRENT_GENERIC_SPELL] = Cast(&druid, &tank, &flashHeal);
    InterruptForRouteHold(&druid, false);
    CHECK(druid.blanket && !druid.current[CURRENT_GENERIC_SPELL]);
    return failures ? 1 : 0;
}
''')
    _run(tmp_path, program)


def test_sites_use_the_scoped_interrupt_and_the_hold_claims_the_cast_lanes() -> None:
    trash = _code(_source("BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp"))
    rejection = trash[trash.index("Unit* rejected = returning ? returnTrashRejected : trashThreatControl.AreaTarget;"):]
    rejection = rejection[:rejection.index('"trash_threat_hold");')]
    assert ("BotRouteHoldInterrupt::InterruptForRouteHold(bot,\n"
            "            BotRouteHoldInterrupt::OffensiveOnlyScope(Cohort(), Party()));") in rejection
    assert "InterruptNonMeleeSpells" not in rejection
    hold = trash[:trash.index('"trash_threat_pickup_hold");')]
    hold = hold[hold.rindex("bool const offensiveOnly = BotRouteHoldInterrupt::OffensiveOnlyScope(Cohort(), Party());"):]
    for marker in ("BotRouteHoldInterrupt::InterruptForRouteHold(bot, offensiveOnly);",
                   "state.ValidationRouteOffenseHold = offensiveOnly;"):
        assert marker in hold, marker
    assert "InterruptNonMeleeSpells" not in hold
    focus = _code(_source("BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp"))
    undeclared = focus[focus.index("&& !BotValidationRouteRecoveryReturn::AdmitsReturnTrash("):]
    undeclared = undeclared[:undeclared.index('"shared_focus_not_declared");')]
    assert ("BotRouteHoldInterrupt::InterruptForRouteHold(bot,\n"
            "                    BotRouteHoldInterrupt::OffensiveOnlyScope(Cohort(), Party()));") in undeclared
    assert "InterruptNonMeleeSpells" not in undeclared
    heal = _code(_source("BotWorldPopulationMgrValidationGroupHeal.cpp"))
    anchor = heal[heal.index("if (pendingDungeonPullCount > 0 && !healer->IsFalling())"):]
    anchor = anchor[:anchor.index("bool moved = false;")]
    assert ("if (healer->HasUnitState(UNIT_STATE_CASTING))\n"
            "                BotRouteHoldInterrupt::InterruptForRouteHold(healer,\n"
            "                    BotRouteHoldInterrupt::OffensiveOnlyScope(Cohort(), Party()));") in anchor
    fallback = _code(_source("BotWorldPopulationMgrUpdateBotKernelFallback.cpp"))
    assert fallback.index("context.State.ValidationRouteOffenseHold = false;") < fallback.index(
        "routeAttempt->Handled = TryValidationRouteObjective(")
    assert "routeAttempt->OffenseHold = context.State.ValidationRouteOffenseHold;" in fallback
    action = fallback[fallback.index('routeAction.Key = "world.validation_route_action";'):]
    action = action[:action.index("context.State.DecisionKernel.Submit(std::move(routeAction));")]
    assert ("if (routeAttempt->OffenseHold)\n"
            '                return BotActionArbitration::Outcome::Submitted("route_offense_hold");') in action
    state = _code(_source("BotWorldPopulationMgrBotState.h"))
    assert "bool ValidationRouteOffenseHold = false;" in state
    server = _code(_source("BotRouteHoldInterruptServer.h"))
    assert "BotSpellCastTarget::UnitTarget(spell)" in server and "GetUnitTarget()" not in server
    for name in ("BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp",
                 "BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp",
                 "BotWorldPopulationMgrValidationGroupHeal.cpp",
                 "BotWorldPopulationMgrUpdateBotKernelFallback.cpp",
                 "BotWorldPopulationMgrBotState.h", "BotRouteHoldInterrupt.h",
                 "BotRouteHoldInterruptServer.h"):
        assert len(_source(name).splitlines()) < 1000, name
