#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "DatabaseEnv.h"
#include "Object.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Server/Packets/QuestPackets.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Totem.h"
#include "Unit.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrNativeHelpers
{
bool IsNativeCombatResSpell(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    // The Cataclysm DBC exposes Rebirth as learned base spell 20484, but its
    // effect row is not tagged with the generic combat-resurrection attribute.
    // The caller still requires this exact spell to be present in the owner's
    // native spell map and applies the normal range/LOS/path/cooldown/power
    // gates; this branch only preserves the immutable DBC identity.
    if (spellInfo->Id == 20484)
        return true;

    bool const isResurrect = spellInfo->HasEffect(SPELL_EFFECT_RESURRECT)
        || spellInfo->HasEffect(SPELL_EFFECT_RESURRECT_NEW)
        || spellInfo->HasEffect(SPELL_EFFECT_RESURRECT_WITH_AURA);
    return isResurrect && spellInfo->HasAttribute(SPELL_ATTR8_ENFORCE_IN_COMBAT_RESSURECTION_LIMIT);
}

bool IsNativeCombatObserved(Player const* bot, Unit const* target)
{
    if (!bot || !target)
        return false;

    // These are the same postconditions visible to an ordinary client. Merely
    // selecting a target or submitting Attack/CastSpell is intent, not proof
    // that combat started or that the target made health progress.
    return bot->IsInCombat() || target->IsInCombat();
}

bool SubmitNativeQuestAccept(Player* bot, WorldObject* giver, uint32 questId)
{
    if (!bot || !giver || !questId || !bot->GetSession()
        || !bot->IsWithinDistInMap(giver, INTERACTION_DISTANCE))
        return false;

    WorldPackets::Quest::QuestGiverAcceptQuest packet(
        WorldPacket(CMSG_QUEST_GIVER_ACCEPT_QUEST, 0));
    packet.QuestGiverGUID = giver->GetGUID();
    packet.QuestID = questId;
    packet.StartCheat = 0;
    bot->GetSession()->HandleQuestgiverAcceptQuestOpcode(packet);
    QuestStatus const status = bot->GetQuestStatus(questId);
    return status == QUEST_STATUS_INCOMPLETE || status == QUEST_STATUS_COMPLETE;
}

bool SubmitNativeQuestReward(Player* bot, WorldObject* giver, uint32 questId, uint32 rewardChoice)
{
    if (!bot || !giver || !questId || !bot->GetSession()
        || !bot->IsWithinDistInMap(giver, INTERACTION_DISTANCE))
        return false;

    WorldPackets::Quest::QuestGiverChooseReward packet(
        WorldPacket(CMSG_QUEST_GIVER_CHOOSE_REWARD, 0));
    packet.QuestGiverGUID = giver->GetGUID();
    packet.QuestID = int32(questId);
    packet.ItemChoiceID = int32(rewardChoice);
    bot->GetSession()->HandleQuestgiverChooseRewardOpcode(packet);
    return bot->GetQuestStatus(questId) != QUEST_STATUS_COMPLETE;
}

uint64 ReadLastInsertId()
{
    if (QueryResult result = CharacterDatabase.Query("SELECT LAST_INSERT_ID()"))
        return result->Fetch()[0].GetUInt64();

    return 0;
}

float Distance2d(float ax, float ay, float bx, float by)
{
    float dx = ax - bx;
    float dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}

bool UsesRangedAoeCalibrationLane(std::string const& spec)
{
    static constexpr std::array<char const*, 12> RangedAoeSpecs =
    {
        "balance_druid", "beast_mastery_hunter", "marksmanship_hunter", "survival_hunter",
        "shadow_priest", "elemental_shaman", "arcane_mage", "fire_mage", "frost_mage",
        "affliction_warlock", "demonology_warlock", "destruction_warlock"
    };
    return std::find(RangedAoeSpecs.begin(), RangedAoeSpecs.end(), spec) != RangedAoeSpecs.end();
}

float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;

    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}

bool HasPowerForSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > powerCost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(powerCost);
}

uint32 ControlledDispelAuraForHealer(Player const* healer)
{
    // Nature's Cure reliably removes curses without depending on the optional
    // Restoration magic-dispel talent. The other healer profiles use their
    // native hostile-magic dispel against Shadow Word: Pain.
    return healer && healer->getClass() == CLASS_DRUID ? 702 : 589;
}

Player* CombatOwnerPlayer(Unit* unit)
{
    if (!unit)
        return nullptr;

    if (Player* player = unit->GetCharmerOrOwnerPlayerOrPlayerItself())
        return player;

    // Resolve nested summon ownership (for example elemental -> totem ->
    // player). The generic helper only checks one owner GUID level.
    Unit* current = unit;
    for (uint8 depth = 0; depth < 4 && current; ++depth)
    {
        current = current->IsTotem() ? current->ToTotem()->GetOwner() : current->GetCharmerOrOwner();
        if (!current)
            break;
        if (Player* player = current->ToPlayer())
            return player;
    }

    return nullptr;
}

bool CancelRemovableShapeshifts(Player* bot)
{
    if (!bot)
        return false;

    Unit::AuraEffectList const& shapeshiftAuras = bot->GetAuraEffectsByType(SPELL_AURA_MOD_SHAPESHIFT);
    std::vector<Aura*> removable;
    for (AuraEffect* effect : shapeshiftAuras)
    {
        Aura* aura = effect ? effect->GetBase() : nullptr;
        SpellInfo const* auraInfo = aura ? aura->GetSpellInfo() : nullptr;
        if (!auraInfo || auraInfo->HasAttribute(SPELL_ATTR0_NO_AURA_CANCEL)
            || !auraInfo->IsPositive() || auraInfo->IsPassive())
            continue;
        if (std::find(removable.begin(), removable.end(), aura) == removable.end())
            removable.push_back(aura);
    }

    for (Aura* aura : removable)
        bot->RemoveOwnedAura(aura, AuraRemoveFlags::ByCancel);
    return !removable.empty();
}

bool MaintainedProfileAuraBlocksRefresh(Unit const* target, BotActionProfileSpell const& spell)
{
    Aura const* aura = target && spell.MaintainAuraId ? target->GetAura(spell.MaintainAuraId) : nullptr;
    if (!aura)
        return false;
    int32 durationMs = aura->GetDuration();
    return !spell.RefreshAuraBelowMs || durationMs < 0 || uint32(durationMs) > spell.RefreshAuraBelowMs;
}
}
