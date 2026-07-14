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
    uint8 MinEnemies = 1;
    uint8 MaxEnemies = 0;
    float MinTargetHealthPct = 0.0f;
    float MaxTargetHealthPct = 1.0f;
    float MinSelfHealthPct = 0.0f;
    float MaxSelfHealthPct = 1.0f;
    uint32 RequiredSelfAura = 0;
    uint32 ForbiddenSelfAura = 0;
    uint32 RequiredTargetAura = 0;
    uint32 ForbiddenTargetAura = 0;
    bool RequiresInterruptibleTarget = false;
    bool RequiresTargetNotVictim = false;
    bool RequiresTargetVictim = false;
    bool RequiresMeleeRange = false;
    bool RequiresRangedRange = false;
    std::string TargetSelector = "enemy";
    std::string MovementDirective;
    std::string AutoAttackMode;
    float MinRange = 0.0f;
    float MaxRange = 0.0f;
    bool RequiresInstantCast = false;
    uint32 MaxCastTimeMs = 0;
    uint32 MaintainAuraId = 0;
    uint32 RefreshAuraBelowMs = 0;
    uint8 MinInjuredPlayers = 0;
    uint8 MaxInjuredPlayers = 0;
    float InjuredHealthPct = 1.0f;
    float MinManaPct = 0.0f;
    float MaxManaPct = 1.0f;
    uint8 MinAttackers = 0;
    uint8 MaxAttackers = 0;
    bool RequiresStationary = false;
    bool RequiresMoving = false;
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
    float PredictedRawHeal = 0.0f;
    float PredictedEffectiveHeal = 0.0f;
    float PredictedOverheal = 0.0f;
    uint32 ManaCost = 0;
    uint32 CastTimeMs = 0;
    BotActionProfileSpell Profile;
};

struct BotClassSpecActionProfile
{
    uint8 ClassId = 0;
    std::string SpecTag = "generic";
    std::string Role = "dps";
    std::string ResourceType = "mana";
    std::string RangeBand = "mixed";
    std::string MovementDirective;
    std::string AutoAttackMode;
    float MinRange = 0.0f;
    float MaxRange = 0.0f;
    std::string ProfileSource = "missing_db_rotation_profile";
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
    static std::string ReloadDbProfiles();
    static std::string DbProfilesJson();
    static std::string DbProfileDumpJson(uint8 classId, std::string const& specTag, std::string const& role);
};

#endif
