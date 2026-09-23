from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/server/game/Bots"


def _function(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def _section(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def _production_fixture_source() -> str:
    planning = _function(
        (BOT / "BotWorldPopulationMgrRaidPlanning.cpp").read_text(),
        "uint32 BotWorldPopulationMgr::ResolveScopedEncounterAreaSpellId(",
    )
    planning = planning.replace(
        "uint32 BotWorldPopulationMgr::ResolveScopedEncounterAreaSpellId",
        "uint32 ResolveScopedEncounterAreaSpellId",
    ).replace(") const\n{", ")\n{")
    semantics = _function(
        (BOT / "BotWorldPopulationMgrSpellSemantics.cpp").read_text(),
        "bool SpellHasHostileMeleeChainSemantics(",
    )
    boss_mechanics = (BOT / "BotWorldPopulationMgrBossMechanics.cpp").read_text()
    caller = _section(
        boss_mechanics,
        "    uint32 const scopedAreaSpellId = ResolveScopedEncounterAreaSpellId(bot, result.Target);",
        "    BotActionResult actionResult = ExecuteProfileCombatAction(",
    ).replace(
        "ResolveScopedEncounterAreaSpellId(bot, result.Target)",
        "manager.ResolveScopedEncounterAreaSpellId(bot, target)",
    )
    resolver = (BOT / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    resolver_start = resolver.index(
        "        if (HasNearbyProtectedEncounterTarget(bot, target, candidateSpellInfo)"
    )
    resolver_guard = resolver[resolver_start : resolver.index(
        "        if (forbidArea", resolver_start
    )]
    declarative_guard = _section(
        resolver,
        "        if (forbidArea && SpellHasHostileMultiTargetSemantics(candidateSpellInfo)",
        "        if (bot->HasUnitState(UNIT_STATE_CONTROLLED)",
    )
    executor = (BOT / "BotActionExecutor.cpp").read_text()
    combat_start = executor.index(
        "BotActionResult BotActionExecutor::ExecuteCombat("
    )
    primary_start = executor.index(
        "    if (Creature const* creature = target ? target->ToCreature() : nullptr;",
        combat_start,
    )
    primary_guard = executor[primary_start : executor.index(
        '    if (action.Type == "pull"', primary_start
    )]
    preview_start = executor.index("    if ((action.SuppressAreaDamage\n")
    preview_guard = executor[preview_start : executor.index(
        "    if (!target", preview_start
    )]
    final_start = executor.index("    if ((action.SuppressAreaDamage\n", preview_start + 1)
    final_guard = executor[final_start : executor.index(
        "    BotActionResult check =", final_start
    )]

    # Keep the planner as its native member call and compile the exact guard
    # blocks. Only the world/profile/DBC objects around them are deterministic
    # fixture dependencies; the admission predicates remain production text.
    return """
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
constexpr uint8 MAX_SPELL_EFFECTS = 3;
constexpr uint32 SPELL_DAMAGE_CLASS_MELEE = 2;

struct Guid
{
    uint64 value = 0;
    uint64 GetRawValue() const { return value; }
};

struct Creature
{
    uint32 entry = 0;
    uint32 spawn = 0;
    Guid guid;
    uint32 GetEntry() const { return entry; }
    uint32 GetSpawnId() const { return spawn; }
    Guid const& GetGUID() const { return guid; }
};

struct Unit
{
    uint32 entry = 0;
    Creature* creature = nullptr;
    uint32 GetEntry() const { return entry; }
    Creature* ToCreature() const { return creature; }
};

struct Player
{
    std::string specTag;
};

struct SpellEffectInfo
{
    uint32 Effect = 0;
    uint32 ChainTarget = 0;
    bool Positive = false;
    bool IsEffect() const { return Effect != 0; }
};

struct SpellInfo
{
    uint32 DmgClass = 0;
    bool MultiTarget = false;
    SpellEffectInfo Effects[MAX_SPELL_EFFECTS];
    bool IsPositiveEffect(uint8 index) const { return Effects[index].Positive; }
};

struct SpellMgr
{
    SpellInfo const* heart = nullptr;
    SpellInfo const* magic = nullptr;

    SpellInfo const* GetSpellInfo(uint32 id) const
    {
        return id == 55050 ? heart : (id == 421 || id == 48505 ? magic : nullptr);
    }
};

SpellMgr* sSpellMgr = nullptr;

namespace BotWorldPopulationMgrSpellSemantics
{
""" + semantics + """
}

struct ValidationRouteManifestNode
{
    std::string NodeId;
    bool MechanicContractResolved = false;
    bool AllowAreaDamage = false;
    std::vector<uint32> AreaDamageSpellAllowlist;
    std::vector<uint32> AreaDamageTargetAllowlist;
};

struct PartyState
{
    std::size_t ValidationRouteManifestIndex = 0;
    std::vector<ValidationRouteManifestNode> ValidationRouteManifest;
};

struct BotClassSpecActionProfile
{
    std::string SpecTag;
};

namespace BotClassSpecActionProfileStore
{
BotClassSpecActionProfile Build(Player* bot, std::string const&)
{
    return { bot ? bot->specTag : std::string() };
}
}

struct BotWorldPopulationMgr
{
    PartyState party;
    PartyState const& Party() const { return party; }
    std::string GetDungeonRole(Player*) const { return "tank"; }
""" + planning.replace("\n}", "\n}", 1) + """
};

struct RaidMechanicAdapter
{
    bool ContractResolved = false;
    bool AllowAreaDamage = false;
    std::string TargetControl;
};

using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMeleeChainSemantics;

bool CallerForbidArea(BotWorldPopulationMgr& manager, Player* bot,
    Unit const* target, RaidMechanicAdapter const& raidAdapter,
    bool controlledAoeReleased)
{
""" + caller + r"""
    return forbidArea;
}

bool nearbyProtected = false;
bool HasNearbyProtectedEncounterTarget(Player*, Unit const*, SpellInfo const* = nullptr)
{
    return nearbyProtected;
}

namespace BotWorldPopulationMgrSpellSemantics
{
bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo)
{
    return spellInfo && spellInfo->MultiTarget;
}
}

using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMeleeChainSemantics;
using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;

struct Candidate
{
    std::string RejectReason;
};

std::string ResolverAdmission(Player* bot, Unit const* target,
    SpellInfo const* candidateSpellInfo, bool magmawMushroomAction,
    bool scopedAreaAction)
{
    Candidate candidate;
    for (int iteration = 0; iteration < 1; ++iteration)
    {
""" + resolver_guard + """
    }
    return candidate.RejectReason;
}

std::string DeclarativeAdmission(uint32 candidateSpellId,
    SpellInfo const* candidateSpellInfo,
    bool forbidArea, bool magmawMushroomAction, bool scopedAreaAction)
{
    Candidate candidate;
    (void)candidateSpellId;
    for (int iteration = 0; iteration < 1; ++iteration)
    {
""" + declarative_guard + r"""
    }
    return candidate.RejectReason;
}

enum class BotActionResult : uint8
{
    NoAction,
    Ok
};

struct ResolvedCombatAction
{
    bool SuppressAreaDamage = false;
    bool AllowMagmawBalanceMushroomSplash = false;
    bool AllowScopedEncounterAreaDamage = false;
};

struct ResolvedSpell
{
    SpellInfo const* Effective = nullptr;
};

BotActionResult PreviewAdmission(ResolvedCombatAction const& action,
    Player* bot, Unit const* target, ResolvedSpell const& preview)
{
""" + preview_guard + """
    return BotActionResult::Ok;
}

BotActionResult FinalAdmission(ResolvedCombatAction const& action,
    Player* bot, Unit const* target, ResolvedSpell const& resolved)
{
""" + final_guard + """
    return BotActionResult::Ok;
}

bool protectedPrimary = false;
namespace BotRaidAreaAuthority
{
bool IsProtectedEncounterTarget(uint64, uint32, uint32, uint64)
{
    return protectedPrimary;
}
}

BotActionResult PrimaryAdmission(Unit* target)
{
    uint64 const ownerGuid = 1;
""" + primary_guard + """
    return BotActionResult::Ok;
}

int main()
{
    BotWorldPopulationMgr manager;
    ValidationRouteManifestNode node;
    node.NodeId = "bwd.magmaw.encounter";
    node.MechanicContractResolved = true;
    node.AllowAreaDamage = false;
    node.AreaDamageSpellAllowlist = { 421, 48505, 55050 };
    node.AreaDamageTargetAllowlist = { 41570, 42347 };
    manager.party.ValidationRouteManifest.push_back(node);

    Player blood{ "blood_death_knight" };
    Player elemental{ "elemental_shaman" };
    Player balance{ "balance_druid" };
    Player other{ "frost_death_knight" };
    Unit body{ 41570 };
    Unit head{ 42347 };
    Unit parasite{ 41806 };
    Unit arbitrary{ 99999 };

    assert(manager.ResolveScopedEncounterAreaSpellId(&blood, &body) == 55050);
    assert(manager.ResolveScopedEncounterAreaSpellId(&blood, &head) == 55050);
    assert(manager.ResolveScopedEncounterAreaSpellId(&blood, &parasite) == 0);
    assert(manager.ResolveScopedEncounterAreaSpellId(&blood, &arbitrary) == 0);
    assert(manager.ResolveScopedEncounterAreaSpellId(&elemental, &body) == 421);
    assert(manager.ResolveScopedEncounterAreaSpellId(&balance, &body) == 48505);
    assert(manager.ResolveScopedEncounterAreaSpellId(&other, &body) == 0);

    SpellInfo heart;
    heart.DmgClass = SPELL_DAMAGE_CLASS_MELEE;
    heart.MultiTarget = true;
    heart.Effects[0] = { 2, 3, false };
    SpellInfo magic;
    magic.MultiTarget = true;
    magic.Effects[0] = { 2, 3, false };
    SpellInfo singleMelee;
    singleMelee.DmgClass = SPELL_DAMAGE_CLASS_MELEE;
    singleMelee.MultiTarget = false;
    singleMelee.Effects[0] = { 2, 1, false };
    SpellInfo positiveMelee = heart;
    positiveMelee.Effects[0].Positive = true;
    assert(SpellHasHostileMeleeChainSemantics(&heart));
    assert(!SpellHasHostileMeleeChainSemantics(&magic));
    assert(!SpellHasHostileMeleeChainSemantics(&singleMelee));
    assert(!SpellHasHostileMeleeChainSemantics(&positiveMelee));

    sSpellMgr = new SpellMgr{ &heart, &magic };
    RaidMechanicAdapter contractAdapter{ true, false, "" };
    BotWorldPopulationMgr oldManager;
    ValidationRouteManifestNode oldNode = node;
    oldNode.AreaDamageSpellAllowlist = { 421, 48505 };
    oldManager.party.ValidationRouteManifest.push_back(oldNode);
    assert(oldManager.ResolveScopedEncounterAreaSpellId(&blood, &body) == 0);
    bool const oldForbid = CallerForbidArea(oldManager, &blood, &body,
        contractAdapter, false);
    assert(oldForbid);
    assert(DeclarativeAdmission(55050, &heart, oldForbid, false, false)
        == "declarative_area_damage_semantics_forbidden");
    assert(CallerForbidArea(manager, &blood, &body, contractAdapter, false));
    assert(CallerForbidArea(manager, &blood, &head, contractAdapter, false));
    assert(!CallerForbidArea(manager, &elemental, &body, contractAdapter, false));
    assert(!CallerForbidArea(manager, &balance, &body, contractAdapter, false));
    SpellInfo dnd = magic;
    SpellInfo bloodBoil = magic;
    bool const bloodForbid = CallerForbidArea(manager, &blood, &body,
        contractAdapter, false);
    assert(DeclarativeAdmission(43265, &dnd, bloodForbid, false, false)
        == "declarative_area_damage_semantics_forbidden");
    assert(DeclarativeAdmission(48721, &bloodBoil, bloodForbid, false, false)
        == "declarative_area_damage_semantics_forbidden");
    assert(DeclarativeAdmission(55050, &heart, bloodForbid, false, true).empty());
    assert(DeclarativeAdmission(421, &magic,
        CallerForbidArea(manager, &elemental, &body, contractAdapter, false),
        false, true).empty());
    RaidMechanicAdapter permissiveAdapter{ true, true, "" };
    assert(!CallerForbidArea(manager, &blood, &body, permissiveAdapter, false));
    RaidMechanicAdapter controlledAdapter{ true, true, "controlled_aoe" };
    assert(CallerForbidArea(manager, &blood, &body, controlledAdapter, false));
    assert(!CallerForbidArea(manager, &blood, &body, controlledAdapter, true));

    nearbyProtected = false;
    assert(ResolverAdmission(&blood, &body, &heart, false, true).empty());
    nearbyProtected = true;
    assert(ResolverAdmission(&blood, &body, &heart, false, true)
        == "future_encounter_splash_forbidden");
    assert(ResolverAdmission(&elemental, &body, &magic, false, true).empty());

    ResolvedCombatAction scoped;
    scoped.AllowScopedEncounterAreaDamage = true;
    ResolvedSpell preview{ &heart };
    ResolvedSpell resolved{ &heart };
    assert(PreviewAdmission(scoped, &blood, &body, preview)
        == BotActionResult::NoAction);
    assert(FinalAdmission(scoped, &blood, &body, resolved)
        == BotActionResult::NoAction);

    nearbyProtected = false;
    assert(PreviewAdmission(scoped, &blood, &body, preview)
        == BotActionResult::Ok);
    nearbyProtected = true;
    assert(FinalAdmission(scoped, &blood, &body, resolved)
        == BotActionResult::NoAction);

    ResolvedCombatAction scopedMagic = scoped;
    preview.Effective = &magic;
    resolved.Effective = &magic;
    assert(PreviewAdmission(scopedMagic, &elemental, &body, preview)
        == BotActionResult::Ok);
    assert(FinalAdmission(scopedMagic, &elemental, &body, resolved)
        == BotActionResult::Ok);

    ResolvedCombatAction unscoped;
    nearbyProtected = false;
    assert(ResolverAdmission(&blood, &parasite, &heart, false, false).empty());
    nearbyProtected = true;
    assert(ResolverAdmission(&other, &body, &magic, false, false)
        == "future_encounter_splash_forbidden");

    Creature primaryCreature{ 41570, 9, { 4157009 } };
    Unit primary{ 41570, &primaryCreature };
    protectedPrimary = true;
    assert(PrimaryAdmission(&primary) == BotActionResult::NoAction);
    protectedPrimary = false;
    assert(PrimaryAdmission(&primary) == BotActionResult::Ok);

    return 0;
}
"""


def test_scoped_heart_strike_fixture_executes_production_admission(tmp_path: Path) -> None:
    config = json.loads(
        (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text()
    )
    contracts = [
        step["mechanic_contract"]
        for scenarios in (config["scenarios"], config["diagnostic_scenarios"])
        for scenario in scenarios
        for step in scenario["route"]
        if step.get("node_id") == "bwd.magmaw.encounter"
    ]
    assert len(contracts) == 2
    assert all(contract["area_damage_spell_allowlist"] == [421, 48505, 55050]
               for contract in contracts)
    assert all(contract["area_damage_target_allowlist"] == [41570, 42347]
               for contract in contracts)

    source = tmp_path / "magmaw_scoped_heart_strike.cpp"
    binary = tmp_path / "magmaw_scoped_heart_strike"
    source.write_text(_production_fixture_source())
    result = subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True)
