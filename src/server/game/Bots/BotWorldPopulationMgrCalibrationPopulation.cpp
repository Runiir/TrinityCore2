#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotMgr.h"

#include "CellImpl.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "PathGenerator.h"
#include "PhasingHandler.h"
#include "Pet.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TerrainMgr.h"
#include "TemporarySummon.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <memory>
#include <string>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

bool UsesRangedAoeCalibrationLane(std::string const& spec)
{
    static constexpr std::array<char const*, 12> RangedAoeSpecs =
    {
        "balance_druid", "beast_mastery_hunter", "marksmanship_hunter", "survival_hunter",
        "shadow_priest", "elemental_shaman", "arcane_mage", "fire_mage", "frost_mage",
        "affliction_warlock", "demonology_warlock", "destruction_warlock"
    };
    return std::find(RangedAoeSpecs.begin(), RangedAoeSpecs.end(), spec)
        != RangedAoeSpecs.end();
}
}

void BotWorldPopulationMgr::EnsureCalibrationPopulation()
{
    if (!Cohort().CalibrationFailureReason.empty())
        return;

    static constexpr uint32 IsolatedSingleTargetDummyEntry =
        BotCalibrationFixtureContractGenerated::TargetEntry;
    // WoWSims FreshDefaultTargetConfig at the campaign's pinned revision uses
    // CharacterLevel + 3, 11,977 armor, and MobTypeMechanical. The fixture is
    // explicitly non-certifying, but its comparison target must still expose
    // those exact native inputs before any scored action is allowed.
    static constexpr uint8 IsolatedSingleTargetLevel =
        BotCalibrationFixtureContractGenerated::TargetLevel;
    static constexpr uint32 IsolatedSingleTargetArmor =
        BotCalibrationFixtureContractGenerated::TargetArmor;
    static constexpr uint32 IsolatedSingleTargetCreatureType =
        BotCalibrationFixtureContractGenerated::TargetCreatureType;
    // The narrowest configured-to-boundary margin is the 22% fixture value to
    // the 20% execute gate. One billion health therefore gives that interval a
    // 20M native-damage safety margin; per-damage-event observations
    // independently prove that no interval consumes the margin.
    static constexpr uint32 IsolatedSingleTargetMaxHealth =
        BotCalibrationFixtureContractGenerated::TargetMaxHealth;
    // The previous -9060,520 lane sat below the local liquid surface. Ranged
    // profiles legitimately approached their target and exhausted the
    // three-minute breath timer, producing six environmental self-damage
    // ticks that looked like rotation collateral. This nearby dry anchor has
    // no static creature within 99 yards; the runtime hostile, liquid, LOS,
    // and complete-path checks below remain authoritative.
    static constexpr float IsolatedSingleTargetDummyX = -9140.0f;
    static constexpr float IsolatedSingleTargetDummyY = 520.0f;
    static constexpr float IsolatedSingleTargetGroundZ = 75.8f;
    static constexpr float IsolatedSingleTargetRangedRadius = 15.0f;
    static constexpr float MinimumIsolatedDummyClearance = 45.0f;
    bool const clusteredDummyMode = Cohort().CalibrationMode == "aoe_300"
        || Cohort().CalibrationMode == "tank_threat_300";
    bool const rangedAoeMode = Cohort().CalibrationMode == "aoe_300"
        && UsesRangedAoeCalibrationLane(Cohort().CalibrationTargetSpec);
    bool const demonologyAoeMode = Cohort().CalibrationMode == "aoe_300"
        && Cohort().CalibrationTargetSpec == "demonology_warlock";
    bool const rangedSingleTargetMode = Cohort().CalibrationMode == "single_target_300"
        && UsesRangedAoeCalibrationLane(Cohort().CalibrationTargetSpec);
    bool const isolatedSingleTargetMode = Cohort().CalibrationMode == "single_target_300";
    if (isolatedSingleTargetMode)
    {
        Cohort().CalibrationFixtureExpectedTargetLevel =
            IsolatedSingleTargetLevel;
        Cohort().CalibrationFixtureExpectedTargetArmor =
            IsolatedSingleTargetArmor;
        Cohort().CalibrationFixtureExpectedTargetCreatureType =
            IsolatedSingleTargetCreatureType;
        Cohort().CalibrationFixtureExpectedTargetMaxHealth =
            IsolatedSingleTargetMaxHealth;
    }
    // Single-target comparison uses one temporary server-owned dummy in an open
    // fixture lane, at least 45 yards from every other hostile visible to the bot.
    // This preserves legitimate single-target spells with area-capable semantics
    // without allowing collateral damage or procs to inflate the score. AoE and
    // tank-threat windows retain the permanent training cluster. Ranged AoE uses
    // its known courtyard lane, while Demonology AoE uses the open centroid that
    // keeps the cluster inside Hellfire/Immolation range.
    float calibrationX = isolatedSingleTargetMode
        ? IsolatedSingleTargetDummyX + IsolatedSingleTargetRangedRadius
        : (demonologyAoeMode ? -8967.4f
            : (rangedAoeMode ? -8947.0f : (clusteredDummyMode ? -8965.59f : -8962.05f)));
    float calibrationY = isolatedSingleTargetMode
        ? IsolatedSingleTargetDummyY
        : (demonologyAoeMode ? -152.9f
            : (rangedAoeMode ? -159.438f : (clusteredDummyMode ? -158.66f : -157.16f)));
    float const calibrationZ = isolatedSingleTargetMode
        ? IsolatedSingleTargetGroundZ : 81.5856f;
    float calibrationSpawnZ = calibrationZ;
    float calibrationFixtureGroundZ = calibrationZ;
    struct CalibrationSpawnCandidate
    {
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float HeightDelta = 0.0f;
        float DistanceError = 0.0f;
    };
    std::vector<CalibrationSpawnCandidate> calibrationSpawnCandidates;
    BotCalibrationFixtureContractGenerated::SpecContract const*
        distanceContract = isolatedSingleTargetMode
            ? BotCalibrationFixtureContractGenerated::FindSpec(
                Cohort().CalibrationTargetSpec)
            : nullptr;
    if (isolatedSingleTargetMode)
    {
        if (!distanceContract)
        {
            Cohort().LastPopulationFailureReason =
                "calibration_fixture_spec_contract_missing";
            Cohort().CalibrationFailureReason = Cohort().LastPopulationFailureReason;
            Cohort().CalibrationWindowComplete = true;
            return;
        }
        // The old fixture used the dummy's historical reference Z for both
        // player placement and terrain lookup.  At the isolated lane the real
        // floor is several yards lower, leaving melee profiles off-mesh and
        // able to use only ranged actions/pets.  Resolve the server-owned
        // pre-activation placement against terrain before loading the bot; no
        // active player is relocated and normal movement remains authoritative
        // once the calibration controller starts.
        std::shared_ptr<TerrainInfo> terrain = sTerrainMgr.LoadTerrain(0);
        // Seed the collision query from the raw map surface rather than the
        // historical fixture Z.  GetStaticHeight only accepts map ground at
        // or below the supplied probe; a valid dry hill above that old Z must
        // not be misclassified as missing terrain.
        float const fixtureGridZ = terrain ? terrain->GetGridHeight(
            PhasingHandler::GetEmptyPhaseShift(), 0,
            IsolatedSingleTargetDummyX, IsolatedSingleTargetDummyY)
            : INVALID_HEIGHT;
        float const fixtureGroundZ = terrain
            && std::isfinite(fixtureGridZ) && fixtureGridZ > INVALID_HEIGHT
            ? terrain->GetStaticHeight(
                PhasingHandler::GetEmptyPhaseShift(), 0,
                IsolatedSingleTargetDummyX, IsolatedSingleTargetDummyY,
                fixtureGridZ + 4.0f, true, 64.0f)
            : INVALID_HEIGHT;
        if (!std::isfinite(fixtureGroundZ)
            || fixtureGroundZ <= INVALID_HEIGHT)
        {
            Cohort().LastPopulationFailureReason =
                "calibration_isolated_target_ground_unavailable";
            Cohort().CalibrationFailureReason =
                Cohort().LastPopulationFailureReason;
            Cohort().CalibrationWindowComplete = true;
            return;
        }
        if (terrain->IsInWater(PhasingHandler::GetEmptyPhaseShift(), 0,
                IsolatedSingleTargetDummyX, IsolatedSingleTargetDummyY,
                fixtureGroundZ))
        {
            Cohort().LastPopulationFailureReason =
                "calibration_isolated_target_not_dry_land";
            Cohort().CalibrationFailureReason =
                Cohort().LastPopulationFailureReason;
            Cohort().CalibrationWindowComplete = true;
            return;
        }
        calibrationFixtureGroundZ = fixtureGroundZ;

        // Both the historical four-yard melee point and the historical
        // fifteen-yard ranged point can land on a different terrain shelf.
        // Search deterministic rings around the observed fixture floor for
        // both lanes. The post-summon native reach/LOS/path gate below remains
        // the final authority.
        float const distanceMidpoint = 0.5f
            * (distanceContract->RuntimeMinimumDistanceYards
                + distanceContract->RuntimeMaximumDistanceYards);
        std::vector<float> const candidateRadii = rangedSingleTargetMode
            ? std::vector<float>{
                distanceContract->RuntimeMinimumDistanceYards,
                distanceMidpoint,
                distanceContract->RuntimeMaximumDistanceYards }
            : std::vector<float>{ 2.0f, 2.5f, 3.0f };
        constexpr uint32 CandidateAngles = 16;
        for (float radius : candidateRadii)
            for (uint32 index = 0; index < CandidateAngles; ++index)
            {
                float const angle = 2.0f * float(M_PI)
                    * float(index) / float(CandidateAngles);
                float const candidateX = IsolatedSingleTargetDummyX
                    + std::cos(angle) * radius;
                float const candidateY = IsolatedSingleTargetDummyY
                    + std::sin(angle) * radius;
                float const candidateZ = terrain->GetStaticHeight(
                    PhasingHandler::GetEmptyPhaseShift(), 0, candidateX,
                    candidateY, fixtureGroundZ + 4.0f, true, 64.0f);
                if (!std::isfinite(candidateZ)
                    || candidateZ <= INVALID_HEIGHT)
                    continue;
                if (terrain->IsInWater(PhasingHandler::GetEmptyPhaseShift(),
                        0, candidateX, candidateY, candidateZ))
                    continue;
                float const heightDelta = std::fabs(candidateZ - fixtureGroundZ);
                // A ranged point may legitimately be on the lower side of a
                // walkable slope while remaining at the exact three-dimensional
                // comparison distance. Do not discard it solely because its
                // terrain height differs from the target; the native path gate
                // below is authoritative. Melee still requires the same-floor
                // bound before the stronger native reach check.
                if (!rangedSingleTargetMode && heightDelta > 1.0f)
                    continue;
                float const approximateDistance = std::sqrt(
                    radius * radius + heightDelta * heightDelta);
                if (approximateDistance
                        < distanceContract->RuntimeMinimumDistanceYards - 0.25f
                    || approximateDistance
                        > distanceContract->RuntimeMaximumDistanceYards + 0.25f)
                    continue;
                calibrationSpawnCandidates.push_back({ candidateX,
                    candidateY, candidateZ, heightDelta,
                    std::fabs(approximateDistance
                        - distanceMidpoint) });
            }
        std::stable_sort(calibrationSpawnCandidates.begin(),
            calibrationSpawnCandidates.end(),
            [](CalibrationSpawnCandidate const& left,
                CalibrationSpawnCandidate const& right)
            {
                if (left.DistanceError != right.DistanceError)
                    return left.DistanceError < right.DistanceError;
                return left.HeightDelta < right.HeightDelta;
            });
        if (calibrationSpawnCandidates.empty())
        {
            Cohort().LastPopulationFailureReason = rangedSingleTargetMode
                ? "calibration_isolated_ranged_ground_unavailable"
                : "calibration_isolated_melee_ground_unavailable";
            Cohort().CalibrationFailureReason = Cohort().LastPopulationFailureReason;
            Cohort().CalibrationWindowComplete = true;
            return;
        }
        calibrationX = calibrationSpawnCandidates.front().X;
        calibrationY = calibrationSpawnCandidates.front().Y;
        calibrationSpawnZ = calibrationSpawnCandidates.front().Z;
        if (!std::isfinite(calibrationSpawnZ)
            || calibrationSpawnZ <= INVALID_HEIGHT)
        {
            Cohort().LastPopulationFailureReason =
                "calibration_isolated_spawn_ground_unavailable";
            Cohort().CalibrationFailureReason =
                Cohort().LastPopulationFailureReason;
            Cohort().CalibrationWindowComplete = true;
            return;
        }
    }
    uint32 calibrationPopulation = Cohort().CalibrationMode == "healer_controlled_damage_300" ? 5
        : (Cohort().CalibrationMode == "tank_threat_300" ? 2 : 1);
    auto restoreWarmupBot = [](Player* bot)
    {
        if (!bot || bot->IsAlive())
            return false;
        bot->CombatStopWithPets(true);
        bot->CastStop();
        bot->ResurrectPlayer(1.0f, false);
        bot->SpawnCorpseBones();
        bot->SetFullHealth();
        if (bot->GetMaxPower(POWER_MANA))
            bot->SetPower(POWER_MANA, bot->GetMaxPower(POWER_MANA));
        if (bot->getClass() == CLASS_WARLOCK && bot->GetMaxPower(POWER_SOUL_SHARDS))
            bot->SetPower(POWER_SOUL_SHARDS, bot->GetMaxPower(POWER_SOUL_SHARDS));
        return true;
    };
    if (!Cohort().CalibrationScoredStartedMs)
        for (WorldBotState& state : Party().CalibrationBots)
            if (Player* bot = GetLoadedBot(state); restoreWarmupBot(bot))
            {
                state.DecisionTimer = 0;
                TC_LOG_INFO("server", "BotWorld calibration warmup restored dead bot=%s",
                    state.Guid.ToString().c_str());
            }

    uint32 attempts = 0;
    uint32 const maximumPopulationAttempts = isolatedSingleTargetMode
        ? uint32(calibrationSpawnCandidates.size())
        : calibrationPopulation * 4;
    while (Cohort().CalibrationActive && !Cohort().CalibrationWindowComplete
        && Party().CalibrationBots.size() < calibrationPopulation
        && attempts++ < maximumPopulationAttempts)
    {
        size_t slot = Party().CalibrationBots.size();
        uint32 candidateGuid = SelectCalibrationPoolCandidateGuid(slot);
        if (!candidateGuid)
            break;

        if (!ClaimBotGuid(candidateGuid, "calibration_" + std::to_string(slot)))
            continue;

        CalibrationSpawnCandidate const* spawnCandidate =
            isolatedSingleTargetMode
                ? &calibrationSpawnCandidates[attempts - 1] : nullptr;
        float x = spawnCandidate ? spawnCandidate->X
            : calibrationX + float(slot % 2) * 2.0f;
        float y = spawnCandidate ? spawnCandidate->Y
            : calibrationY + float(slot / 2) * 2.0f;
        float z = spawnCandidate ? spawnCandidate->Z : calibrationSpawnZ;
        Player* bot = sBotMgr->SpawnWorldBot("any", std::to_string(candidateGuid), 0, x, y, z, 0.0f);
        if (!bot)
        {
            if (ReleaseBotGuid(candidateGuid))
                CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", candidateGuid);
            continue;
        }

        if (isolatedSingleTargetMode
            && Cohort().CalibrationFixtureTargetGuid.IsEmpty())
        {
            Map* map = bot->GetMap();
            float fixtureZ = map ? map->GetHeight(bot->GetPhaseShift(),
                IsolatedSingleTargetDummyX, IsolatedSingleTargetDummyY,
                calibrationFixtureGroundZ + 4.0f, true, 64.0f) : INVALID_HEIGHT;
            TempSummon* fixtureTarget = nullptr;
            if (map && fixtureZ != INVALID_HEIGHT)
            {
                SummonCreatureExtraArgs fixtureArgs;
                fixtureArgs.SetSummonDuration(20 * 60 * IN_MILLISECONDS);
                fixtureArgs.CreatureLevel = IsolatedSingleTargetLevel;
                fixtureArgs.SummonHealth = IsolatedSingleTargetMaxHealth;
                fixtureTarget = map->SummonCreature(IsolatedSingleTargetDummyEntry,
                    Position{ IsolatedSingleTargetDummyX,
                        IsolatedSingleTargetDummyY, fixtureZ, 0.0f },
                    fixtureArgs);
            }

            // Set the native physical armor basis once, immediately after the
            // server-owned summon and before scoring. SetArmor alone only
            // writes the derived field; applying and then clearing reference
            // armor debuffs would recalculate it from the level-3 template's
            // base value. Pinning UNIT_MOD_ARMOR preserves the level-88 target
            // across ordinary aura recalculation without any scored-tick
            // fixture mutation.
            if (fixtureTarget)
            {
                fixtureTarget->SetStatFlatModifier(UNIT_MOD_ARMOR, BASE_VALUE,
                    float(IsolatedSingleTargetArmor));
                fixtureTarget->UpdateArmor();
            }

            // The scan radius is also the conservative lower bound when no
            // other attackable creature is present. Avoid serializing an
            // implementation-specific floating-point infinity/max value.
            float nearestHostileClearance = 120.0f;
            if (fixtureTarget)
            {
                std::vector<WorldObject*> nearbyObjects;
                Trinity::AllWorldObjectsInRange fixtureCheck(fixtureTarget, 120.0f);
                Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange>
                    fixtureSearcher(fixtureTarget, nearbyObjects, fixtureCheck);
                Cell::VisitAllObjects(fixtureTarget, fixtureSearcher, 120.0f);
                for (WorldObject* object : nearbyObjects)
                {
                    Creature* other = object ? object->ToCreature() : nullptr;
                    if (!other || other == fixtureTarget || !other->IsAlive()
                        || !bot->IsValidAttackTarget(other))
                        continue;
                    nearestHostileClearance = std::min(nearestHostileClearance,
                        std::min(fixtureTarget->GetExactDist(other),
                            bot->GetExactDist(other)));
                }
            }

            bool nativeLineOfSight = fixtureTarget
                && bot->IsWithinLOSInMap(fixtureTarget);
            bool nativePathReachable = false;
            bool nativePathDryLand = false;
            bool nativePathCalculated = false;
            PathType nativePathType = PATHFIND_NOPATH;
            if (fixtureTarget)
            {
                PathGenerator nativePath(bot);
                nativePathCalculated = nativePath.CalculatePath(
                    fixtureTarget->GetPositionX(),
                    fixtureTarget->GetPositionY(),
                    fixtureTarget->GetPositionZ(), false);
                nativePathType = nativePath.GetPathType();
                nativePathReachable = nativePathCalculated
                    && (nativePathType & PATHFIND_NORMAL)
                    && !(nativePathType & PATHFIND_NOPATH)
                    && !(nativePathType & PATHFIND_NOT_USING_PATH)
                    && !(nativePathType & PATHFIND_INCOMPLETE)
                    && !(nativePathType & PATHFIND_SHORTCUT)
                    && !(nativePathType & PATHFIND_FARFROMPOLY);
                nativePathDryLand = nativePathReachable
                    && std::all_of(nativePath.GetPath().begin(),
                        nativePath.GetPath().end(),
                        [map, bot](G3D::Vector3 const& point)
                        {
                            ZLiquidStatus const liquidStatus =
                                map->GetLiquidStatus(bot->GetPhaseShift(),
                                    point.x, point.y, point.z,
                                    map_liquidHeaderTypeFlags::AllLiquids,
                                    nullptr, bot->GetCollisionHeight());
                            return !(liquidStatus
                                & (LIQUID_MAP_IN_WATER
                                    | LIQUID_MAP_UNDER_WATER));
                        });
            }
            bool const nativeDryLand = fixtureTarget
                && !bot->IsInWater() && !bot->IsUnderWater()
                && !fixtureTarget->IsInWater()
                && !fixtureTarget->IsUnderWater()
                && nativePathDryLand;
            bool const nativeMeleeReachable = fixtureTarget
                && bot->IsWithinMeleeRange(fixtureTarget);
            bool const nativeMeleeFixtureReady = rangedSingleTargetMode
                || (nativeMeleeReachable && nativeLineOfSight
                    && nativePathReachable);
            float const botTargetDistance = fixtureTarget
                ? bot->GetExactDist(fixtureTarget) : 0.0f;
            bool const fixtureGeometryValidated = rangedSingleTargetMode
                ? (nativeLineOfSight
                    && botTargetDistance
                        >= distanceContract->RuntimeMinimumDistanceYards
                    && botTargetDistance
                        <= distanceContract->RuntimeMaximumDistanceYards
                    && nativePathReachable && nativeDryLand)
                : (nativeMeleeFixtureReady && nativeDryLand);
            bool const fixtureTargetFidelityValidated = fixtureTarget
                && fixtureTarget->getLevel() == IsolatedSingleTargetLevel
                && fixtureTarget->GetArmor() == IsolatedSingleTargetArmor
                && fixtureTarget->GetCreatureType()
                    == IsolatedSingleTargetCreatureType
                && fixtureTarget->GetMaxHealth()
                    == IsolatedSingleTargetMaxHealth;
            bool const fixtureTargetAttackable = fixtureTarget
                && bot->IsValidAttackTarget(fixtureTarget);
            bool const fixtureClearanceValidated = fixtureTarget
                && nearestHostileClearance >= MinimumIsolatedDummyClearance;
            bool const rangedDistanceValidated = !rangedSingleTargetMode
                || (botTargetDistance
                        >= distanceContract->RuntimeMinimumDistanceYards
                    && botTargetDistance
                        <= distanceContract->RuntimeMaximumDistanceYards);

            bool const fixtureValid = fixtureTarget
                && fixtureTargetAttackable
                && fixtureClearanceValidated
                && fixtureGeometryValidated
                && fixtureTargetFidelityValidated;
            if (!fixtureValid)
            {
                TC_LOG_INFO("server",
                    "BotWorld calibration isolated target rejected bot=%s target=%s "
                    "attackable=%u clearance=%.3f clearance_ok=%u los=%u "
                    "path_calculated=%u path_type=%u path=%u "
                    "path_dry=%u dry=%u melee=%u distance=%.3f "
                    "distance_ok=%u geometry=%u fidelity=%u",
                    bot->GetGUID().ToString().c_str(),
                    fixtureTarget ? fixtureTarget->GetGUID().ToString().c_str() : "none",
                    uint32(fixtureTargetAttackable), nearestHostileClearance,
                    uint32(fixtureClearanceValidated), uint32(nativeLineOfSight),
                    uint32(nativePathCalculated), uint32(nativePathType),
                    uint32(nativePathReachable), uint32(nativePathDryLand),
                    uint32(nativeDryLand), uint32(nativeMeleeReachable),
                    botTargetDistance, uint32(rangedDistanceValidated),
                    uint32(fixtureGeometryValidated),
                    uint32(fixtureTargetFidelityValidated));
                if (fixtureTarget)
                    fixtureTarget->UnSummon();
                ObjectGuid const failedGuid = bot->GetGUID();
                sBotMgr->RemoveWorldBot(failedGuid);
                if (ReleaseBotGuid(candidateGuid))
                    CharacterDatabase.DirectPExecute(
                        "UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u",
                        candidateGuid);
                bool const retryAlternateSpawn =
                    attempts < maximumPopulationAttempts
                    && fixtureTarget && fixtureTargetFidelityValidated
                    && fixtureTargetAttackable && fixtureClearanceValidated
                    && (!nativeLineOfSight || !rangedDistanceValidated
                        || !nativePathReachable || !nativeDryLand
                        || !nativeMeleeFixtureReady);
                if (retryAlternateSpawn)
                    continue;
                if (!fixtureTarget)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_summon_failed";
                else if (!fixtureTargetFidelityValidated)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_fidelity_mismatch";
                else if (!fixtureTargetAttackable)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_not_attackable";
                else if (!fixtureClearanceValidated)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_hostile_clearance_failed";
                else if (!nativeLineOfSight)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_line_of_sight_failed";
                else if (!rangedDistanceValidated)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_distance_failed";
                else if (!nativePathReachable)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_path_failed";
                else if (!nativeDryLand)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_not_dry_land";
                else if (!nativeMeleeFixtureReady)
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_melee_fixture_unreachable";
                else
                    Cohort().LastPopulationFailureReason =
                        "calibration_isolated_target_provisioning_failed";
                Cohort().CalibrationFailureReason =
                    Cohort().LastPopulationFailureReason;
                Cohort().CalibrationWindowComplete = true;
                break;
            }

            Cohort().CalibrationFixtureTargetGuid = fixtureTarget->GetGUID();
            Cohort().CalibrationFixtureTargetEntry = fixtureTarget->GetEntry();
            Cohort().CalibrationFixtureObservedTargetLevel =
                fixtureTarget->getLevel();
            Cohort().CalibrationFixtureObservedTargetArmor =
                fixtureTarget->GetArmor();
            Cohort().CalibrationFixtureObservedTargetCreatureType =
                fixtureTarget->GetCreatureType();
            Cohort().CalibrationFixtureObservedTargetCreatureTypeMask =
                fixtureTarget->GetCreatureTypeMask();
            Cohort().CalibrationFixtureObservedTargetMaxHealth =
                fixtureTarget->GetMaxHealth();
            Cohort().CalibrationFixtureTargetMapId = fixtureTarget->GetMapId();
            Cohort().CalibrationFixtureTargetX = fixtureTarget->GetPositionX();
            Cohort().CalibrationFixtureTargetY = fixtureTarget->GetPositionY();
            Cohort().CalibrationFixtureTargetZ = fixtureTarget->GetPositionZ();
            Cohort().CalibrationFixtureTargetNearestHostileClearance =
                nearestHostileClearance;
            Cohort().CalibrationFixtureTargetProvisionedAtMs = NowMs();
            Cohort().CalibrationFixtureBotSpawnX = bot->GetPositionX();
            Cohort().CalibrationFixtureBotSpawnY = bot->GetPositionY();
            Cohort().CalibrationFixtureBotSpawnZ = bot->GetPositionZ();
            Cohort().CalibrationFixtureBotTargetDistance = botTargetDistance;
            Cohort().CalibrationFixtureNativeLineOfSight = nativeLineOfSight;
            Cohort().CalibrationFixtureNativePathReachable =
                nativePathReachable;
            Cohort().CalibrationFixtureNativeMeleeReachable =
                nativeMeleeReachable;
            Cohort().CalibrationFixtureNativeDryLand = nativeDryLand;
            Cohort().CalibrationFixtureGeometryValidated =
                fixtureGeometryValidated;
            Cohort().CalibrationFixtureProfileLane =
                rangedSingleTargetMode ? "ranged" : "melee";
        }

        bool const restoredDeadBot = restoreWarmupBot(bot);
        bot->SetFullHealth();
        if (bot->GetMaxPower(POWER_MANA))
            bot->SetPower(POWER_MANA, bot->GetMaxPower(POWER_MANA));
        if (bot->getClass() == CLASS_WARLOCK && bot->GetMaxPower(POWER_SOUL_SHARDS))
            bot->SetPower(POWER_SOUL_SHARDS, bot->GetMaxPower(POWER_SOUL_SHARDS));

        WorldBotState state;
        state.Guid = bot->GetGUID();
        state.DecisionTimer = 0;
        state.LastX = bot->GetPositionX();
        state.LastY = bot->GetPositionY();
        state.LastZ = bot->GetPositionZ();
        state.SpawnedMs = NowMs();
        state.SpawnSource = "combat_calibration";
        state.SpawnMapId = bot->GetMapId();
        state.SpawnX = bot->GetPositionX();
        state.SpawnY = bot->GetPositionY();
        state.SpawnZ = bot->GetPositionZ();
        state.SpawnO = bot->GetOrientation();
        Party().CalibrationBots.push_back(state);
        if (slot == 0)
            Cohort().CalibrationTargetGuid = bot->GetGUID();

        CalibrationMetrics metrics;
        Cohort().CalibrationMetricsByGuid.emplace(bot->GetGUID().GetCounter(), std::move(metrics));
        TC_LOG_INFO("server", "BotWorld calibration clone spawned bot=%s slot=%zu map=%u position=%f,%f,%f restored_dead_state=%u",
            bot->GetGUID().ToString().c_str(), slot, bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(),
            restoredDeadBot ? 1u : 0u);
    }
}

