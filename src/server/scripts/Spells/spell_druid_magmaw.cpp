/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 */

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Log.h"
#include "ScriptMgr.h"
#include "SpellScript.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <list>

namespace Spells::Druid
{
namespace
{
constexpr float MagmawParasiteGroundRadius = 8.0f;

class spell_dru_wild_mushroom_damage : public SpellScript
{
    void TraceTargets(std::list<WorldObject*>& targets)
    {
        Unit* caster = GetCaster();
        if (!caster || caster->GetMapId() != 669)
            return;

        WorldLocation const* destination = GetExplTargetDest();
        float const destinationX = destination ? destination->GetPositionX() : caster->GetPositionX();
        float const destinationY = destination ? destination->GetPositionY() : caster->GetPositionY();
        float const destinationZ = destination ? destination->GetPositionZ() : caster->GetPositionZ();
        float const nativeRadius = GetSpellInfo()->Effects[EFFECT_0].CalcRadius(
            caster, SpellTargetIndex::TargetB);
        // Magmaw's airborne parasite ring is 7 yards from the ground marker.
        // The ordinary DBC radius is 6 yards, so the explicitly allowlisted
        // encounter duty needs a small ground-plane envelope to hit the
        // parasites without moving the player's mushroom destination.
        float const effectiveRadius = std::max(
            nativeRadius, MagmawParasiteGroundRadius);

        struct LavaParasiteNearbyCheck
        {
            float DestinationX;
            float DestinationY;
            float Radius;

            bool operator()(WorldObject* object) const
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!creature || !creature->IsAlive()
                    || (creature->GetEntry() != 41806
                        && creature->GetEntry() != 42321))
                    return false;

                float const deltaX = creature->GetPositionX() - DestinationX;
                float const deltaY = creature->GetPositionY() - DestinationY;
                return deltaX * deltaX + deltaY * deltaY <= Radius * Radius;
            }
        };

        std::list<WorldObject*> nearbyTargets;
        LavaParasiteNearbyCheck check{ destinationX, destinationY, 12.0f };
        Trinity::WorldObjectListSearcher<LavaParasiteNearbyCheck> searcher(
            caster, nearbyTargets, check);
        Cell::VisitAllObjects(
            destinationX, destinationY, caster->GetMap(), searcher, 12.0f);

        TC_LOG_INFO("server",
            "MagmawWildMushroomNative event=nearby_targets destination=%.3f,%.3f,%.3f "
            "probe_radius=12.000 native_radius=%.3f effective_radius=%.3f target_count=%zu",
            destinationX, destinationY, destinationZ, nativeRadius, effectiveRadius,
            nearbyTargets.size());

        for (WorldObject* object : nearbyTargets)
        {
            Creature* target = object ? object->ToCreature() : nullptr;
            if (!target)
                continue;

            float const deltaX = target->GetPositionX() - destinationX;
            float const deltaY = target->GetPositionY() - destinationY;
            float const deltaZ = target->GetPositionZ() - destinationZ;
            float const distance2d = std::sqrt(deltaX * deltaX + deltaY * deltaY);
            float const distance3d = std::sqrt(
                deltaX * deltaX + deltaY * deltaY + deltaZ * deltaZ);

            TC_LOG_INFO("server",
                "MagmawWildMushroomNative event=nearby_target target=%s entry=%u "
                "position=%.3f,%.3f,%.3f distance_2d=%.3f distance_3d=%.3f",
                target->GetGUID().ToString().c_str(), target->GetEntry(),
                target->GetPositionX(), target->GetPositionY(), target->GetPositionZ(),
                distance2d, distance3d);

            // The native DBC area query measures the airborne parasite's Z and
            // rejects a ground mushroom even when its X/Y is inside the spell
            // radius. Apply the bounded ground-plane envelope for this
            // explicitly allowlisted Magmaw add duty.
            if (distance2d <= effectiveRadius
                && std::find(targets.begin(), targets.end(), object) == targets.end())
                targets.push_back(object);
        }

        TC_LOG_INFO("server",
            "MagmawWildMushroomNative event=damage_targets caster=%s caster_entry=%u "
            "destination=%.3f,%.3f,%.3f target_count=%zu",
            caster->GetGUID().ToString().c_str(), caster->GetEntry(), destinationX,
            destinationY, destinationZ, targets.size());

        for (WorldObject* target : targets)
            if (target)
                TC_LOG_INFO("server",
                    "MagmawWildMushroomNative event=damage_target caster=%s target=%s "
                    "entry=%u position=%.3f,%.3f,%.3f",
                    caster->GetGUID().ToString().c_str(),
                    target->GetGUID().ToString().c_str(), target->GetEntry(),
                    target->GetPositionX(), target->GetPositionY(),
                    target->GetPositionZ());
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(
            &spell_dru_wild_mushroom_damage::TraceTargets,
            EFFECT_0, TARGET_UNIT_DEST_AREA_ENEMY);
    }
};
}
}

void AddSC_druid_magmaw_spell_scripts()
{
    using namespace Spells::Druid;
    RegisterSpellScript(spell_dru_wild_mushroom_damage);
}
