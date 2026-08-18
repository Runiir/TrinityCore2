#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotActionExecutor.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Cryptography/CryptoHash.h"
#include "Entities/Item/Item.h"
#include "Entities/Item/ItemTemplate.h"
#include "GameTime.h"
#include "ObjectMgr.h"
#include "Pet.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <string>
#include <vector>

namespace
{
struct OrdinaryPetSpellIdentity
{
    uint32 SpellId = 0;
    uint8 Active = 0;
    uint8 Type = 0;
};

struct OrdinaryPetSetupSnapshot
{
    bool Present = false;
    bool InWorld = false;
    bool Alive = false;
    bool Owned = false;
    bool Permanent = false;
    ObjectGuid Guid;
    uint32 Entry = 0;
    uint32 FamilyId = 0;
    uint32 PetType = uint32(MAX_PET_TYPE);
    uint32 CreatedBySpellId = 0;
    uint32 Health = 0;
    uint32 MaxHealth = 0;
    uint32 PowerType = 0;
    uint32 Power = 0;
    uint32 MaxPower = 0;
    std::vector<OrdinaryPetSpellIdentity> Spellbook;
    std::string SpellbookSha256;
    std::vector<uint32> AutocastSpellIds;
};

std::string OrdinaryPetSpellbookSha256(
    std::vector<OrdinaryPetSpellIdentity> const& spellbook)
{
    std::ostringstream canonical;
    for (size_t index = 0; index < spellbook.size(); ++index)
    {
        if (index)
            canonical << ';';
        OrdinaryPetSpellIdentity const& spell = spellbook[index];
        canonical << spell.SpellId << ':' << uint32(spell.Active)
                  << ':' << uint32(spell.Type);
    }
    std::string digest = ByteArrayToHexStr(
        Trinity::Crypto::SHA256::GetDigestOf(canonical.str()));
    std::transform(digest.begin(), digest.end(), digest.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });
    return digest;
}

OrdinaryPetSetupSnapshot ObserveOrdinaryPetSetup(Player const* bot)
{
    OrdinaryPetSetupSnapshot snapshot;
    if (!bot)
        return snapshot;

    Pet* pet = bot->GetPet();
    if (!pet)
        return snapshot;

    snapshot.Present = true;
    snapshot.InWorld = pet->IsInWorld();
    snapshot.Alive = pet->IsAlive();
    snapshot.Owned = pet->GetOwner() == bot;
    snapshot.Permanent = pet->IsPermanentPetFor(const_cast<Player*>(bot))
        && !pet->isTemporarySummoned()
        && (pet->getPetType() == SUMMON_PET
            || pet->getPetType() == HUNTER_PET);
    snapshot.Guid = pet->GetGUID();
    snapshot.Entry = pet->GetEntry();
    snapshot.FamilyId = pet->GetCreatureTemplate()
        ? uint32(pet->GetCreatureTemplate()->family) : 0;
    snapshot.PetType = uint32(pet->getPetType());
    snapshot.CreatedBySpellId = pet->GetUInt32Value(UNIT_CREATED_BY_SPELL);
    snapshot.Health = pet->GetHealth();
    snapshot.MaxHealth = pet->GetMaxHealth();
    Powers const powerType = pet->GetPowerType();
    snapshot.PowerType = uint32(powerType);
    snapshot.Power = pet->GetPower(powerType);
    snapshot.MaxPower = pet->GetMaxPower(powerType);
    for (auto const& [spellId, petSpell] : pet->m_spells)
        if (petSpell.state != PETSPELL_REMOVED)
            snapshot.Spellbook.push_back({ spellId, uint8(petSpell.active),
                uint8(petSpell.type) });
    std::sort(snapshot.Spellbook.begin(), snapshot.Spellbook.end(),
        [](OrdinaryPetSpellIdentity const& left,
            OrdinaryPetSpellIdentity const& right)
        {
            if (left.SpellId != right.SpellId)
                return left.SpellId < right.SpellId;
            if (left.Active != right.Active)
                return left.Active < right.Active;
            return left.Type < right.Type;
        });
    snapshot.SpellbookSha256 = OrdinaryPetSpellbookSha256(
        snapshot.Spellbook);
    snapshot.AutocastSpellIds.assign(
        pet->m_autospells.begin(), pet->m_autospells.end());
    std::sort(snapshot.AutocastSpellIds.begin(),
        snapshot.AutocastSpellIds.end());
    snapshot.AutocastSpellIds.erase(std::unique(
        snapshot.AutocastSpellIds.begin(), snapshot.AutocastSpellIds.end()),
        snapshot.AutocastSpellIds.end());
    return snapshot;
}

bool OrdinaryPersistentPetMatches(OrdinaryPetSetupSnapshot const& snapshot,
    uint32 expectedEntry, uint32 expectedFamilyId, uint32 expectedPetType,
    uint32 expectedPowerType, uint32 expectedCreatedBySpellId)
{
    return snapshot.Present && snapshot.InWorld && snapshot.Alive
        && snapshot.Owned && snapshot.Permanent
        && snapshot.Entry == expectedEntry
        && snapshot.FamilyId == expectedFamilyId
        && snapshot.PetType == expectedPetType
        && snapshot.PowerType == expectedPowerType
        && snapshot.CreatedBySpellId == expectedCreatedBySpellId
        && snapshot.Health > 0 && snapshot.MaxHealth > 0
        && snapshot.MaxPower > 0 && !snapshot.Spellbook.empty()
        && snapshot.SpellbookSha256.size() == 64;
}


uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

bool BotWorldPopulationMgr::IsNativePoisonSetupReady(Player const* bot,
    WorldBotState::NativePoisonSetupReceipt const& receipt) const
{
    constexpr uint32 PoisonRefreshThresholdMs = 900000;
    Item const* weapon = bot ? bot->GetItemByPos(INVENTORY_SLOT_BAG_0,
        receipt.EquipmentSlot) : nullptr;
    ItemTemplate const* weaponTemplate = weapon
        ? weapon->GetTemplate() : nullptr;
    return weaponTemplate
        && weaponTemplate->GetClass() == ITEM_CLASS_WEAPON
        && receipt.ItemAvailable && receipt.SpellAvailable
        && receipt.NativeUseSubmittedAtMs
        && receipt.NativeUseFinishedSuccessfully
        && receipt.NativeUseFinishedAtMs >= receipt.NativeUseSubmittedAtMs
        && receipt.NativeUseFinishedItemGuid == receipt.SubmittedItemGuid
        && receipt.NativeUseFinishedWeaponGuid == receipt.SubmittedWeaponGuid
        && receipt.SubmittedWeaponGuid == weapon->GetGUID()
        && receipt.ObservedWeaponGuid == weapon->GetGUID()
        && receipt.ObservedWeaponGuid == receipt.SubmittedWeaponGuid
        && receipt.EnchantObservedAtMs >= receipt.NativeUseFinishedAtMs
        && weapon->GetEnchantmentId(TEMP_ENCHANTMENT_SLOT)
            == receipt.RequiredEnchantId
        && weapon->GetEnchantmentDuration(TEMP_ENCHANTMENT_SLOT)
            >= PoisonRefreshThresholdMs;
}

bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup(WorldBotState& state, Player* bot, Unit* target,
    char const* specTagOverride)
{
    if (!bot || !bot->IsAlive())
        return false;

    std::string const role = GetDungeonRole(bot);
    BotClassSpecActionProfile const profile = specTagOverride && *specTagOverride
        ? BotClassSpecActionProfileStore::BuildForSpec(
            bot, role.c_str(), specTagOverride)
        : BotClassSpecActionProfileStore::Build(bot, role.c_str());
    bool const unholyPresenceSetup = role == "dps"
        && (profile.SpecTag == "frost_death_knight"
            || profile.SpecTag == "unholy_death_knight");
    state.RequiredPresenceSetupSpellId = unholyPresenceSetup ? 48265 : 0;
    state.RequiredPresenceSetupAuraId = unholyPresenceSetup ? 48265 : 0;
    state.RequiredPresenceSetupSpellKnown = unholyPresenceSetup
        && bot->HasSpell(48265);
    if (!unholyPresenceSetup)
    {
        state.PresenceSetupNativeCastSubmittedAtMs = 0;
        state.PresenceSetupAuraObservedAtMs = 0;
    }

    // The pinned source setup uses ordinary permanent pets: Felhunter for
    // Affliction, Felguard for Demonology, and the Master-of-Ghouls Raise Dead
    // pet for Unholy. Submit the learned player spell and wait for native
    // finish plus a later complete live-pet observation. Never manufacture,
    // teach, replace, heal, or refill the pet here.
    WorldBotState::NativePersistentPetSetupReceipt requiredPet;
    char const* requiredPetName = nullptr;
    if (!ConfigureAfflictionPetRequirements(requiredPet, requiredPetName,
        role, profile.SpecTag))
    {
        if (role == "dps" && profile.SpecTag == "demonology_warlock")
        {
            requiredPet.RequiredSummonSpellId = 30146; // Summon Felguard
            requiredPet.RequiredCreatedBySpellId = 30146;
            requiredPet.RequiredEntry = ENTRY_FELGUARD;
            requiredPet.RequiredFamilyId = CREATURE_FAMILY_FELGUARD;
            requiredPet.RequiredPetType = uint32(SUMMON_PET);
            requiredPet.RequiredPowerType = uint32(POWER_MANA);
            requiredPetName = "summon_felguard";
        }
        else if (role == "dps" && profile.SpecTag == "unholy_death_knight")
        {
            requiredPet.RequiredSummonSpellId = 46584; // Raise Dead
            requiredPet.RequiredEntry = ENTRY_GHOUL;
            requiredPet.RequiredFamilyId = sObjectMgr->GetCreatureTemplate(
                ENTRY_GHOUL) ? uint32(sObjectMgr->GetCreatureTemplate(
                ENTRY_GHOUL)->family) : uint32(CREATURE_FAMILY_NONE);
            requiredPet.RequiredPetType = uint32(SUMMON_PET);
            requiredPet.RequiredPowerType = uint32(POWER_ENERGY);
            if (SpellInfo const* raiseDead = sSpellMgr->GetSpellInfo(46584))
                requiredPet.RequiredCreatedBySpellId = uint32(std::max<int32>(
                    0, raiseDead->Effects[EFFECT_1].CalcValue(bot)));
            requiredPetName = "raise_dead_permanent_ghoul";
        }
    }
    WorldBotState::NativePersistentPetSetupReceipt& petSetup =
        state.PersistentPetSetup;
    bool const petRequirementChanged =
        petSetup.RequiredSummonSpellId != requiredPet.RequiredSummonSpellId
        || petSetup.RequiredCreatedBySpellId
            != requiredPet.RequiredCreatedBySpellId
        || petSetup.RequiredEntry != requiredPet.RequiredEntry
        || petSetup.RequiredFamilyId != requiredPet.RequiredFamilyId
        || petSetup.RequiredPetType != requiredPet.RequiredPetType
        || petSetup.RequiredPowerType != requiredPet.RequiredPowerType;
    if (petRequirementChanged)
        petSetup = {};
    petSetup.RequiredSummonSpellId = requiredPet.RequiredSummonSpellId;
    petSetup.RequiredCreatedBySpellId = requiredPet.RequiredCreatedBySpellId;
    petSetup.RequiredEntry = requiredPet.RequiredEntry;
    petSetup.RequiredFamilyId = requiredPet.RequiredFamilyId;
    petSetup.RequiredPetType = requiredPet.RequiredPetType;
    petSetup.RequiredPowerType = requiredPet.RequiredPowerType;
    petSetup.SummonSpellKnown = petSetup.RequiredSummonSpellId
        && bot->HasSpell(petSetup.RequiredSummonSpellId);

    // Poison receipts are a calibration pre-score contract. A normal dungeon
    // party may legitimately arrive with no consumable stack in the generated
    // roster; do not hold its rogue in persistent setup forever. Calibration
    // still remains fail-closed and requires the native item-use/finish/live
    // enchant evidence before the scored window opens.
    bool const roguePoisonSetup = Cohort().CalibrationActive && role == "dps"
        && (profile.SpecTag == "assassination_rogue"
            || profile.SpecTag == "combat_rogue");
    state.RoguePoisonSetupRequired = roguePoisonSetup;
    auto configurePoisonRequirement = [](WorldBotState::NativePoisonSetupReceipt& receipt,
        uint8 equipmentSlot, uint32 itemEntry, uint32 spellId,
        uint32 enchantId)
    {
        bool const changed = receipt.EquipmentSlot != equipmentSlot
            || receipt.RequiredItemEntry != itemEntry
            || receipt.RequiredSpellId != spellId
            || receipt.RequiredEnchantId != enchantId;
        if (changed)
            receipt = {};
        receipt.EquipmentSlot = equipmentSlot;
        receipt.RequiredItemEntry = itemEntry;
        receipt.RequiredSpellId = spellId;
        receipt.RequiredEnchantId = enchantId;
    };
    if (roguePoisonSetup)
    {
        // Both pinned WoWSims Assassination and Combat primary fixtures use
        // Deadly on main hand and Instant on off hand. Item, spell, and
        // resulting enchant identities come from the Cataclysm DBCs.
        configurePoisonRequirement(state.RogueMainhandPoisonSetup,
            EQUIPMENT_SLOT_MAINHAND, 43233, 2823, 7);
        configurePoisonRequirement(state.RogueOffhandPoisonSetup,
            EQUIPMENT_SLOT_OFFHAND, 43231, 8679, 323);
    }
    else
    {
        state.RogueMainhandPoisonSetup = {};
        state.RogueOffhandPoisonSetup = {};
    }
    struct SelfBuff
    {
        uint8 ClassId;
        char const* Role;
        char const* SpecTag;
        uint32 SpellId;
        uint32 AuraId;
        uint32 AlternateAuraId;
        char const* Name;
    };
    static SelfBuff const buffs[] =
    {
        { CLASS_WARRIOR, "tank", "protection_warrior", 71, 71, 0, "defensive_stance" },
        { CLASS_WARRIOR, "dps", "arms_warrior", 2457, 2457, 0, "battle_stance" },
        { CLASS_WARRIOR, "dps", "fury_warrior", 2458, 2458, 0, "berserker_stance" },
        { CLASS_PALADIN, "tank", nullptr, 25780, 25780, 0, "righteous_fury" },
        { CLASS_PALADIN, "tank", nullptr, 31801, 31801, 0, "seal_of_truth" },
        { CLASS_PALADIN, "tank", nullptr, 465, 465, 0, "devotion_aura" },
        { CLASS_DEATH_KNIGHT, "tank", "blood_death_knight", 48263, 48263, 0, "blood_presence" },
        { CLASS_DEATH_KNIGHT, "dps", "frost_death_knight", 48265, 48265, 0, "unholy_presence" },
        { CLASS_DEATH_KNIGHT, "dps", "unholy_death_knight", 48265, 48265, 0, "unholy_presence" },
        { CLASS_DRUID, "tank", "feral_druid_tank", 5487, 5487, 0, "bear_form" },
        { CLASS_DRUID, "dps", "feral_druid_dps", 768, 768, 0, "cat_form" },
        { CLASS_DRUID, "dps", "balance_druid", 24858, 24858, 0, "moonkin_form" },
        { CLASS_PALADIN, nullptr, nullptr, 20217, 20217, 79063, "blessing_of_kings" },
        { CLASS_MAGE, nullptr, nullptr, 1459, 1459, 79058, "arcane_brilliance" },
        { CLASS_MAGE, nullptr, nullptr, 30482, 30482, 6117, "class_armor" },
        { CLASS_HUNTER, nullptr, nullptr, 13165, 13165, 0, "aspect_of_the_hawk" },
        { CLASS_WARLOCK, nullptr, nullptr, 28176, 28176, 0, "fel_armor" },
        { CLASS_SHAMAN, "healer", nullptr, 52127, 52127, 0, "water_shield" },
        { CLASS_SHAMAN, "dps", nullptr, 324, 324, 0, "lightning_shield" },
    };

    for (SelfBuff const& buff : buffs)
    {
        if (buff.ClassId != bot->getClass() || (buff.Role && role != buff.Role)
            || (buff.SpecTag && profile.SpecTag != buff.SpecTag))
            continue;

        bool const trackedPresence = unholyPresenceSetup && buff.SpellId == 48265;
        bool const auraActive = bot->HasAura(buff.AuraId)
            || (buff.AlternateAuraId && bot->HasAura(buff.AlternateAuraId));
        if (auraActive && (!trackedPresence || state.PresenceSetupNativeCastSubmittedAtMs))
        {
            // A submitted receipt and the later native aura observation are
            // separate facts.  This never creates or refreshes the aura.
            if (trackedPresence
                && state.PresenceSetupAuraObservedAtMs < state.PresenceSetupNativeCastSubmittedAtMs)
                state.PresenceSetupAuraObservedAtMs = NowMs();
            continue;
        }
        if (!bot->HasSpell(buff.SpellId))
        {
            std::string blocker = std::string("persistent_setup_spell_missing:") + std::to_string(buff.SpellId);
            ObserveBotCandidateFailure(state, bot,
                "world.setup.self_buff:" + std::to_string(buff.SpellId), blocker);
            continue;
        }

        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(buff.SpellId);
        if (!spellInfo || bot->HasUnitState(UNIT_STATE_CASTING)
            || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo) || !bot->GetSpellHistory()->IsReady(spellInfo))
            return true;

        ResolvedCombatAction action;
        action.Valid = true;
        action.Type = "cast";
        action.SpellId = buff.SpellId;
        action.TargetGuid = bot->GetGUID();
        action.DebugName = buff.Name;
        BotActionExecutor executor;
        BotActionResult const result = executor.ExecuteCombat(bot, bot, action);
        if (result == BotActionResult::Ok)
        {
            if (trackedPresence)
            {
                state.PresenceSetupNativeCastSubmittedAtMs = NowMs();
                state.PresenceSetupAuraObservedAtMs = 0;
            }
            RecordCombatAttempt(state, bot, bot, "persistent_setup", &action, result, buff.Name);
            return true;
        }
        RecordCombatAttempt(state, bot, bot, "persistent_setup", &action, result,
            "self_buff_native_submission_pending_or_rejected");
        return true;
    }

    if (petSetup.RequiredSummonSpellId)
    {
        uint64 const nowMs = NowMs();
        OrdinaryPetSetupSnapshot const observedPet =
            ObserveOrdinaryPetSetup(bot);
        bool const exactPetObserved = OrdinaryPersistentPetMatches(
            observedPet, petSetup.RequiredEntry,
            petSetup.RequiredFamilyId, petSetup.RequiredPetType,
            petSetup.RequiredPowerType,
            petSetup.RequiredCreatedBySpellId);
        bool const nativeCastFinished =
            petSetup.NativeCastSubmittedAtMs
            && petSetup.NativeCastFinishedSuccessfully
            && petSetup.NativeCastFinishedAtMs
                >= petSetup.NativeCastSubmittedAtMs;
        if (nativeCastFinished && exactPetObserved)
        {
            if (petSetup.NativeCastObservedAtMs
                < petSetup.NativeCastFinishedAtMs)
                petSetup.NativeCastObservedAtMs = nowMs;
            TryResolveBotBlocker(state, bot,
                "persistent_native_pet_setup_ready");
            return false;
        }

        // Do not cast a summon onto the same already-live permanent pet merely
        // to fabricate this run's receipt. Core summon handling can heal and
        // refill an existing summon; a fixture must begin without that pet or
        // retain the real receipt from the cast that created it.
        bool const allowPreexistingAfflictionPet =
            Cohort().CalibrationActive
            && Cohort().CalibrationTargetSpec == "affliction_warlock"
            && profile.SpecTag == "affliction_warlock"
            && petSetup.RequiredSummonSpellId == 691
            && petSetup.RequiredCreatedBySpellId == 691
            && petSetup.RequiredEntry == ENTRY_FELHUNTER
            && petSetup.SummonSpellKnown;
        if (exactPetObserved && !petSetup.NativeCastSubmittedAtMs
            && allowPreexistingAfflictionPet)
        {
            // Calibration may start from an already loaded ordinary Felhunter.
            // Its complete live identity is the only accepted evidence here;
            // never synthesize a native cast receipt or mutate the pet.
            TryResolveBotBlocker(state, bot,
                "persistent_preexisting_affliction_pet_observed");
            state.LastRecoveryMode.clear();
            state.LastRecoveryResult.clear();
            state.LastNoProgressReason.clear();
            return false;
        }
        if (exactPetObserved && !petSetup.NativeCastSubmittedAtMs)
        {
            ObserveBotCandidateFailure(state, bot,
                "world.setup.native_pet:" + std::to_string(
                    petSetup.RequiredSummonSpellId),
                "persistent_setup_preexisting_pet_without_native_receipt",
                1000, 15000, 3, 15000);
            return true;
        }

        // A submitted cast owns setup until the native finish callback. A
        // successful finish gets a short observation window for the pet to
        // enter the map; after that, retry the same legal spell rather than
        // inventing a replacement.
        if (petSetup.NativeCastSubmittedAtMs
            && !petSetup.NativeCastFinishedAtMs)
            return true;
        if (nativeCastFinished && !exactPetObserved
            && nowMs - petSetup.NativeCastFinishedAtMs < 3000)
            return true;

        std::string const attemptKey =
            "persistent_setup:native_pet:"
            + std::to_string(petSetup.RequiredSummonSpellId);
        auto retryItr = state.ReadinessRetryUntilMs.find(attemptKey);
        if (retryItr != state.ReadinessRetryUntilMs.end())
        {
            if (retryItr->second > nowMs)
                return true;
            state.ReadinessRetryUntilMs.erase(retryItr);
        }
        if (profile.SpecTag == "unholy_death_knight"
            && !bot->HasAura(52143))
        {
            ObserveBotCandidateFailure(state, bot,
                "world.setup.native_pet:46584",
                "persistent_setup_unholy_master_of_ghouls_missing:52143",
                1000, 15000, 3, 15000);
            return true;
        }
        if (!petSetup.RequiredCreatedBySpellId)
        {
            ObserveBotCandidateFailure(state, bot,
                "world.setup.native_pet:" + std::to_string(
                    petSetup.RequiredSummonSpellId),
                "persistent_setup_native_pet_created_by_spell_missing",
                1000, 15000, 3, 15000);
            return true;
        }
        if (!petSetup.SummonSpellKnown)
        {
            std::string const blocker =
                "persistent_setup_spell_missing:"
                + std::to_string(petSetup.RequiredSummonSpellId);
            ObserveBotCandidateFailure(state, bot,
                "world.setup.native_pet:" + std::to_string(
                    petSetup.RequiredSummonSpellId), blocker,
                1000, 15000, 3, 15000);
            return true;
        }

        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(
            petSetup.RequiredSummonSpellId);
        if (!spellInfo)
        {
            std::string const blocker =
                "persistent_setup_spell_info_missing:"
                + std::to_string(petSetup.RequiredSummonSpellId);
            ObserveBotCandidateFailure(state, bot,
                "world.setup.native_pet:" + std::to_string(
                    petSetup.RequiredSummonSpellId), blocker,
                1000, 15000, 3, 15000);
            return true;
        }
        if (bot->HasUnitState(UNIT_STATE_CASTING)
            || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo)
            || !bot->GetSpellHistory()->IsReady(spellInfo))
            return true;

        ResolvedBotAction nativeAction;
        nativeAction.TargetGuid = bot->GetGUID();
        nativeAction.SpellId = petSetup.RequiredSummonSpellId;
        nativeAction.DebugName = requiredPetName;
        BotActionExecutor executor;
        // Publish the pending identity before CastSpell: an instant cast-time
        // modifier can make Spell::finish run synchronously inside the native
        // executor. A rejected submission clears these provisional fields
        // immediately below and is never reported as submitted evidence.
        petSetup.NativeCastSubmittedAtMs = nowMs;
        petSetup.NativeCastFinishedAtMs = 0;
        petSetup.NativeCastFinishedSuccessfully = false;
        petSetup.NativeCastObservedAtMs = 0;
        BotActionResult const result = executor.Execute(
            bot, bot, nativeAction);

        ResolvedCombatAction telemetryAction;
        telemetryAction.Valid = true;
        telemetryAction.Type = "cast";
        telemetryAction.SpellId = petSetup.RequiredSummonSpellId;
        telemetryAction.TargetGuid = bot->GetGUID();
        telemetryAction.DebugName = requiredPetName;
        if (result == BotActionResult::Ok)
        {
            state.ReadinessRetryUntilMs.erase(attemptKey);
            RecordCombatAttempt(state, bot, bot, "persistent_setup",
                &telemetryAction, result, requiredPetName);
            return true;
        }

        petSetup.NativeCastSubmittedAtMs = 0;
        petSetup.NativeCastFinishedAtMs = 0;
        petSetup.NativeCastFinishedSuccessfully = false;
        petSetup.NativeCastObservedAtMs = 0;
        state.ReadinessRetryUntilMs[attemptKey] = nowMs + 1500;
        std::string const reason = "persistent_pet_native_submission_"
            + std::string(ToString(result));
        ObserveBotCandidateFailure(state, bot,
            "world.setup.native_pet:" + std::to_string(
                petSetup.RequiredSummonSpellId), reason,
            1000, 15000, 3, 15000);
        RecordCombatAttempt(state, bot, bot, "persistent_setup",
            &telemetryAction, result, reason.c_str());
        return true;
    }

    // Mana Gem creation is optional consumable preparation, not a combat
    // prerequisite.  Once a pull has started, a missing/consumed gem must not
    // re-enter persistent setup and suppress the mage's ordinary rotation on
    // every decision tick.  The profile's normal use-item action remains
    // authoritative when a real gem is present.
    if (bot->getClass() == CLASS_MAGE && !bot->IsInCombat())
    {
        bool manaGemEnabled = std::any_of(profile.Spells.begin(), profile.Spells.end(), [](BotActionProfileSpell const& spell)
        {
            return spell.Category == BotCombatActionCategory::UseItem && spell.SpellId == 5405;
        });
        if (manaGemEnabled && !bot->GetItemByEntry(36799))
        {
            constexpr uint32 ConjureManaGemSpellId = 759;
            if (!bot->HasSpell(ConjureManaGemSpellId))
            {
                ObserveBotCandidateFailure(state, bot,
                    "world.setup.conjure_mana_gem",
                    "persistent_setup_spell_missing:759");
                return true;
            }

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(ConjureManaGemSpellId);
            if (!spellInfo || bot->HasUnitState(UNIT_STATE_CASTING)
                || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo)
                || !bot->GetSpellHistory()->IsReady(spellInfo))
                return true;

            ResolvedCombatAction action;
            action.Valid = true;
            action.Type = "cast";
            action.SpellId = ConjureManaGemSpellId;
            action.TargetGuid = bot->GetGUID();
            action.DebugName = "conjure_mana_gem";
            BotActionResult result = bot->CastSpell(bot, ConjureManaGemSpellId, false) == SPELL_CAST_OK
                ? BotActionResult::Ok : BotActionResult::CastFailed;
            RecordCombatAttempt(state, bot, bot, "persistent_setup", &action, result,
                result == BotActionResult::Ok ? "conjure_mana_gem" : "conjure_mana_gem_failed");
            return true;
        }
    }

    if (bot->getClass() == CLASS_SHAMAN)
    {
        auto ensureWeaponImbue = [&](uint8 equipmentSlot, uint32 spellId, char const* name) -> bool
        {
            Item* weapon = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, equipmentSlot);
            ItemTemplate const* itemTemplate = weapon ? weapon->GetTemplate() : nullptr;
            if (!itemTemplate || itemTemplate->GetClass() != ITEM_CLASS_WEAPON)
                return false;
            if (!bot->HasSpell(spellId))
            {
                std::string blocker = std::string("persistent_setup_spell_missing:") + std::to_string(spellId);
                ObserveBotCandidateFailure(state, bot,
                    "world.setup.weapon_imbue:" + std::to_string(spellId), blocker);
                return false;
            }

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            uint32 desiredEnchantId = 0;
            if (spellInfo)
                for (SpellEffectInfo const& effect : spellInfo->Effects)
                    if (effect.Effect == SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY)
                    {
                        desiredEnchantId = uint32(effect.MiscValue);
                        break;
                    }
            if (!desiredEnchantId)
            {
                std::string blocker = std::string("persistent_setup_enchant_missing:") + std::to_string(spellId);
                ObserveBotCandidateFailure(state, bot,
                    "world.setup.weapon_enchant:" + std::to_string(spellId), blocker);
                return true;
            }

            uint32 const currentEnchantId = weapon->GetEnchantmentId(TEMP_ENCHANTMENT_SLOT);
            if (currentEnchantId == desiredEnchantId)
                return false;

            if (!spellInfo || bot->HasUnitState(UNIT_STATE_CASTING)
                || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo)
                || !bot->GetSpellHistory()->IsReady(spellInfo))
                return true;

            ResolvedCombatAction action;
            action.Valid = true;
            action.Type = "cast";
            action.SpellId = spellId;
            action.TargetGuid = bot->GetGUID();
            action.DebugName = name;
            SpellCastResult const castResult = bot->CastSpell(
                weapon, spellId, CastSpellExtraArgs(TRIGGERED_NONE));
            BotActionResult const result = castResult == SPELL_CAST_OK
                ? BotActionResult::Ok : BotActionResult::CastFailed;
            std::string const reason = result == BotActionResult::Ok
                ? name
                : "weapon_imbue_spell_cast_result_" + std::to_string(uint32(castResult));
            RecordCombatAttempt(state, bot, bot, "persistent_setup", &action, result, reason.c_str());
            return true;
        };

        bool const enhancement = profile.SpecTag == "enhancement"
            || profile.SpecTag == "enhancement_shaman";
        uint32 const mainhandImbueSpell = enhancement ? 8232 : 8024;
        char const* mainhandImbueName = enhancement ? "windfury_weapon" : "flametongue_weapon";
        if (ensureWeaponImbue(EQUIPMENT_SLOT_MAINHAND, mainhandImbueSpell, mainhandImbueName))
            return true;
        if (enhancement && ensureWeaponImbue(EQUIPMENT_SLOT_OFFHAND, 8024, "flametongue_weapon"))
            return true;
    }

    if (state.RoguePoisonSetupRequired)
    {
        constexpr uint32 PoisonRefreshThresholdMs = 900000;
        auto ensureWeaponPoison = [&](WorldBotState::NativePoisonSetupReceipt& receipt,
            char const* name) -> bool
        {
            uint64 const nowMs = NowMs();
            Item* weapon = bot->GetItemByPos(INVENTORY_SLOT_BAG_0,
                receipt.EquipmentSlot);
            ItemTemplate const* weaponTemplate = weapon
                ? weapon->GetTemplate() : nullptr;
            receipt.ObservedWeaponItemEntry = weapon ? weapon->GetEntry() : 0;
            receipt.ObservedWeaponGuid = weapon
                ? weapon->GetGUID() : ObjectGuid::Empty;
            receipt.ObservedEnchantId = weapon
                ? weapon->GetEnchantmentId(TEMP_ENCHANTMENT_SLOT) : 0;
            receipt.ObservedEnchantDurationMs = weapon
                ? weapon->GetEnchantmentDuration(TEMP_ENCHANTMENT_SLOT) : 0;

            Item* poisonItem = bot->GetItemByEntry(
                receipt.RequiredItemEntry);
            bool const itemCurrentlyAvailable = poisonItem
                && poisonItem->GetCount();
            // Availability is a submission receipt, not a requirement that a
            // consumable remain afterward. A one-count stack is ordinarily
            // destroyed by the native spell. If this enchant later needs a
            // refresh, the live check below still fails closed without a new
            // source item.
            receipt.ItemAvailable = receipt.ItemAvailable
                || itemCurrentlyAvailable;
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(
                receipt.RequiredSpellId);
            ItemTemplate const* poisonItemTemplate = poisonItem
                ? poisonItem->GetTemplate()
                : sObjectMgr->GetItemTemplate(receipt.RequiredItemEntry);
            bool itemDeclaresExactSpell = false;
            if (poisonItemTemplate)
                for (ItemEffect const& effect :
                    poisonItemTemplate->Effects)
                    if (effect.SpellID == int32(receipt.RequiredSpellId)
                        && effect.Trigger == ITEM_SPELLTRIGGER_ON_USE)
                    {
                        itemDeclaresExactSpell = true;
                        break;
                    }
            bool spellDeclaresExactEnchant = false;
            if (spellInfo)
                for (SpellEffectInfo const& effect : spellInfo->Effects)
                    if (effect.Effect
                            == SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY
                        && uint32(effect.MiscValue)
                            == receipt.RequiredEnchantId)
                    {
                        spellDeclaresExactEnchant = true;
                        break;
                    }
            receipt.SpellAvailable = itemDeclaresExactSpell
                && spellDeclaresExactEnchant;

            bool const receiptOwnsCurrentWeapon = weapon
                && receipt.NativeUseSubmittedAtMs
                && receipt.SubmittedWeaponGuid == weapon->GetGUID();
            bool const exactEnchantObserved = receiptOwnsCurrentWeapon
                && receipt.ObservedWeaponGuid
                    == receipt.SubmittedWeaponGuid
                && receipt.NativeUseFinishedSuccessfully
                && receipt.NativeUseFinishedAtMs
                    >= receipt.NativeUseSubmittedAtMs
                && receipt.NativeUseFinishedItemGuid
                    == receipt.SubmittedItemGuid
                && receipt.NativeUseFinishedWeaponGuid
                    == receipt.SubmittedWeaponGuid
                && receipt.ObservedEnchantId == receipt.RequiredEnchantId
                && receipt.ObservedEnchantDurationMs
                    >= PoisonRefreshThresholdMs;
            if (exactEnchantObserved)
            {
                if (receipt.EnchantObservedAtMs
                    < receipt.NativeUseFinishedAtMs)
                    receipt.EnchantObservedAtMs = nowMs;
                return false;
            }
            receipt.EnchantObservedAtMs = 0;

            if (!weaponTemplate
                || weaponTemplate->GetClass() != ITEM_CLASS_WEAPON)
            {
                std::string blocker = std::string("persistent_setup_weapon_missing:") + name;
                ObserveBotCandidateFailure(state, bot,
                    "world.setup.weapon_poison:" + std::string(name),
                    blocker, 1000, 15000, 3, 15000);
                return true;
            }
            if (!itemCurrentlyAvailable)
            {
                std::string const blocker =
                    "persistent_setup_poison_item_missing:"
                    + std::to_string(receipt.RequiredItemEntry);
                ObserveBotCandidateFailure(state, bot,
                    "world.setup.weapon_poison:" + std::string(name),
                    blocker, 1000, 15000, 3, 15000);
                return true;
            }
            if (!receipt.SpellAvailable)
            {
                std::string const blocker =
                    "persistent_setup_poison_spell_contract_missing:"
                    + std::to_string(receipt.RequiredSpellId);
                ObserveBotCandidateFailure(state, bot,
                    "world.setup.weapon_poison:" + std::string(name),
                    blocker, 1000, 15000, 3, 15000);
                return true;
            }
            if (receipt.NextNativeUseRetryAtMs > nowMs
                || bot->HasUnitState(UNIT_STATE_CASTING))
                return true;

            BotNativeAction::UseItem useItem;
            useItem.Item = poisonItem->GetGUID();
            useItem.Target = weapon->GetGUID();
            useItem.SpellId = receipt.RequiredSpellId;
            // Publish pending identity before entering WorldSession. A future
            // cast-time modifier may finish the native item spell
            // synchronously; the finish callback must still be able to bind
            // that exact request. Rejected submissions clear these fields.
            receipt.SubmittedItemGuid = useItem.Item;
            receipt.SubmittedWeaponGuid = useItem.Target;
            receipt.NativeUseSubmittedAtMs = nowMs;
            receipt.NativeUseFinishedAtMs = 0;
            receipt.NativeUseFinishedSuccessfully = false;
            receipt.NativeUseFinishedItemGuid.Clear();
            receipt.NativeUseFinishedWeaponGuid.Clear();
            receipt.EnchantObservedAtMs = 0;
            BotActionArbitration::Outcome const outcome =
                ExecuteNativeActionIntent(state, bot, useItem,
                    BotMovementArbitration::Owner::Support,
                    BotMovementArbitration::Priority::Support);

            ResolvedCombatAction telemetryAction;
            telemetryAction.Valid = true;
            telemetryAction.Type = "use_item";
            telemetryAction.SpellId = receipt.RequiredSpellId;
            telemetryAction.TargetGuid = bot->GetGUID();
            telemetryAction.DebugName = name;
            bool const submitted = outcome.Result
                    == BotActionArbitration::Disposition::Committed
                && outcome.LifecyclePhase
                    == BotActionArbitration::Phase::Submitted;
            if (submitted)
            {
                receipt.NextNativeUseRetryAtMs = nowMs + 5000;
                RecordCombatAttempt(state, bot, bot,
                    "persistent_setup", &telemetryAction,
                    BotActionResult::Ok, outcome.Reason.c_str());
                return true;
            }

            receipt.SubmittedItemGuid.Clear();
            receipt.SubmittedWeaponGuid.Clear();
            receipt.NativeUseSubmittedAtMs = 0;
            receipt.NativeUseFinishedAtMs = 0;
            receipt.NativeUseFinishedSuccessfully = false;
            receipt.NativeUseFinishedItemGuid.Clear();
            receipt.NativeUseFinishedWeaponGuid.Clear();
            receipt.EnchantObservedAtMs = 0;
            receipt.NextNativeUseRetryAtMs = nowMs + 1000;
            ObserveBotCandidateFailure(state, bot,
                "world.setup.weapon_poison:" + std::string(name),
                outcome.Reason, 1000, 15000, 3, 15000);
            RecordCombatAttempt(state, bot, bot, "persistent_setup",
                &telemetryAction, BotActionResult::CastFailed,
                outcome.Reason.c_str());
            return true;
        };

        if (ensureWeaponPoison(state.RogueMainhandPoisonSetup,
                "deadly_poison_mainhand"))
            return true;
        if (ensureWeaponPoison(state.RogueOffhandPoisonSetup,
                "instant_poison_offhand"))
            return true;
    }

    if (bot->getClass() == CLASS_HUNTER && target && target->IsAlive() && bot->HasSpell(1130)
        && !target->HasAura(1130, bot->GetGUID()))
    {
        std::string retryKey = "persistent_setup:hunters_mark:" + std::to_string(target->GetGUID().GetCounter());
        uint64 nowMs = NowMs();
        auto retryItr = state.ReadinessRetryUntilMs.find(retryKey);
        if (retryItr != state.ReadinessRetryUntilMs.end())
        {
            if (retryItr->second > nowMs)
                return false;
            state.ReadinessRetryUntilMs.erase(retryItr);
        }

        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(1130);
        if (!spellInfo || bot->HasUnitState(UNIT_STATE_CASTING)
            || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo) || !bot->GetSpellHistory()->IsReady(spellInfo))
            return true;

        ResolvedCombatAction action;
        action.Valid = true;
        action.Type = "cast";
        action.SpellId = 1130;
        action.TargetGuid = target->GetGUID();
        action.DebugName = "hunters_mark";
        SpellCastResult castResult = bot->CastSpell(target, 1130, false);
        BotActionResult result = castResult == SPELL_CAST_OK ? BotActionResult::Ok : BotActionResult::CastFailed;
        std::string resultReason = result == BotActionResult::Ok
            ? "hunters_mark"
            : "hunters_mark_spell_cast_result_" + std::to_string(uint32(castResult));
        if (result == BotActionResult::Ok)
            state.ReadinessRetryUntilMs.erase(retryKey);
        else
        {
            state.ReadinessRetryUntilMs[retryKey] = nowMs + 5000;
        }
        RecordCombatAttempt(state, bot, target, "persistent_setup", &action, result, resultReason.c_str());
        return true;
    }

    TryResolveBotBlocker(state, bot, "persistent_combat_setup_ready");
    return false;
}
