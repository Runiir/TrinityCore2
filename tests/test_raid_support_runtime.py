"""Round 5 class package 02: raid support runtime for the canonical composition.

1. Combat-res eligibility: the reconciler never makes a tank the caster in a
   canonical raid (round 4), but the route group recovery still counted every
   living member with a ready combat res. Once the Feral tank knows Rebirth, a
   trash pull that loses its healers would neither retreat nor be resurrected.
   One shared rule (BotCombatResEligibility.h) now decides both.
2. Power Word: Fortitude re-cast after a wipe (persistent contract, 79105/79104).
3. Runtime raid buffs: Blessing of Might in place of Kings under a druid's Mark,
   Retribution / Devotion Aura, and a boss lust where no strategy times one.

Every change is canonical-raid scope (BotCanonicalRaidScope::IsCanonicalRaid);
Stonecore, the calibrations and the legacy Magmaw roster keep their behaviour.
"""
from __future__ import annotations

import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
DBC = ROOT / "data/dbc/enUS"
TRAINERS = ROOT / "dataset/world_knowledge/trainers.jsonl"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
ENCOUNTERS = BOTS / "Content/Raids/BlackwingDescent/Encounters"
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/server/shared",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
    "dep/recastnavigation/Detour/Include",
]
TOUCHED = [
    "BotCanonicalRaidScope.h", "BotCombatResEligibility.h", "BotRaidPersistentBuffs.h",
    "BotRaidBossLust.h", "BotRaidBossLustLatch.h", "BotWorldPopulationMgrRaidBossLust.cpp",
    "BotWorldPopulationMgrCombatRes.cpp", "BotWorldPopulationMgrValidationRouteGroupRecovery.cpp",
    "BotWorldPopulationMgrNativeHelpers.cpp", "BotWorldPopulationMgrNativeHelpers.h",
    "BotWorldPopulationMgrPersistentSetup.cpp", "BotWorldPopulationMgrDungeonRoute.cpp",
    "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp", "BotWorldPopulationMgr.h",
    "BotWorldPopulationMgrRuntimeContracts.h",
]


def _run(tmp_path: Path, name: str, program: str) -> str:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def _text(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


# 1. Combat-res eligibility -------------------------------------------------

def test_the_feral_tank_with_rebirth_is_never_a_living_caster_in_a_canonical_raid(tmp_path: Path) -> None:
    out = _run(tmp_path, "eligibility", r'''
#include "Bots/BotCombatResEligibility.h"
#include <cassert>
#include <cstdio>
#include <string_view>
int main() {
    using namespace BotCombatResEligibility;
    using BotCanonicalRaidScope::IsCanonicalRaid;
    assert(IsCanonicalRaid(true, "blackwing_descent_10n_omnotron_c0_diagnostic"));
    assert(IsCanonicalRaid(true, "blackwing_descent_10n_full_c0"));
    assert(!IsCanonicalRaid(false, "blackwing_descent_10n_full_c0"));
    assert(!IsCanonicalRaid(true, "blackwing_descent_10n_magmaw_diagnostic"));
    assert(!IsCanonicalRaid(true, "stonecore_5n"));
    int probes = 0, roles = 0;
    auto rebirthReady = [&probes] { ++probes; return true; };
    auto nothingReady = [&probes] { ++probes; return false; };
    auto role = [&roles](char const* name) { return [&roles, name] { ++roles; return std::string_view(name); }; };
    // Canonical raid: the Feral tank's ready Rebirth never counts, and its
    // spell book is not even read.
    assert(!CountsAsLivingCaster(true, role("tank"), rebirthReady) && probes == 0 && roles == 1);
    // Legacy scope is unchanged: the spell probe alone decides, tanks
    // included, and the role (a possible database lookup) is never read.
    assert(CountsAsLivingCaster(false, role("tank"), rebirthReady) && probes == 1);
    assert(!CountsAsLivingCaster(false, role("tank"), nothingReady) && probes == 2 && roles == 1);
    // The Balance druid and the healers still count in a canonical raid.
    assert(CountsAsLivingCaster(true, role("dps"), rebirthReady));
    assert(CountsAsLivingCaster(true, role("healer"), rebirthReady));
    assert(!CountsAsLivingCaster(true, role("healer"), nothingReady));
    assert(RoleMayCast(false, "tank") && !RoleMayCast(true, "tank") && RoleMayCast(true, "dps"));
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_reconciler_and_group_recovery_share_the_eligibility_rule() -> None:
    reconciler = _text("BotWorldPopulationMgrCombatRes.cpp")
    recovery = _text("BotWorldPopulationMgrValidationRouteGroupRecovery.cpp")
    helpers = _text("BotWorldPopulationMgrNativeHelpers.cpp")
    scope = ("BotCanonicalRaidScope::IsCanonicalRaid(\n")
    assert '#include "Bots/BotCombatResEligibility.h"' in reconciler
    assert '#include "Bots/BotCombatResEligibility.h"' in recovery
    assert scope in reconciler and scope in recovery
    # The role (GetDungeonRole can query the database) is read only in a
    # canonical raid, exactly as PR_05's short-circuit did.
    assert ("        if (canonicalRaid && !BotCombatResEligibility::RoleMayCast(canonicalRaid,\n"
            "                GetDungeonRole(member.Bot)))\n"
            "            continue;\n") in reconciler
    assert 'std::string(GetDungeonRole(member.Bot)) == "tank"' not in reconciler
    assert ("                if (!retreatThreat && std::string(Manager.GetDungeonRole(member)) == \"tank\")\n"
            "                    retreatThreat = member->GetVictim();\n"
            "                if (!livingCombatResurrectionCaster\n"
            "                    && BotCombatResEligibility::CountsAsLivingCaster(canonicalRaid,\n"
            "                        [this, member] { return std::string_view(Manager.GetDungeonRole(member)); },\n"
            "                        [member] { return HasReadyNativeCombatRes(member); }))\n"
            "                    livingCombatResurrectionCaster = true;\n") in recovery
    # The living-caster spell test moved verbatim into the shared helper.
    body = helpers[helpers.index("bool HasReadyNativeCombatRes(Player const* member)"):]
    body = body[:body.index("\n}\n")]
    for clause in ("playerSpell.state == PLAYERSPELL_REMOVED || playerSpell.disabled || !playerSpell.active || !member->HasSpell(spellId)",
                   "IsNativeCombatResSpell(spellInfo)",
                   "member->GetSpellHistory()->IsReady(spellInfo) && HasPowerForSpell(member, spellInfo)"):
        assert clause in body
        assert clause not in recovery
    # The reconciler still proves each owner's learned, active, ready spell.
    usable = reconciler[reconciler.index("bool BotWorldPopulationMgr::CurrentCombatResOwnerUsable"):]
    for reason in ("declined_combat_res_not_learned", "declined_combat_res_cooldown", "declined_insufficient_power"):
        assert reason in usable
    # The retreat still fires on the same predicate.
    assert "!livingCombatResurrectionCaster\n            && !currentLivePackCanContinue" in recovery


# 2 and 3a/3b. Persistent raid buffs ------------------------------------------

def test_persistent_contract_is_unchanged_outside_canonical_raids_and_adds_raid_buffs_inside(tmp_path: Path) -> None:
    out = _run(tmp_path, "buffs", r'''
#include "Bots/BotRaidPersistentBuffs.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <iterator>
#include <string>
namespace C = BotPersistentSelfBuffContract;
namespace R = BotRaidPersistentBuffs;
struct FakePlayer;
struct FakeRef {
    FakePlayer* Player; FakeRef* Next;
    FakeRef* next() { return Next; }
    FakePlayer* GetSource() const { return Player; }
};
struct FakeGroup { FakeRef* First = nullptr; FakeRef* GetFirstMember() { return First; } };
struct FakePlayer {
    uint8 Class; bool KnowsMark; int Map; FakeGroup* Group = nullptr;
    FakeGroup* GetGroup() { return Group; }
    uint8 getClass() const { return Class; }
    bool HasSpell(uint32 spell) const { return KnowsMark && spell == R::MarkOfTheWild; }
    bool IsInMap(FakePlayer const* other) const { return Map == other->Map; }
};
bool Same(C::SelfBuff const& a, C::SelfBuff const& b) {
    auto text = [](char const* l, char const* r) { return (!l && !r) || (l && r && !std::strcmp(l, r)); };
    return a.ClassId == b.ClassId && text(a.Role, b.Role) && text(a.SpecTag, b.SpecTag)
        && a.SpellId == b.SpellId && a.AuraId == b.AuraId && a.AlternateAuraId == b.AlternateAuraId
        && text(a.Name, b.Name);
}
C::SelfBuff const* Find(std::vector<C::SelfBuff> const& rows, uint32 spell) {
    for (C::SelfBuff const& row : rows) if (row.SpellId == spell) return &row;
    return nullptr;
}
int main() {
    std::size_t const base = std::size(C::Buffs);
    int probes = 0;
    auto mark = [&probes] { ++probes; return true; };
    auto noMark = [&probes] { ++probes; return false; };
    auto knowsAll = [](uint32) { return true; };
    // Outside a canonical raid: the table itself, row for row, no probe.
    for (uint8 cls : { uint8(CLASS_PALADIN), uint8(CLASS_PRIEST), uint8(CLASS_DRUID) }) {
        auto rows = R::Contract(C::Buffs, false, cls, mark, knowsAll);
        assert(rows.size() == base);
        for (std::size_t i = 0; i < base; ++i) assert(Same(rows[i], C::Buffs[i]));
    }
    assert(probes == 0);
    // A canonical paladin under a druid's Mark blesses Might where Kings was.
    auto paladin = R::Contract(C::Buffs, true, CLASS_PALADIN, mark, knowsAll);
    assert(probes == 1 && paladin.size() == base + 2);  // + Retribution and Devotion Aura
    std::size_t kings = 0;
    while (C::Buffs[kings].SpellId != R::BlessingOfKings) ++kings;
    assert(Same(paladin[kings], R::BlessingOfMight) && !Find(paladin, R::BlessingOfKings));
    assert(paladin[kings].AuraId == 79102 && paladin[kings].AlternateAuraId == 79101);
    // Without a Mark provider the stats category stays with Kings.
    auto kept = R::Contract(C::Buffs, true, CLASS_PALADIN, noMark, knowsAll);
    assert(probes == 2 && Find(kept, R::BlessingOfKings) && !Find(kept, 19740));
    // Known active spells only: an unprovisioned Might keeps Kings (without
    // probing the group) and an unprovisioned aura is left out.
    auto untrainedMight = R::Contract(C::Buffs, true, CLASS_PALADIN, mark,
        [](uint32 spell) { return spell != 19740; });
    assert(probes == 2 && Find(untrainedMight, R::BlessingOfKings) && !Find(untrainedMight, 19740));
    auto untrainedAura = R::Contract(C::Buffs, true, CLASS_PALADIN, mark,
        [](uint32 spell) { return spell != 7294; });
    assert(probes == 3 && !Find(untrainedAura, 7294) && Find(untrainedAura, 19740));
    // The Mark probe is paladin-only; each class gets only its own rows.
    auto priest = R::Contract(C::Buffs, true, CLASS_PRIEST, mark, knowsAll);
    assert(probes == 3 && Find(priest, R::BlessingOfKings) && priest.size() == base + 1);
    assert(!Find(priest, 7294) && R::Contract(C::Buffs, true, CLASS_PRIEST, mark,
        [](uint32) { return false; }).size() == base);
    C::SelfBuff const* fortitude = Find(priest, R::PowerWordFortitude);
    assert(fortitude && fortitude->AuraId == 79105 && fortitude->AlternateAuraId == 79104);
    assert(C::Matches(*fortitude, CLASS_PRIEST, "healer", "discipline_priest"));
    C::SelfBuff const* retribution = Find(paladin, 7294);
    C::SelfBuff const* devotion = nullptr;
    for (C::SelfBuff const& row : paladin)
        if (row.SpellId == 465 && row.SpecTag && std::string(row.SpecTag) == "holy_paladin") devotion = &row;
    assert(retribution && C::Matches(*retribution, CLASS_PALADIN, "dps", "retribution_paladin"));
    assert(!C::Matches(*retribution, CLASS_PALADIN, "healer", "holy_paladin"));
    assert(devotion && C::Matches(*devotion, CLASS_PALADIN, "healer", "holy_paladin"));
    assert(!C::Matches(*devotion, CLASS_PALADIN, "dps", "retribution_paladin"));
    // Readiness rows the contract owns in a canonical raid.
    assert(!R::ReadinessOwnedByContract(false, R::PowerWordFortitude, mark));
    assert(R::ReadinessOwnedByContract(true, R::PowerWordFortitude, noMark));
    assert(R::ReadinessOwnedByContract(true, R::BlessingOfKings, mark));
    assert(!R::ReadinessOwnedByContract(true, R::BlessingOfKings, noMark));
    assert(!R::ReadinessOwnedByContract(true, 1459, mark) && !R::ReadinessOwnedByContract(true, 1126, mark));
    // The Mark provider: another druid on the map that knows Mark of the Wild.
    FakePlayer paladinBot{ CLASS_PALADIN, false, 669 }, druid{ CLASS_DRUID, true, 669 },
        farDruid{ CLASS_DRUID, true, 0 }, untrained{ CLASS_DRUID, false, 669 };
    FakeGroup group;
    FakeRef druidRef{ &druid, nullptr }, selfRef{ &paladinBot, &druidRef };
    group.First = &selfRef;
    assert(!R::GroupHasMarkOfTheWild(&paladinBot));
    paladinBot.Group = &group;
    assert(R::GroupHasMarkOfTheWild(&paladinBot));
    // Membership, not map: a released druid running back from the graveyard
    // outside the instance still provides the Mark, so Might never flips to Kings.
    druidRef.Player = &farDruid;
    assert(R::GroupHasMarkOfTheWild(&paladinBot));
    druidRef.Player = &untrained;
    assert(!R::GroupHasMarkOfTheWild(&paladinBot));
    selfRef.Next = nullptr;
    assert(!R::GroupHasMarkOfTheWild(&paladinBot));
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_persistent_setup_and_readiness_use_the_canonical_contract() -> None:
    setup = _text("BotWorldPopulationMgrPersistentSetup.cpp")
    loop = ("    bool const canonicalRaid = BotCanonicalRaidScope::IsCanonicalRaid(\n"
            "        Cohort().Raid.RaidInstance, Cohort().Config.ValidationRouteScenarioId);\n"
            "    for (auto const& buff : BotRaidPersistentBuffs::Contract(BotPersistentSelfBuffContract::Buffs,\n"
            "             canonicalRaid, bot->getClass(),\n"
            "             [bot] { return BotRaidPersistentBuffs::GroupHasMarkOfTheWild(bot); },\n"
            "             [bot](uint32 spellId) { return bot->HasSpell(spellId); }))\n"
            "    {\n"
            "        if (!BotPersistentSelfBuffContract::Matches(buff, bot->getClass(), role, profile.SpecTag))")
    assert loop in setup
    # The ordinary aura test, spell-book guard and native cast are unchanged.
    after = setup[setup.index(loop):]
    assert "bot->HasAura(buff.AuraId)\n            || (buff.AlternateAuraId && bot->HasAura(buff.AlternateAuraId))" in after
    assert "bot->HasSpell(buff.SpellId)" in after and "executor.ExecuteCombat(bot, bot, action)" in after
    route = _text("BotWorldPopulationMgrDungeonRoute.cpp")
    readiness = route[route.index("for (ActiveBuffRequirement const& requirement : requirements)"):]
    readiness = readiness[:readiness.index("std::string missing")]
    assert ("            if (BotRaidPersistentBuffs::ReadinessOwnedByContract(canonicalRaid, requirement.SpellId,\n"
            "                    [bot] { return BotRaidPersistentBuffs::GroupHasMarkOfTheWild(bot); }))\n"
            "                continue;\n") in readiness
    # The shared readiness table itself is untouched (dungeons keep it).
    assert '{ CLASS_PRIEST, nullptr, 21562, { 21562 }, "power_word_fortitude_ready", true },' in route
    assert '{ CLASS_PALADIN, nullptr, 20217, { 20217, 79063 }, "blessing_of_kings_ready", true },' in route


def _spells() -> tuple[dict, dict, dict]:
    blob = (DBC / "Spell.dbc").read_bytes()
    count, fields, size, _ = struct.unpack_from("<4I", blob, 4)
    records = blob[20:20 + count * size]
    spells = {}
    for index in range(count):
        values = struct.unpack_from(f"<{fields}I", records, index * size)
        spells[values[0]] = values
    blob = (DBC / "SpellEffect.dbc").read_bytes()
    count, fields, size, _ = struct.unpack_from("<4I", blob, 4)
    records = blob[20:20 + count * size]
    effects: dict[int, list[tuple[int, ...]]] = {}
    for index in range(count):
        values = struct.unpack_from(f"<{fields}I", records, index * size)
        base = struct.unpack_from("<i", records, index * size + 5 * 4)[0]
        # Effect 1, EffectAura 3, BasePoints 5, SpellClassMask 18-20, TargetA 22, SpellID 24.
        effects.setdefault(values[24], []).append((values[1], values[3], base, values[18], values[19], values[20], values[22]))
    blob = (DBC / "SpellClassOptions.dbc").read_bytes()
    count, fields, size, _ = struct.unpack_from("<4I", blob, 4)
    records = blob[20:20 + count * size]
    options = {}
    for index in range(count):
        values = struct.unpack_from(f"<{fields}I", records, index * size)
        options[values[0]] = values
    return spells, effects, options


def test_raid_buff_dbc_facts() -> None:
    for name in ("Spell.dbc", "SpellEffect.dbc", "SpellClassOptions.dbc"):
        assert (DBC / name).is_file(), f"extract the client DBCs: {name}"
    spells, effects, options = _spells()
    # Dummy raid buffs: the script casts base points (single) or base + 1 (raid).
    for spell, single in ((21562, 79104), (19740, 79101), (20217, 79062), (1126, 79060)):
        assert any(effect[0] == 3 and effect[2] == single for effect in effects[spell]), spell
        # The raid variant is an area aura on the caster (TARGET_UNIT_CASTER_AREA_RAID 56).
        assert all(effect[6] == 56 for effect in effects[single + 1]), single + 1
    # Paladin auras are raid area auras (SPELL_EFFECT_APPLY_AREA_AURA_RAID 65) on
    # the paladin and survive death (SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD 0x100000,
    # Spell.dbc AttributesEx3 field 4); Fortitude's dummy does not.
    for aura in (7294, 465):
        assert all(effect[0] == 65 for effect in effects[aura]), aura
        assert spells[aura][4] & 0x100000, aura
    assert not spells[21562][4] & 0x100000
    # The raid lust lockouts are stripped by death: after a quick re-pull only
    # the owner's own lust cooldown gates the next cast.
    for lockout in (57723, 57724, 80354, 95809):
        assert not spells[lockout][4] & 0x100000, lockout
    # Communion's party damage modifier (aura 107, SPELLMOD_EFFECT2 12) targets
    # family flags[2] 0x1000: only Retribution Aura Overflow 63531 carries it.
    modifier = next(effect for effect in effects[31876] if effect[1] == 107)
    assert modifier[2] == 3 and modifier[3:6] == (0, 0, 0x1000)
    # Spell.dbc SpellClassOptionsId is field 36; SpellClassOptions: flags 2-4, family 5.
    hits = sorted(spell for spell, row in spells.items()
                  if row[36] in options and options[row[36]][5] == 10 and options[row[36]][4] & 0x1000)
    assert hits == [63531]


def test_no_core_path_applies_retribution_aura_overflow() -> None:
    """Communion's +3% needs 63531 on the raid; the core only names it in an unused enum."""
    hits = [(path.name, line.strip()) for path in (ROOT / "src/server").rglob("*.cpp")
            for line in path.read_text(errors="replace").splitlines() if "63531" in line]
    assert [name for name, _ in hits] == ["spell_paladin.cpp"]
    assert hits[0][1].replace(" ", "") == "SPELL_PALADIN_SANCTIFIED_RETRIBUTION_AURA=63531,"
    paladin = (ROOT / "src/server/scripts/Spells/spell_paladin.cpp").read_text(errors="replace")
    assert paladin.count("SPELL_PALADIN_SANCTIFIED_RETRIBUTION_AURA") == 1


# 3c. Boss lust fallback ------------------------------------------------------

LUST_PRELUDE = r'''
#include "Bots/BotRaidBossLust.h"
#include <cassert>
#include <cstdio>
#include <string>
using namespace BotEncounter;
namespace L = BotRaidBossLust;
std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }
static ObjectGuid G(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }
static ActorSnapshot Member(uint32 guid, char const* role, char const* spec) {
    ActorSnapshot player; player.Guid = G(guid); player.Kind = ActorKind::Player;
    player.Role = role; player.ClassSpec = spec; player.Alive = true; return player;
}
static Blackboard Board() {
    Blackboard board;
    board.Players = { Member(1, "tank", "blood_death_knight"), Member(2, "tank", "feral_druid_tank"),
        Member(3, "dps", "survival_hunter"), Member(4, "dps", "fire_mage"), Member(5, "healer", "holy_paladin"),
        Member(6, "dps", "retribution_paladin"), Member(7, "healer", "discipline_priest"),
        Member(8, "dps", "assassination_rogue"), Member(9, "dps", "elemental_shaman"),
        Member(10, "dps", "demonology_warlock") };
    ActorSnapshot boss; boss.Guid = ObjectGuid(HighGuid::Unit, uint32(41442), uint32(900));
    boss.Entry = 41442; boss.Alive = true; boss.InCombat = true; boss.VictimGuid = G(1);
    boss.Attackable = boss.Selectable = true;
    ActorSnapshot add; add.Guid = ObjectGuid(HighGuid::Unit, uint32(41807), uint32(800));
    add.Entry = 41807; add.Alive = true; add.InCombat = true; add.VictimGuid = G(2);
    add.Attackable = add.Selectable = true;
    board.Hostiles = { boss, add };
    return board;
}
'''


def test_boss_lust_owner_timing_and_scope(tmp_path: Path) -> None:
    out = _run(tmp_path, "lust", LUST_PRELUDE + r'''
int main() {
    // Strategies with their own lust timing keep it.
    assert(L::StrategyOwnsLust("bwd.chimaeron.encounter", "blackwing_descent_10n_chimaeron_c0_diagnostic"));
    assert(L::StrategyOwnsLust("bwd.maloriak.encounter", "blackwing_descent_10n_full_c0"));
    assert(L::StrategyOwnsLust("bwd.magmaw.encounter", "blackwing_descent_10n_magmaw_c0_diagnostic"));
    // Magmaw's own lust is scoped to its shard scenarios; the full raid falls back.
    assert(!L::StrategyOwnsLust("bwd.magmaw.encounter", "blackwing_descent_10n_full_c0"));
    for (char const* node : { "bwd.atramedes.encounter", "bwd.omnotron.encounter", "bwd.nefarian.encounter" })
        assert(!L::StrategyOwnsLust(node, "blackwing_descent_10n_full_c0"));

    // Owner: Chimaeron's rule, a living mage (Time Warp) first, then a shaman (Bloodlust).
    Blackboard board = Board();
    auto owner = L::SelectOwner(board);
    assert(owner && owner->Guid == G(4) && owner->ProposedSpell == 80353);
    board.Players[3].Alive = false;
    owner = L::SelectOwner(board);
    assert(owner && owner->Guid == G(9) && owner->ProposedSpell == 2825);
    board.Players[8].Alive = false;
    assert(!L::SelectOwner(board));
    board = Board();

    // The hold: the boss (by the native probe) on a living tank-role bot.
    auto isBoss = [](ObjectGuid guid) { return guid.GetEntry() == 41442; };
    L::TankHold hold = L::FindTankHold(board, isBoss);
    assert(hold.Boss == board.Hostiles[0].Guid && hold.Tank == G(1));
    Blackboard onHealer = Board(); onHealer.Hostiles[0].VictimGuid = G(5);
    assert(L::FindTankHold(onHealer, isBoss).Boss.IsEmpty());   // the add on the Feral tank is no boss
    Blackboard deadTank = Board(); deadTank.Players[0].Alive = false;
    assert(L::FindTankHold(deadTank, isBoss).Boss.IsEmpty());
    Blackboard idle = Board(); idle.Hostiles[0].InCombat = false;
    assert(L::FindTankHold(idle, isBoss).Boss.IsEmpty());

    L::Latch latch;
    L::Rebind(latch, 7, 1, 30);
    L::ObserveTankHold(latch, hold.Boss, hold.Tank, 100000);
    assert(std::string(L::BlockedReason(board, latch, 104999)) == "raid_boss_lust_tank_hold_pending");
    L::ObserveTankHold(latch, hold.Boss, hold.Tank, 104000);  // same pair: the hold continues
    assert(L::BlockedReason(board, latch, 105000) == nullptr);
    L::ObserveTankHold(latch, hold.Boss, G(2), 105000);       // a tank swap restarts it
    assert(!L::TankHeld(latch, 109999) && L::TankHeld(latch, 110000));
    L::ObserveTankHold(latch, ObjectGuid(), ObjectGuid(), 110000);
    assert(!L::TankHeld(latch, 200000));
    L::ObserveTankHold(latch, hold.Boss, hold.Tank, 200000);
    // Raid lockouts (Magmaw's FindRaidLockout) block it.
    Blackboard sated = Board(); sated.Players[6].Auras.push_back({ 57724, ObjectGuid(), 1, 0 });
    assert(std::string(L::BlockedReason(sated, latch, 205000)) == "sated_lockout");
    latch.Submitted = true;
    assert(std::string(L::BlockedReason(board, latch, 205000)) == "raid_boss_lust_already_submitted");
    // One cast per attempt, wipe and route node.
    L::Rebind(latch, 7, 1, 30);
    assert(latch.Submitted);
    L::Rebind(latch, 7, 2, 30);
    assert(!latch.Submitted && !latch.Holding && latch.WipeGeneration == 2);
    std::puts("ok");
}
''')
    assert out.strip() == "ok"


def test_boss_lust_runtime_is_canonical_boss_scoped_and_reuses_the_lust_plumbing() -> None:
    runtime = _text("BotWorldPopulationMgrRaidBossLust.cpp")
    for gate in ("BotCanonicalRaidScope::IsCanonicalRaid(cohort.Raid.RaidInstance,",
                 'cohort.Config.ValidationRouteKind != "boss"',
                 "!cohort.Raid.EncounterInProgress",
                 "BotRaidBossLust::StrategyOwnsLust(cohort.Config.ValidationRouteNodeId,",
                 "owner->Guid != bot->GetGUID()",
                 "BotEncounter::Chimaeron::KnownLustSpell(",
                 "creature->IsDungeonBoss() || creature->isWorldBoss()",
                 "TryCastFriendlySpell(bot, bot, spell, &failureReason)"):
        assert gate in runtime, gate
    # The latch is committed only after the native submission succeeds.
    attempt = runtime[runtime.index("lust.Attempt"):]
    assert attempt.index("TryCastFriendlySpell") < attempt.index("current.Submitted = true;")
    # The owner's own cooldown is checked before any cast is submitted and
    # published as a typed, resource-free reason; the gate is re-evaluated each
    # decision, so a cooldown that returns mid-fight still casts (once).
    ready = runtime.index("!bot->GetSpellHistory()->IsReady(spellInfo)")
    assert ready < runtime.index("BotActionArbitration::Candidate lust;")
    cooldown = runtime[ready:runtime.index("BotActionArbitration::Candidate lust;")]
    for marker in ("BotActionArbitration::Resource::None", "BotRaidBossLust::OwnerLustCooldownReason",
                   "Outcome::NotApplicable", "return;"):
        assert marker in cooldown, marker
    assert "latch.Submitted" not in cooldown
    lust = _text("BotRaidBossLust.h")
    assert 'OwnerLustCooldownReason = "raid_boss_lust_owner_lust_cooldown"' in lust
    assert "BotEncounter::Chimaeron::BuildDuties(board)" in lust
    assert "BotEncounter::MagmawBloodlust::FindRaidLockout(board)" in lust
    maloriak = (ENCOUNTERS / "Maloriak/BotMaloriakFacts.h").read_text()
    assert 'constexpr std::string_view EncounterNode = "bwd.maloriak.encounter";' in maloriak
    assert 'constexpr std::string_view MaloriakEncounterNode = "bwd.maloriak.encounter";' in lust
    kernel = _text("BotWorldPopulationMgrUpdateBotKernelCandidates.cpp")
    assert ("        SubmitAdaptiveChimaeronCandidates(context);\n"
            "        SubmitRaidBossLustCandidate(context);\n") in kernel
    assert "    void SubmitRaidBossLustCandidate(BotUpdateContext& context);\n" in _text("BotWorldPopulationMgr.h")
    assert "        BotRaidBossLust::Latch BossLust;\n" in _text("BotWorldPopulationMgrRuntimeContracts.h")
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text()
    assert "${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRaidBossLust.cpp" in cmake


def test_touched_sources_stay_below_the_module_limit() -> None:
    for name in TOUCHED:
        assert len(_text(name).splitlines()) < 1000, name


# Provisioning: every spell this package casts must be in the canonical spellbook.

RELIED_ON = {
    "paladin_ret": {"retribution_paladin": [19740, 7294]},
    "paladin_holy": {"holy_paladin": [19740, 465]},
    "priest": {"discipline_priest": [21562]},
    "druid": {"balance_druid": [1126], "feral_druid_tank": [1126]},
    "mage": {"fire_mage": [80353]},
    "shaman": {"elemental_shaman": [32182], "restoration_shaman": [32182]},
}


def test_the_canonical_spellbooks_hold_every_spell_this_package_casts() -> None:
    """Fails closed until the composition declares what the trainer baseline does not provision (for M)."""
    absent = [str(path.relative_to(ROOT)) for path in (DBC / "SkillLineAbility.dbc", TRAINERS) if not path.is_file()]
    assert not absent, f"extract the client DBCs and dvc pull the plan inputs: {absent}"
    from tools.raid_program.raid_loadout_spells import loadout_known_spells
    from tools.raid_program.raid_shard_scenarios import build_plan

    plan = build_plan(COMPOSITION)
    missing = set()
    checked = set()
    for shard in plan["shards"]:
        for bot in shard["bots"]:
            wanted = RELIED_ON.get(bot["character_key"], {}).get(bot["class_spec"])
            if not wanted:
                continue
            known = set(loadout_known_spells(bot, DBC, trainers_path=TRAINERS)["known_spell_ids"])
            missing |= {(bot["character_key"], spell) for spell in wanted if spell not in known}
            checked.add((bot["character_key"], bot["class_spec"]))
    assert checked == {(key, spec) for key, specs in RELIED_ON.items() for spec in specs}
    assert not missing, sorted(missing)
