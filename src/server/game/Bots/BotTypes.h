#ifndef TRINITY_BOT_TYPES_H
#define TRINITY_BOT_TYPES_H

#include "Define.h"
#include "ObjectGuid.h"
#include <map>
#include <string>
#include <vector>

class Unit;

enum class BotRole : uint8
{
    HolyPaladinHealer,
    Warrior,
    Hunter,
    Rogue,
    Priest,
    DeathKnight,
    Shaman,
    Mage,
    Warlock,
    Druid,
    Generic
};

enum class BotRoleCategory : uint8
{
    Tank,
    Healer,
    Damage
};

enum class BotMovementMode : uint8
{
    Follow,
    Stay,
    Stop,
    MoveTo,
    ReturnToGroup,
    MoveSafe,
    Unstuck
};

struct BotMovementTarget
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    bool Active = false;
};

struct BotMovementFrame
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    float Orientation = 0.0f;
    bool Moving = false;
    bool Mounted = false;
    bool InCombat = false;
    float HpPct = 1.0f;
    float DistanceToLeader = 0.0f;
    float DistanceToGroupCenter = 0.0f;
    bool LineOfSightToLeader = false;
    bool OnTransport = false;
    bool Indoors = false;
    float CurrentPathLength = 0.0f;
    bool PathAvailable = false;
    float StuckScore = 0.0f;
    uint32 LastProgressTimeMs = 0;
    bool NearbyHazard = false;
    bool SafePositionAvailable = false;
};

enum class HealerMode : uint8
{
    Conserve,
    PrepareTankBurst,
    PrepareGroupAoe,
    HoldUntilDamage,
    Precast,
    RecoverAfterDamage,
    Emergency
};

enum class HealerIntent : uint8
{
    Wait,
    EfficientSingleHeal,
    FastSingleHeal,
    BigSingleHeal,
    InstantSingleHeal,
    AoeHeal,
    Dispel,
    ThroughputCooldown,
    ExternalDefensive,
    MoveSafe
};

struct HealerUnitFrame
{
    ObjectGuid Guid;
    std::string Name;
    uint8 Role = 0;
    uint8 Subgroup = 0;
    uint8 HealthPct = 100;
    float Distance = 0.0f;
    bool Alive = false;
    bool Friendly = false;
    bool LineOfSight = false;
    bool IsOwner = false;
    uint32 CastSpellId = 0;
    uint32 ChannelSpellId = 0;
    uint32 AuraCount = 0;
    uint32 DebuffCount = 0;
    uint32 RecentDamageTaken = 0;
    uint32 RecentHealingReceived = 0;
};

struct BotRecentEvents
{
    uint32 DamageTaken = 0;
    uint32 HealingDone = 0;
    uint32 HealingReceived = 0;
    std::map<ObjectGuid, uint32> PartyDamageTaken;
    std::map<ObjectGuid, uint32> PartyHealingReceived;
};

struct HealerFrame
{
    ObjectGuid OwnerGuid;
    ObjectGuid BotGuid;
    uint32 MapId = 0;
    uint32 BotHealthPct = 100;
    uint32 BotManaPct = 100;
    bool BotAlive = false;
    bool BotCasting = false;
    uint32 BotCastSpellId = 0;
    uint32 BotChannelSpellId = 0;
    uint32 BotAuraCount = 0;
    uint32 BotDebuffCount = 0;
    bool GcdReady = true;
    bool InCombat = false;
    uint32 RecentDamageTaken = 0;
    uint32 RecentHealingDone = 0;
    uint32 RecentHealingReceived = 0;
    BotMovementMode MovementMode = BotMovementMode::Follow;
    std::vector<HealerUnitFrame> Party;
};

struct HealerDecision
{
    HealerMode Mode = HealerMode::Conserve;
    HealerIntent Intent = HealerIntent::Wait;
    ObjectGuid TargetGuid;
    float Confidence = 1.0f;
    std::vector<HealerIntent> Fallbacks;
};

struct ResolvedBotAction
{
    HealerIntent Intent = HealerIntent::Wait;
    ObjectGuid TargetGuid;
    uint32 SpellId = 0;
    std::string DebugName;
};

enum class BotActionResult : uint8
{
    Ok,
    Disabled,
    NoOwner,
    NoBot,
    InvalidTarget,
    NotFriendly,
    DeadTarget,
    OutOfRange,
    NoLineOfSight,
    Casting,
    GlobalCooldown,
    Cooldown,
    NoMana,
    BadSpell,
    CastFailed,
    Throttled,
    NoAction
};

char const* ToString(BotMovementMode mode);
char const* ToString(BotRole role);
char const* ToString(HealerMode mode);
char const* ToString(HealerIntent intent);
char const* ToString(BotActionResult result);
std::string NormalizeBotRole(std::string const& role);
BotRole ParseBotRole(std::string const& role);
BotRoleCategory GetBotRoleCategory(BotRole role);
bool IsKnownBotRole(std::string const& role);
bool IsMixedBotRoleSelector(std::string const& role);
bool IsHealerBotRole(BotRole role);

#endif
