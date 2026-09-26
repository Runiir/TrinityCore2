#ifndef TRINITY_BOT_ENCOUNTER_INTERRUPT_VETO_H
#define TRINITY_BOT_ENCOUNTER_INTERRUPT_VETO_H

#include "Define.h"

#include <chrono>
#include <initializer_list>
#include <map>
#include <mutex>
#include <tuple>
#include <unordered_map>

// Casts an encounter strategy needs to finish, for example Maloriak's
// admitted Release Aberrations (the reserve must drain before 25%). Generic
// rotation interrupts consult this; the strategy's own interrupt candidates
// decide separately. A publisher refreshes its entry every decision tick and
// the entry lapses after its lease, so a stale strategy cannot pin a veto.
//
// Entries are keyed by the caster's map id, instance id and raw GUID:
// creature GUIDs are generated per map, so two concurrent instances of one
// raid map can hold the same boss GUID.
//
// Scope: only the kernel profile resolver
// (BotWorldPopulationMgr::ResolveProfileCombatAction) honours the veto. The
// legacy paths (BotWorldPopulationMgr::SelectCombatSpell, the BotController
// combat candidates) do not check it; encounter owners must keep bots off
// those paths while a veto matters.
namespace BotEncounterInterruptVeto
{
constexpr uint64 DefaultLeaseMs = 1500;

using CasterKey = std::tuple<uint32, uint32, uint64>;

inline std::mutex Mutex;
// (map id, instance id, caster raw GUID) -> spell id -> lease expiry
// (steady clock, ms).
inline std::map<CasterKey, std::unordered_map<uint32, uint64>> Leases;

inline uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

inline void Set(uint32 mapId, uint32 instanceId, uint64 casterGuid,
    uint32 spellId, bool vetoed, uint64 leaseMs = DefaultLeaseMs)
{
    if (!casterGuid || !spellId)
        return;
    CasterKey const key{ mapId, instanceId, casterGuid };
    std::lock_guard<std::mutex> guard(Mutex);
    if (vetoed)
    {
        Leases[key][spellId] = NowMs() + leaseMs;
        return;
    }
    auto caster = Leases.find(key);
    if (caster == Leases.end())
        return;
    caster->second.erase(spellId);
    if (caster->second.empty())
        Leases.erase(caster);
}

inline bool IsVetoed(uint32 mapId, uint32 instanceId, uint64 casterGuid,
    uint32 spellId)
{
    std::lock_guard<std::mutex> guard(Mutex);
    auto caster = Leases.find(CasterKey{ mapId, instanceId, casterGuid });
    if (caster == Leases.end())
        return false;
    auto spell = caster->second.find(spellId);
    if (spell == caster->second.end())
        return false;
    if (spell->second > NowMs())
        return true;
    caster->second.erase(spell);
    if (caster->second.empty())
        Leases.erase(caster);
    return false;
}

// True while the caster's current generic cast or channel is vetoed in the
// caster's own map instance. A template, instantiated where Unit and Spell
// are complete, so this header stays free of entity includes.
template <typename Caster, typename SpellType>
bool IsCurrentCastVetoed(Caster const* caster, SpellType generic,
    SpellType channeled)
{
    if (!caster)
        return false;
    for (SpellType spellType : { generic, channeled })
        if (auto const* spell = caster->GetCurrentSpell(spellType))
            if (IsVetoed(caster->GetMapId(), caster->GetInstanceId(),
                    caster->GetGUID().GetRawValue(), spell->GetSpellInfo()->Id))
                return true;
    return false;
}
}

#endif
