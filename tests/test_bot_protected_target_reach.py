"""Protected-encounter splash guard uses native melee-chain reach.

Base-0891a99 Magmaw 10N kills rejected Heart Strike on 31-41% of evaluations
because a protected Lava Parasite was within the fixed 45-yard target radius,
although Heart Strike's native chain only jumps 5 yards from the caster.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
SEMANTICS = BOTS / "BotWorldPopulationMgrSpellSemantics.cpp"
DBC = ROOT / "data/dbc/enUS"

# Client 4.3.4 rows (Spell, SpellCategories.DefenseType, SpellClassOptions and
# SpellEffect): (dmg class, AttributesEx2, AttributesEx5, family,
# [(index, effect, chain targets, target A, target B, trigger spell)]).
NATIVE_SPELLS = {
    55050: (2, 0x1000, 0x8000, 15, [(0, 121, 3, 6, 0, 0), (1, 31, 3, 6, 0, 0), (2, 3, 0, 25, 0, 0)]),
    31935: (2, 0x0, 0x0, 10, [(0, 2, 3, 6, 0, 0), (1, 68, 3, 6, 0, 0), (2, 6, 3, 6, 0, 0)]),
    845: (2, 0x1000, 0x8000, 4, [(0, 2, 2, 6, 0, 0), (1, 0, 0, 0, 0, 0)]),
    48721: (1, 0x0, 0x0, 15, [(0, 2, 0, 18, 16, 0)]),
    43265: (1, 0x0, 0x0, 15, [(0, 27, 0, 87, 28, 0), (1, 6, 0, 1, 0, 0)]),
    53595: (2, 0x0, 0x0, 10, [(0, 31, 0, 6, 0, 0), (1, 30, 0, 1, 0, 0), (2, 64, 0, 6, 0, 88263)]),
    88263: (1, 0x0, 0x0, 10, [(0, 2, 0, 53, 16, 0)]),
    49998: (2, 0x0, 0x0, 15, [(0, 121, 0, 6, 0, 0), (1, 31, 0, 6, 0, 0), (2, 3, 0, 6, 0, 0)]),
}


def _function(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def _area_target_ids() -> list[int]:
    info = (ROOT / "src/server/game/Spells/SpellInfo.cpp").read_text()
    ids = [int(match) for match in re.findall(
        r"TARGET_SELECT_CATEGORY_(?:AREA|CONE)\s*,.*//\s*(\d+)\s", info)]
    assert {15, 16}.issubset(ids) and not {6, 22, 25, 53}.intersection(ids)
    return ids


def _compile_and_run(tmp_path: Path, name: str, body: str) -> None:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(body, encoding="utf-8")
    result = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
         str(source), "-o", str(binary)],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_reach_envelope_is_a_superset_of_native_chain_selection(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, "reach_envelope", r'''
#include "Bots/BotProtectedTargetReach.h"
#include <algorithm>
#include <cassert>
#include <cmath>

using namespace BotProtectedTargetReach;

int main()
{
    Reach area = Resolve({});
    assert(area.From == Anchor::AreaGuard && area.Radius == 45.0f && !area.AddCandidateMeleeRange);
    assert(Resolve({ true, 1, false, false }).From == Anchor::AreaGuard);
    assert(Resolve({ false, 3, true, true }).From == Anchor::AreaGuard);
    Reach heart = Resolve({ true, 3, true, true });
    assert(heart.From == Anchor::Caster && heart.Radius == 5.0f && !heart.AddCandidateMeleeRange);
    Reach shield = Resolve({ true, 3, false, false });
    assert(shield.From == Anchor::Target && shield.Radius == 10.0f && !shield.AddCandidateMeleeRange);
    assert(Resolve({ true, 4, false, false }).Radius == 15.0f);
    Reach wide = Resolve({ true, 2, false, true });
    assert(wide.From == Anchor::Target && wide.Radius == 5.0f && wide.AddCandidateMeleeRange);
    assert(CollectRadius(shield, 1.5f) == 10.0f);
    assert(std::fabs(CollectRadius(wide, 1.5f) - 10.0f) < 1e-5f);
    assert(std::fabs(CollectRadius(wide, 4.5f) - (5.0f + 4.5f + 1.3333334f)) < 1e-5f);

    // Sweep geometry: any unit the native search can select is collected by
    // the combat-reach-inclusive searcher and passes the exact reach test.
    for (int chain = 2; chain <= 5; ++chain)
    for (int treat = 0; treat <= 1; ++treat)
    for (float ownerReach : { 0.0f, 1.5f, 4.0f })
    for (float anchorReach : { 0.0f, 1.5f, 15.0f })
    for (float candidateReach : { 0.0f, 1.5f, 6.0f })
    for (float dist = 0.0f; dist <= 60.0f; dist += 0.25f)
    {
        Reach target = Resolve({ true, uint32(chain), false, treat != 0 });
        float melee = std::max(candidateReach + ownerReach + MeleeRangeReachSlack, NominalMeleeRange);
        bool native = dist <= float(chain - 1) * 5.0f + (treat ? melee : 0.0f);
        bool collected = dist <= CollectRadius(target, ownerReach) + anchorReach + candidateReach;
        if (native)
            assert(collected && TargetAnchoredCandidateInReach(target, dist, melee));
        else
            assert(!TargetAnchoredCandidateInReach(target, dist, melee));

        Reach caster = Resolve({ true, uint32(chain), true, treat != 0 });
        bool nativeJump = dist <= 5.0f + ownerReach + candidateReach;
        bool casterCollected = dist <= CollectRadius(caster, ownerReach) + ownerReach + candidateReach;
        assert(nativeJump == casterCollected);
    }
    return 0;
}
''')


def _production_fixture() -> str:
    source = SEMANTICS.read_text()
    multi = _function(source, "bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth)")
    melee = _function(source, "bool SpellHasHostileMeleeChainSemantics(SpellInfo const* spellInfo)")
    describe = _function(source, "BotProtectedTargetReach::MeleeChainShape DescribeMeleeChain(")
    guard = _function(source, "bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target,\n    SpellInfo const* spellInfo)")
    area_ids = ", ".join(str(value) for value in _area_target_ids())
    spells = "\n".join(
        "    Define({id}, {dmg}, {a2:#x}, {a5:#x}, {family}, {{ {effects} }});".format(
            id=spell_id, dmg=row[0], a2=row[1], a5=row[2], family=row[3],
            effects=", ".join("{{ {}, {}, {}, {}, {}, {} }}".format(*effect) for effect in row[4]))
        for spell_id, row in NATIVE_SPELLS.items())
    return r'''
#include "Bots/BotProtectedTargetReach.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <initializer_list>
#include <map>
#include <set>
#include <vector>

constexpr uint8 MAX_SPELL_EFFECTS = 3;
constexpr uint32 SPELL_EFFECT_PERSISTENT_AREA_AURA = 27;
constexpr uint32 SPELL_DAMAGE_CLASS_MELEE = 2;
constexpr uint32 SPELLFAMILY_GENERIC = 0;
enum SpellAttr2 : uint32 { SPELL_ATTR2_CHAIN_FROM_CASTER = 0x00001000 };
enum SpellAttr5 : uint32 { SPELL_ATTR5_TREAT_AS_AREA_EFFECT = 0x00008000 };
enum class SpellModOp { ChainTargets = 17 };
std::set<uint32> const AreaTargets = { ''' + area_ids + r''' };
std::set<uint32> const AreaAuraEffects = { 35, 65, 119, 128, 129, 143 };

struct SpellEffectInfo
{
    uint32 Effect = 0, ChainTarget = 0, TargetA = 0, TargetB = 0, TriggerSpell = 0;
    bool IsEffect() const { return Effect != 0; }
    bool IsEffect(uint32 effect) const { return Effect == effect; }
    bool IsTargetingArea() const { return AreaTargets.count(TargetA) || AreaTargets.count(TargetB); }
    bool IsAreaAuraEffect() const { return AreaAuraEffects.count(Effect) != 0; }
};

struct SpellInfo
{
    uint32 Id = 0, DmgClass = 0, AttributesEx2 = 0, AttributesEx5 = 0, SpellFamilyName = 0;
    SpellEffectInfo Effects[MAX_SPELL_EFFECTS];
    bool IsPositiveEffect(uint8) const { return false; }
    bool HasAttribute(SpellAttr2 attribute) const { return AttributesEx2 & attribute; }
    bool HasAttribute(SpellAttr5 attribute) const { return AttributesEx5 & attribute; }
};

struct SpellMgrFixture
{
    std::map<uint32, SpellInfo> Spells;
    SpellInfo const* GetSpellInfo(uint32 id) const
    {
        auto itr = Spells.find(id);
        return itr == Spells.end() ? nullptr : &itr->second;
    }
} manager;
SpellMgrFixture* sSpellMgr = &manager;

struct Guid { uint64 Raw = 0; uint64 GetRawValue() const { return Raw; } };
struct Creature;
struct WorldObject
{
    float X = 0.0f, Y = 0.0f, Reach = 0.0f;
    virtual ~WorldObject() = default;
    virtual Creature* ToCreature() { return nullptr; }
    float GetCombatReach() const { return Reach; }
    float GetExactDist2d(WorldObject const* other) const { return std::hypot(X - other->X, Y - other->Y); }
};
struct Unit : WorldObject
{
    bool Alive = true;
    bool IsAlive() const { return Alive; }
    float GetMeleeRange(Unit const* target) const
    {
        return std::max(Reach + target->Reach + 1.3333334f, 5.0f);
    }
};
struct Creature : Unit
{
    uint32 Entry = 0, Spawn = 0;
    Guid Id;
    bool Hostile = true;
    Creature* ToCreature() override { return this; }
    uint32 GetEntry() const { return Entry; }
    uint32 GetSpawnId() const { return Spawn; }
    Guid const& GetGUID() const { return Id; }
};
struct Player : Unit
{
    Guid Id;
    std::map<uint32, uint32> ChainBonus;
    Guid const& GetGUID() const { return Id; }
    bool IsValidAttackTarget(Creature const* creature) const { return creature->Hostile; }
    Player* GetSpellModOwner() const { return const_cast<Player*>(this); }
    template <class T> void ApplySpellMod(SpellInfo const* spellInfo, SpellModOp op, T& value) const
    {
        auto itr = ChainBonus.find(spellInfo->Id);
        if (op == SpellModOp::ChainTargets && itr != ChainBonus.end())
            value += itr->second;
    }
};

std::vector<WorldObject*> World;
WorldObject const* LastAnchor = nullptr;
float LastRadius = 0.0f;
namespace Trinity
{
struct AllWorldObjectsInRange
{
    WorldObject const* Center;
    float Range;
    AllWorldObjectsInRange(WorldObject const* center, float range) : Center(center), Range(range) { }
    bool operator()(WorldObject* object) const
    {
        return Center->GetExactDist2d(object) <= Range + Center->GetCombatReach() + object->GetCombatReach();
    }
};
template <class Check> struct WorldObjectListSearcher
{
    std::vector<WorldObject*>& Out;
    Check& Test;
    WorldObjectListSearcher(WorldObject const*, std::vector<WorldObject*>& out, Check& check) : Out(out), Test(check) { }
};
}
struct Cell
{
    template <class Searcher> static void VisitAllObjects(WorldObject const* anchor, Searcher& searcher, float radius)
    {
        LastAnchor = anchor;
        LastRadius = radius;
        for (WorldObject* object : World)
            if (searcher.Test(object))
                searcher.Out.push_back(object);
    }
};

namespace BotRaidAreaAuthority
{
bool HasEntries = true;
std::set<uint32> Protected = { 41806 };
bool HasProtectedEncounterEntries(uint64) { return HasEntries; }
bool IsProtectedEncounterTarget(uint64, uint32 entry, uint32, uint64) { return Protected.count(entry) != 0; }
}

namespace BotWorldPopulationMgrSpellSemantics
{
constexpr uint32 ForceOfNatureSpellId = 33831;
bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth = 0);
bool SpellHasHostileMeleeChainSemantics(SpellInfo const* spellInfo);
bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target, SpellInfo const* spellInfo = nullptr);
''' + multi + "\n" + melee + "\nnamespace\n{\n" + describe + "\n}\n" + guard + r'''
}

using namespace BotWorldPopulationMgrSpellSemantics;

struct NativeEffect { uint32 Index, Effect, Chain, TargetA, TargetB, Trigger; };
void Define(uint32 id, uint32 dmgClass, uint32 attr2, uint32 attr5, uint32 family,
    std::initializer_list<NativeEffect> effects)
{
    SpellInfo& info = manager.Spells[id];
    info.Id = id;
    info.DmgClass = dmgClass;
    info.AttributesEx2 = attr2;
    info.AttributesEx5 = attr5;
    info.SpellFamilyName = family;
    for (NativeEffect const& effect : effects)
        info.Effects[effect.Index] = { effect.Effect, effect.Chain, effect.TargetA, effect.TargetB, effect.Trigger };
}

Creature Parasite(float x, float y)
{
    Creature parasite;
    parasite.Entry = 41806;
    parasite.X = x;
    parasite.Y = y;
    return parasite;
}

int main()
{
''' + spells + r'''
    SpellInfo const* heart = manager.GetSpellInfo(55050);
    SpellInfo const* shield = manager.GetSpellInfo(31935);
    SpellInfo const* cleave = manager.GetSpellInfo(845);
    SpellInfo const* bloodBoil = manager.GetSpellInfo(48721);
    SpellInfo const* deathAndDecay = manager.GetSpellInfo(43265);
    SpellInfo const* hammer = manager.GetSpellInfo(53595);
    SpellInfo const* deathStrike = manager.GetSpellInfo(49998);
    for (SpellInfo const* spell : { heart, shield, cleave, bloodBoil, deathAndDecay, hammer })
        assert(SpellHasHostileMultiTargetSemantics(spell));
    assert(!SpellHasHostileMultiTargetSemantics(deathStrike));

    // Base-0891a99 Magmaw geometry: 15-yard combat reach body at the origin,
    // Blood tank in melee on the +X side, parasites around the body.
    Creature magmaw;
    magmaw.Entry = 41570;
    magmaw.Reach = 15.0f;
    Player dk;
    dk.Id.Raw = 30002;
    dk.X = 16.0f;
    dk.Reach = 1.5f;
    Creature far = Parasite(28.0f, 0.0f);     // 12 yd from the tank's centre
    Creature opposite = Parasite(-28.0f, 0.0f); // behind Magmaw, 28 yd from its centre
    World = { &magmaw, &dk, &far, &opposite };

    // Areas and callers without a spell keep the unchanged 45-yard guard.
    assert(HasNearbyProtectedEncounterTarget(&dk, &magmaw));
    assert(LastAnchor == &magmaw && LastRadius == 45.0f);
    for (SpellInfo const* spell : { bloodBoil, deathAndDecay, hammer, deathStrike })
    {
        assert(HasNearbyProtectedEncounterTarget(&dk, &magmaw, spell));
        assert(LastAnchor == &magmaw && LastRadius == 45.0f);
    }

    // Heart Strike and Cleave chain from the caster with a 5-yard jump.
    for (SpellInfo const* spell : { heart, cleave })
    {
        assert(!HasNearbyProtectedEncounterTarget(&dk, &magmaw, spell));
        assert(LastAnchor == &dk && LastRadius == 5.0f);
    }
    Creature near = Parasite(21.0f, 1.0f); // 3.6 yd edge distance from the tank
    World.push_back(&near);
    assert(HasNearbyProtectedEncounterTarget(&dk, &magmaw, heart));
    near.Alive = false;
    assert(!HasNearbyProtectedEncounterTarget(&dk, &magmaw, heart));
    near.Alive = true;
    near.Entry = 41572; // unprotected hostile beside the tank
    assert(!HasNearbyProtectedEncounterTarget(&dk, &magmaw, heart));
    near.Hostile = false;
    near.Entry = 41806;
    assert(!HasNearbyProtectedEncounterTarget(&dk, &magmaw, heart));
    World.pop_back();

    // Avenger's Shield chains 5 yd x 2 from the primary target's position;
    // Magmaw's own 15-yard combat reach does not widen it.
    Creature inside = Parasite(12.0f, 0.0f);
    World = { &magmaw, &dk, &inside, &opposite };
    assert(!HasNearbyProtectedEncounterTarget(&dk, &magmaw, shield));
    assert(LastAnchor == &magmaw && LastRadius == 10.0f);
    inside.X = 9.5f;
    assert(HasNearbyProtectedEncounterTarget(&dk, &magmaw, shield));
    inside.X = 12.0f;
    dk.ChainBonus[31935] = 1; // owner spell modifiers extend the native chain
    assert(HasNearbyProtectedEncounterTarget(&dk, &magmaw, shield));
    assert(LastRadius == 15.0f);
    dk.ChainBonus.clear();

    // A target-anchored treat-as-area melee chain adds each candidate's melee
    // range to the caster; the generic family does not.
    Define(900001, 2, 0x0, 0x8000, 4, { { 0, 2, 2, 6, 0, 0 } });
    inside.X = 9.5f;
    assert(HasNearbyProtectedEncounterTarget(&dk, &magmaw, manager.GetSpellInfo(900001)));
    assert(std::fabs(LastRadius - 10.0f) < 1e-5f);
    Define(900002, 2, 0x0, 0x8000, 0, { { 0, 2, 2, 6, 0, 0 } });
    assert(!HasNearbyProtectedEncounterTarget(&dk, &magmaw, manager.GetSpellInfo(900002)));

    // A melee chain with any other hostile multi-target source stays an area.
    Define(900003, 2, 0x1000, 0x0, 4, { { 0, 2, 3, 6, 0, 0 }, { 1, 2, 0, 22, 15, 0 } });
    Define(900004, 2, 0x1000, 0x0, 4, { { 0, 2, 3, 6, 0, 0 }, { 1, 64, 0, 6, 0, 88263 } });
    for (uint32 id : { 900003u, 900004u })
    {
        assert(HasNearbyProtectedEncounterTarget(&dk, &magmaw, manager.GetSpellInfo(id)));
        assert(LastAnchor == &magmaw && LastRadius == 45.0f);
    }

    // The primary target is never its own splash, and no protected entries
    // means no guard at all.
    Creature protectedBody = magmaw;
    protectedBody.Entry = 41806;
    World = { &protectedBody, &dk };
    assert(!HasNearbyProtectedEncounterTarget(&dk, &protectedBody));
    World = { &magmaw, &dk, &near };
    BotRaidAreaAuthority::HasEntries = false;
    assert(!HasNearbyProtectedEncounterTarget(&dk, &magmaw));
    assert(!HasNearbyProtectedEncounterTarget(nullptr, &magmaw, heart));
    assert(!HasNearbyProtectedEncounterTarget(&dk, nullptr, heart));
    return 0;
}
'''


def test_production_guard_uses_native_reach_for_melee_chains(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, "protected_reach", _production_fixture())


def test_native_spell_rows_match_client_data() -> None:
    if not (DBC / "SpellEffect.dbc").exists():
        pytest.skip("client DBC data not extracted")
    import sys
    sys.path.insert(0, str(ROOT))
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    spell_fmt = "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii".replace("x", "i")
    spells = {row[0]: row for row in load_wdbc_values(DBC / "Spell.dbc", spell_fmt)}
    categories = {row[0]: row for row in load_wdbc_values(DBC / "SpellCategories.dbc", "niiiiii")}
    classes = {row[0]: row for row in load_wdbc_values(DBC / "SpellClassOptions.dbc", "niiiiis")}
    effects: dict[int, list[tuple[int, ...]]] = {}
    for row in load_wdbc_values(DBC / "SpellEffect.dbc", "nifiiiffiiiiiifiifiiiiiiiii"):
        if row[24] in NATIVE_SPELLS:
            effects.setdefault(row[24], []).append((row[25], row[1], row[8], row[22], row[23], row[21]))
    for spell_id, (dmg, attr2, attr5, family, rows) in NATIVE_SPELLS.items():
        spell = spells[spell_id]
        category = categories.get(spell[35])
        options = classes.get(spell[36])
        assert (category[2] if category else 0) == dmg, spell_id
        assert spell[3] & 0x1000 == attr2, spell_id
        assert spell[6] & 0x8000 == attr5, spell_id
        assert (options[5] if options else 0) == family, spell_id
        assert sorted(effects[spell_id]) == rows, spell_id


def test_every_caller_shares_one_spell_aware_guard() -> None:
    definitions = [
        path.name for path in BOTS.glob("*.cpp")
        if re.search(r"\bbool HasNearbyProtectedEncounterTarget\(", path.read_text())
    ]
    assert definitions == ["BotWorldPopulationMgrSpellSemantics.cpp"]
    header = (BOTS / "BotWorldPopulationMgrSpellSemantics.h").read_text()
    assert "SpellInfo const* spellInfo = nullptr);" in header
    reach = (BOTS / "BotProtectedTargetReach.h").read_text()
    assert "constexpr float AreaGuardRadius = 45.0f;" in reach

    callers = {
        "BotWorldPopulationMgrCombatResolver.cpp": ["HasNearbyProtectedEncounterTarget(bot, target, candidateSpellInfo)"],
        "BotActionExecutor.cpp": [
            "HasNearbyProtectedEncounterTarget(bot, target, spellInfo)",
            "HasNearbyProtectedEncounterTarget(bot, target, preview.Effective)",
            "HasNearbyProtectedEncounterTarget(bot, target, resolved.Effective)",
        ],
        "BotWorldPopulationMgrCombatSpell.cpp": ["HasNearbyProtectedEncounterTarget(bot, target, spellInfo)"],
        "BotWorldPopulationMgrCombatSupport.cpp": ["HasNearbyProtectedEncounterTarget(bot, target, spellInfo)"],
    }
    for name, calls in callers.items():
        text = (BOTS / name).read_text()
        assert "using BotWorldPopulationMgrSpellSemantics::HasNearbyProtectedEncounterTarget;" in text
        assert "AllWorldObjectsInRange check(target, 45.0f)" not in text
        for call in calls:
            assert text.count(call) == 1, (name, call)
        assert len(text.splitlines()) < 1000
    # Fire's Living Bomb spread is not one spell's splash; it keeps the area guard.
    resolver = (BOTS / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    assert "&& !HasNearbyProtectedEncounterTarget(bot, target)\n        && bot->getClass() == CLASS_MAGE" in resolver
