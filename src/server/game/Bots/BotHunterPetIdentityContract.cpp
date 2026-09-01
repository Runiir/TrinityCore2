#include "Bots/BotHunterPetIdentityContract.h"

namespace BotHunterPetIdentityContract
{
PersistentIdentityStatus ClassifyPersistentIdentity(
    PersistentIdentityFacts const& facts)
{
    if (!facts.CharmInfoPresent)
        return PersistentIdentityStatus::CharmInfoMissing;
    if (!facts.PersistentRowPresent)
        return PersistentIdentityStatus::PersistentRowMissing;
    if (!facts.StoredTypeHunter)
        return PersistentIdentityStatus::StoredTypeMismatch;
    if (!facts.LiveTypeHunter)
        return PersistentIdentityStatus::LiveTypeMismatch;
    if (!facts.Permanent)
        return PersistentIdentityStatus::NotPermanent;
    if (!facts.LiveOwnerMatches)
        return PersistentIdentityStatus::LiveOwnerMismatch;
    if (!facts.StoredOwnerMatches)
        return PersistentIdentityStatus::StoredOwnerMismatch;
    if (!facts.StoredPetId)
        return PersistentIdentityStatus::StoredPetIdMissing;
    if (!facts.StoredEntry)
        return PersistentIdentityStatus::StoredEntryMissing;
    if (facts.LivePetId != facts.StoredPetId)
        return PersistentIdentityStatus::PetIdMismatch;
    if (facts.LiveEntry != facts.StoredEntry)
        return PersistentIdentityStatus::PetEntryMismatch;
    return PersistentIdentityStatus::Observed;
}

char const* PersistentIdentityFailureReason(PersistentIdentityStatus status)
{
    switch (status)
    {
        case PersistentIdentityStatus::CharmInfoMissing:
            return "validation_active_hunter_pet_observation_charm_info_missing";
        case PersistentIdentityStatus::PersistentRowMissing:
            return "validation_active_hunter_pet_observation_persistent_row_missing";
        case PersistentIdentityStatus::StoredTypeMismatch:
            return "validation_active_hunter_pet_observation_stored_type_mismatch";
        case PersistentIdentityStatus::LiveTypeMismatch:
            return "validation_active_hunter_pet_observation_live_type_mismatch";
        case PersistentIdentityStatus::NotPermanent:
            return "validation_active_hunter_pet_observation_not_permanent";
        case PersistentIdentityStatus::LiveOwnerMismatch:
            return "validation_active_hunter_pet_observation_live_owner_mismatch";
        case PersistentIdentityStatus::StoredOwnerMismatch:
            return "validation_active_hunter_pet_observation_stored_owner_mismatch";
        case PersistentIdentityStatus::StoredPetIdMissing:
            return "validation_active_hunter_pet_observation_stored_pet_id_missing";
        case PersistentIdentityStatus::StoredEntryMissing:
            return "validation_active_hunter_pet_observation_stored_entry_missing";
        case PersistentIdentityStatus::PetIdMismatch:
            return "validation_active_hunter_pet_observation_pet_id_mismatch";
        case PersistentIdentityStatus::PetEntryMismatch:
            return "validation_active_hunter_pet_observation_pet_entry_mismatch";
        case PersistentIdentityStatus::Observed:
            return "";
    }
    return "validation_active_hunter_pet_observation_status_unknown";
}

FrozenReceiptStatus ClassifyFrozenReceipt(
    FrozenReceiptComparison const& comparison)
{
    if (!comparison.PetIdMatches)
        return FrozenReceiptStatus::PetIdMismatch;
    if (!comparison.PetEntryMatches)
        return FrozenReceiptStatus::PetEntryMismatch;
    if (!comparison.OwnerMatches)
        return FrozenReceiptStatus::OwnerMismatch;
    if (!comparison.SpellCountMatches)
        return FrozenReceiptStatus::SpellCountMismatch;
    if (!comparison.SpellbookMatches)
        return FrozenReceiptStatus::SpellbookMismatch;
    if (!comparison.SpellbookDigestMatches)
        return FrozenReceiptStatus::SpellbookDigestMismatch;
    if (!comparison.AutocastMatches)
        return FrozenReceiptStatus::AutocastMismatch;
    return FrozenReceiptStatus::Matches;
}

char const* FrozenReceiptFailureReason(FrozenReceiptStatus status)
{
    switch (status)
    {
        case FrozenReceiptStatus::PetIdMismatch:
            return "validation_active_hunter_pet_receipt_pet_id_mismatch";
        case FrozenReceiptStatus::PetEntryMismatch:
            return "validation_active_hunter_pet_receipt_pet_entry_mismatch";
        case FrozenReceiptStatus::OwnerMismatch:
            return "validation_active_hunter_pet_receipt_owner_mismatch";
        case FrozenReceiptStatus::SpellCountMismatch:
            return "validation_active_hunter_pet_receipt_spell_count_mismatch";
        case FrozenReceiptStatus::SpellbookMismatch:
            return "validation_active_hunter_pet_receipt_spellbook_mismatch";
        case FrozenReceiptStatus::SpellbookDigestMismatch:
            return "validation_active_hunter_pet_receipt_spellbook_digest_mismatch";
        case FrozenReceiptStatus::AutocastMismatch:
            return "validation_active_hunter_pet_receipt_autocast_mismatch";
        case FrozenReceiptStatus::Matches:
            return "";
    }
    return "validation_active_hunter_pet_receipt_status_unknown";
}
}
