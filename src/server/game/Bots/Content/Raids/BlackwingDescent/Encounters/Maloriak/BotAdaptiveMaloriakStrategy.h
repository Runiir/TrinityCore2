#ifndef TRINITY_BOT_ADAPTIVE_MALORIAK_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_MALORIAK_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotEncounterLatches.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakAddControl.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakDuties.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFormationPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakGeometry.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakLatches.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakPullPost.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakSphereDrag.h"

#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <string_view>
#include <tuple>
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

    // User tactic (user raid experience 2026-09-26): every release goes
    // through and each Aberration is killed as it comes, one at a time
    // (Maloriak::BurnFocus), with no wait for the Green slime window. If
    // Aberrations are left at 50% (Maloriak::AddSwitchHealthPct), the latched add switch
    // (BotMaloriakLatches.h) keeps every damage dealer off the boss until
    // they are all dead.

    // Hazard radii come from client rows (BotMaloriakFormation.h): Absolute
    // Zero trigger 3 yd and explosion 5 yd, Magma Jets fire 3 yd, Shatter
    // 5 yd, Biting Chill 3 yd.
    static constexpr float AbsoluteZeroDanger = Maloriak::AbsoluteZeroDanger;
    static constexpr float AbsoluteZeroExit = 11.0f;
    static constexpr float MagmaFireDanger = Maloriak::MagmaFireDanger;
    static constexpr float MagmaFireExit = 7.5f;
    static constexpr float ShatterDanger = Maloriak::ShatterDanger;
    static constexpr float ShatterExit = Maloriak::ShatterExit;
    static constexpr float BitingChillDanger = 6.0f;
    static constexpr float BitingChillExit = 8.0f;
    // A chilled melee damage dealer within BitingChillRingReach of the boss
    // moves only when an ally is closer than the trigger, to a melee ring
    // point the clearance from every ally. The tick area is 3 yards of exact
    // distance (spell family generic: no hitbox term), so both keep two
    // yards or more; the clearance exceeds the trigger (no oscillation).
    static constexpr float BitingChillRingReach = 8.0f;
    static constexpr float BitingChillRingTrigger = 5.0f;
    static constexpr float BitingChillRingClearance = 5.5f;
    static constexpr float MagmaJetsSidestep = 8.0f;

    static constexpr float StagingTolerance = 3.0f;
    static constexpr float TankSpotTolerance = 4.0f;
    // Beyond this the boss is not in melee with his tank (walking back from
    // the cauldron): the tank holds the spot instead of chasing him.
    static constexpr float TankHoldReach = 7.0f;
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

    // latches: the cohort's published latch view (BotMaloriakLatches.h);
    // without it the add switch is this snapshot's unlatched condition.
    AdaptiveMaloriakPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role, EncounterLatchView const* latches = nullptr) const
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
        plan.Boss = boss.Guid;
        plan.ReleaseAdmitted = Maloriak::ReleaseAdmitted(observation);
        plan.Phase = Maloriak::PhaseName(observation.CurrentPhase);
        std::string_view const botRole = bot->Role.empty()
            ? role : std::string_view(bot->Role);
        Maloriak::TankDuties const tanks = Maloriak::ResolveTanks(board);
        Maloriak::AddSwitchState const addSwitch =
            Maloriak::ResolveAddSwitch(board, observation, latches);
        plan.AddSwitchWindow = addSwitch.Active;
        plan.AddSwitchCapReleased = addSwitch.CapReleased;
        // The Blood DK main tank keeps full damage through the switch (Death
        // Strike keeps him alive); everyone else is off the boss.
        plan.AddSwitchRestricts = plan.AddSwitchWindow && botGuid != tanks.MainTank;

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
        if (!plan.AddSwitchWindow)
            AssignDispel(board, observation, botGuid, plan);
        Maloriak::AddControl const control =
            Maloriak::ResolveAddControl(board, observation, tanks.OffTank);
        plan.LustWindow = observation.CurrentPhase == Maloriak::Phase::PhaseTwo
            && Maloriak::ResolveLustOwner(board) == botGuid;
        if (botRole == "healer")
            plan.PriorityHealTarget = SelectPriorityHeal(board, botGuid);

        Maloriak::BossFrame const frame = Maloriak::ResolveFrame(boss,
            Maloriak::FindPlayer(board, tanks.MainTank));
        bool const mainTank = botGuid == tanks.MainTank;
        plan.Movement = ProposeHazard(board, observation, frame, *bot, mainTank,
            botRole == "tank");

        if (mainTank)
        {
            SelectMainTank(boss, botGuid, plan);
            if (!plan.Movement)
                plan.Movement = ProposeSphereDrag(board, observation, frame, *bot);
            if (!plan.Movement)
                plan.Movement = ProposeTankSpot(board, observation, *bot);
        }
        else if (botRole == "tank")
            SelectOffTank(board, observation, control, *bot, plan);
        else
        {
            SelectDamageTarget(observation, control, *bot, botRole, plan);
            if (!plan.Movement)
                plan.Movement = ProposeKiteTrapPost(board, observation, control, *bot);
            if (!plan.Movement)
                plan.Movement = Maloriak::ProposeFormation(board, observation, *bot,
                    botRole, frame, plan, ResolveFanBias(board, observation, control, frame));
        }
        AssignAddControl(control, *bot, tanks, plan);
        return plan;
    }

private:
    static BotNativeAction::Candidate BuildMove(Blackboard const& board,
        Vector3 const& point, std::string_view mechanic, ObjectGuid actor,
        BotActionArbitration::Priority priority, float utility,
        bool preemptCasting)
    {
        return Maloriak::BuildMove(board, point, mechanic, actor, priority,
            utility, preemptCasting);
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
        std::string_view const hold = PullHoldReason(board, staged);
        if (pullTank)
        {
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
        // Every holder reports the closed pull gate, not only the pull tank:
        // the shared pre-pot stage keys on "prepull_pull_owner_wait", and a
        // 25 s potion must not be spent while the raid is still dead,
        // healing or staging (round 3). Once the gate opens the raid waits
        // only on the pull owner.
        plan.SuppressReason = hold.empty() ? "prepull_pull_owner_wait" : hold;
        plan.Duty = "prepull_stage";
        Vector3 const destination = botRole == "tank"
            ? Maloriak::AddAnchorFor(boss.Position, &bot.Position)
            : Maloriak::StagingSlot(Maloriak::IndexIn(staged, bot.Guid), staged.size());
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
        // Arcane Storm only: Release Aberrations is never interrupted.
        if (!observation.ArcaneStormInterruptible)
            return;
        Maloriak::InterruptPools const pools =
            Maloriak::ResolveInterruptPools(board, *observation.Boss);
        if (Maloriak::Contains(Maloriak::ArcaneStormInterrupters(pools,
                observation.ArcaneStormElapsedMs), botGuid))
        {
            plan.InterruptTarget = observation.Boss->Guid;
            plan.InterruptSpellId = Maloriak::ArcaneStormSpell;
            plan.InterruptLane = "arcane_storm";
        }
    }

    // Threat, traps and slows around the Feral off-tank (user tactic):
    //  - Misdirection (hunter) and Tricks of the Trade (rogue) go on the
    //    off-tank only while the bot's own next target is a loose Aberration,
    //    so the redirected attacks land on an add, never on Maloriak;
    //  - the hunter lays Freeze Trap for an unhit Aberration running at it
    //    and Ice Trap otherwise, or for the kited pack at its loop corner;
    //  - the shaman Frost Shocks a loose Aberration, else one of the kited
    //    pack, never a frozen or freeze-reserved one; no slow totem
    //    (Earthbind would replace the earth-slot buff totem);
    //  - the off-tank keeps Nature's Grasp up while it holds Aberrations.
    static void AssignAddControl(Maloriak::AddControl const& control,
        ActorSnapshot const& bot, Maloriak::TankDuties const& tanks,
        AdaptiveMaloriakPlan& plan)
    {
        if (plan.Phase == Maloriak::PhaseName(Maloriak::Phase::PhaseTwo)
            || tanks.OffTank.IsEmpty())
            return;
        if (bot.Guid == tanks.OffTank)
        {
            plan.NaturesGrasp = !control.Pack.empty()
                && !Maloriak::HasAura(bot, Maloriak::NaturesGraspSpell);
            return;
        }
        if (uint32 const redirect = Maloriak::ThreatRedirectSpellFor(bot.ClassSpec))
            for (ActorSnapshot const* add : control.Loose)
                if (add->Guid == plan.DamageTarget)
                {
                    plan.ThreatRedirectTarget = tanks.OffTank;
                    plan.ThreatRedirectSpellId = redirect;
                }
        if (bot.Guid == control.Hunter && control.TrapPoint)
        {
            ActorSnapshot const* trapped = control.FreezeTarget
                ? control.FreezeTarget : control.IceTrapTarget;
            plan.TrapTarget = trapped->Guid;
            plan.TrapSpellId = control.FreezeTarget
                ? Maloriak::FreezeTrapSpell : Maloriak::IceTrapSpell;
            plan.TrapPoint = *control.TrapPoint;
        }
        if (Maloriak::SlowsAberrations(bot.ClassSpec) && control.SlowTarget)
            plan.SlowTarget = control.SlowTarget->Guid;
    }

    // The hunter's post at the kite loop's trap corner for the kited pack's
    // Ice Trap (outside Red, where the cone stack comes first): it walks
    // there, then holds the post (an explicit hold, so formation movement
    // does not pull it back while the trap is placed or on cooldown) as long
    // as the kite needs a trap. A Biting Chill target keeps its isolation.
    static std::optional<BotNativeAction::Candidate> ProposeKiteTrapPost(
        Blackboard const& board, Maloriak::Observation const& observation,
        Maloriak::AddControl const& control, ActorSnapshot const& bot)
    {
        if (!control.KiteTrap || bot.Guid != control.Hunter || !control.TrapPoint
            || !observation.Boss->ReactAggressive
            || Maloriak::HasAura(bot, Maloriak::BitingChillSpell))
            return std::nullopt;
        // It holds where it stands only while that spot itself keeps the
        // spread and chill clearance the corner was chosen with; otherwise it
        // steps onto the validated corner.
        bool const atPost = Maloriak::Distance2d(bot.Position, *control.TrapPoint)
            <= Maloriak::KiteTrapTolerance
            && Maloriak::TrapPostPositionClear(board, bot.Position, bot.Guid);
        return BuildMove(board, atPost ? bot.Position : *control.TrapPoint,
            atPost ? "hunter_kite_trap_post_hold" : "hunter_kite_trap_corner",
            observation.Boss->Guid, BotActionArbitration::Priority::Mechanic, 180.0f, false);
    }

    // The ranged fan leans to the side of the kite the off-tank is actually
    // on (Maloriak::OccupiedKite), or of where it holds when it cannot reach
    // a loop, while Aberrations are up in phase one (Maloriak::FanBias); the
    // Frost Shock owner takes its flank. In phase two the fan keeps its
    // spread, and the healers keep the off-tank holding the Prime Subjects
    // (or an Aberration left) within heal reach (Maloriak::OffTankHold).
    static Maloriak::FanBias ResolveFanBias(Blackboard const& board,
        Maloriak::Observation const& observation,
        Maloriak::AddControl const& control, Maloriak::BossFrame const& frame)
    {
        Maloriak::FanBias bias;
        if (control.OffTank.IsEmpty())
            return bias;
        if (observation.CurrentPhase == Maloriak::Phase::PhaseTwo)
        {
            ActorSnapshot const* offTank = Maloriak::FindPlayer(board, control.OffTank);
            bool const holding = !control.Pack.empty() || std::any_of(
                observation.PrimeSubjects.begin(), observation.PrimeSubjects.end(),
                [](ActorSnapshot const* subject) { return subject->Attackable; });
            if (offTank && offTank->Alive && holding)
                bias.OffTankHold = control.OffTankPosition;
            return bias;
        }
        if (control.Loose.empty() && control.Pack.empty())
            return bias;
        Maloriak::KiteGeometry const kite = Maloriak::OccupiedKite(observation,
            control.OffTankPosition, control.Pack);
        Vector3 const anchor = kite.Waypoints.empty() ? control.OffTankPosition : kite.Center;
        bias.Active = true;
        bias.Side = Maloriak::ToFramePolar(frame, anchor).Angle >= 0.0f ? 1.0f : -1.0f;
        bias.FlankOwner = control.SlowOwner;
        return bias;
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

    // Magma Jets (78194, 2 s cast) spawn fire along the boss facing, which
    // the script turns to the victim before the cast. The sidestep target is
    // latched per cast without state: it is derived from quantities that do
    // not change while the tank sidesteps (the boss position and facing, the
    // tank's projection on the jet line and the side it already stands on),
    // so every tick of the same cast proposes the same point.
    static std::optional<Vector3> MagmaJetsSidestepPoint(
        Maloriak::Observation const& observation, ActorSnapshot const& bot)
    {
        ActorSnapshot const& boss = *observation.Boss;
        float const ux = std::cos(boss.Facing);
        float const uy = std::sin(boss.Facing);
        float const dx = bot.Position.X - boss.Position.X;
        float const dy = bot.Position.Y - boss.Position.Y;
        float const along = std::max(1.0f, dx * ux + dy * uy);
        float const lateral = -dx * uy + dy * ux;
        if (std::fabs(lateral) >= MagmaJetsSidestep - 1.0f)
            return std::nullopt;
        auto point = [&](float side)
        {
            return Maloriak::ClampToRoom({ boss.Position.X + ux * along
                    - uy * side * MagmaJetsSidestep,
                boss.Position.Y + uy * along + ux * side * MagmaJetsSidestep,
                bot.Position.Z });
        };
        float side = lateral >= 0.0f ? 1.0f : -1.0f;
        if (std::fabs(lateral) < 0.5f)
        {
            // On the line: the side with fewer burning jets, left on a tie.
            auto burning = [&observation](Vector3 const& at)
            {
                return std::count_if(observation.MagmaJetFires.begin(),
                    observation.MagmaJetFires.end(), [&at](ActorSnapshot const* fire)
                    {
                        return Maloriak::Distance2d(at, fire->Position) < 10.0f;
                    });
            };
            side = burning(point(-1.0f)) < burning(point(1.0f)) ? -1.0f : 1.0f;
        }
        return point(side);
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
        Maloriak::BossFrame const& frame, ActorSnapshot const& bot, bool mainTank,
        bool tank)
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
            if (std::optional<Vector3> const sidestep =
                    MagmaJetsSidestepPoint(observation, bot))
                return BuildMove(board, *sidestep, "magma_jets_sidestep",
                    observation.Boss->Guid, Priority::Survival, 460.0f, true);
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
            if (!nearest)
                return std::nullopt;
            // A melee damage dealer at the boss keeps fighting from a clear
            // point of the back melee rings (Maloriak::ChillRingPoint).
            if (bot.Role == "dps" && Maloriak::IsMeleeSpec(bot.ClassSpec)
                && Maloriak::Distance2d(bot.Position, observation.Boss->Position)
                    <= BitingChillRingReach)
            {
                if (nearestDistance >= BitingChillRingTrigger)
                    return std::nullopt;
                std::vector<Vector3> allies;
                for (ActorSnapshot const& player : board.Players)
                    if (player.Alive && player.Guid != bot.Guid)
                        allies.push_back(player.Position);
                if (std::optional<Vector3> const ring = Maloriak::ChillRingPoint(frame,
                        Maloriak::CollectFormationHazards(observation), allies,
                        bot.Position, BitingChillRingClearance))
                    return BuildMove(board, *ring, "biting_chill_ring_isolation",
                        nearest->Guid, Priority::Mechanic, 320.0f, false);
            }
            else if (nearestDistance >= BitingChillDanger)
                return std::nullopt;
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
        // Icy Veins (Cataclysm Classic, 2024-07-29): "Maloriak will gain
        // Shadow Imbued, making him immune to taunts." The native aura 92716
        // (aura 147, mechanic mask 1614) grants no taunt immunity; the ledger
        // keeps that gap open and the bot follows the guide. A passive boss
        // (vial walk, phase change) has no victim to take.
        if (boss.ReactAggressive && !boss.VictimGuid.IsEmpty()
            && boss.VictimGuid != botGuid
            && !Maloriak::HasAura(boss, Maloriak::ShadowImbuedSpell))
            plan.TauntTarget = boss.Guid;
    }

    // The off-tank collects released Aberrations, Prime Subjects and heroic
    // Vile Swills (Maloriak::ResolveAddControl picks the pickup; a frozen
    // Aberration is left asleep). Holding Aberrations in phase one it kites
    // them round a flank loop away from Maloriak (Growth Catalyst reaches 10
    // yards), paced so the pack stays together (Maloriak::KiteStep). Without
    // adds it waits at the add spot while chamber creatures remain,
    // otherwise it helps on the boss.
    static void SelectOffTank(Blackboard const& board,
        Maloriak::Observation const& observation, Maloriak::AddControl const& control,
        ActorSnapshot const& bot, AdaptiveMaloriakPlan& plan)
    {
        std::vector<ActorSnapshot const*> held;
        for (ActorSnapshot const* aberration : observation.ActiveAberrations)
            if (aberration->Attackable && aberration->VictimGuid == bot.Guid)
                held.push_back(aberration);
        for (ActorSnapshot const* subject : observation.PrimeSubjects)
            if (subject->Attackable && subject->VictimGuid == bot.Guid)
                held.push_back(subject);
        ActorSnapshot const* pickup = control.OffTankPickup;
        for (ActorSnapshot const* swill : observation.VileSwills)
        {
            if (swill->VictimGuid == bot.Guid)
                held.push_back(swill);
            else if (!pickup && Maloriak::Distance2d(bot.Position, swill->Position)
                    <= LooseAddPickupRange)
                pickup = swill;
        }
        if (pickup)
        {
            plan.DamageTarget = pickup->Guid;
            plan.Duty = "off_tank_pickup";
            // Adds must not stay on healers, damage dealers or the boss tank
            // (Growth Catalyst would buff Maloriak).
            if (!pickup->VictimGuid.IsEmpty())
                plan.TauntTarget = pickup->Guid;
            // An add at Maloriak is taunted from a post 15 yards out, so
            // neither the off-tank nor its pack enters Growth Catalyst's
            // 10 yards around him (Maloriak::CatalystPullPost). A renewed
            // hold at the post keeps the mechanic movement lease; the
            // pack's focus stays the damage target meanwhile.
            if (plan.Movement || pickup->Entry == Maloriak::VileSwillEntry)
                return;
            std::optional<Vector3> const post = Maloriak::CatalystPullPost(
                observation, Maloriak::AddAnchorFor(observation.Boss->Position,
                    &bot.Position), pickup->Position);
            if (!post)
                return;
            if (ActorSnapshot const* focus = HeldFocus(held))
                plan.DamageTarget = focus->Guid;
            plan.Duty = "off_tank_pull_post";
            bool const atPost = Maloriak::Distance2d(bot.Position, *post)
                <= Maloriak::PullPostTolerance;
            plan.Movement = BuildMove(board, atPost ? bot.Position : *post,
                atPost ? "off_tank_pull_post_hold" : "off_tank_pull_post",
                pickup->Guid, BotActionArbitration::Priority::Mechanic, 260.0f, false);
            return;
        }
        if (held.empty())
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
                Vector3 const anchor = Maloriak::AddAnchorFor(
                    observation.Boss->Position, &bot.Position);
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

        ActorSnapshot const* focus = HeldFocus(held);
        plan.DamageTarget = focus->Guid;
        plan.Duty = "off_tank_hold";
        if (plan.Movement)
            return;
        if (!control.Pack.empty() && observation.CurrentPhase != Maloriak::Phase::PhaseTwo)
        {
            plan.Duty = "off_tank_kite";
            Maloriak::KiteDecision const step = Maloriak::KiteStep(
                Maloriak::ResolveKite(observation, bot.Position), bot.Position,
                control.Pack, observation.Boss->Position,
                Maloriak::CollectFormationHazards(observation));
            // A hold is an explicit, renewed move to where the off-tank
            // stands: it keeps the mechanic movement lease, so combat range
            // movement does not chase a straggler back.
            plan.Movement = BuildMove(board, step.Move ? step.Destination : bot.Position,
                step.Move ? "off_tank_kite" : "off_tank_kite_hold", focus->Guid,
                BotActionArbitration::Priority::Mechanic, 260.0f, false);
            return;
        }
        Vector3 const anchor = Maloriak::AddAnchorFor(observation.Boss->Position,
            &bot.Position);
        if (Maloriak::Distance2d(bot.Position, anchor) > AddAnchorTolerance)
            plan.Movement = BuildMove(board, anchor, "off_tank_add_anchor",
                focus->Guid, BotActionArbitration::Priority::Mechanic, 260.0f, false);
    }

    // The held add the off-tank hits: an Aberration before a Prime Subject,
    // the weakest first.
    static ActorSnapshot const* HeldFocus(std::vector<ActorSnapshot const*> const& held)
    {
        ActorSnapshot const* focus = nullptr;
        for (ActorSnapshot const* add : held)
            if (!focus || std::make_tuple(add->Entry == Maloriak::PrimeSubjectEntry,
                    add->HealthPct, add->Guid.GetRawValue())
                < std::make_tuple(focus->Entry == Maloriak::PrimeSubjectEntry,
                    focus->HealthPct, focus->Guid.GetRawValue()))
                focus = add;
        return focus;
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
        Maloriak::AddControl const& control, ActorSnapshot const& bot,
        std::string_view botRole, AdaptiveMaloriakPlan& plan)
    {
        plan.DamageTarget = observation.Boss->Guid;
        plan.Duty = botRole == "healer" ? "healer" : "boss_damage";
        if (botRole != "dps")
        {
            WaitForAdds(plan);
            return;
        }
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
        // Every Aberration is killed as it comes, one at a time, with no
        // wait for the Green slime window (user tactic).
        if (!control.Focus)
        {
            WaitForAdds(plan);
            return;
        }
        plan.DamageTarget = control.Focus->Guid;
        plan.Duty = observation.SlimeWindow ? "aberration_slime_burn"
            : "aberration_burn";
    }

    // Inside the add switch with no loose Aberration to kill (the next
    // release is still in the chambers), damage dealers and healers wait off
    // the boss. The boss stays the formation target; the suppression only
    // clears the offensive target.
    static void WaitForAdds(AdaptiveMaloriakPlan& plan)
    {
        if (!plan.AddSwitchWindow)
            return;
        plan.SuppressOffense = true;
        plan.SuppressReason = "add_switch_wait";
        plan.Duty = "add_switch_wait";
    }

    // Phase two: an Absolute Zero sphere beside Maloriak blocks the melee
    // ring (Maloriak::SphereDragPoint). While melee damage dealers are alive
    // and he is on this tank, the tank steps away and he follows.
    static std::optional<BotNativeAction::Candidate> ProposeSphereDrag(
        Blackboard const& board, Maloriak::Observation const& observation,
        Maloriak::BossFrame const& frame, ActorSnapshot const& bot)
    {
        ActorSnapshot const& boss = *observation.Boss;
        if (!boss.ReactAggressive || boss.VictimGuid != bot.Guid
            || !Maloriak::HasLivingMeleeDamageDealer(board))
            return std::nullopt;
        std::optional<Vector3> const point =
            Maloriak::SphereDragPoint(observation, frame, bot.Position);
        if (!point)
            return std::nullopt;
        return BuildMove(board, *point, "main_tank_sphere_drag", boss.Guid,
            BotActionArbitration::Priority::Mechanic, 230.0f, false);
    }

    // In phase one the main tank walks to MainTankSpot (north of the
    // cauldron) whenever it is away from it and the spot is clear of hazards;
    // Maloriak follows his tank after every cauldron visit, so the raid
    // fights him off the rim. Phase two starts wherever that fight is and
    // belongs to the Magma Jets sidestep (a return to the spot would cross
    // the jet line). Hazard moves always come first.
    //
    // At the spot the tank keeps proposing it while the boss is passive (at
    // the cauldron) or out of melee reach: otherwise ordinary combat-range
    // movement chases him back to the rim once the mechanic lease lapses and
    // the two owners swap 3-4 times per cauldron visit. At the spot this
    // resubmits a near-zero native move every tick, which is what keeps the
    // mechanic movement lease held (a kernel claim alone does not stop the
    // combat profile's range reconcile).
    //
    // An aggressive boss on anyone but the tank is an aggro loss: the tank
    // must go and taunt (Dark Command reaches 30 yards, SpellRange 4), so it
    // neither walks to nor holds the spot.
    static std::optional<BotNativeAction::Candidate> ProposeTankSpot(
        Blackboard const& board, Maloriak::Observation const& observation,
        ActorSnapshot const& bot)
    {
        ActorSnapshot const& boss = *observation.Boss;
        if (boss.ReactAggressive && !boss.VictimGuid.IsEmpty()
            && boss.VictimGuid != bot.Guid)
            return std::nullopt;
        bool const atSpot = Maloriak::Distance2d(bot.Position,
            Maloriak::MainTankSpot) <= TankSpotTolerance;
        bool const holdSpot = !boss.ReactAggressive
            || Maloriak::Distance2d(bot.Position, boss.Position)
                > TankHoldReach;
        if (observation.CurrentPhase == Maloriak::Phase::PhaseTwo
            || (atSpot && !holdSpot)
            || !Maloriak::ClearOfHazards(Maloriak::MainTankSpot,
                Maloriak::CollectFormationHazards(observation)))
            return std::nullopt;
        return BuildMove(board, Maloriak::MainTankSpot, "main_tank_spot",
            observation.Boss->Guid, BotActionArbitration::Priority::Mechanic,
            220.0f, false);
    }

};
}

#endif
