#ifndef TRINITY_BOT_CLASS_SPEC_ACTION_PROFILE_H
#define TRINITY_BOT_CLASS_SPEC_ACTION_PROFILE_H

#include "Bots/BotCombatActionCatalog.h"
#include "Define.h"
#include <string>
#include <vector>

class Player;
class Unit;

struct BotActionProfileSpell
{
    uint32 SpellId = 0;
    BotCombatActionCategory Category = BotCombatActionCategory::Builder;
    std::string MechanicTags;
    float DamageWeight = 0.0f;
    float HealingWeight = 0.0f;
    float ThreatWeight = 0.0f;
    float MitigationWeight = 0.0f;
    float SurvivalWeight = 0.0f;
    float MovementWeight = 0.0f;
    float ProgressionWeight = 0.0f;
    float ProfessionWeight = 0.0f;
    uint8 PriorityBucket = 5;
};

struct BotActionCandidate
{
    uint32 ActionId = 0;
    uint32 SpellId = 0;
    BotCombatActionCategory Category = BotCombatActionCategory::Wait;
    std::string TargetType = "enemy";
    uint64 TargetGuid = 0;
    uint32 TargetEntry = 0;
    float Score = 0.0f;
    std::string Reason;
    std::string RejectReason;
    BotActionProfileSpell Profile;
};

struct BotClassSpecActionProfile
{
    uint8 ClassId = 0;
    std::string SpecTag = "generic";
    std::string Role = "dps";
    std::string ResourceType = "mana";
    std::string RangeBand = "mixed";
    std::string ProfileSource = "generic_fallback";
    bool MissingProfile = true;
    std::vector<BotActionProfileSpell> Spells;

    std::string EmbeddingJson() const;
    std::string QualityFlagsJson() const;
};

class BotClassSpecActionProfileStore
{
public:
    static BotClassSpecActionProfile Build(Player const* bot, char const* roleHint = nullptr);
    static std::vector<BotActionCandidate> BuildCandidates(Player const* bot, Unit const* target, BotClassSpecActionProfile const& profile);
    static std::string CandidateMaskJson(std::vector<BotActionCandidate> const& candidates, BotClassSpecActionProfile const& profile, char const* roleGoal, char const* saturationJson, char const* profileSourceOverride = nullptr);
    static std::string ChosenActionJson(BotActionCandidate const* candidate, BotClassSpecActionProfile const& profile, char const* roleGoal, char const* balanceMode, float confidence);
};

#endif
