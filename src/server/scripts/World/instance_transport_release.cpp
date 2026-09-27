/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#include "ScriptMgr.h"
#include "GameObject.h"
#include "InstanceScript.h"
#include "Log.h"
#include "Map.h"
#include "Player.h"
#include "VehicleDefines.h"
#include "instance_transport_release.h"

namespace InstanceTransportRelease
{
class InstanceTransportReleaseScript : public PlayerScript
{
public:
    InstanceTransportReleaseScript() : PlayerScript("InstanceTransportReleaseScript") { }

    // BuildPlayerRepop has made the body a ghost and placed the corpse; the
    // caller runs RepopAtGraveyard next (see instance_transport_release.h).
    void OnPlayerRepop(Player* player) override
    {
        if (!player || player->IsAlive())
            return;

        TransportBase* transport = player->GetTransport();
        Map* map = player->GetMap();
        InstanceScript const* instance = player->GetInstanceScript();
        Observation observation;
        observation.OnTransport = transport != nullptr;
        GameObject const* object = transport && map ? map->GetGameObject(transport->GetTransportGUID()) : nullptr;
        observation.StaticElevator = object && object->GetGoType() == GAMEOBJECT_TYPE_TRANSPORT;
        observation.RaidMap = map && map->IsRaid();
        observation.EncounterInProgress = instance && instance->IsEncounterInProgress();
        if (!DetachBeforeGraveyard(observation))
            return;

        TC_LOG_DEBUG("entities.player", "InstanceTransportRelease: %s released on transport %s during an encounter on map %u; leaving the transport as a ghost.",
            player->GetGUID().ToString().c_str(), transport->GetTransportGUID().ToString().c_str(), player->GetMapId());
        transport->RemovePassenger(player);
    }
};
}

void AddSC_instance_transport_release()
{
    new InstanceTransportRelease::InstanceTransportReleaseScript();
}
