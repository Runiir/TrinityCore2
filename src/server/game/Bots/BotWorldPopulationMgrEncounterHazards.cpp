#include "Bots/BotWorldPopulationMgrEncounterHazards.h"

#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "AreaTrigger.h"
#include "CellImpl.h"
#include "Creature.h"
#include "DynamicObject.h"
#include "GameObject.h"
#include "GridNotifiersImpl.h"
#include "Object.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
#include <cmath>
#include <utility>
#include <vector>

namespace
{
constexpr float HazardScanRadius = 35.0f;

float SpellRadius(SpellInfo const* spellInfo, WorldObject* caster)
{
    if (!spellInfo)
        return 0.0f;

    float radius = 0.0f;
    for (uint8 index = 0; index < MAX_SPELL_EFFECTS; ++index)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[index];
        if (!effect.IsEffect())
            continue;
        float const effectRadius = effect.CalcRadius(caster);
        if (effectRadius > radius
            && (effect.IsTargetingArea()
                || effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE
                || BotWorldPopulationMgrSpellSemantics::SpellLooksDangerous(
                    spellInfo)))
            radius = effectRadius;
    }
    return radius;
}

bool IsHazardSpell(SpellInfo const* spellInfo, float radius)
{
    return spellInfo && radius > 0.0f
        && (BotWorldPopulationMgrSpellSemantics::SpellLooksLikeGroundDanger(
                spellInfo)
            || BotWorldPopulationMgrSpellSemantics::SpellLooksDangerous(
                spellInfo));
}

uint64 ExpiryFromSpell(uint64 observedAtMs, SpellInfo const* spellInfo,
    WorldObject* source)
{
    if (!spellInfo)
        return 0;
    int32 durationMs = spellInfo->GetDuration();
    if (durationMs > 0)
        return observedAtMs + uint64(durationMs);
    if (Creature* creature = source ? source->ToCreature() : nullptr)
    {
        int32 castTimeMs = spellInfo->CalcCastTime(creature->getLevel());
        if (castTimeMs > 0)
            return observedAtMs + uint64(castTimeMs);
    }
    return 0;
}

uint64 RegionGeneration(ObjectGuid guid, uint32 spellId)
{
    return guid.GetRawValue() ^ (uint64(spellId) << 32);
}

void AppendRegion(BotEncounter::Blackboard& board, WorldObject* source,
    uint32 spellId, float radius, uint64 expiresAtMs)
{
    if (!source || !source->IsInWorld() || radius <= 0.0f)
        return;

    BotEncounter::SpatialRegion region;
    region.Id = "shared_hazard:" + std::to_string(
        source->GetGUID().GetRawValue()) + ":" + std::to_string(spellId);
    region.Kind = BotEncounter::RegionKind::Hazard;
    region.SourceGuid = source->GetGUID();
    region.SpellId = spellId;
    region.Center = { source->GetPositionX(), source->GetPositionY(),
        source->GetPositionZ() };
    region.Radius = radius;
    region.Danger = 1.0f;
    region.Generation = RegionGeneration(region.SourceGuid, spellId);
    region.ExpiresAtMs = expiresAtMs;
    board.Regions.push_back(std::move(region));
}

SpellInfo const* CurrentHazardSpell(Creature* creature, float& radius)
{
    if (!creature)
        return nullptr;

    for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL,
        CURRENT_CHANNELED_SPELL })
    {
        Spell* spell = creature->GetCurrentSpell(spellType);
        SpellInfo const* spellInfo = spell ? spell->GetSpellInfo() : nullptr;
        float const spellRadius = SpellRadius(spellInfo, creature);
        if (IsHazardSpell(spellInfo, spellRadius))
        {
            radius = spellRadius;
            return spellInfo;
        }
    }
    return nullptr;
}

void AppendTriggerRegion(BotEncounter::Blackboard& board, Creature* creature,
    uint64 observedAtMs)
{
    if (!creature || !creature->IsAlive()
        || (!creature->IsTrigger()
            && !creature->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE)))
        return;

    float radius = 0.0f;
    SpellInfo const* spellInfo = CurrentHazardSpell(creature, radius);
    if (!spellInfo)
        return;
    AppendRegion(board, creature, spellInfo->Id, radius,
        ExpiryFromSpell(observedAtMs, spellInfo, creature));
}

void AppendTrapRegion(BotEncounter::Blackboard& board, GameObject* gameObject,
    uint64 observedAtMs)
{
    if (!gameObject || !gameObject->isSpawned()
        || gameObject->GetGoType() != GAMEOBJECT_TYPE_TRAP
        || !gameObject->GetGOInfo())
        return;

    GameObjectTemplate const* info = gameObject->GetGOInfo();
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(info->trap.spell);
    float radius = info->trap.radius
        ? float(info->trap.radius) / 2.0f
        : SpellRadius(spellInfo, gameObject);
    // This is the same native fallback used by GameObject::Update for
    // battleground traps. It is retained only when the server exposes the
    // exact trap contract (cooldown == 3), never as a generic guessed radius.
    if (radius <= 0.0f && info->trap.cooldown == 3)
        radius = 3.0f;
    if (!IsHazardSpell(spellInfo, radius))
        return;

    uint64 expiresAtMs = observedAtMs;
    if (info->trap.autoClose)
        expiresAtMs += uint64(info->trap.autoClose);
    else
        expiresAtMs = ExpiryFromSpell(observedAtMs, spellInfo, gameObject);
    AppendRegion(board, gameObject, info->trap.spell, radius, expiresAtMs);
}

void AppendDynamicRegion(BotEncounter::Blackboard& board,
    DynamicObject* dynamicObject, uint64 observedAtMs)
{
    if (!dynamicObject || !dynamicObject->IsInWorld())
        return;

    SpellInfo const* spellInfo = dynamicObject->GetSpellInfo();
    float radius = dynamicObject->GetRadius();
    if (radius <= 0.0f)
        radius = SpellRadius(spellInfo, dynamicObject);
    if (!IsHazardSpell(spellInfo, radius))
        return;
    int32 durationMs = dynamicObject->GetDuration();
    uint64 expiresAtMs = durationMs > 0
        ? observedAtMs + uint64(durationMs)
        : ExpiryFromSpell(observedAtMs, spellInfo, dynamicObject);
    AppendRegion(board, dynamicObject, dynamicObject->GetSpellId(), radius,
        expiresAtMs);
}

void AppendAreaTriggerRegion(BotEncounter::Blackboard& board,
    AreaTrigger* areaTrigger, uint64 observedAtMs)
{
    if (!areaTrigger || !areaTrigger->IsInWorld())
        return;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(
        areaTrigger->GetSpellId());
    float const radius = SpellRadius(spellInfo, areaTrigger);
    if (!IsHazardSpell(spellInfo, radius))
        return;
    int32 durationMs = areaTrigger->GetDuration();
    uint64 expiresAtMs = durationMs > 0
        ? observedAtMs + uint64(durationMs)
        : ExpiryFromSpell(observedAtMs, spellInfo, areaTrigger);
    AppendRegion(board, areaTrigger, areaTrigger->GetSpellId(), radius,
        expiresAtMs);
}
}

namespace BotEncounterHazards
{
void Populate(BotEncounter::Blackboard& board,
    std::vector<Player*> const& observers,
    uint64 observedAtMs)
{
    board.Regions.clear();
    for (Player* observer : observers)
    {
        if (!observer || !observer->IsInWorld())
            continue;

        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(observer, HazardScanRadius);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange>
            searcher(observer, objects, check);
        Cell::VisitAllObjects(observer, searcher, HazardScanRadius);
        for (WorldObject* object : objects)
        {
            if (!object || object->GetMap() != observer->GetMap())
                continue;
            if (DynamicObject* dynamicObject = object->ToDynObject())
                AppendDynamicRegion(board, dynamicObject, observedAtMs);
            else if (AreaTrigger* areaTrigger = object->ToAreaTrigger())
                AppendAreaTriggerRegion(board, areaTrigger, observedAtMs);
            else if (GameObject* gameObject = object->ToGameObject())
                AppendTrapRegion(board, gameObject, observedAtMs);
            else if (Creature* creature = object->ToCreature())
                AppendTriggerRegion(board, creature, observedAtMs);
        }
    }

    std::sort(board.Regions.begin(), board.Regions.end(),
        [](BotEncounter::SpatialRegion const& left,
            BotEncounter::SpatialRegion const& right)
        {
            if (left.SourceGuid != right.SourceGuid)
                return left.SourceGuid < right.SourceGuid;
            return left.SpellId < right.SpellId;
        });
    board.Regions.erase(std::unique(board.Regions.begin(), board.Regions.end(),
        [](BotEncounter::SpatialRegion const& left,
            BotEncounter::SpatialRegion const& right)
        {
            return left.SourceGuid == right.SourceGuid
                && left.SpellId == right.SpellId;
        }), board.Regions.end());
}
}
