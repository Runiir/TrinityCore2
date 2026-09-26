"""Round 6: a raid-wide persistent buff row is kept for the raid, not only its caster.

Round 5 re-cast a row only when the caster lacked its own aura. The characters
database saved at the round 5 clears shows both Retribution paladins (Magmaw and
Atramedes shards) without Power Word: Fortitude 79105, one also without Mark of
the Wild 79061, while their casters and the other nine bots carried them: a
member that died and came back while the caster lived stayed unbuffed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
INCLUDES = ["src/server/game", "src/server/shared", "src/common", "src/common/Utilities",
            "dep/recastnavigation/Detour/Include"]


def _run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "recast.cpp"
    binary = tmp_path / "recast"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


def test_a_living_member_without_the_raid_buff_reopens_the_row_once_per_window(tmp_path: Path) -> None:
    out = _run(tmp_path, r"""
#include "Bots/BotRaidPersistentBuffs.h"
#include <cassert>
#include <cstdio>
#include <map>
#include <set>
#include <string>
namespace R = BotRaidPersistentBuffs;
struct FakePlayer;
struct FakeRef {
    FakePlayer* Player; FakeRef* Next;
    FakeRef* next() { return Next; }
    FakePlayer* GetSource() const { return Player; }
};
struct FakeGroup { FakeRef* First = nullptr; FakeRef* GetFirstMember() { return First; } };
struct FakePlayer {
    uint32 Guid = 0; uint8 Class = CLASS_PRIEST; int Map = 669; float X = 0.0f; bool Alive = true;
    bool Combat = false; bool Sight = true; std::set<uint32> Auras; FakeGroup* Group = nullptr;
    FakeGroup* GetGroup() { return Group; }
    uint32 GetGUID() const { return Guid; }
    uint8 getClass() const { return Class; }
    bool IsAlive() const { return Alive; }
    bool IsInCombat() const { return Combat; }
    bool IsInMap(FakePlayer const* other) const { return Map == other->Map; }
    bool IsWithinLOSInMap(FakePlayer const* other) const { return other->Sight; }
    float GetExactDist(FakePlayer const* other) const { return X > other->X ? X - other->X : other->X - X; }
    bool HasAura(uint32 aura) const { return Auras.count(aura) > 0; }
};
int main() {
    R::SelfBuff const fortitude = R::CanonicalRows[0];
    assert(fortitude.SpellId == R::PowerWordFortitude && fortitude.AuraId == 79105);
    R::SelfBuff mark{};
    for (auto const& row : BotPersistentSelfBuffContract::Buffs)
        if (row.SpellId == R::MarkOfTheWild) mark = row;
    FakePlayer priest, ret, tank;
    priest.Guid = 7; ret.Guid = 6; tank.Guid = 1;
    priest.Auras = { 79105, 79061 }; tank.Auras = { 79105, 79061 };
    FakeGroup group;
    FakeRef tankRef{ &tank, nullptr }, retRef{ &ret, &tankRef }, priestRef{ &priest, &retRef };
    group.First = &priestRef;
    priest.Group = ret.Group = tank.Group = &group;
    std::map<std::string, uint64> retry;
    bool ready = true;
    int probes = 0;
    auto castReady = [&] { ++probes; return ready; };
    std::string const key = "raid_buff_coverage:21562";

    // 1. The Retribution paladin came back without Fortitude: the row re-opens,
    // then waits out its window instead of re-casting on every tick.
    assert(!R::RaidCoverageHolds(&priest, fortitude, retry, 1000, castReady));
    assert(R::RaidCoverageHolds(&priest, fortitude, retry, 1000 + R::RaidCoverageRetryMs - 1, castReady));
    assert(!R::RaidCoverageHolds(&priest, fortitude, retry, 1000 + R::RaidCoverageRetryMs, castReady));
    // A busy caster (mid-Penance, on the GCD, wrong form) opens no window:
    // it holds, keeps the window unspent and re-opens once it can cast.
    retry.clear(); ready = false;
    assert(R::RaidCoverageHolds(&priest, fortitude, retry, 5000, castReady) && retry[key] == 0);
    assert(R::RaidCoverageHolds(&priest, fortitude, retry, 5100, castReady) && retry[key] == 0);
    ready = true;
    assert(!R::RaidCoverageHolds(&priest, fortitude, retry, 5200, castReady)
        && retry[key] == 5200 + R::RaidCoverageRetryMs);

    // 2a. In combat only Fortitude re-opens (health after a combat res).
    retry.clear(); priest.Combat = true;
    assert(!R::RaidCoverageHolds(&priest, fortitude, retry, 9000, castReady));
    probes = 0;
    assert(R::RaidCoverageHolds(&priest, mark, retry, 9000, castReady) && probes == 0);
    priest.Combat = false;
    assert(!R::RaidCoverageHolds(&priest, mark, retry, 9000, castReady));  // out of combat: every row
    // 2b. Line of sight: a member behind a pillar is not the row's to cover.
    retry.clear(); ret.Sight = false;
    assert(R::RaidCoverageHolds(&priest, fortitude, retry, 12000, castReady) && retry.empty());
    ret.Sight = true;

    // Covered (the raid aura or its single-target alternate) holds; dead,
    // far or elsewhere members are not the row's to cover.
    ret.Auras = { 79104 };
    assert(R::RaidCoverageHolds(&priest, fortitude, retry, 12000, castReady) && retry.empty());
    ret.Auras.clear(); ret.Alive = false;
    assert(R::RaidCoverageHolds(&priest, fortitude, retry, 12000, castReady));
    ret.Alive = true; ret.X = R::RaidCoverageRangeYards + 1.0f;
    assert(R::RaidCoverageHolds(&priest, fortitude, retry, 12000, castReady));
    ret.X = 0.0f; ret.Map = 0;
    assert(R::RaidCoverageHolds(&priest, fortitude, retry, 12000, castReady) && retry.empty());
    ret.Map = 669; ret.Auras = { 79105, 79061 };

    // 2c. One owner for blessing coverage: the lowest-GUID living paladin.
    R::SelfBuff const might = R::BlessingOfMight;
    FakePlayer holy, retPaladin, rogue;
    holy.Guid = 5; holy.Class = CLASS_PALADIN; holy.Auras = { 79102 };
    retPaladin.Guid = 6; retPaladin.Class = CLASS_PALADIN; retPaladin.Auras = { 79102 };
    rogue.Guid = 8; rogue.Class = CLASS_ROGUE;  // came back without Might
    FakeGroup blessed;
    FakeRef rogueRef{ &rogue, nullptr }, retPalRef{ &retPaladin, &rogueRef }, holyRef{ &holy, &retPalRef };
    blessed.First = &holyRef;
    holy.Group = retPaladin.Group = rogue.Group = &blessed;
    retry.clear();
    assert(R::RaidCoverageHolds(&retPaladin, might, retry, 20000, castReady) && retry.empty());
    assert(!R::RaidCoverageHolds(&holy, might, retry, 20000, castReady));
    holy.Alive = false;  // the owner died: the next living paladin owns it
    std::map<std::string, uint64> retRetry;
    assert(!R::RaidCoverageHolds(&retPaladin, might, retRetry, 20000, castReady));
    assert(R::IsBlessingRow(R::BlessingOfKings) && R::IsBlessingRow(19740) && !R::IsBlessingRow(21562));

    // Not raid-wide: a self buff or a paladin aura (death-persistent area aura).
    for (R::SelfBuff const& row : R::CanonicalRows)
        if (row.SpellId != R::PowerWordFortitude)
            assert(R::RaidCoverageHolds(&priest, row, retry, 30000, castReady));
    assert(R::RaidCoverageHolds(&priest, BotPersistentSelfBuffContract::Buffs[0], retry, 30000, castReady));
    for (uint32 spell : { 1126u, 20217u, 19740u, 21562u, 1459u })
        assert(R::IsRaidWideRow(spell));
    assert(!R::IsRaidWideRow(465) && !R::IsRaidWideRow(7294) && !R::IsRaidWideRow(24858));
    FakePlayer alone; alone.Auras = { 79105 };
    assert(R::RaidCoverageHolds(&alone, fortitude, retry, 30000, castReady));
    std::puts("ok");
}
""")
    assert out.strip() == "ok"


def test_persistent_setup_requires_raid_coverage_only_in_canonical_raids() -> None:
    setup = (BOTS / "BotWorldPopulationMgrPersistentSetup.cpp").read_text()
    assert ("        bool const auraActive = (bot->HasAura(buff.AuraId)\n"
            "            || (buff.AlternateAuraId && bot->HasAura(buff.AlternateAuraId)))\n"
            "            && (!canonicalRaid || BotRaidPersistentBuffs::RaidCoverageHolds(bot, buff,\n"
            "                state.ReadinessRetryUntilMs, NowMs(), [bot, &buff] {\n") in setup
    # The window opens only for a cast that can start now: not casting, off
    # the GCD and cooldown, in a form that allows the spell.
    probe = setup[setup.index("[bot, &buff] {"):setup.index("}));", setup.index("[bot, &buff] {"))]
    for gate in ("sSpellMgr->GetSpellInfo(buff.SpellId)", "!bot->HasUnitState(UNIT_STATE_CASTING)",
                 "!bot->GetSpellHistory()->HasGlobalCooldown(info)", "bot->GetSpellHistory()->IsReady(info)",
                 "info->CheckShapeshift(bot->GetShapeshiftForm()) == SPELL_CAST_OK"):
        assert gate in probe, gate
    # The raid check runs only after the caster's own aura (short-circuit), so
    # a caster without its aura re-casts exactly as before.
    assert setup.index("bool const auraActive = (bot->HasAura(buff.AuraId)") < setup.index("RaidCoverageHolds(")
    assert len(setup.splitlines()) < 1000
    header = (BOTS / "BotRaidPersistentBuffs.h").read_text()
    assert '"raid_buff_coverage:"' in header
