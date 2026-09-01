#ifndef TRINITY_BOT_HUNTER_PET_IDENTITY_CONTRACT_H
#define TRINITY_BOT_HUNTER_PET_IDENTITY_CONTRACT_H

#include <cstdint>

namespace BotHunterPetIdentityContract
{
enum class PersistentIdentityStatus : std::uint8_t
{
    Observed = 0,
    CharmInfoMissing,
    PersistentRowMissing,
    StoredTypeMismatch,
    LiveTypeMismatch,
    NotPermanent,
    LiveOwnerMismatch,
    StoredOwnerMismatch,
    StoredPetIdMissing,
    StoredEntryMissing,
    PetIdMismatch,
    PetEntryMismatch
};

struct PersistentIdentityFacts
{
    bool CharmInfoPresent = false;
    bool PersistentRowPresent = false;
    // PlayerPetData::Active is changed by ordinary dismiss/call lifecycle.
    // It is observed here to make its deliberate exclusion from identity
    // classification explicit.
    bool StoredLifecycleActive = false;
    bool StoredTypeHunter = false;
    bool LiveTypeHunter = false;
    bool Permanent = false;
    bool LiveOwnerMatches = false;
    bool StoredOwnerMatches = false;
    std::uint32_t StoredPetId = 0;
    std::uint32_t StoredEntry = 0;
    std::uint32_t LivePetId = 0;
    std::uint32_t LiveEntry = 0;
};

PersistentIdentityStatus ClassifyPersistentIdentity(
    PersistentIdentityFacts const& facts);
char const* PersistentIdentityFailureReason(PersistentIdentityStatus status);

enum class FrozenReceiptStatus : std::uint8_t
{
    Matches = 0,
    PetIdMismatch,
    PetEntryMismatch,
    OwnerMismatch,
    SpellCountMismatch,
    SpellbookMismatch,
    SpellbookDigestMismatch,
    AutocastMismatch
};

struct FrozenReceiptComparison
{
    bool PetIdMatches = false;
    bool PetEntryMatches = false;
    bool OwnerMatches = false;
    bool SpellCountMatches = false;
    bool SpellbookMatches = false;
    bool SpellbookDigestMatches = false;
    bool AutocastMatches = false;
};

FrozenReceiptStatus ClassifyFrozenReceipt(
    FrozenReceiptComparison const& comparison);
char const* FrozenReceiptFailureReason(FrozenReceiptStatus status);
}

#endif
