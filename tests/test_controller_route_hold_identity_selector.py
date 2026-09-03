from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotControllerRouteHoldIdentitySelector.h"
MODULE = ROOT / (
    "src/server/game/Bots/BotWorldPopulationMgrChainwielderOwnerCheckpoint.cpp"
)


def test_compiled_selector_maps_each_fixture_and_preserves_default(tmp_path: Path) -> None:
    source = tmp_path / "controller_route_hold_identity_selector.cpp"
    binary = tmp_path / "controller_route_hold_identity_selector"
    source.write_text(
        r'''
#include "Bots/BotControllerRouteHoldIdentitySelector.h"

#include <cassert>
#include <string_view>

using BotControllerRouteHoldIdentitySelector::AuthorityCatalog;
using BotControllerRouteHoldIdentitySelector::AuthorityTriple;
using BotControllerRouteHoldIdentitySelector::Select;

AuthorityCatalog Catalog()
{
    return {
        { "profile-config", "profile-seal", "profile-source" },
        { "native-config", "native-seal", "native-source" },
        { "transfer-config", "transfer-seal", "transfer-source" },
        { "chain-config", "chain-seal", "chain-source" },
    };
}

void AssertTriple(AuthorityTriple const& actual,
    std::string_view fixture, std::string_view seal, std::string_view source)
{
    assert(actual.FixtureId == fixture);
    assert(actual.SealSha256 == seal);
    assert(actual.SourceCommit == source);
}

int main()
{
    AuthorityCatalog const authorities = Catalog();
    AssertTriple(Select(BotProfileCombatRangeCheckpoint::FixtureId, authorities),
        "profile-config", "profile-seal", "profile-source");
    AssertTriple(Select(BotNativePathCheckpoint::FixtureId, authorities),
        "native-config", "native-seal", "native-source");
    AssertTriple(
        Select(BotEncounter::MagmawTransferLaneCheckpoint::FixtureId,
            authorities),
        "transfer-config", "transfer-seal", "transfer-source");
    AssertTriple(Select(BotChainwielderOwnerCheckpoint::FixtureId, authorities),
        "chain-config", "chain-seal", "chain-source");

    // Unknown and empty IDs preserve the existing Chainwielder fallback.
    AssertTriple(Select("unknown-fixture", authorities),
        "chain-config", "chain-seal", "chain-source");
    AssertTriple(Select({}, authorities),
        "chain-config", "chain-seal", "chain-source");

    // Adjacent IDs never alias a supported dialect.
    for (std::string_view adjacent : {
        "generic_profile_min_range_production_boundary_v1_adjacent",
        "map669_native_path_production_boundary_v1_adjacent",
        "map669_magmaw_transfer_lane_authority_off_v1_adjacent",
        "chainwielder_pre_admission_rejection_isolation_v1_adjacent",
    })
        AssertTriple(Select(adjacent, authorities),
            "chain-config", "chain-seal", "chain-source");

    // Empty values remain a value-level result and cannot cause another
    // dialect to be selected.
    AuthorityCatalog emptyProfile = authorities;
    emptyProfile.ProfileCombatRange = {};
    AssertTriple(Select(BotProfileCombatRangeCheckpoint::FixtureId,
        emptyProfile), {}, {}, {});
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_current_identity_uses_the_production_selector() -> None:
    header = HEADER.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    assert "struct AuthorityTriple" in header
    assert "struct AuthorityCatalog" in header
    assert "BotProfileCombatRangeCheckpoint::FixtureId" in header
    assert "BotNativePathCheckpoint::FixtureId" in header
    assert "BotEncounter::MagmawTransferLaneCheckpoint::FixtureId" in header
    assert "return authorities.Chainwielder;" in header
    current = module[module.index(
        "BotWorldPopulationMgr::CurrentControllerRouteHoldIdentity"
    ):module.index(
        "std::string BotWorldPopulationMgr::StartAutonomyHeldForCohort"
    )]
    assert "BotControllerRouteHoldIdentitySelector::Select(" in current
    assert "ProfileCombatRangeCheckpointFixtureId" in current
    assert "authority.FixtureId" in current
