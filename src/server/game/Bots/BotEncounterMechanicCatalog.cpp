#include "Bots/BotEncounterMechanicCatalog.h"
#include "Creature.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <algorithm>
#include <sstream>

namespace
{
std::string EncounterMechanicEscape(std::string const& value)
{
    std::ostringstream out;
    for (char c : value)
    {
        if (c == '\\' || c == '"')
            out << '\\';
        out << c;
    }
    return out.str();
}
}

char const* BotEncounterMechanicCatalog::ToString(BotEncounterMechanicFamily family)
{
    switch (family)
    {
        case BotEncounterMechanicFamily::TrashPack: return "trash_pack";
        case BotEncounterMechanicFamily::CasterPack: return "caster_pack";
        case BotEncounterMechanicFamily::HealerMob: return "healer_mob";
        case BotEncounterMechanicFamily::PatrolRisk: return "patrol_risk";
        case BotEncounterMechanicFamily::CleaveRisk: return "cleave_risk";
        case BotEncounterMechanicFamily::InterruptRequired: return "interrupt_required";
        case BotEncounterMechanicFamily::DispelRequired: return "dispel_required";
        case BotEncounterMechanicFamily::TankBuster: return "tank_buster";
        case BotEncounterMechanicFamily::RaidAoe: return "raid_aoe";
        case BotEncounterMechanicFamily::GroundDanger: return "ground_danger";
        case BotEncounterMechanicFamily::Stack: return "stack";
        case BotEncounterMechanicFamily::Spread: return "spread";
        case BotEncounterMechanicFamily::Adds: return "adds";
        case BotEncounterMechanicFamily::TargetSwitch: return "target_switch";
        case BotEncounterMechanicFamily::Enrage: return "enrage";
        case BotEncounterMechanicFamily::MovementCheck: return "movement_check";
        case BotEncounterMechanicFamily::BossPhase: return "boss_phase";
        case BotEncounterMechanicFamily::WipeRisk: return "wipe_risk";
        default: return "trash_pack";
    }
}

std::string BotEncounterMechanicEmbedding::ToJson() const
{
    std::ostringstream json;
    json << "{\"mechanic_family\":\"" << EncounterMechanicEscape(BotEncounterMechanicCatalog::ToString(Family)) << "\""
         << ",\"source_entry\":" << SourceEntry
         << ",\"spell_id\":" << SpellId
         << ",\"role_response\":\"" << EncounterMechanicEscape(RoleResponse) << "\""
         << ",\"danger_score\":" << DangerScore
         << ",\"interrupt_priority\":" << InterruptPriority
         << ",\"dispel_priority\":" << DispelPriority
         << ",\"movement_response\":\"" << EncounterMechanicEscape(MovementResponse) << "\""
         << ",\"tank_responsibility\":" << (TankResponsibility ? "true" : "false")
         << ",\"healer_responsibility\":" << (HealerResponsibility ? "true" : "false")
         << ",\"dps_responsibility\":" << (DpsResponsibility ? "true" : "false") << "}";
    return json.str();
}

BotEncounterMechanicEmbedding BotEncounterMechanicCatalog::Classify(Player const* /*bot*/, Unit const* source, SpellInfo const* spellInfo, float baseDanger, bool interrupt, bool groundDanger, bool tankSpike, bool raidDamage, bool adds)
{
    BotEncounterMechanicEmbedding embedding;
    if (Creature const* creature = source ? source->ToCreature() : nullptr)
        embedding.SourceEntry = creature->GetEntry();
    embedding.SpellId = spellInfo ? spellInfo->Id : 0;
    embedding.DangerScore = std::min(1.0f, std::max(0.0f, baseDanger));

    if (interrupt)
    {
        embedding.Family = BotEncounterMechanicFamily::InterruptRequired;
        embedding.RoleResponse = "interrupt_or_stop_cast";
        embedding.InterruptPriority = std::max(0.75f, embedding.DangerScore);
        embedding.DpsResponsibility = true;
    }
    else if (tankSpike)
    {
        embedding.Family = BotEncounterMechanicFamily::TankBuster;
        embedding.RoleResponse = "mitigate_or_external";
        embedding.TankResponsibility = true;
        embedding.HealerResponsibility = true;
    }
    else if (groundDanger)
    {
        embedding.Family = BotEncounterMechanicFamily::GroundDanger;
        embedding.RoleResponse = "move";
        embedding.MovementResponse = "move_out";
        embedding.TankResponsibility = true;
        embedding.HealerResponsibility = true;
        embedding.DpsResponsibility = true;
    }
    else if (adds)
    {
        embedding.Family = BotEncounterMechanicFamily::Adds;
        embedding.RoleResponse = "target_switch";
        embedding.DpsResponsibility = true;
        embedding.TankResponsibility = true;
    }
    else if (raidDamage)
    {
        embedding.Family = BotEncounterMechanicFamily::RaidAoe;
        embedding.RoleResponse = "heal_or_defensive";
        embedding.HealerResponsibility = true;
        embedding.DpsResponsibility = true;
    }
    else if (embedding.DangerScore >= 0.80f)
    {
        embedding.Family = BotEncounterMechanicFamily::WipeRisk;
        embedding.RoleResponse = "recover";
        embedding.TankResponsibility = true;
        embedding.HealerResponsibility = true;
        embedding.DpsResponsibility = true;
    }
    else
    {
        embedding.Family = BotEncounterMechanicFamily::BossPhase;
        embedding.RoleResponse = "maintain_role";
    }
    return embedding;
}

std::string BotEncounterMechanicCatalog::FamiliesJson()
{
    std::ostringstream json;
    json << "[";
    for (uint8 i = uint8(BotEncounterMechanicFamily::TrashPack); i <= uint8(BotEncounterMechanicFamily::WipeRisk); ++i)
    {
        if (i)
            json << ",";
        json << "\"" << EncounterMechanicEscape(ToString(BotEncounterMechanicFamily(i))) << "\"";
    }
    json << "]";
    return json.str();
}
