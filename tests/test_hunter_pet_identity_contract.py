from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
CONTRACT = GAME / "Bots/BotHunterPetIdentityContract.cpp"


def test_hunter_pet_identity_contract_is_compiled_and_behavioral() -> None:
    harness = r'''
#include "Bots/BotHunterPetIdentityContract.h"

#include <array>
#include <cassert>

using namespace BotHunterPetIdentityContract;

struct PetRow
{
    unsigned PetId = 0;
    unsigned Entry = 0;
    unsigned Owner = 0;
    bool Hunter = false;
    bool Active = false;
};

PersistentIdentityFacts validIdentity()
{
    PersistentIdentityFacts facts;
    facts.CharmInfoPresent = true;
    facts.PersistentRowPresent = true;
    facts.StoredLifecycleActive = true;
    facts.StoredTypeHunter = true;
    facts.LiveTypeHunter = true;
    facts.Permanent = true;
    facts.LiveOwnerMatches = true;
    facts.StoredOwnerMatches = true;
    facts.StoredPetId = 8700009;
    facts.StoredEntry = 8959;
    facts.LivePetId = 8700009;
    facts.LiveEntry = 8959;
    return facts;
}

FrozenReceiptComparison validReceipt()
{
    FrozenReceiptComparison comparison;
    comparison.PetIdMatches = true;
    comparison.PetEntryMatches = true;
    comparison.OwnerMatches = true;
    comparison.SpellCountMatches = true;
    comparison.SpellbookMatches = true;
    comparison.SpellbookDigestMatches = true;
    comparison.AutocastMatches = true;
    return comparison;
}

int main()
{
    // Production selection is keyed by the live CharmInfo pet number. An
    // unrelated active row must not displace the admitted inactive row.
    std::array<PetRow, 2> rows = {{
        {8700009, 8959, 30009, true, false},
        {42, 1, 30009, true, true},
    }};
    auto lookup = [&rows](unsigned petId) -> PetRow const*
    {
        for (PetRow const& row : rows)
            if (row.PetId == petId)
                return &row;
        return nullptr;
    };
    PetRow const* selected =
        SelectPersistentRowForLivePet<PetRow>(8700009, lookup);
    assert(selected == &rows[0]);
    assert(!selected->Active);

    PersistentIdentityFacts identity = validIdentity();
    identity.PersistentRowPresent = selected != nullptr;
    identity.StoredLifecycleActive = selected && selected->Active;
    identity.StoredTypeHunter = selected && selected->Hunter;
    identity.StoredOwnerMatches = selected && selected->Owner == 30009;
    identity.StoredPetId = selected ? selected->PetId : 0;
    identity.StoredEntry = selected ? selected->Entry : 0;
    assert(ClassifyPersistentIdentity(identity) == PersistentIdentityStatus::Observed);

    FrozenReceiptComparison receipt = validReceipt();
    receipt.PetIdMatches = selected && selected->PetId == 8700009;
    receipt.PetEntryMatches = selected && selected->Entry == 8959;
    receipt.OwnerMatches = selected && selected->Owner == 30009;
    assert(ClassifyFrozenReceipt(receipt) == FrozenReceiptStatus::Matches);

    // No live instance (including an ordinarily dismissed pet before it is
    // called again) has no live pet number and cannot select any row.
    assert(SelectPersistentRowForLivePet<PetRow>(0, lookup) == nullptr);

    // A lookup that violates its key contract is rejected at the selection
    // boundary rather than being classified as the requested pet.
    auto wrongLookup = [&rows](unsigned) -> PetRow const* { return &rows[1]; };
    assert(SelectPersistentRowForLivePet<PetRow>(8700009, wrongLookup) == nullptr);

    // A different live pet may select its own valid row, but must still fail
    // reconciliation against the frozen admitted pet.
    selected = SelectPersistentRowForLivePet<PetRow>(42, lookup);
    assert(selected == &rows[1]);
    receipt = validReceipt();
    receipt.PetIdMatches = selected->PetId == 8700009;
    assert(ClassifyFrozenReceipt(receipt) == FrozenReceiptStatus::PetIdMismatch);

    // The exact Canary 48abb counterexample remains explicit: the same
    // permanent owned live
    // pet and row remain identity-valid after ordinary lifecycle code changes
    // PlayerPetData::Active to false.
    identity.StoredLifecycleActive = false;
    assert(ClassifyPersistentIdentity(identity) == PersistentIdentityStatus::Observed);

    auto expectIdentityFailure = [](PersistentIdentityFacts facts,
        PersistentIdentityStatus expected)
    {
        assert(ClassifyPersistentIdentity(facts) == expected);
        assert(*PersistentIdentityFailureReason(expected));
    };
    identity = validIdentity(); identity.PersistentRowPresent = false;
    expectIdentityFailure(identity, PersistentIdentityStatus::PersistentRowMissing);
    identity = validIdentity(); identity.StoredTypeHunter = false;
    expectIdentityFailure(identity, PersistentIdentityStatus::StoredTypeMismatch);
    identity = validIdentity(); identity.LiveTypeHunter = false;
    expectIdentityFailure(identity, PersistentIdentityStatus::LiveTypeMismatch);
    identity = validIdentity(); identity.Permanent = false;
    expectIdentityFailure(identity, PersistentIdentityStatus::NotPermanent);
    identity = validIdentity(); identity.LiveOwnerMatches = false;
    expectIdentityFailure(identity, PersistentIdentityStatus::LiveOwnerMismatch);
    identity = validIdentity(); identity.StoredOwnerMatches = false;
    expectIdentityFailure(identity, PersistentIdentityStatus::StoredOwnerMismatch);
    identity = validIdentity(); identity.StoredPetId = 42;
    expectIdentityFailure(identity, PersistentIdentityStatus::PetIdMismatch);
    identity = validIdentity(); identity.LiveEntry = 42;
    expectIdentityFailure(identity, PersistentIdentityStatus::PetEntryMismatch);

    receipt = validReceipt();
    assert(ClassifyFrozenReceipt(receipt) == FrozenReceiptStatus::Matches);
    auto expectReceiptFailure = [](FrozenReceiptComparison comparison,
        FrozenReceiptStatus expected)
    {
        assert(ClassifyFrozenReceipt(comparison) == expected);
        assert(*FrozenReceiptFailureReason(expected));
    };
    receipt = validReceipt(); receipt.PetIdMatches = false;
    expectReceiptFailure(receipt, FrozenReceiptStatus::PetIdMismatch);
    receipt = validReceipt(); receipt.PetEntryMatches = false;
    expectReceiptFailure(receipt, FrozenReceiptStatus::PetEntryMismatch);
    receipt = validReceipt(); receipt.OwnerMatches = false;
    expectReceiptFailure(receipt, FrozenReceiptStatus::OwnerMismatch);
    receipt = validReceipt(); receipt.SpellCountMatches = false;
    expectReceiptFailure(receipt, FrozenReceiptStatus::SpellCountMismatch);
    receipt = validReceipt(); receipt.SpellbookMatches = false;
    expectReceiptFailure(receipt, FrozenReceiptStatus::SpellbookMismatch);
    receipt = validReceipt(); receipt.SpellbookDigestMatches = false;
    expectReceiptFailure(receipt, FrozenReceiptStatus::SpellbookDigestMismatch);
    receipt = validReceipt(); receipt.AutocastMatches = false;
    expectReceiptFailure(receipt, FrozenReceiptStatus::AutocastMismatch);
}
'''
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        source = directory_path / "hunter_pet_identity_contract_test.cpp"
        binary = directory_path / "hunter_pet_identity_contract_test"
        source.write_text(harness, encoding="utf-8")
        subprocess.run(
            [
                "g++",
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(GAME),
                str(source),
                str(CONTRACT),
                "-o",
                str(binary),
            ],
            check=True,
        )
        subprocess.run([str(binary)], check=True)


def test_runtime_observer_uses_live_pet_number_not_mutable_current_flag() -> None:
    observer = (
        GAME / "Bots/BotWorldPopulationMgrCalibrationIdentity.cpp"
    ).read_text(encoding="utf-8")
    cohort = (
        GAME / "Bots/BotWorldPopulationMgrValidationCohortGroup.cpp"
    ).read_text(encoding="utf-8")

    assert "SelectPersistentRowForLivePet<PlayerPetData>" in observer
    assert "GetPlayerPetDataById(petId)" in observer
    assert "GetPlayerPetDataCurrent()" not in observer[
        observer.index("ObserveActiveOrdinaryHunterPetStatus") :
    ]
    assert "ClassifyPersistentIdentity(facts)" in observer
    assert "ClassifyFrozenReceipt(comparison)" in cohort
    assert "PersistentIdentityFailureReason" in cohort
    assert "FrozenReceiptFailureReason" in cohort
