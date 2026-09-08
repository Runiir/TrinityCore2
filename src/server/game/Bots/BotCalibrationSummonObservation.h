#ifndef TRINITY_BOT_CALIBRATION_SUMMON_OBSERVATION_H
#define TRINITY_BOT_CALIBRATION_SUMMON_OBSERVATION_H

#include "Map.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "TemporarySummon.h"
#include "Totem.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <set>
#include <sstream>
#include <vector>
#include <utility>

namespace BotCalibrationSummonObservation
{
// A point-in-time observation. GUIDs are full raw GUIDs; elapsed time is the
// timeline sampling time, never an inferred spawn or cast-completion time.
inline std::string Capture(Player* owner, Unit* offensiveTarget, uint64 elapsedMs)
{
    std::ostringstream json;
    Unit* victim = owner ? owner->GetVictim() : nullptr;
    Unit* helperTarget = owner ? owner->getAttackerForHelper() : nullptr;
    auto guid = [](Unit const* unit) { return unit ? unit->GetGUID().GetRawValue() : uint64(0); };
    auto valid = [owner](Unit* unit) { return owner && unit && unit->IsAlive() && owner->IsValidAttackTarget(unit); };
    json << "{\"schema\":\"calibration_summon_sample_v1\",\"observed_elapsed_ms\":" << elapsedMs
         << ",\"owner_guid\":" << guid(owner)
         << ",\"owner_victim_guid\":" << guid(victim)
         << ",\"owner_victim_valid\":" << (valid(victim) ? "true" : "false")
         << ",\"owner_engaged\":" << (owner && owner->IsEngaged() ? "true" : "false")
         << ",\"owner_helper_target_guid\":" << guid(helperTarget)
         << ",\"owner_helper_target_valid\":" << (valid(helperTarget) ? "true" : "false")
         << ",\"offensive_target_guid\":" << guid(offensiveTarget)
         << ",\"offensive_target_valid\":" << (valid(offensiveTarget) ? "true" : "false");
    // Match ObserveCalibrationEffectiveStats: inverse native cast-haste time.
    // Missing/invalid observations are null rather than a fabricated 1.0.
    float const spellTime = owner ? owner->GetFloatValue(UNIT_MOD_CAST_HASTE) : 0.0f;
    json << ",\"owner_spell_speed_multiplier\":";
    if (owner && std::isfinite(spellTime) && spellTime > 0.0f)
        json << std::setprecision(9) << 1.0 / double(spellTime);
    else
        json << "null";
    ObjectGuid slotGuid = owner ? owner->m_SummonSlot[SUMMON_SLOT_TOTEM_FIRE] : ObjectGuid::Empty;
    Creature* fire = owner && owner->GetMap() && slotGuid
        ? owner->GetMap()->GetCreature(slotGuid) : nullptr;
    bool const ownedFire = fire && fire->IsTotem() && fire->GetOwner() == owner;
    json << ",\"fire_slot\":{\"guid\":" << slotGuid.GetRawValue()
         << ",\"present\":" << (fire ? "true" : "false")
         << ",\"owned\":" << (ownedFire ? "true" : "false")
         << ",\"entry\":" << (fire ? fire->GetEntry() : 0)
         << ",\"created_by_spell\":" << (fire ? fire->GetUInt32Value(UNIT_CREATED_BY_SPELL) : 0)
         << ",\"alive\":" << (fire && fire->IsAlive() ? "true" : "false") << '}';
    std::vector<Unit*> candidates;
    if (owner)
        candidates.assign(owner->m_Controlled.begin(), owner->m_Controlled.end());
    // Native Minion ownership may be the totem rather than the player.
    if (ownedFire)
        candidates.insert(candidates.end(), fire->m_Controlled.begin(), fire->m_Controlled.end());
    std::sort(candidates.begin(), candidates.end(), [guid](Unit* left, Unit* right) { return guid(left) < guid(right); });
    std::set<uint64> seen;
    uint32 foreign = 0;
    bool first = true;
    json << ",\"guardians\":[";
    for (Unit* unit : candidates)
    {
        Creature* creature = unit ? unit->ToCreature() : nullptr;
        if (!creature || unit->IsTotem() || (!unit->IsGuardian() && creature->GetEntry() != 15438)
            || !seen.insert(guid(unit)).second)
            continue;
        std::vector<uint64> ownerChain, summonerChain;
        auto chain = [&](bool summoners, std::vector<uint64>& values)
        {
            Unit* current = unit;
            for (uint8 depth = 0; current && depth < 4; ++depth)
            {
                TempSummon* summon = summoners ? current->ToTempSummon() : nullptr;
                current = summon ? summon->GetSummoner() : current->GetCharmerOrOwner();
                if (!current)
                    break;
                values.push_back(guid(current));
                if (current == owner)
                    return true;
            }
            return false;
        };
        bool const ownerMatches = chain(false, ownerChain);
        bool const summonerMatches = chain(true, summonerChain);
        if (!ownerMatches && !summonerMatches)
        {
            ++foreign;
            continue;
        }
        if (!first)
            json << ',';
        first = false;
        auto writeChain = [&](char const* key, std::vector<uint64> const& values)
        {
            json << ",\"" << key << "\":[";
            for (size_t index = 0; index < values.size(); ++index)
                json << (index ? "," : "") << values[index];
            json << ']';
        };
        Unit* guardianVictim = unit->GetVictim();
        json << "{\"guid\":" << guid(unit) << ",\"entry\":" << creature->GetEntry()
             << ",\"created_by_spell\":" << unit->GetUInt32Value(UNIT_CREATED_BY_SPELL)
             << ",\"runtime_type\":\"" << (unit->IsPet() ? "pet" : (unit->IsGuardian() ? "guardian" : "creature")) << '"'
             << ",\"alive\":" << (unit->IsAlive() ? "true" : "false")
             << ",\"ai_enabled\":" << (unit->IsAIEnabled() ? "true" : "false")
             << ",\"victim_guid\":" << guid(guardianVictim)
             << ",\"victim_valid\":" << (guardianVictim && guardianVictim->IsAlive() && unit->IsValidAttackTarget(guardianVictim) ? "true" : "false");
        writeChain("owner_chain", ownerChain);
        writeChain("summoner_chain", summonerChain);
        for (auto const& [key, type] : {std::pair{"current_generic_spell", CURRENT_GENERIC_SPELL},
                std::pair{"current_channeled_spell", CURRENT_CHANNELED_SPELL}})
        {
            Spell* spell = unit->GetCurrentSpell(type);
            json << ",\"" << key << "\":" << (spell ? spell->GetSpellInfo()->Id : 0);
        }
        json << '}';
    }
    json << "],\"foreign_guardians_excluded\":" << foreign << '}';
    return json.str();
}
}
#endif
