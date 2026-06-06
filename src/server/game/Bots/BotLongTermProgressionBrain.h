#ifndef TRINITY_BOT_LONG_TERM_PROGRESSION_BRAIN_H
#define TRINITY_BOT_LONG_TERM_PROGRESSION_BRAIN_H

#include "Define.h"
#include <string>
#include <vector>

class Item;
class ItemTemplate;
class Player;

enum class BotProgressionStage : uint8
{
    Leveling,
    FreshMax,
    DungeonGearing,
    HeroicGearing,
    RaidReady,
    HeroicRaid
};

enum class BotProgressionActivity : uint8
{
    Questing,
    Grinding,
    NormalDungeon,
    HeroicDungeon,
    Raid,
    HeroicRaid,
    ReputationDaily,
    ProfessionFarm,
    GoldFarm,
    VendorRepairTrain,
    AssistPlayerGroup,
    ExperimentExploration
};

struct BotRolePowerBreakdown
{
    float ItemLevelScore = 0.0f;
    float RoleStatWeightScore = 0.0f;
    float WeaponScore = 0.0f;
    float TrinketScore = 0.0f;
    float SetBonusScore = 0.0f;
    float EnchantGemScore = 0.0f;
    float ProfessionBonusScore = 0.0f;
    float ReputationUnlockScore = 0.0f;
    float ContentUnlockScore = 0.0f;
    float GoldUtilityScore = 0.0f;
    float Total = 0.0f;
};

struct BotActivityScore
{
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    float ExpectedPowerGain = 0.0f;
    float ExpectedXpGain = 0.0f;
    float ExpectedGoldGain = 0.0f;
    float ExpectedUnlockValue = 0.0f;
    float ExpectedDatasetValue = 0.0f;
    float ExpectedDeathRisk = 0.0f;
    float ExpectedWipeRisk = 0.0f;
    float ExpectedTimeCost = 0.0f;
    float ExpectedStuckRisk = 0.0f;
    float Score = 0.0f;
};

struct BotGearUpgradeEvaluation
{
    uint32 ItemId = 0;
    uint8 Bag = 0;
    uint8 Slot = 0;
    uint8 InventoryType = 0;
    uint8 Quality = 0;
    float CandidateScore = 0.0f;
    float EquippedScore = 0.0f;
    float PowerDelta = 0.0f;
    bool CanEquip = false;
    bool Upgrade = false;
};

class BotLongTermProgressionBrain
{
public:
    static BotRolePowerBreakdown CalculateRolePower(Player const* bot);
    static BotProgressionStage ClassifyStage(Player const* bot, BotRolePowerBreakdown const& power);
    static std::vector<BotActivityScore> ScoreActivities(Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, bool allowQuesting, bool allowCombat);
    static BotActivityScore ChooseActivity(std::vector<BotActivityScore> const& activities);
    static BotGearUpgradeEvaluation EvaluateGearUpgrade(Player* bot);

    static float ScoreItemForRole(Player const* bot, ItemTemplate const* proto);
    static char const* ToString(BotProgressionStage stage);
    static char const* ToString(BotProgressionActivity activity);
};

#endif
