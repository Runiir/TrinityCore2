#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakNativeTimers.h"

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"

#include "Creature.h"
#include "CreatureAI.h"
#include "ObjectAccessor.h"

#include <limits>

namespace BotEncounter
{
void AppendMaloriakMechanicTimers(Blackboard& snapshot, WorldObject const& observer)
{
    if (snapshot.Route.NodeId != Maloriak::EncounterNode)
        return;
    for (ActorSnapshot& actor : snapshot.Hostiles)
    {
        if (actor.Entry != Maloriak::BossEntry || !actor.Alive)
            continue;
        Creature const* boss = ObjectAccessor::GetCreature(observer, actor.Guid);
        if (!boss || boss->GetEntry() != Maloriak::BossEntry || !boss->IsAIEnabled())
            continue;
        for (uint32 spellId : Maloriak::PublishedMechanicSpells)
        {
            uint32 const remainingMs = boss->AI()->GetTimeUntilEncounterMechanic(spellId);
            if (remainingMs == std::numeric_limits<uint32>::max())
                continue;
            actor.MechanicTimers.push_back({ spellId, remainingMs, remainingMs == 0,
                FactSource::NativeInstanceState });
        }
    }
}
}
