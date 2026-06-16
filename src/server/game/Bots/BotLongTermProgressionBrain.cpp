#include "Bots/BotLongTermProgressionBrain.h"
#include "DataStores/DBCEnums.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Entities/Item/ItemTemplate.h"
#include "Player.h"
#include <algorithm>

namespace
{
float GetProgressionStatWeight(uint8 classId, uint32 statType)
{
    switch (classId)
    {
        case CLASS_WARRIOR:
        case CLASS_DEATH_KNIGHT:
            if (statType == ITEM_MOD_STRENGTH) return 2.0f;
            if (statType == ITEM_MOD_STAMINA) return 1.2f;
            if (statType == ITEM_MOD_DODGE_RATING || statType == ITEM_MOD_PARRY_RATING || statType == ITEM_MOD_MASTERY_RATING) return 1.4f;
            break;
        case CLASS_HUNTER:
        case CLASS_ROGUE:
            if (statType == ITEM_MOD_AGILITY) return 2.0f;
            if (statType == ITEM_MOD_HIT_RATING || statType == ITEM_MOD_EXPERTISE_RATING) return 1.5f;
            if (statType == ITEM_MOD_STAMINA) return 0.8f;
            break;
        case CLASS_MAGE:
        case CLASS_PRIEST:
        case CLASS_WARLOCK:
            if (statType == ITEM_MOD_INTELLECT) return 2.0f;
            if (statType == ITEM_MOD_SPIRIT && classId == CLASS_PRIEST) return 1.2f;
            if (statType == ITEM_MOD_STAMINA) return 0.7f;
            break;
        case CLASS_DRUID:
        case CLASS_SHAMAN:
        case CLASS_PALADIN:
            if (statType == ITEM_MOD_INTELLECT || statType == ITEM_MOD_STRENGTH || statType == ITEM_MOD_AGILITY) return 1.6f;
            if (statType == ITEM_MOD_SPIRIT) return 1.0f;
            if (statType == ITEM_MOD_STAMINA) return 1.0f;
            break;
        default:
            break;
    }

    switch (statType)
    {
        case ITEM_MOD_HIT_RATING:
        case ITEM_MOD_CRIT_RATING:
        case ITEM_MOD_HASTE_RATING:
        case ITEM_MOD_MASTERY_RATING:
        case ITEM_MOD_EXPERTISE_RATING:
            return 1.2f;
        case ITEM_MOD_STAMINA:
            return 0.8f;
        default:
            return 0.25f;
    }
}

bool IsGear(ItemTemplate const* proto)
{
    return proto && (proto->GetClass() == ITEM_CLASS_ARMOR || proto->GetClass() == ITEM_CLASS_WEAPON);
}

bool IsWeaponSlot(uint8 inventoryType)
{
    return inventoryType == INVTYPE_WEAPON
        || inventoryType == INVTYPE_2HWEAPON
        || inventoryType == INVTYPE_WEAPONMAINHAND
        || inventoryType == INVTYPE_WEAPONOFFHAND
        || inventoryType == INVTYPE_RANGED
        || inventoryType == INVTYPE_RANGEDRIGHT
        || inventoryType == INVTYPE_THROWN;
}

uint8 RepresentativeEquipSlot(uint8 inventoryType)
{
    switch (inventoryType)
    {
        case INVTYPE_HEAD: return EQUIPMENT_SLOT_HEAD;
        case INVTYPE_NECK: return EQUIPMENT_SLOT_NECK;
        case INVTYPE_SHOULDERS: return EQUIPMENT_SLOT_SHOULDERS;
        case INVTYPE_BODY: return EQUIPMENT_SLOT_BODY;
        case INVTYPE_CHEST:
        case INVTYPE_ROBE: return EQUIPMENT_SLOT_CHEST;
        case INVTYPE_WAIST: return EQUIPMENT_SLOT_WAIST;
        case INVTYPE_LEGS: return EQUIPMENT_SLOT_LEGS;
        case INVTYPE_FEET: return EQUIPMENT_SLOT_FEET;
        case INVTYPE_WRISTS: return EQUIPMENT_SLOT_WRISTS;
        case INVTYPE_HANDS: return EQUIPMENT_SLOT_HANDS;
        case INVTYPE_FINGER: return EQUIPMENT_SLOT_FINGER1;
        case INVTYPE_TRINKET: return EQUIPMENT_SLOT_TRINKET1;
        case INVTYPE_CLOAK: return EQUIPMENT_SLOT_BACK;
        case INVTYPE_WEAPON:
        case INVTYPE_2HWEAPON:
        case INVTYPE_WEAPONMAINHAND: return EQUIPMENT_SLOT_MAINHAND;
        case INVTYPE_WEAPONOFFHAND:
        case INVTYPE_SHIELD:
        case INVTYPE_HOLDABLE: return EQUIPMENT_SLOT_OFFHAND;
        case INVTYPE_RANGED:
        case INVTYPE_RANGEDRIGHT:
        case INVTYPE_THROWN: return EQUIPMENT_SLOT_RANGED;
        default: return EQUIPMENT_SLOT_END;
    }
}

void AddActivity(std::vector<BotActivityScore>& activities, Player const* bot, BotExperienceLearningConfig const* learning, BotProgressionActivity activity, float power, float xp, float gold, float unlock, float dataset, float deathRisk, float wipeRisk, float timeCost, float stuckRisk)
{
    BotActivityScore score;
    score.Activity = activity;
    score.ExpectedPowerGain = power;
    score.ExpectedXpGain = xp;
    score.ExpectedGoldGain = gold;
    score.ExpectedUnlockValue = unlock;
    score.ExpectedDatasetValue = dataset;
    score.ExpectedDeathRisk = deathRisk;
    score.ExpectedWipeRisk = wipeRisk;
    score.ExpectedTimeCost = timeCost;
    score.ExpectedStuckRisk = stuckRisk;
    if (learning && learning->Enabled)
    {
        BotLearnedScore learned = BotExperienceLearningPolicy::ScoreActivity(bot, activity, *learning);
        score.LearnedScore = learned.Score;
        score.LearnedPenalty = learned.Penalty;
        score.LearnedConfidence = learned.Confidence;
        score.LearnedSampleCount = learned.SampleCount;
        score.LearnedDangerScore = learned.DangerScore;
        score.LearnedProgressionValue = learned.ProgressionValue;
        score.LearnedReason = learned.Reason;
    }
    score.Score = power + xp + gold + unlock + dataset - deathRisk - wipeRisk - timeCost - stuckRisk + score.LearnedScore;
    activities.push_back(score);
}
}

BotRolePowerBreakdown BotLongTermProgressionBrain::CalculateRolePower(Player const* bot)
{
    BotRolePowerBreakdown power;
    if (!bot)
        return power;

    power.ItemLevelScore = bot->GetAverageItemLevel() * 0.8f;
    power.GoldUtilityScore = std::min<float>(50.0f, float(bot->GetMoney()) / 100000.0f);
    power.ContentUnlockScore = float(bot->getLevel()) * 2.0f;

    for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
    {
        Item const* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot);
        if (!item)
            continue;

        ItemTemplate const* proto = item->GetTemplate();
        if (!IsGear(proto))
            continue;

        power.RoleStatWeightScore += ScoreItemForRole(bot, proto);
        if (IsWeaponSlot(proto->GetInventoryType()))
            power.WeaponScore += ScoreItemForRole(bot, proto) * 0.35f;
        if (proto->GetInventoryType() == INVTYPE_TRINKET)
            power.TrinketScore += ScoreItemForRole(bot, proto) * 0.25f;
        if (proto->GetQuality() >= ITEM_QUALITY_RARE)
            power.EnchantGemScore += float(proto->GetQuality()) * 0.5f;
    }

    if (bot->HasSkill(SKILL_COOKING))
    {
        uint16 maxSkill = bot->GetMaxSkillValue(SKILL_COOKING);
        if (maxSkill)
            power.ProfessionBonusScore += 10.0f * float(bot->GetSkillValue(SKILL_COOKING)) / float(maxSkill);
    }

    power.Total = power.ItemLevelScore
        + power.RoleStatWeightScore
        + power.WeaponScore
        + power.TrinketScore
        + power.SetBonusScore
        + power.EnchantGemScore
        + power.ProfessionBonusScore
        + power.ReputationUnlockScore
        + power.ContentUnlockScore
        + power.GoldUtilityScore;
    return power;
}

BotProgressionStage BotLongTermProgressionBrain::ClassifyStage(Player const* bot, BotRolePowerBreakdown const& /*power*/)
{
    if (!bot || bot->getLevel() < DEFAULT_MAX_LEVEL)
        return BotProgressionStage::Leveling;

    float itemLevel = bot->GetAverageItemLevel();
    if (itemLevel < 333.0f)
        return BotProgressionStage::FreshMax;
    if (itemLevel < 346.0f)
        return BotProgressionStage::DungeonGearing;
    if (itemLevel < 359.0f)
        return BotProgressionStage::HeroicGearing;
    if (itemLevel < 372.0f)
        return BotProgressionStage::RaidReady;
    return BotProgressionStage::HeroicRaid;
}

std::vector<BotActivityScore> BotLongTermProgressionBrain::ScoreActivities(Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, bool allowQuesting, bool allowCombat, BotExperienceLearningConfig const* learning)
{
    std::vector<BotActivityScore> activities;
    if (!bot)
        return activities;

    float lowBagPenalty = bot->GetFreeInventorySpace() <= 1 ? 120.0f : 0.0f;
    float trainValue = bot->getLevel() < DEFAULT_MAX_LEVEL && bot->GetMoney() > 10000 ? 8.0f : 0.0f;
    float gearDeficit = std::max<float>(0.0f, float(bot->getLevel()) * 5.0f - bot->GetAverageItemLevel());

    if (lowBagPenalty > 0.0f || trainValue > 0.0f)
        AddActivity(activities, bot, learning, BotProgressionActivity::VendorRepairTrain, lowBagPenalty + trainValue, 0.0f, 2.0f, trainValue, 0.1f, 0.1f, 0.0f, 1.5f, 0.5f);

    if (stage == BotProgressionStage::Leveling)
    {
        if (allowQuesting)
            AddActivity(activities, bot, learning, BotProgressionActivity::Questing, 6.0f, 18.0f, 2.0f, 4.0f, 2.0f, 2.0f, 0.0f, 4.0f, 2.0f);
        if (allowCombat)
            AddActivity(activities, bot, learning, BotProgressionActivity::Grinding, 4.0f + gearDeficit * 0.05f, 10.0f, 1.5f, 0.5f, 1.0f, 1.5f, 0.0f, 2.5f, 1.0f);
        AddActivity(activities, bot, learning, BotProgressionActivity::ProfessionFarm, 2.0f, 0.5f, 2.0f, 1.0f, 0.5f, 0.5f, 0.0f, 3.0f, 1.0f);
    }
    else if (stage == BotProgressionStage::FreshMax)
    {
        AddActivity(activities, bot, learning, BotProgressionActivity::NormalDungeon, 20.0f, 0.0f, 4.0f, 10.0f, 2.0f, 5.0f, 3.0f, 8.0f, 1.0f);
        AddActivity(activities, bot, learning, BotProgressionActivity::ReputationDaily, 10.0f, 0.0f, 3.0f, 8.0f, 1.0f, 2.0f, 0.0f, 5.0f, 1.5f);
        AddActivity(activities, bot, learning, BotProgressionActivity::GoldFarm, 3.0f, 0.0f, 8.0f, 1.0f, 0.5f, 1.0f, 0.0f, 4.0f, 1.0f);
    }
    else if (stage == BotProgressionStage::DungeonGearing)
        AddActivity(activities, bot, learning, BotProgressionActivity::HeroicDungeon, 24.0f, 0.0f, 5.0f, 12.0f, 2.0f, 7.0f, 4.0f, 9.0f, 1.0f);
    else if (stage == BotProgressionStage::HeroicGearing)
        AddActivity(activities, bot, learning, BotProgressionActivity::Raid, 30.0f, 0.0f, 6.0f, 18.0f, 3.0f, 10.0f, 7.0f, 12.0f, 1.5f);
    else
        AddActivity(activities, bot, learning, BotProgressionActivity::HeroicRaid, 35.0f, 0.0f, 8.0f, 22.0f, 4.0f, 14.0f, 10.0f, 15.0f, 2.0f);

    AddActivity(activities, bot, learning, BotProgressionActivity::ExperimentExploration, 1.0f + power.Total * 0.001f, 0.5f, 0.5f, 0.0f, 3.0f, 0.5f, 0.0f, 1.0f, 0.5f);
    return activities;
}

BotActivityScore BotLongTermProgressionBrain::ChooseActivity(std::vector<BotActivityScore> const& activities)
{
    if (activities.empty())
        return BotActivityScore();

    return *std::max_element(activities.begin(), activities.end(), [](BotActivityScore const& left, BotActivityScore const& right)
    {
        return left.Score < right.Score;
    });
}

BotGearUpgradeEvaluation BotLongTermProgressionBrain::EvaluateGearUpgrade(Player* bot)
{
    BotGearUpgradeEvaluation best;
    if (!bot)
        return best;

    auto considerItem = [&](Item* item)
    {
        if (!item)
            return;

        ItemTemplate const* proto = item->GetTemplate();
        if (!IsGear(proto))
            return;

        uint16 equipDest = 0;
        bool canEquip = bot->CanEquipItem(NULL_SLOT, equipDest, item, false) == EQUIP_ERR_OK;
        uint8 representativeSlot = RepresentativeEquipSlot(proto->GetInventoryType());
        if (!canEquip || representativeSlot >= EQUIPMENT_SLOT_END)
            return;

        float equippedScore = 0.0f;
        if (Item* equipped = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, representativeSlot))
            equippedScore = ScoreItemForRole(bot, equipped->GetTemplate());

        float candidateScore = ScoreItemForRole(bot, proto);
        float delta = candidateScore - equippedScore;
        if (delta <= best.PowerDelta)
            return;

        best.ItemId = item->GetEntry();
        best.Bag = item->GetBagSlot();
        best.Slot = item->GetSlot();
        best.InventoryType = proto->GetInventoryType();
        best.Quality = proto->GetQuality();
        best.CandidateScore = candidateScore;
        best.EquippedScore = equippedScore;
        best.PowerDelta = delta;
        best.CanEquip = canEquip;
        best.Upgrade = delta > 0.5f;
    };

    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        considerItem(bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));

    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        if (Bag* bag = bot->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                considerItem(bag->GetItemByPos(slot));

    return best;
}

BotGearUpgradeEvaluation BotLongTermProgressionBrain::EvaluateGearTemplate(Player const* bot, ItemTemplate const* proto, float equippedScoreOverride)
{
    BotGearUpgradeEvaluation evaluation;
    if (!bot || !IsGear(proto))
        return evaluation;

    uint8 representativeSlot = RepresentativeEquipSlot(proto->GetInventoryType());
    if (representativeSlot >= EQUIPMENT_SLOT_END)
        return evaluation;

    int32 allowableClass = proto->GetAllowableClass();
    int32 allowableRace = proto->GetAllowableRace();
    bool classAllowed = allowableClass == -1 || allowableClass == 0 || (allowableClass & (1 << (bot->getClass() - 1)));
    bool raceAllowed = allowableRace == -1 || allowableRace == 0 || (allowableRace & (1 << (bot->getRace() - 1)));
    bool levelAllowed = proto->GetRequiredLevel() <= bot->getLevel();
    if (!classAllowed || !raceAllowed || !levelAllowed)
        return evaluation;

    float equippedScore = equippedScoreOverride >= 0.0f ? equippedScoreOverride : 0.0f;
    if (equippedScoreOverride < 0.0f)
        if (Item* equipped = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, representativeSlot))
            equippedScore = ScoreItemForRole(bot, equipped->GetTemplate());

    evaluation.ItemId = proto->GetId();
    evaluation.InventoryType = proto->GetInventoryType();
    evaluation.Quality = proto->GetQuality();
    evaluation.CandidateScore = ScoreItemForRole(bot, proto);
    evaluation.EquippedScore = equippedScore;
    evaluation.PowerDelta = evaluation.CandidateScore - evaluation.EquippedScore;
    evaluation.CanEquip = true;
    evaluation.Upgrade = evaluation.PowerDelta > 0.5f;
    return evaluation;
}

float BotLongTermProgressionBrain::ScoreItemForRole(Player const* bot, ItemTemplate const* proto)
{
    if (!bot || !IsGear(proto))
        return 0.0f;

    float score = float(proto->GetBaseItemLevel()) * 0.5f;
    for (uint32 i = 0; i < MAX_ITEM_PROTO_STATS; ++i)
    {
        int32 statValue = proto->GetItemStatValue(i);
        if (!statValue)
            continue;

        score += float(statValue) * GetProgressionStatWeight(bot->getClass(), uint32(proto->GetItemStatType(i)));
    }

    if (IsWeaponSlot(proto->GetInventoryType()))
        score += float(proto->GetBaseItemLevel()) * 0.25f;
    if (proto->GetInventoryType() == INVTYPE_TRINKET)
        score += float(proto->GetQuality()) * 2.0f;

    return score;
}

char const* BotLongTermProgressionBrain::ToString(BotProgressionStage stage)
{
    switch (stage)
    {
        case BotProgressionStage::Leveling: return "leveling";
        case BotProgressionStage::FreshMax: return "fresh_max";
        case BotProgressionStage::DungeonGearing: return "dungeon_gearing";
        case BotProgressionStage::HeroicGearing: return "heroic_gearing";
        case BotProgressionStage::RaidReady: return "raid_ready";
        case BotProgressionStage::HeroicRaid: return "heroic_raid";
        default: return "unknown";
    }
}

char const* BotLongTermProgressionBrain::ToString(BotProgressionActivity activity)
{
    switch (activity)
    {
        case BotProgressionActivity::Questing: return "questing";
        case BotProgressionActivity::Grinding: return "grinding";
        case BotProgressionActivity::NormalDungeon: return "normal_dungeon";
        case BotProgressionActivity::HeroicDungeon: return "heroic_dungeon";
        case BotProgressionActivity::Raid: return "raid";
        case BotProgressionActivity::HeroicRaid: return "heroic_raid";
        case BotProgressionActivity::ReputationDaily: return "reputation_daily";
        case BotProgressionActivity::ProfessionFarm: return "profession_farm";
        case BotProgressionActivity::GoldFarm: return "gold_farm";
        case BotProgressionActivity::VendorRepairTrain: return "vendor_repair_train";
        case BotProgressionActivity::AssistPlayerGroup: return "assist_player_group";
        case BotProgressionActivity::ExperimentExploration: return "experiment_exploration";
        default: return "unknown";
    }
}
