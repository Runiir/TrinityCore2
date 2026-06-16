#ifndef TRINITY_BOT_ENCOUNTER_MECHANIC_CATALOG_H
#define TRINITY_BOT_ENCOUNTER_MECHANIC_CATALOG_H

#include "Define.h"
#include <string>

class Player;
class SpellInfo;
class Unit;

enum class BotEncounterMechanicFamily : uint8
{
    TrashPack,
    CasterPack,
    HealerMob,
    PatrolRisk,
    CleaveRisk,
    InterruptRequired,
    DispelRequired,
    TankBuster,
    RaidAoe,
    GroundDanger,
    Stack,
    Spread,
    Adds,
    TargetSwitch,
    Enrage,
    MovementCheck,
    BossPhase,
    WipeRisk
};

struct BotEncounterMechanicEmbedding
{
    BotEncounterMechanicFamily Family = BotEncounterMechanicFamily::TrashPack;
    uint32 SourceEntry = 0;
    uint32 SpellId = 0;
    std::string RoleResponse = "maintain_role";
    float DangerScore = 0.0f;
    float InterruptPriority = 0.0f;
    float DispelPriority = 0.0f;
    std::string MovementResponse = "none";
    bool TankResponsibility = false;
    bool HealerResponsibility = false;
    bool DpsResponsibility = false;

    std::string ToJson() const;
};

class BotEncounterMechanicCatalog
{
public:
    static char const* ToString(BotEncounterMechanicFamily family);
    static BotEncounterMechanicEmbedding Classify(Player const* bot, Unit const* source, SpellInfo const* spellInfo, float baseDanger, bool interrupt, bool groundDanger, bool tankSpike, bool raidDamage, bool adds);
    static std::string FamiliesJson();
};

#endif
