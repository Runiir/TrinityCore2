from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]


def _compile_and_run(tmp_path: Path, program: str) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


PRELUDE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDutyCallouts.h"
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

using namespace BotRaidDuty;
namespace Magmaw = BotEncounter::MagmawDutyCallouts;

static int failures = 0;

[[maybe_unused]] static void Expect(char const* text, std::vector<std::string_view> duties,
    CalloutIntent intent)
{
    std::vector<Callout> const callouts = ParseCallouts(text, Magmaw::Table());
    bool ok = callouts.size() == duties.size();
    for (std::size_t index = 0; ok && index < duties.size(); ++index)
        ok = callouts[index].Duty == duties[index]
            && callouts[index].Intent == intent;
    if (!ok)
    {
        std::fprintf(stderr, "FAIL: \"%s\" -> %zu callouts\n", text, callouts.size());
        ++failures;
    }
}

[[maybe_unused]] static void ExpectEach(char const* text,
    std::vector<std::pair<std::string_view, CalloutIntent>> expected)
{
    std::vector<Callout> const callouts = ParseCallouts(text, Magmaw::Table());
    bool ok = callouts.size() == expected.size();
    for (std::size_t index = 0; ok && index < expected.size(); ++index)
        ok = callouts[index].Duty == expected[index].first
            && callouts[index].Intent == expected[index].second;
    if (!ok)
    {
        std::fprintf(stderr, "FAIL: \"%s\" -> %zu callouts\n", text, callouts.size());
        ++failures;
    }
}

[[maybe_unused]] static void ExpectNone(char const* text)
{
    if (!ParseCallouts(text, Magmaw::Table()).empty())
    {
        std::fprintf(stderr, "FAIL: \"%s\" should not be a callout\n", text);
        ++failures;
    }
}
'''


def test_callouts_claim_release_and_ignore_chatter(tmp_path: Path) -> None:
    _compile_and_run(
        tmp_path,
        PRELUDE
        + r'''
int main()
{
    auto const claim = CalloutIntent::Claim;
    auto const release = CalloutIntent::Release;
    Expect("I do chains", { Magmaw::Chains }, claim);
    Expect("I'll take chains", { Magmaw::Chains }, claim);
    Expect("I\xE2\x80\x99ll do the pincers", { Magmaw::Chains }, claim);
    Expect("chains on me", { Magmaw::Chains }, claim);
    Expect("hooks mine", { Magmaw::Chains }, claim);
    Expect("I'm on bait", { Magmaw::Bait }, claim);
    Expect("I do chains and bait", { Magmaw::Chains, Magmaw::Bait }, claim);
    Expect("i got hero", { Bloodlust }, claim);
    Expect("I'll lust at 30%", { Bloodlust }, claim);
    Expect("time warp on me", { Bloodlust }, claim);
    Expect("I'll brez the tank", { BattleRes }, claim);
    Expect("I do mushrooms", { Magmaw::Mushrooms }, claim);
    Expect("no bots, I do chains", { Magmaw::Chains }, claim);

    Expect("bots do chains", { Magmaw::Chains }, release);
    Expect("I'll let bots do chains", { Magmaw::Chains }, release);
    Expect("I can't do chains", { Magmaw::Chains }, release);
    Expect("i wont bait anymore", { Magmaw::Bait }, release);
    Expect("release chains", { Magmaw::Chains }, release);

    Expect("bres on me", { BattleRes }, claim);
    ExpectEach("bots do chains, I do bait",
        { { Magmaw::Chains, release }, { Magmaw::Bait, claim } });
    ExpectEach("I do chains but bots do bait",
        { { Magmaw::Chains, claim }, { Magmaw::Bait, release } });
    if (ParseCallouts("I can't do chains", Magmaw::Table()).front().Personal != true
        || ParseCallouts("bots do chains", Magmaw::Table()).front().Personal != false)
        ++failures;

    // Review findings (e4fa8a143a): requests, other spells and positions.
    ExpectNone("brez me");
    ExpectNone("give me lust");
    ExpectNone("lust me");
    ExpectNone("I'll chain heal the melee");
    ExpectNone("im chain lightning the adds");
    ExpectNone("I'm at the pillar");
    ExpectNone("I'm the hero");
    ExpectNone("the chains were late");
    ExpectNone("chains now");
    ExpectNone("lust now");
    ExpectNone("i need a brez");
    ExpectNone("can someone do chains?");
    ExpectNone("who has bait");
    ExpectNone("I am ready");
    ExpectNone("");
    return failures == 0 ? 0 : 1;
}
''',
    )


def test_claims_store_tracks_owner_and_releases(tmp_path: Path) -> None:
    _compile_and_run(
        tmp_path,
        PRELUDE
        + r'''
int main()
{
    Claims claims;
    ObjectGuid const human(HighGuid::Player, uint32(50001));
    ObjectGuid const other(HighGuid::Player, uint32(50002));
    if (!claims.Empty() || claims.IsClaimed(Magmaw::Chains))
        return 1;
    Callout const chains{ std::string(Magmaw::Chains), CalloutIntent::Claim };
    if (!claims.Apply(chains, human, 10) || claims.Owner(Magmaw::Chains) != human)
        return 2;
    // Repeating one's own claim changes nothing; another human takes over.
    if (claims.Apply(chains, human, 11))
        return 3;
    if (!claims.Apply(chains, other, 12) || claims.Owner(Magmaw::Chains) != other)
        return 4;
    Callout const bait{ std::string(Magmaw::Bait), CalloutIntent::Claim };
    claims.Apply(bait, other, 13);
    if (claims.ReleaseAllOwnedBy(other) != 2 || !claims.Empty())
        return 5;
    claims.Apply(chains, human, 14);
    Callout const giveBack{ std::string(Magmaw::Chains), CalloutIntent::Release };
    if (!claims.Apply(giveBack, other, 15) || claims.IsClaimed(Magmaw::Chains))
        return 6;
    if (claims.Apply(giveBack, other, 16))
        return 7;
    // "I can't do chains" from someone else leaves the owner's claim.
    claims.Apply(chains, human, 17);
    Callout const cannot{ std::string(Magmaw::Chains), CalloutIntent::Release, true };
    if (claims.Apply(cannot, other, 18) || claims.Owner(Magmaw::Chains) != human)
        return 8;
    if (!claims.Apply(cannot, human, 19) || claims.IsClaimed(Magmaw::Chains))
        return 9;
    return 0;
}
''',
    )
