#ifndef TRINITY_BOT_ADAPTIVE_MALORIAK_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_MALORIAK_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakDuties.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakGeometry.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakPlan.h"

#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

// Maloriak (Blackwing Descent) adaptive encounter owner. Research and
// sources: docs/bot_raids/strategies/t11/blackwing_descent/maloriak.md and
// experiments/configs/cata_raid_encounters/blackwing_descent/maloriak_*.json.
//
// Every tick is a pure function of the cohort blackboard: duties come from
// capabilities (Duties.h), anchors from the observed boss/tank frame
// (Geometry.h). The plan only names targets, native casts and ordinary
// movement destinations for the dispatch to revalidate.
namespace BotEncounter
{
class AdaptiveMaloriakStrategy
{
public:
    static constexpr uint32 BossEntry = Maloriak::BossEntry;
    static constexpr uint32 AberrationEntry = Maloriak::AberrationEntry;
    static constexpr uint32 FreezeEntry = Maloriak::FlashFreezeEntry;
    static constexpr uint32 PrimeSubjectEntry = Maloriak::PrimeSubjectEntry;
    static constexpr uint32 AbsoluteZeroEntry = Maloriak::AbsoluteZeroEntry;

    // Aberrations are burned in the Green slime window (+100% damage taken),
    // when six or more are loose, or before the 25% release of the reserve.
    static constexpr std::size_t OverflowBurnCount = 6;
    static constexpr float CleanupBeforePhaseTwoPct = 30.0f;

    // Hazard radii come from client rows: Absolute Zero trigger 3 yd and
    // explosion 5 yd, Magma Jets fire 3 yd, Shatter 5 yd, Biting Chill 3 yd.
    static constexpr float AbsoluteZeroDanger = 7.0f;
    static constexpr float AbsoluteZeroExit = 11.0f;
    static constexpr float MagmaFireDanger = 4.5f;
    static constexpr float MagmaFireExit = 7.5f;
    static constexpr float ShatterDanger = 5.5f;
    static constexpr float ShatterExit = 8.0f;
    static constexpr float BitingChillDanger = 6.0f;
    static constexpr float BitingChillExit = 8.0f;
    static constexpr float MagmaJetsSidestep = 8.0f;

    static constexpr float RangedSlotTolerance = 4.0f;
    static constexpr float MeleeSlotTolerance = 2.5f;
    static constexpr float StagingTolerance = 3.0f;
    static constexpr float AddAnchorTolerance = 6.0f;
    // Aberrations leap out of chambers on both side walls, 50+ yards apart.
    static constexpr float LooseAddPickupRange = 90.0f;
    static constexpr float PriorityHealBelowPct = 85.0f;
    // The spot healer yields to the ordinary lowest-health scan while a tank
    // is low or someone else is clearly lower.
    static constexpr float PriorityHealTankFloorPct = 50.0f;
    static constexpr float PriorityHealMarginPct = 10.0f;
    // Pull gates: everyone alive, recovered and on the entrance line.
    static constexpr float PrepullHealthPct = 70.0f;
    static constexpr float PrepullStagedYards = 15.0f;
    // With Green (the slime window) this close, loose Aberrations wait for it.
    static constexpr uint32 GreenImminentMs = 15000;
    static constexpr std::size_t OverflowBurnCountBeforeGreen = 9;

    AdaptiveMaloriakPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        AdaptiveMaloriakPlan plan;
        if (board.Route.NodeId != Maloriak::EncounterNode)
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;
        Maloriak::Observation const observation = Maloriak::Observe(board);
        if (!observation.Boss)
            return plan;
        ActorSnapshot const& boss = *observation.Boss;
        plan.OwnsNode = true;
        plan.Phase = Maloriak::PhaseName(observation.CurrentPhase);
        std::string_view const botRole = bot->Role.empty()
            ? role : std::string_view(bot->Role);
        Maloriak::TankDuties const tanks = Maloriak::ResolveTanks(board);

        if (observation.CurrentPhase == Maloriak::Phase::Prepull)
        {
            ProposePrepull(board, *bot, boss, botRole, tanks, plan);
            return plan;
        }
        if (Maloriak::IsFrozen(*bot))
        {
            plan.Duty = "flash_frozen";
            return plan;
        }

        AssignInterrupt(board, observation, botGuid, plan);
        AssignDispel(board, observation, botGuid, plan);
        plan.LustWindow = observation.CurrentPhase == Maloriak::Phase::PhaseTwo
            && Maloriak::ResolveLustOwner(board) == botGuid;
        if (botRole == "healer")
            plan.PriorityHealTarget = SelectPriorityHeal(board, botGuid);

        Maloriak::BossFrame const frame = Maloriak::ResolveFrame(boss,
            Maloriak::FindPlayer(board, tanks.MainTank));
        bool const mainTank = botGuid == tanks.MainTank;
        plan.Movement = ProposeHazard(board, observation, *bot, mainTank,
            botRole == "tank", frame);

        if (mainTank)
            SelectMainTank(boss, botGuid, plan);
        else if (botRole == "tank")
            SelectOffTank(board, observation, *bot, plan);
        else
        {
            SelectDamageTarget(observation, *bot, botRole, plan);
            if (!plan.Movement)
                plan.Movement = ProposeFormation(board, observation, *bot,
                    botRole, frame, plan.DamageTarget == boss.Guid);
        }
        return plan;
    }

private:
    static BotNativeAction::Candidate BuildMove(Blackboard const& board,
        Vector3 const& point, std::string_view mechanic, ObjectGuid actor,
        BotActionArbitration::Priority priority, float utility,
        bool preemptCasting)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = std::string(Maloriak::StrategyName);
        candidate.Id.Mechanic = std::string(mechanic);
        candidate.Id.Actor = actor;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = priority;
        candidate.Utility = utility;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{ point.X, point.Y, point.Z,
            mechanic, preemptCasting };
        return candidate;
    }

    static std::vector<ActorSnapshot const*> SortedGroup(Blackboard const& board,
        bool melee)
    {
        std::vector<ActorSnapshot const*> group;
        for (ActorSnapshot const& player : board.Players)
            if (player.Alive && player.Role != "tank"
                && (player.Role == "dps" && Maloriak::IsMeleeSpec(player.ClassSpec)) == melee)
                group.push_back(&player);
        std::sort(group.begin(), group.end(), [](ActorSnapshot const* left,
            ActorSnapshot const* right)
        {
            return left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
        return group;
    }

    static std::size_t IndexIn(std::vector<ActorSnapshot const*> const& group,
        ObjectGuid guid)
    {
        for (std::size_t index = 0; index < group.size(); ++index)
            if (group[index]->Guid == guid)
                return index;
        return group.size();
    }

    // Everyone but the pull tank holds offense and forms on the entrance
    // line; the off-tank waits at the add spot. Engagement ends the hold.
    static void ProposePrepull(Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, std::string_view botRole,
        Maloriak::TankDuties const& tanks, AdaptiveMaloriakPlan& plan)
    {
        std::vector<ActorSnapshot const*> staged;
        for (ActorSnapshot const& player : board.Players)
            if (player.Alive && player.Role != "tank")
                staged.push_back(&player);
        std::sort(staged.begin(), staged.end(), [](ActorSnapshot const* left,
            ActorSnapshot const* right)
        {
            return left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
        bool const pullTank = bot.Guid == tanks.MainTank
            || (tanks.MainTank.IsEmpty() && botRole == "tank");
        if (pullTank)
        {
            std::string_view const hold = PullHoldReason(board, staged);
            if (hold.empty())
            {
                plan.DamageTarget = boss.Guid;
                plan.Duty = "pull_tank";
                return;
            }
            plan.SuppressOffense = true;
            plan.SuppressReason = hold;
            plan.Duty = "pull_tank_hold";
            Vector3 const front{ Maloriak::StagingCenterX,
                Maloriak::StagingY - Maloriak::StagingSpacing, Maloriak::RoomFloorZ };
            if (Maloriak::Distance2d(bot.Position, front) > StagingTolerance)
                plan.Movement = BuildMove(board, front, "prepull_stage",
                    boss.Guid, BotActionArbitration::Priority::Mechanic, 250.0f, false);
            return;
        }
        plan.SuppressOffense = true;
        plan.SuppressReason = "prepull_pull_owner_wait";
        plan.Duty = "prepull_stage";
        Vector3 const destination = botRole == "tank"
            ? Maloriak::AddAnchorFor(boss.Position)
            : Maloriak::StagingSlot(IndexIn(staged, bot.Guid), staged.size());
        if (Maloriak::Distance2d(bot.Position, destination) > StagingTolerance)
            plan.Movement = BuildMove(board, destination, "prepull_stage",
                boss.Guid, BotActionArbitration::Priority::Mechanic, 250.0f, false);
    }

    // Empty when the pull tank may pull: the play-mode pull timer allows it,
    // nobody is dead, everyone recovered from the trash and every non-tank
    // stands near its entrance slot.
    static std::string_view PullHoldReason(Blackboard const& board,
        std::vector<ActorSnapshot const*> const& staged)
    {
        if (!board.Route.PullPermitted)
            return "prepull_pull_timer_wait";
        for (ActorSnapshot const& player : board.Players)
        {
            if (!player.Alive)
                return "prepull_raid_dead_wait";
            if (player.HealthPct < PrepullHealthPct)
                return "prepull_health_recovery";
        }
        for (std::size_t index = 0; index < staged.size(); ++index)
            if (Maloriak::Distance2d(staged[index]->Position,
                    Maloriak::StagingSlot(index, staged.size())) > PrepullStagedYards)
                return "prepull_formation_staging";
        return {};
    }

    static void AssignInterrupt(Blackboard const& board,
        Maloriak::Observation const& observation, ObjectGuid botGuid,
        AdaptiveMaloriakPlan& plan)
    {
        if (!observation.ArcaneStormInterruptible
            && !(observation.ReleaseInterruptible && !Maloriak::ReleaseAdmitted(observation)))
            return;
        Maloriak::InterruptPools const pools =
            Maloriak::ResolveInterruptPools(board, *observation.Boss);
        if (observation.ArcaneStormInterruptible)
        {
            if (Maloriak::Contains(Maloriak::ArcaneStormInterrupters(pools,
                    observation.ArcaneStormElapsedMs), botGuid))
            {
                plan.InterruptTarget = observation.Boss->Guid;
                plan.InterruptSpellId = Maloriak::ArcaneStormSpell;
                plan.InterruptLane = "arcane_storm";
            }
            return;
        }
        if (Maloriak::Contains(Maloriak::ReleaseInterrupters(pools), botGuid))
        {
            plan.InterruptTarget = observation.Boss->Guid;
            plan.InterruptSpellId = Maloriak::ReleaseAberrationsSpell;
            plan.InterruptLane = "release_aberrations_quota";
        }
    }

    static void AssignDispel(Blackboard const& board,
        Maloriak::Observation const& observation, ObjectGuid botGuid,
        AdaptiveMaloriakPlan& plan)
    {
        if (!observation.RemedyElapsedMs)
            return;
        if (Maloriak::Contains(Maloriak::RemedyDispellers(board, *observation.Boss,
                *observation.RemedyElapsedMs), botGuid))
            plan.DispelTarget = observation.Boss->Guid;
    }

    // One spot healer (the lowest-GUID alive healer) watches the frozen,
    // Consuming Flames and Biting Chill players. It yields to the ordinary
    // lowest-health scan while a tank is low or another player is clearly
    // lower, so a debuffed player never starves the tank.
    static ObjectGuid SelectPriorityHeal(Blackboard const& board, ObjectGuid botGuid)
    {
        ObjectGuid spotHealer;
        float lowestTank = 100.0f;
        float lowestAny = 100.0f;
        for (ActorSnapshot const& player : board.Players)
        {
            if (!player.Alive)
                continue;
            if (player.Role == "healer" && (spotHealer.IsEmpty()
                    || player.Guid.GetRawValue() < spotHealer.GetRawValue()))
                spotHealer = player.Guid;
            if (player.Role == "tank")
                lowestTank = std::min(lowestTank, player.HealthPct);
            lowestAny = std::min(lowestAny, player.HealthPct);
        }
        if (botGuid != spotHealer || lowestTank < PriorityHealTankFloorPct)
            return ObjectGuid();
        ActorSnapshot const* best = nullptr;
        for (ActorSnapshot const& player : board.Players)
        {
            if (!player.Alive || player.HealthPct >= PriorityHealBelowPct)
                continue;
            if (!Maloriak::IsFrozen(player)
                && !Maloriak::HasAnyAura(player, Maloriak::ConsumingFlamesSpells)
                && !Maloriak::HasAura(player, Maloriak::BitingChillSpell))
                continue;
            if (!best || player.HealthPct < best->HealthPct)
                best = &player;
        }
        if (!best || best->HealthPct > lowestAny + PriorityHealMarginPct)
            return ObjectGuid();
        return best->Guid;
    }

    // Exit from the nearest hazard, rotated up to 90 degrees when the
    // straight exit would land in another sphere or jet fire.
    static Vector3 SafeHazardExit(Maloriak::Observation const& observation,
        ActorSnapshot const& bot, Vector3 const& source, float exitDistance)
    {
        auto safe = [&observation](Vector3 const& point)
        {
            for (ActorSnapshot const* sphere : observation.AbsoluteZeros)
                if (Maloriak::Distance2d(point, sphere->Position) < AbsoluteZeroDanger)
                    return false;
            for (ActorSnapshot const* fire : observation.MagmaJetFires)
                if (Maloriak::Distance2d(point, fire->Position) < MagmaFireDanger)
                    return false;
            return true;
        };
        float dx = bot.Position.X - source.X;
        float dy = bot.Position.Y - source.Y;
        float length = std::sqrt(dx * dx + dy * dy);
        if (length < 0.01f)
        {
            dx = std::cos(bot.Facing);
            dy = std::sin(bot.Facing);
            length = 1.0f;
        }
        dx /= length;
        dy /= length;
        static constexpr float Rotations[] = { 0.0f, 30.0f, -30.0f, 60.0f, -60.0f,
            90.0f, -90.0f };
        for (float degrees : Rotations)
        {
            float const radians = degrees * Maloriak::Pi / 180.0f;
            float const rx = dx * std::cos(radians) - dy * std::sin(radians);
            float const ry = dx * std::sin(radians) + dy * std::cos(radians);
            Vector3 const point = Maloriak::ClampToRoom({ source.X + rx * exitDistance,
                source.Y + ry * exitDistance, bot.Position.Z });
            if (safe(point))
                return point;
        }
        return Maloriak::AwayFromPoint(bot, source, exitDistance);
    }

    static ActorSnapshot const* NearestWithin(
        std::vector<ActorSnapshot const*> const& actors, ActorSnapshot const& bot,
        float radius)
    {
        ActorSnapshot const* best = nullptr;
        float bestDistance = radius;
        for (ActorSnapshot const* actor : actors)
        {
            float const distance = Maloriak::Distance2d(bot.Position, actor->Position);
            if (distance < bestDistance)
            {
                best = actor;
                bestDistance = distance;
            }
        }
        return best;
    }

    static std::optional<BotNativeAction::Candidate> ProposeHazard(
        Blackboard const& board, Maloriak::Observation const& observation,
        ActorSnapshot const& bot, bool mainTank, bool tank,
        Maloriak::BossFrame const& frame)
    {
        using BotActionArbitration::Priority;
        if (ActorSnapshot const* sphere = NearestWithin(observation.AbsoluteZeros,
                bot, AbsoluteZeroDanger))
            return BuildMove(board, SafeHazardExit(observation, bot, sphere->Position,
                AbsoluteZeroExit), "absolute_zero_evade", sphere->Guid,
                Priority::Survival, 480.0f, true);
        if (ActorSnapshot const* fire = NearestWithin(observation.MagmaJetFires,
                bot, MagmaFireDanger))
            return BuildMove(board, SafeHazardExit(observation, bot, fire->Position,
                MagmaFireExit), "magma_jet_fire_evade", fire->Guid,
                Priority::Survival, 470.0f, true);
        if (mainTank && observation.MagmaJetsCasting)
        {
            // The jet line runs from Maloriak through the tank; step
            // sideways to the side with fewer burning jets.
            Vector3 const left{ bot.Position.X + frame.Vx() * MagmaJetsSidestep,
                bot.Position.Y + frame.Vy() * MagmaJetsSidestep, bot.Position.Z };
            Vector3 const right{ bot.Position.X - frame.Vx() * MagmaJetsSidestep,
                bot.Position.Y - frame.Vy() * MagmaJetsSidestep, bot.Position.Z };
            auto burning = [&observation](Vector3 const& point)
            {
                return std::count_if(observation.MagmaJetFires.begin(),
                    observation.MagmaJetFires.end(), [&point](ActorSnapshot const* fire)
                    {
                        return Maloriak::Distance2d(point, fire->Position) < 10.0f;
                    });
            };
            return BuildMove(board, Maloriak::ClampToRoom(burning(right) < burning(left)
                ? right : left), "magma_jets_sidestep", observation.Boss->Guid,
                Priority::Survival, 460.0f, true);
        }
        for (ActorSnapshot const* block : observation.FlashFreezeBlocks)
            if (Maloriak::Distance2d(bot.Position, block->Position) < ShatterDanger)
                return BuildMove(board, Maloriak::AwayFromPoint(bot, block->Position,
                    ShatterExit), "flash_freeze_shatter_clearance", block->Guid,
                    Priority::Mechanic, 330.0f, false);
        // Tanks keep Maloriak and the adds in place; healers cover them.
        if (!tank && Maloriak::HasAura(bot, Maloriak::BitingChillSpell))
        {
            ActorSnapshot const* nearest = nullptr;
            float nearestDistance = 0.0f;
            for (ActorSnapshot const& player : board.Players)
            {
                if (!player.Alive || player.Guid == bot.Guid)
                    continue;
                float const distance = Maloriak::Distance2d(bot.Position, player.Position);
                if (!nearest || distance < nearestDistance)
                {
                    nearest = &player;
                    nearestDistance = distance;
                }
            }
            if (nearest && nearestDistance < BitingChillDanger)
                return BuildMove(board, Maloriak::AwayFromPoint(bot, nearest->Position,
                    BitingChillExit), "biting_chill_isolation", nearest->Guid,
                    Priority::Mechanic, 320.0f, false);
        }
        return std::nullopt;
    }

    static void SelectMainTank(ActorSnapshot const& boss, ObjectGuid botGuid,
        AdaptiveMaloriakPlan& plan)
    {
        plan.DamageTarget = boss.Guid;
        plan.Duty = "main_tank";
        // Shadow Imbued (heroic Dark phase) makes Maloriak immune to taunt;
        // a passive boss (vial walk, phase change) has no victim to take.
        if (boss.ReactAggressive && !boss.VictimGuid.IsEmpty()
            && boss.VictimGuid != botGuid
            && !Maloriak::HasAura(boss, Maloriak::ShadowImbuedSpell))
            plan.TauntTarget = boss.Guid;
    }

    // The off-tank collects released Aberrations, Prime Subjects and heroic
    // Vile Swills and holds them at an add spot away from Maloriak (Growth
    // Catalyst reaches 10 yards). Without adds it waits at that spot while
    // chamber creatures remain, otherwise it helps on the boss.
    static void SelectOffTank(Blackboard const& board,
        Maloriak::Observation const& observation, ActorSnapshot const& bot,
        AdaptiveMaloriakPlan& plan)
    {
        std::vector<ActorSnapshot const*> adds;
        for (ActorSnapshot const* aberration : observation.ActiveAberrations)
            if (aberration->Attackable)
                adds.push_back(aberration);
        for (ActorSnapshot const* subject : observation.PrimeSubjects)
            if (subject->Attackable)
                adds.push_back(subject);
        adds.insert(adds.end(), observation.VileSwills.begin(),
            observation.VileSwills.end());
        if (adds.empty())
        {
            // Released Aberrations run to their first target; an off-tank
            // waiting at the add spot keeps them (and Growth Catalyst) away
            // from Maloriak. With the reserve spent, or in phase two once
            // the adds are handled, it helps on the boss.
            if (observation.ReserveAberrations
                && observation.CurrentPhase != Maloriak::Phase::PhaseTwo)
            {
                plan.SuppressOffense = true;
                plan.SuppressReason = "off_tank_add_spot_wait";
                plan.Duty = "off_tank_add_spot_wait";
                Vector3 const anchor = Maloriak::AddAnchorFor(observation.Boss->Position);
                if (!plan.Movement
                    && Maloriak::Distance2d(bot.Position, anchor) > AddAnchorTolerance)
                    plan.Movement = BuildMove(board, anchor, "off_tank_add_anchor",
                        observation.Boss->Guid, BotActionArbitration::Priority::Mechanic,
                        260.0f, false);
                return;
            }
            plan.DamageTarget = observation.Boss->Guid;
            plan.Duty = "off_tank_boss_assist";
            return;
        }

        auto victimIsSquishy = [&board](ActorSnapshot const& add)
        {
            ActorSnapshot const* victim = Maloriak::FindPlayer(board, add.VictimGuid);
            return victim && victim->Role != "tank";
        };
        ActorSnapshot const* loose = nullptr;
        auto looseRank = [&](ActorSnapshot const& add)
        {
            return std::make_tuple(add.Entry == Maloriak::PrimeSubjectEntry ? 0 : 1,
                victimIsSquishy(add) ? 0 : 1,
                Maloriak::Distance2d(bot.Position, add.Position), add.Guid.GetRawValue());
        };
        for (ActorSnapshot const* add : adds)
            if (add->VictimGuid != bot.Guid
                && Maloriak::Distance2d(bot.Position, add->Position) <= LooseAddPickupRange
                && (!loose || looseRank(*add) < looseRank(*loose)))
                loose = add;
        if (loose)
        {
            plan.DamageTarget = loose->Guid;
            plan.Duty = "off_tank_pickup";
            // Adds must not stay on healers, damage dealers or the boss tank
            // (Growth Catalyst would buff Maloriak).
            if (!loose->VictimGuid.IsEmpty())
                plan.TauntTarget = loose->Guid;
            return;
        }

        ActorSnapshot const* focus = nullptr;
        for (ActorSnapshot const* add : adds)
            if (!focus || std::make_tuple(add->Entry == Maloriak::PrimeSubjectEntry,
                    add->HealthPct, add->Guid.GetRawValue())
                < std::make_tuple(focus->Entry == Maloriak::PrimeSubjectEntry,
                    focus->HealthPct, focus->Guid.GetRawValue()))
                focus = add;
        plan.DamageTarget = focus->Guid;
        plan.Duty = "off_tank_hold";
        Vector3 const anchor = Maloriak::AddAnchorFor(observation.Boss->Position);
        if (!plan.Movement
            && Maloriak::Distance2d(bot.Position, anchor) > AddAnchorTolerance)
            plan.Movement = BuildMove(board, anchor, "off_tank_add_anchor",
                focus->Guid, BotActionArbitration::Priority::Mechanic, 260.0f, false);
    }

    static ActorSnapshot const* Nearest(std::vector<ActorSnapshot const*> const& actors,
        ActorSnapshot const& bot)
    {
        ActorSnapshot const* best = nullptr;
        for (ActorSnapshot const* actor : actors)
            if (!best || Maloriak::Distance2d(bot.Position, actor->Position)
                < Maloriak::Distance2d(bot.Position, best->Position))
                best = actor;
        return best;
    }

    static void SelectDamageTarget(Maloriak::Observation const& observation,
        ActorSnapshot const& bot, std::string_view botRole,
        AdaptiveMaloriakPlan& plan)
    {
        plan.DamageTarget = observation.Boss->Guid;
        plan.Duty = botRole == "healer" ? "healer" : "boss_damage";
        if (botRole != "dps")
            return;
        if (Maloriak::IsRangedDamageSpec(bot.ClassSpec, botRole)
            && !observation.FlashFreezeBlocks.empty())
        {
            plan.DamageTarget = Nearest(observation.FlashFreezeBlocks, bot)->Guid;
            plan.Duty = "flash_freeze_break";
            return;
        }
        if (observation.CurrentPhase == Maloriak::Phase::PhaseTwo)
            return;
        if (!observation.VileSwills.empty())
        {
            plan.DamageTarget = Nearest(observation.VileSwills, bot)->Guid;
            plan.Duty = "vile_swill_burn";
            return;
        }
        std::size_t const attackable = observation.AttackableAberrationCount();
        if (!attackable)
            return;
        bool const greenImminent = observation.NextGreenVialMs
            && *observation.NextGreenVialMs <= GreenImminentMs;
        std::size_t const overflow = greenImminent
            ? OverflowBurnCountBeforeGreen : OverflowBurnCount;
        if (!observation.SlimeWindow && attackable < overflow
            && observation.Boss->HealthPct > CleanupBeforePhaseTwoPct)
            return;
        ActorSnapshot const* weakest = nullptr;
        for (ActorSnapshot const* aberration : observation.ActiveAberrations)
            if (aberration->Attackable && (!weakest
                || std::make_pair(aberration->HealthPct, aberration->Guid.GetRawValue())
                    < std::make_pair(weakest->HealthPct, weakest->Guid.GetRawValue())))
                weakest = aberration;
        plan.DamageTarget = weakest->Guid;
        plan.Duty = observation.SlimeWindow ? "aberration_slime_burn"
            : "aberration_burn";
    }

    // Formation: Red stacks in the Scorching Blast cone except Consuming
    // Flames targets; Blue, Dark and phase two spread behind. Green and the
    // vial transitions leave ordinary combat movement alone. A bot whose
    // target is not the boss (adds, ice blocks) keeps native combat movement.
    static std::optional<BotNativeAction::Candidate> ProposeFormation(
        Blackboard const& board, Maloriak::Observation const& observation,
        ActorSnapshot const& bot, std::string_view botRole,
        Maloriak::BossFrame const& frame, bool bossTarget)
    {
        // A passive boss is walking to the cauldron or changing phase: its
        // facing points at the cauldron, not at the tank, so no formation.
        if (!bossTarget || !observation.Boss->ReactAggressive)
            return std::nullopt;
        // A chilled player and anyone whose slot is near an ice block keep
        // the position their hazard exit gave them until the block breaks.
        if (Maloriak::HasAura(bot, Maloriak::BitingChillSpell))
            return std::nullopt;
        bool const melee = botRole == "dps" && Maloriak::IsMeleeSpec(bot.ClassSpec);
        std::vector<ActorSnapshot const*> const group = SortedGroup(board, melee);
        std::size_t const index = IndexIn(group, bot.Guid);
        if (index == group.size())
            return std::nullopt;
        Vector3 destination;
        std::string_view mechanic;
        switch (observation.CurrentPhase)
        {
            case Maloriak::Phase::Red:
                if (Maloriak::HasAnyAura(bot, Maloriak::ConsumingFlamesSpells))
                {
                    destination = Maloriak::BehindSlot(frame, melee);
                    mechanic = "consuming_flames_leave_cone";
                }
                else
                {
                    destination = melee ? Maloriak::FrontMeleeSlot(frame, index)
                        : Maloriak::FrontStackSlot(frame, index);
                    mechanic = "red_cone_stack";
                }
                break;
            case Maloriak::Phase::Blue:
            case Maloriak::Phase::Black:
            case Maloriak::Phase::PhaseTwo:
                destination = melee ? Maloriak::BackMeleeSlot(frame, index)
                    : Maloriak::BackRangedSlot(frame, index, group.size());
                mechanic = observation.CurrentPhase == Maloriak::Phase::Blue
                    ? "blue_spread"
                    : observation.CurrentPhase == Maloriak::Phase::Black
                        ? "dark_spread" : "phase_two_spread";
                break;
            default:
                return std::nullopt;
        }
        for (ActorSnapshot const* block : observation.FlashFreezeBlocks)
            if (Maloriak::Distance2d(destination, block->Position) < ShatterExit + 1.0f)
                return std::nullopt;
        float const tolerance = melee ? MeleeSlotTolerance : RangedSlotTolerance;
        if (Maloriak::Distance2d(bot.Position, destination) <= tolerance)
            return std::nullopt;
        return BuildMove(board, destination, mechanic, observation.Boss->Guid,
            BotActionArbitration::Priority::Mechanic, 200.0f, false);
    }
};
}

#endif
