"""BWD 10N round 3 (Atramedes): raid-wide Sound near 0, every bot dodges everything avoidable.

User tactic 2026-09-30 (user raid experience, authoritative): "For atramedes ideally everyone is as
close to 0 sound as possible, meaning the bots dodge everything." In 10N Modulation adds no Sound (client
rows, ledger client_spell_values.modulation), so every Sound source is avoidable:
- ground: Sonar Pulse disks (+3 per 0.5 s within 5 yd), Sonic Breath (+20 per 1 s tick in its 15 degree
  cone), Searing Flame fire patches (+5 per 1 s within 3 yd; the channel itself is gonged);
- air: the Roaring Flame Breath (+3 per 0.5 s within 5 yd), its fire trail (+5 per 1 s within 3 yd) and
  Sonar Bomb impacts (+20 within 6 yd).

The program replays whole ground phases (native first-phase schedule) and air phases (the strategy test's
air replay, cut at its harness sentinel) with every bot driven by the production strategy, and reports per
role the mean and max Sound gained per phase. The same program compiled against a snapshot of the headers
before this change gives the "before" numbers (see the dossier). Negative control: the same hazards with the
bots' dodges ignored hit hard, so the harness bites.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from tests.test_atramedes_strategy import INCLUDES, PROGRAM, ROOT

HARNESS = PROGRAM[:PROGRAM.index("// ---- end of the air-phase replay harness ----")]

METRIC = r'''
// ---- raid-wide Sound metric ----
// Roles of the canonical roster, as the strategy assigns duties.
static std::string RoleOf(uint32 slot, A::DutyPlan const& duties)
{
    ObjectGuid const guid = PlayerGuid(slot);
    if (guid == duties.Tank)
        return "tank";
    if (slot == Mage)
        return "ice_mage";
    if (guid == duties.GongOwner || guid == duties.GongBackup || guid == duties.GongThird)
        return "gong_relay";
    if (slot == HolyPaladin || slot == Discipline)
        return "healer";
    if (slot == Retribution || slot == Rogue)
        return "melee";
    return "ranged";
}

struct RoleTally
{
    uint64 Samples = 0;
    uint64 Sum = 0;
    uint32 Max = 0;
    uint64 BarSum = 0;
    uint32 BarMax = 0;
    uint64 MoveSteps = 0;
    void Add(uint32 gained, uint32 bar, int moveSteps = 0)
    {
        ++Samples;
        MoveSteps += uint64(moveSteps);
        Sum += gained;
        Max = std::max(Max, gained);
        BarSum += bar;
        BarMax = std::max(BarMax, bar);
    }
    double Mean() const { return Samples ? double(Sum) / double(Samples) : 0.0; }
};

struct SoundBook
{
    // phase -> role -> tally
    std::map<std::string, std::map<std::string, RoleTally>> Tallies;
    // phase -> source -> (Sound, runs)
    std::map<std::string, std::map<std::string, std::pair<uint64, uint64>>> Sources;
    void Source(std::string const& phase, std::string const& source, uint64 sound)
    {
        std::pair<uint64, uint64>& entry = Sources[phase][source];
        entry.first += sound;
        ++entry.second;
    }
    void Add(std::string const& phase, std::string const& role, uint32 gained, uint32 bar, int moveSteps = 0)
    {
        Tallies[phase][role].Add(gained, bar, moveSteps);
    }
    void Print(char const* label) const
    {
        for (auto const& [phase, roles] : Tallies)
            for (auto const& [role, tally] : roles)
                std::printf("raid sound %s %-14s %-12s n=%4llu mean=%6.2f max=%3u bar_mean=%6.2f bar_max=%3u "
                    "move_s=%5.1f\n", label, phase.c_str(), role.c_str(), (unsigned long long)tally.Samples,
                    tally.Mean(), tally.Max, tally.BarSum ? double(tally.BarSum) / double(tally.Samples) : 0.0,
                    tally.BarMax, tally.Samples ? 0.25 * double(tally.MoveSteps) / double(tally.Samples) : 0.0);
        for (auto const& [phase, sources] : Sources)
            for (auto const& [source, entry] : sources)
                std::printf("raid sound %s %-14s source %-16s per_phase=%7.2f\n", label, phase.c_str(),
                    source.c_str(), entry.second ? double(entry.first) / double(entry.second) : 0.0);
    }
    RoleTally Of(std::string const& phase, std::string const& role) const
    {
        auto itr = Tallies.find(phase);
        if (itr == Tallies.end())
            return {};
        auto role_itr = itr->second.find(role);
        return role_itr == itr->second.end() ? RoleTally{} : role_itr->second;
    }
};

// ---- ground-phase replay ----
// The first ground phase from the pull (native schedule, boss_atramedes.cpp):
// Sonar Pulse at 14.5 s then every 11 s (4 disks, each summoned at Atramedes
// by a random player, ticking 77675 every 500 ms from 400 ms, moving at 7
// yd/s (creature_template 41546 speed_run 1) from 1.2 s toward its player's
// position then, for 100 yd); Sonic Breath at 24 s and 66 s (a random
// non-victim; Tracking Flames follow it at 5 yd/s; 2 s cast, 6 s channel,
// +20 per 1 s tick in a 15 degree cone of unlimited range); Searing Flame at
// 46 s (every 200 ms a 77966 missile lands a 41807 patch 1 s later within
// 35 yd until the gong interrupts it; patches tick +5 per 1 s within 3 yd
// for 30 s); liftoff at 91 s. Modulation adds no Sound in 10N. Every strike
// resets every bar (77709) and stuns him 5 s (Vertigo).
struct GroundOptions
{
    uint32 Seed = 1;
    // Negative control: bots ignore every hazard exit (only strikes and the
    // Sonic Breath kite remain), so the hazards land.
    bool Static = false;
    float Seconds = 91.0f;
};

struct GroundReplay
{
    std::map<uint32, uint32> Gained;
    std::map<uint32, uint32> KiterGained;
    std::map<uint32, uint32> MaxBar;
    int DiskTicks = 0;
    int BeamTicks = 0;
    int FireTicks = 0;
    int Strikes = 0;
    int SonicBreaths = 0;
    int MeleeOutOfRangeSteps = 0;
    int MeleeSteps = 0;
    bool DoubleClick = false;
    std::map<uint32, int> MovingSteps;
};

static bool Hazardous(std::string const& mechanic)
{
    static char const* const exits[] = { "sonar_pulse_exit", "sonar_pulse_melee_exit", "sonic_breath_beam_exit",
        "sonic_breath_run_ahead", "roaring_flame_exit", "sonar_bomb_exit", "reverberating_flame_exit" };
    return std::any_of(std::begin(exits), std::end(exits), [&mechanic](char const* exit) { return mechanic == exit; });
}

static GroundReplay ReplayGroundPhase(GroundOptions const& options)
{
    Blackboard board = Board();
    Settle(board);
    ReplayRandom random{ options.Seed * 2246822519u + 7u };
    // The formation settles before the first hazard.
    for (int step = 0; step < 32; ++step)
        StepPlans(board);
    GroundReplay result;
    ActorSnapshot& boss = Boss(board);
    Vector3 const bossAt = boss.Position;
    AddTimer(boss, A::TakeOffSpell, uint32(options.Seconds * 1000.0f));
    AddTimer(boss, A::SearingFlameSpell, 46000);
    struct Disk { uint32 Counter; float Born; float NextTick; bool Moving; float Heading; float Travelled; ObjectGuid Summoner; };
    std::vector<Disk> disks;
    struct Patch { uint32 Counter; float Lands; float NextTick; float Gone; Vector3 At; bool Landed; };
    std::vector<Patch> patches;
    uint32 nextCounter = 9000;
    float nextSonar = 14.5f;
    float const breaths[] = { 24.0f, 66.0f };
    std::size_t nextBreath = 0;
    float breathStart = -100.0f;
    ObjectGuid breathTarget;
    uint32 markerCounter = 0;
    bool searing = false;
    float nextMissile = 0.0f;
    auto hit = [&result, &breathTarget, &breathStart](ActorSnapshot& player, uint32 sound, float t)
    {
        uint32 const slot = player.Guid.GetCounter();
        bool const chased = player.Guid == breathTarget && t <= breathStart + 8.0f;
        player.AlternatePower = std::min<uint32>(100, player.AlternatePower + sound);
        (chased ? result.KiterGained : result.Gained)[slot] += sound;
        result.MaxBar[slot] = std::max(result.MaxBar[slot], player.AlternatePower);
    };
    auto marker = [&board, &markerCounter]() -> ActorSnapshot*
    {
        for (ActorSnapshot& actor : board.Summons)
            if (actor.Entry == A::TrackingFlamesEntry && actor.Guid.GetCounter() == markerCounter)
                return &actor;
        return nullptr;
    };
    for (float t = 0.25f; t <= options.Seconds + 0.001f; t += 0.25f)
    {
        ++board.Revision;
        board.ObservedAtMs += 250;
        for (MechanicTimerSnapshot& timer : Boss(board).MechanicTimers)
            if (timer.SpellId == A::TakeOffSpell || timer.SpellId == A::SearingFlameSpell)
                timer.RemainingMs = timer.RemainingMs > 250 ? timer.RemainingMs - 250 : 0;

        // Boss events.
        if (t + 0.001f >= nextSonar)
        {
            nextSonar += 11.0f;
            std::vector<ActorSnapshot const*> living;
            for (ActorSnapshot const& player : board.Players)
                if (player.Alive)
                    living.push_back(&player);
            for (int pick = 0; pick < 4 && !living.empty(); ++pick)
            {
                std::size_t const index = random.Next() % living.size();
                uint32 const counter = nextCounter++;
                disks.push_back({ counter, t, t + 0.4f, false, 0.0f, 0.0f, living[index]->Guid });
                living.erase(living.begin() + std::ptrdiff_t(index));
                board.Summons.push_back(MakeUnit(A::SonarPulseEntry, counter, bossAt.X, bossAt.Y, ActorKind::Summon));
            }
        }
        if (nextBreath < 2 && t + 0.001f >= breaths[nextBreath])
        {
            ++nextBreath;
            std::vector<ActorSnapshot*> candidates;
            for (ActorSnapshot& player : board.Players)
                if (player.Alive && player.Guid != Boss(board).VictimGuid)
                    candidates.push_back(&player);
            ActorSnapshot& target = *candidates[random.Next() % candidates.size()];
            breathTarget = target.Guid;
            breathStart = t;
            markerCounter = nextCounter++;
            ActorSnapshot flames = MakeUnit(A::TrackingFlamesEntry, markerCounter, target.Position.X,
                target.Position.Y, ActorKind::Summon);
            CastSnapshot channel;
            channel.SpellId = A::TrackingAura;
            channel.TargetGuid = target.Guid;
            channel.Channeled = true;
            flames.Cast = channel;
            board.Summons.push_back(flames);
            AddAura(target, A::TrackingAura, flames.Guid);
            CastOnBoss(board, A::SonicBreathChannelSpells.front());
            ++result.SonicBreaths;
        }
        if (breathStart > 0.0f && t + 0.001f >= breathStart + 8.0f && Boss(board).Cast
            && A::IsAnyOf(A::SonicBreathChannelSpells, Boss(board).Cast->SpellId))
            Boss(board).Cast.reset();
        if (breathStart > 0.0f && t + 0.001f >= breathStart + 10.0f)
        {
            board.Summons.erase(std::remove_if(board.Summons.begin(), board.Summons.end(),
                [](ActorSnapshot const& actor) { return actor.Entry == A::TrackingFlamesEntry; }), board.Summons.end());
            for (ActorSnapshot& player : board.Players)
                EraseAura(player, A::TrackingAura);
            breathStart = -100.0f;
            breathTarget.Clear();
        }
        if (!searing && Boss(board).FindMechanicTimer(A::SearingFlameSpell)
            && !Boss(board).FindMechanicTimer(A::SearingFlameSpell)->RemainingMs)
        {
            searing = true;
            nextMissile = t;
            Boss(board).MechanicTimers.erase(std::remove_if(Boss(board).MechanicTimers.begin(),
                Boss(board).MechanicTimers.end(), [](MechanicTimerSnapshot const& timer)
                { return timer.SpellId == A::SearingFlameSpell; }), Boss(board).MechanicTimers.end());
            CastOnBoss(board, A::SearingFlameSpell);
        }
        if (searing && Boss(board).Cast && Boss(board).Cast->SpellId == A::SearingFlameSpell)
            while (nextMissile <= t + 0.001f)
            {
                nextMissile += 0.2f;
                float const angle = float(random.Next() % 3600) / 3600.0f * G::TwoPi;
                float const radius = 35.0f * std::sqrt(float(random.Next() % 1000) / 1000.0f);
                patches.push_back({ nextCounter++, t + 1.0f, t + 2.0f, t + 31.0f,
                    G::PointAt(bossAt, angle, radius, 75.0f), false });
            }

        // Decisions (a strike resets every bar and stuns him).
        std::map<ObjectGuid, Vector3> destinations;
        ObjectGuid clicker;
        ObjectGuid clicked;
        for (ActorSnapshot const& player : board.Players)
        {
            if (!player.Alive)
                continue;
            AdaptiveAtramedesPlan const plan = AdaptiveAtramedesStrategy().Propose(board, player.Guid,
                player.Role.c_str());
            if (BotNativeAction::SpellClick const* click = ClickOf(plan))
            {
                if (!clicker.IsEmpty())
                    result.DoubleClick = true;
                clicker = player.Guid;
                clicked = click->Target;
                continue;
            }
            if (BotNativeAction::Move const* move = MoveOf(plan))
            {
                if (options.Static && player.Guid != breathTarget
                    && (Hazardous(plan.Movement->Id.Mechanic) || plan.Movement->Id.Mechanic.rfind("air_", 0) == 0))
                    continue;
                destinations[player.Guid] = { move->X, move->Y, 75.0f };
            }
        }
        std::map<ObjectGuid, Vector3> before;
        for (ActorSnapshot const& player : board.Players)
            before[player.Guid] = player.Position;
        MoveBots(board, destinations);
        for (ActorSnapshot const& player : board.Players)
            result.MovingSteps[player.Guid.GetCounter()] += G::Distance2d(before[player.Guid], player.Position) > 0.05f;
        ActorSnapshot& now = Boss(board);
        now.Auras.erase(std::remove_if(now.Auras.begin(), now.Auras.end(), [&board](AuraSnapshot const& aura)
            { return A::IsAnyOf(A::VertigoAuras, aura.SpellId) && aura.ExpiresAtMs <= board.ObservedAtMs; }),
            now.Auras.end());
        if (!clicker.IsEmpty())
        {
            board.Interactables.erase(std::find_if(board.Interactables.begin(), board.Interactables.end(),
                [clicked](ActorSnapshot const& shield) { return shield.Guid == clicked; }));
            for (ActorSnapshot& player : board.Players)
                player.AlternatePower = 0;
            now.Auras.push_back({ A::VertigoAuras.front(), clicked, 0, board.ObservedAtMs + 5000 });
            if (now.Cast && now.Cast->SpellId == A::SearingFlameSpell)
                now.Cast.reset();
            ++result.Strikes;
        }
        for (ActorSnapshot const& player : board.Players)
            if (player.Alive && A::IsMelee(player))
            {
                ++result.MeleeSteps;
                result.MeleeOutOfRangeSteps += G::Distance2d(player.Position, bossAt) > A::MeleeRangeYards;
            }

        // Hazard movement and ticks.
        if (ActorSnapshot* flames = marker())
            if (ActorSnapshot* target = board.Players.data())
            {
                for (ActorSnapshot& player : board.Players)
                    if (player.Guid == breathTarget)
                        target = &player;
                Advance(flames->Position, target->Position, 1.25f);
            }
        for (Disk& disk : disks)
        {
            ActorSnapshot* actor = nullptr;
            for (ActorSnapshot& summon : board.Summons)
                if (summon.Entry == A::SonarPulseEntry && summon.Guid.GetCounter() == disk.Counter)
                    actor = &summon;
            if (!actor)
                continue;
            if (!disk.Moving && t + 0.001f >= disk.Born + 1.2f)
            {
                disk.Moving = true;
                Vector3 toward = bossAt;
                for (ActorSnapshot const& player : board.Players)
                    if (player.Guid == disk.Summoner)
                        toward = player.Position;
                disk.Heading = G::Bearing(bossAt, toward);
            }
            if (disk.Moving)
            {
                actor->Position = G::PointAt(actor->Position, disk.Heading, 1.75f, 75.0f);
                disk.Travelled += 1.75f;
            }
            if (t + 0.001f >= disk.NextTick)
            {
                disk.NextTick += 0.5f;
                for (ActorSnapshot& player : board.Players)
                    if (player.Alive && G::Distance2d(player.Position, actor->Position) <= A::SonarPulseRadius)
                    {
                        hit(player, 3, t);
                        ++result.DiskTicks;
                    }
            }
        }
        disks.erase(std::remove_if(disks.begin(), disks.end(), [&board](Disk const& disk)
        {
            if (disk.Travelled < 100.0f)
                return false;
            board.Summons.erase(std::remove_if(board.Summons.begin(), board.Summons.end(),
                [&disk](ActorSnapshot const& actor)
                { return actor.Entry == A::SonarPulseEntry && actor.Guid.GetCounter() == disk.Counter; }),
                board.Summons.end());
            return true;
        }), disks.end());
        if (breathStart > 0.0f && t > breathStart + 2.5f && t <= breathStart + 8.001f
            && std::fabs(std::fmod(t - breathStart, 1.0f)) < 0.01f)
            if (ActorSnapshot* flames = marker())
            {
                float const beam = G::Bearing(bossAt, flames->Position);
                for (ActorSnapshot& player : board.Players)
                {
                    if (!player.Alive)
                        continue;
                    G::RayOffset const offset = G::OffsetFromRay(bossAt, beam, player.Position);
                    float const off = std::fabs(G::AngleDelta(G::Bearing(bossAt, player.Position), beam));
                    if (offset.Along > 0.0f && (off <= A::SonicBreathHalfAngleRad || offset.Lateral <= 1.0f))
                    {
                        hit(player, 20, t);
                        ++result.BeamTicks;
                    }
                }
            }
        for (Patch& patch : patches)
        {
            if (!patch.Landed && t + 0.001f >= patch.Lands)
            {
                patch.Landed = true;
                board.Summons.push_back(MakeUnit(A::SearingFlamePatchEntry, patch.Counter, patch.At.X, patch.At.Y,
                    ActorKind::Summon));
            }
            if (patch.Landed && t + 0.001f >= patch.NextTick && t < patch.Gone)
            {
                patch.NextTick += 1.0f;
                for (ActorSnapshot& player : board.Players)
                    if (player.Alive && G::Distance2d(player.Position, patch.At) <= A::FirePatchRadius)
                    {
                        hit(player, 5, t);
                        ++result.FireTicks;
                    }
            }
        }
    }
    return result;
}

static void BookGround(SoundBook& book, std::string const& phase, GroundReplay const& run)
{
    A::DutyPlan const duties = A::BuildDutyPlan(Board());
    for (uint32 slot = Tank; slot <= Warlock; ++slot)
    {
        auto get = [slot](std::map<uint32, uint32> const& map)
        {
            auto itr = map.find(slot);
            return itr == map.end() ? 0u : itr->second;
        };
        int const moved = run.MovingSteps.count(slot) ? run.MovingSteps.at(slot) : 0;
        book.Add(phase, RoleOf(slot, duties), get(run.Gained), get(run.MaxBar), moved);
        book.Add(phase, "all", get(run.Gained), get(run.MaxBar), moved);
        if (get(run.KiterGained) || run.SonicBreaths)
            book.Add(phase, "kiter_total", get(run.KiterGained), 0);
    }
    book.Source(phase, "melee_out_of_range_pct", run.MeleeSteps ? uint64(100.0 * run.MeleeOutOfRangeSteps / run.MeleeSteps) : 0);
    book.Source(phase, "sonar_pulse", uint64(run.DiskTicks) * 3);
    book.Source(phase, "sonic_breath", uint64(run.BeamTicks) * 20);
    book.Source(phase, "fire_patch", uint64(run.FireTicks) * 5);
}

static void BookAir(SoundBook& book, std::string const& phase, AirReplay const& run)
{
    A::DutyPlan const duties = A::BuildDutyPlan(Board());
    uint32 kiter = 0;
    for (uint32 slot = Tank; slot <= Warlock; ++slot)
    {
        auto get = [slot](std::map<uint32, uint32> const& map)
        {
            auto itr = map.find(slot);
            return itr == map.end() ? 0u : itr->second;
        };
        int const moved = run.MovingSteps.count(slot) ? run.MovingSteps.at(slot) : 0;
        book.Add(phase, RoleOf(slot, duties), get(run.Gained), get(run.MaxBar), moved);
        book.Add(phase, "all", get(run.Gained), get(run.MaxBar), moved);
        kiter += get(run.KiterGained);
    }
    book.Add(phase, "kiter_total", kiter, run.MaxKiterSound);
    book.Source(phase, "bomb_bystander", uint64(run.BombHits - run.KiterBombHits) * 20);
    book.Source(phase, "bomb_kiter", uint64(run.KiterBombHits) * 20);
    book.Source(phase, "fire_bystander", uint64(run.FireTicks - run.KiterFireTicks) * 5);
    book.Source(phase, "fire_kiter", uint64(run.KiterFireTicks) * 5);
    book.Source(phase, "breath_bystander", uint64(run.OtherTicks) * 3);
    book.Source(phase, "breath_kiter", uint64(run.KiterTicks) * 3);
}

static SoundBook RunBook(bool staticBots)
{
    SoundBook book;
    for (uint32 seed = 1; seed <= 12; ++seed)
    {
        GroundOptions options;
        options.Seed = seed;
        options.Static = staticBots;
        GroundReplay const run = ReplayGroundPhase(options);
        assert(!run.DoubleClick && run.SonicBreaths == 2);
        BookGround(book, "ground", run);
    }
    if (staticBots)
        return book;
    std::vector<uint32> const beforePhase1 = AfterGroundSearing(AllShieldIds(), 100.0f);
    for (uint32 seed : { 1u, 2u, 3u })
        for (float delay : { 7.0f, 3.0f })
            for (uint32 slot = Tank; slot <= Warlock; ++slot)
            {
                ReplayOptions options;
                options.Mobility = true;
                options.Bombs = options.FirePatches = true;
                options.Seed = seed;
                AirReplay const one = ReplayAirPhase(slot, float(A::BuildingSpeedMaxStacks), delay, false,
                    beforePhase1, 100.0f, 31.0f, options);
                BookAir(book, delay > 5.0f ? "air_spawn7" : "air_spawn3", one);
                ReplayOptions later = options;
                later.IceBlockReady = false;
                later.DashRemainingMs = 56000;
                later.Seed = seed + 17;
                AirReplay const two = ReplayAirPhase(slot, float(A::BuildingSpeedMaxStacks), delay, false,
                    AfterGroundSearing(one.ShieldsLeft, 60.0f), 60.0f, 31.0f, later);
                BookAir(book, delay > 5.0f ? "air2_spawn7" : "air2_spawn3", two);
            }
    return book;
}
'''


RULES = r"""
namespace D = BotEncounter::Atramedes::Dodge;

// Everyone at the arena centre but `slot`, on the air board.
static Blackboard QuietAir(uint32 slot, Vector3 at)
{
    Blackboard board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = { 150.0f, -190.0f, 75.0f };
    Member(board, slot).Position = at;
    return board;
}

static Vector3 To(AdaptiveAtramedesPlan const& plan)
{
    return { MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f };
}

static void TestBombExitAvoidsTheNextZone()
{
    // Negative control: one marker, the radial exit (unchanged).
    Vector3 const self{ 145.0f, -225.0f, 75.0f };
    Blackboard board = QuietAir(Elemental, self);
    board.Summons.push_back(MakeUnit(A::SonarBombMarkerEntry, 900, 143.0f, -225.0f, ActorKind::Summon));
    AdaptiveAtramedesPlan one = Plan(board, Elemental);
    assert(Mechanic(one) == "sonar_bomb_exit");
    Vector3 const radial = To(one);
    assert(std::fabs(G::Distance2d(radial, { 143.0f, -225.0f, 75.0f }) - (D::BombClearYards + 1.5f)) < 0.05f);
    // A second marker where that exit lands: the step clears both zones.
    board.Summons.push_back(MakeUnit(A::SonarBombMarkerEntry, 901, radial.X + 1.0f, radial.Y, ActorKind::Summon));
    AdaptiveAtramedesPlan two = Plan(board, Elemental);
    Vector3 const step = To(two);
    assert(Mechanic(two) == "sonar_bomb_exit" && G::Distance2d(step, radial) > 1.0f);
    for (ActorSnapshot const& marker : board.Summons)
        if (marker.Entry == A::SonarBombMarkerEntry)
            assert(G::Distance2d(step, marker.Position) >= D::BombClearYards);
    // The shortest safe step: no farther than needed to clear both.
    assert(G::Distance2d(step, self) < 16.0f);
}

static void TestFireTrailExitLeavesTheBand()
{
    // A Roaring Flame trail: a patch every 2 yd along y = -225.
    Vector3 const self{ 141.0f, -225.3f, 75.0f };
    Blackboard board = QuietAir(Elemental, self);
    for (int index = 0; index < 12; ++index)
        board.Summons.push_back(MakeUnit(A::RoaringFlamePatchEntry, 910 + index, 130.0f + 2.0f * float(index),
            -225.0f, ActorKind::Summon));
    AdaptiveAtramedesPlan const plan = Plan(board, Elemental);
    assert(Mechanic(plan) == "roaring_flame_exit");
    Vector3 const step = To(plan);
    for (ActorSnapshot const& patch : board.Summons)
        if (patch.Entry == A::RoaringFlamePatchEntry)
            assert(G::Distance2d(step, patch.Position) >= D::PatchClearYards);
    // Out across the band (about 5 yd), not along it.
    assert(std::fabs(step.Y - self.Y) >= D::PatchClearYards && G::Distance2d(step, self) < 8.0f);
    // Negative control: the same player beside the trail holds.
    Member(board, Elemental).Position = { 141.0f, -235.0f, 75.0f };
    assert(Mechanic(Plan(board, Elemental)) != "roaring_flame_exit");
}

static void TestMeleeDodgesEveryLaneInRange()
{
    Blackboard board = Board();
    Settle(board);
    Vector3 const boss = Boss(board).Position;
    Vector3 const rogue = G::PointAt(boss, 0.2f, A::MeleeSlotRadius, 75.0f);
    Member(board, Rogue).Position = rogue;
    // Negative control: one disk, the lane exit around the boss.
    float const lane = G::Bearing(boss, rogue);
    board.Summons.push_back(MakeUnit(A::SonarPulseEntry, 920, G::PointAt(boss, lane, 4.0f, 75.0f).X,
        G::PointAt(boss, lane, 4.0f, 75.0f).Y, ActorKind::Summon));
    AdaptiveAtramedesPlan const single = Plan(board, Rogue);
    assert(Mechanic(single) == "sonar_pulse_melee_exit");
    Vector3 const first = To(single);
    // A second disk on the lane that exit steps into.
    float const next = G::Bearing(boss, first);
    board.Summons.push_back(MakeUnit(A::SonarPulseEntry, 921, G::PointAt(boss, next, 4.0f, 75.0f).X,
        G::PointAt(boss, next, 4.0f, 75.0f).Y, ActorKind::Summon));
    AdaptiveAtramedesPlan const both = Plan(board, Rogue);
    Vector3 const step = To(both);
    assert(Mechanic(both) == "sonar_pulse_melee_exit" && G::Distance2d(step, first) > 1.0f);
    for (float heading : { lane, next })
        assert(G::OffsetFromRay(boss, heading, step).Lateral >= A::SonarPulseRadius + A::HazardMargin);
    // Still at maximum melee range (user raid experience 2026-09-25).
    float const range = G::Distance2d(boss, step);
    assert(range <= A::MeleeRangeYards - 1.0f && range >= A::MeleeRangeYards - 1.25f - 4.01f);
    // A walk that meets a moving disk is priced: behind it is safe, into it not.
    D::Field field;
    field.Lanes.push_back({ G::PointAt(boss, 0.0f, 5.0f, 75.0f), 0.0f, D::LaneClearYards });
    assert(!D::DiskSafeWalk(field, { boss.X + 12.0f, boss.Y - 6.0f, 75.0f }, { boss.X + 12.0f, boss.Y + 6.0f, 75.0f }, 7.0f));
    assert(D::DiskSafeWalk(field, { boss.X + 30.0f, boss.Y - 8.0f, 75.0f }, { boss.X + 30.0f, boss.Y - 14.0f, 75.0f }, 7.0f));
}

static void TestTankAndMeleeHoldMaxRange()
{
    Blackboard board = Board();
    Boss(board).Position = A::TankAnchor;
    Member(board, Tank).Position = { A::TankAnchor.X - 7.0f, A::TankAnchor.Y, 75.0f };
    AdaptiveAtramedesPlan const tank = Plan(board, Tank, "tank");
    assert(Mechanic(tank) == "tank_max_range");
    assert(std::fabs(G::Distance2d(To(tank), A::TankAnchor) - A::MeleeSlotRadius) < 0.1f);
    assert(To(tank).X < A::TankAnchor.X);  // along its own bearing
    // Negative controls: already out there; not his victim; still dragging.
    Member(board, Tank).Position = G::PointAt(A::TankAnchor, A::Geometry::Pi, A::MeleeSlotRadius - 1.0f, 75.0f);
    assert(Mechanic(Plan(board, Tank, "tank")).empty());
    Blackboard other = Board();
    Boss(other).Position = A::TankAnchor;
    Boss(other).VictimGuid = PlayerGuid(Rogue);
    Member(other, Tank).Position = A::TankAnchor;
    assert(Mechanic(Plan(other, Tank, "tank")) != "tank_max_range");
    Blackboard drag = Board();
    Boss(drag).Position = { 214.531f, -223.918f, 75.0f };
    assert(Mechanic(Plan(drag, Tank, "tank")) == "tank_anchor_drag");
    // Melee on the far side of their slot walk around the boss on the ring,
    // never through its centre (where the lanes and the beam start).
    Blackboard ring = Board();
    Settle(ring);
    Vector3 const boss = Boss(ring).Position;
    std::optional<Vector3> const slot = A::MeleeSlot(ring, A::BuildFacts(ring), A::BuildDutyPlan(ring),
        Member(ring, Rogue));
    assert(slot);
    Member(ring, Rogue).Position = G::PointAt(boss, G::Bearing(boss, *slot) + A::Geometry::Pi, A::MeleeSlotRadius, 75.0f);
    AdaptiveAtramedesPlan const around = Plan(ring, Rogue);
    assert(Mechanic(around) == "melee_max_range");
    assert(std::fabs(G::Distance2d(To(around), boss) - A::MeleeSlotRadius) < 0.1f);
    assert(G::Distance2d(To(around), *slot) > 5.0f);
    // Negative control: near the slot, straight to it.
    Member(ring, Rogue).Position = G::PointAt(*slot, 0.0f, 3.0f, 75.0f);
    assert(G::Distance2d(To(Plan(ring, Rogue)), *slot) < 0.1f);
}

static void TestFlamePathAndRunner()
{
    // A flame at 10 stacks (15 yd/s) chasing the mage: a bystander 12 yd
    // ahead on its path leaves the path; one 12 yd behind it stays.
    Blackboard board = QuietAir(Elemental, { 130.0f, -225.0f, 75.0f });
    Member(board, Mage).Position = { 150.0f, -225.0f, 75.0f };
    AddFlame(board, Member(board, Mage), { 118.0f, -225.0f, 75.0f }, 10);
    AdaptiveAtramedesPlan const ahead = Plan(board, Elemental);
    assert(Mechanic(ahead) == "reverberating_flame_exit");
    assert(D::DistanceToSegment(To(ahead), { 118.0f, -225.0f, 75.0f }, { 150.0f, -225.0f, 75.0f })
        >= D::FlameClearYards);
    Member(board, Elemental).Position = { 106.0f, -225.0f, 75.0f };
    assert(Mechanic(Plan(board, Elemental)) != "reverberating_flame_exit");

    // The redirect runner (the latest striker, no kiter yet) never walks into
    // an old trail between it and its kite waypoint.
    Blackboard run = AirBoard();
    for (ActorSnapshot& player : run.Players)
        player.Position = A::ArenaCenter;
    run.Summons.push_back(MakeUnit(A::ReverberatingFlameEntry, 81, 100.0f, -225.0f, ActorKind::Summon));
    Member(run, Hunter).Auras.push_back({ A::AirClashAura, ShieldGuid(250125), 0, run.ObservedAtMs + 15000 });
    // A runner whose next waypoint is at least 14 yd away along the ring.
    Vector3 self{};
    Vector3 waypoint{};
    for (float degrees = 0.0f; degrees < 360.0f; degrees += 5.0f)
    {
        self = G::PointAt(A::ArenaCenter, degrees * A::Geometry::Pi / 180.0f, 50.0f, 75.0f);
        Member(run, Hunter).Position = self;
        AdaptiveAtramedesPlan const plain = Plan(run, Hunter);
        if (Mechanic(plain) == "air_redirect_run" && G::Distance2d(To(plain), self) >= 14.0f
            && A::ArenaFloor::Solid(self.X, self.Y))
        {
            waypoint = To(plain);
            break;
        }
    }
    assert(G::Distance2d(waypoint, self) >= 14.0f);
    // An old trail across the run, 60% of the way.
    float const heading = G::Bearing(self, waypoint);
    Vector3 const cross = G::PointAt(self, heading, 0.6f * G::Distance2d(self, waypoint), 75.0f);
    for (int index = -4; index <= 4; ++index)
    {
        Vector3 const at = G::PointAt(cross, heading + A::Geometry::Pi / 2.0f, 2.0f * float(index), 75.0f);
        run.Summons.push_back(MakeUnit(A::RoaringFlamePatchEntry, 934 + index, at.X, at.Y, ActorKind::Summon));
    }
    AdaptiveAtramedesPlan const around = Plan(run, Hunter);
    assert(Mechanic(around) == "air_redirect_run");
    A::Facts const facts = A::BuildFacts(run);
    D::Field const field = D::BuildField(run, facts, Member(run, Hunter));
    assert(D::PathCost(field, self, To(around), 7.0f) == 0.0f && D::Clear(field, To(around), 0.0f));
}

static void TestRedirectUsesTheStruckShieldsRuntimeIdentity()
{
    // The Resonating Clash's caster is the struck shield's runtime GUID; its counter is generated by native
    // creature loading, independently of the database spawn id. Spawn 250131 (entry 42956) is creature
    // counter 1131 here: the two never match numerically.
    ObjectGuid const struck = ShieldGuid(250131);
    assert(struck.GetCounter() != 250131u && ShieldSpawnId(struck) == 250131u);
    A::ShieldSpawn const* spawn = nullptr;
    for (A::ShieldSpawn const& candidate : A::ShieldSpawns)
        if (candidate.SpawnId == 250131u)
            spawn = &candidate;
    assert(spawn);
    Vector3 const shield{ spawn->X, spawn->Y, A::ArenaCenter.Z };

    // A redirect: nobody is chased, the flame flies to the struck shield, the striker (the Hunter) holds the
    // clash. The struck shield stays in the snapshot or, as a used shield does (not selectable, no spellclick),
    // leaves it.
    auto redirect = [&](ObjectGuid caster, bool inSnapshot)
    {
        Blackboard board = AirBoard();
        for (ActorSnapshot& player : board.Players)
            player.Position = A::ArenaCenter;
        Member(board, Hunter).Position = G::PointAt(shield, 3.0f, 8.0f, 75.0f);
        board.Summons.push_back(MakeUnit(A::ReverberatingFlameEntry, 81, 130.0f, shield.Y, ActorKind::Summon));
        Member(board, Hunter).Auras.push_back({ A::AirClashAura, caster, 0, board.ObservedAtMs + 15000 });
        if (!inSnapshot)
            board.Interactables.erase(std::remove_if(board.Interactables.begin(), board.Interactables.end(),
                [caster](ActorSnapshot const& actor) { return actor.Guid == caster; }), board.Interactables.end());
        return board;
    };
    auto heading = [](Blackboard const& board)
    {
        A::Facts const facts = A::BuildFacts(board);
        assert(facts.AirKiter.IsEmpty() && A::AirRedirectRunner(board, facts) && facts.ReverberatingFlames.size() == 1);
        return D::FlameHeadingPoint(board, facts, *facts.ReverberatingFlames.front());
    };
    for (bool inSnapshot : { true, false })
    {
        Blackboard board = redirect(struck, inSnapshot);
        Vector3 const toward = heading(board);
        assert(G::Distance2d(toward, shield) < 0.05f);
        // A bystander 12 yd along the actual redirect path (past the flame's own 9 yd footprint) leaves it.
        Vector3 const flame = board.Summons.back().Position;
        Vector3 const onPath = G::PointAt(flame, G::Bearing(flame, shield), 12.0f, 75.0f);
        assert(G::Distance2d(onPath, flame) > D::FlameClearYards);
        A::Facts const facts = A::BuildFacts(board);
        D::Field const field = D::BuildField(board, facts, Member(board, Elemental));
        assert(!D::Clear(field, onPath, 0.0f));
        // Negative control: well off the path it is clear.
        assert(D::Clear(field, G::PointAt(flame, G::Bearing(flame, shield) + A::Geometry::Pi / 2.0f, 30.0f, 75.0f), 0.0f));
    }

    // Entry 42956 has two spawns (250122 and 250131): with 250131's shield still usable in the snapshot the
    // struck one is 250122; with both struck, the one the striker stood at.
    ObjectGuid const other = ShieldGuid(250122);
    Vector3 const otherShield{ 106.283f, -276.951f, A::ArenaCenter.Z };
    {
        Blackboard board = redirect(other, false);  // 250131 usable, 250122 struck and gone
        assert(G::Distance2d(heading(board), otherShield) < 0.05f);
        board.Interactables.erase(std::remove_if(board.Interactables.begin(), board.Interactables.end(),
            [struck](ActorSnapshot const& actor) { return actor.Guid == struck; }), board.Interactables.end());
        // Both gone: the striker's side decides.
        Member(board, Hunter).Position = G::PointAt(shield, 3.0f, 8.0f, 75.0f);
        assert(G::Distance2d(heading(board), shield) < 0.05f);
        Member(board, Hunter).Position = G::PointAt(otherShield, 3.0f, 8.0f, 75.0f);
        assert(G::Distance2d(heading(board), otherShield) < 0.05f);
    }
    // The runtime counter is never read as a spawn id: a GUID whose counter equals spawn 250131 but whose
    // entry is 42954 (spawns 250123 and 250130, both struck and gone) resolves to one of those, not to
    // 250131's shield.
    {
        Blackboard board = redirect(UnitGuid(42954, 250131), false);
        board.Interactables.erase(std::remove_if(board.Interactables.begin(), board.Interactables.end(),
            [](ActorSnapshot const& actor) { return actor.Entry == 42954; }), board.Interactables.end());
        Vector3 const toward = heading(board);
        assert(G::Distance2d(toward, shield) > 10.0f);
        Vector3 const east{ 181.769f, -253.035f, A::ArenaCenter.Z };
        Vector3 const north{ 108.625f, -171.259f, A::ArenaCenter.Z };
        assert(G::Distance2d(toward, east) < 0.05f || G::Distance2d(toward, north) < 0.05f);
    }
    // Nothing resolves for a caster that is no shield: the flame stays where it is.
    for (ObjectGuid caster : { UnitGuid(A::BossEntry, 9), UnitGuid(A::SonarBombMarkerEntry, 250131), ObjectGuid() })
    {
        Blackboard const board = redirect(caster, false);
        Vector3 const flame = board.Summons.back().Position;
        Vector3 const toward = heading(board);
        assert(G::Distance2d(toward, flame) < 0.05f);
    }
}

static void TestDetoursProgressAndSlotsAvoidFire()
{
    // A walk around fire gains ground every step (no back and forth).
    Blackboard board = QuietAir(Elemental, { 130.0f, -225.0f, 75.0f });
    for (int index = 0; index < 6; ++index)
        board.Summons.push_back(MakeUnit(A::RoaringFlamePatchEntry, 940 + index, 140.0f,
            -231.0f + 2.0f * float(index), ActorKind::Summon));
    D::Field const field = D::BuildField(board, A::BuildFacts(board), Member(board, Elemental));
    Vector3 const goal{ 152.0f, -225.0f, 75.0f };
    std::optional<Vector3> const detour = D::DetourPoint(field, Member(board, Elemental), goal);
    assert(detour && G::Distance2d(*detour, goal) <= G::Distance2d(Member(board, Elemental).Position, goal)
        - D::DetourProgressYards && D::PathCost(field, Member(board, Elemental).Position, *detour, 7.0f) == 0.0f);
    // Negative control: nothing in the way, straight there.
    D::Field const empty;
    assert(G::Distance2d(*D::DetourPoint(empty, Member(board, Elemental), goal), goal) < 0.01f);
    // Ground: a ranged arc slot on a Searing Flame patch moves along the arc.
    Blackboard ground = Board();
    Settle(ground);
    A::DutyPlan const duties = A::BuildDutyPlan(ground);
    std::size_t const index = std::size_t(std::find(duties.RangedOrder.begin(), duties.RangedOrder.end(),
        PlayerGuid(Elemental)) - duties.RangedOrder.begin());
    Vector3 const arc = A::ArcSlot(Boss(ground).Position, index, duties.RangedOrder.size(), A::RangedArcRadius);
    Member(ground, Elemental).Position = { 200.0f, -180.0f, 75.0f };
    assert(G::Distance2d(To(Plan(ground, Elemental)), arc) < 0.01f);
    ground.Summons.push_back(MakeUnit(A::SearingFlamePatchEntry, 950, arc.X, arc.Y, ActorKind::Summon));
    Vector3 const moved = To(Plan(ground, Elemental));
    assert(G::Distance2d(moved, arc) > 1.0f && A::FireFree(A::BuildFacts(ground), moved));
}

// Seconds a straight walk from `from` to `to` spends inside any bomb blast
// (6 yd) of `board`.
static float BlastSeconds(Blackboard const& board, Vector3 const& from, Vector3 const& to)
{
    float seconds = 0.0f;
    for (ActorSnapshot const& marker : board.Summons)
        if (marker.Entry == A::SonarBombMarkerEntry)
            seconds += A::KitePath::SecondsInside(from, to, marker.Position, A::SonarBombRadius, 7.0f);
    return seconds;
}

static void TestBombEscapeGeometry()
{
    // One zone: the escape is radial, just past the zone, and the fastest.
    D::Field field;
    Vector3 const marker{ 140.0f, -225.0f, 75.0f };
    field.Zones.push_back({ marker, D::BombClearYards, false, true });
    ActorSnapshot self = MakePlayer(Elemental, "dps", "elemental_shaman", 142.0f, -225.0f);
    assert(D::InBombZone(field, self.Position));
    std::optional<Vector3> const escape = D::BombEscape(field, self);
    assert(escape && !D::InBombZone(field, *escape));
    assert(std::fabs(G::Bearing(marker, *escape) - G::Bearing(marker, self.Position)) < 0.2f);
    assert(G::Distance2d(*escape, marker) < D::BombClearYards + D::SafetyPad + 1.0f);
    assert(std::fabs(D::ExitAlong(self.Position, 0.0f, marker, 6.0f) - 4.0f) < 0.01f);
    // Negative controls: outside every zone there is nothing to escape, and
    // a fire patch alone is no bomb zone.
    self.Position = { 150.0f, -225.0f, 75.0f };
    assert(!D::BombEscape(field, self));
    D::Field fire;
    fire.Zones.push_back({ marker, D::PatchClearYards, true, false });
    self.Position = marker;
    assert(!D::InBombZone(fire, self.Position) && !D::BombEscape(fire, self));
}

// Live r03 batch 1: a Sonar Bomb landed on the striker the redirected flame
// re-tracks (its first chase sample was 20 Sound) and on a gong relay. Both
// now leave the zone by the fastest escape instead of walking on through the
// marker toward their waypoint or station.
static void TestRunnerAndRelayLeaveABombFirst()
{
    Blackboard run = AirBoard();
    for (ActorSnapshot& player : run.Players)
        player.Position = A::ArenaCenter;
    run.Summons.push_back(MakeUnit(A::ReverberatingFlameEntry, 81, 100.0f, -225.0f, ActorKind::Summon));
    Member(run, Hunter).Auras.push_back({ A::AirClashAura, ShieldGuid(250125), 0, run.ObservedAtMs + 15000 });
    Vector3 self{};
    Vector3 waypoint{};
    for (float degrees = 0.0f; degrees < 360.0f; degrees += 5.0f)
    {
        self = G::PointAt(A::ArenaCenter, degrees * A::Geometry::Pi / 180.0f, 50.0f, 75.0f);
        Member(run, Hunter).Position = self;
        AdaptiveAtramedesPlan const plain = Plan(run, Hunter);
        if (Mechanic(plain) == "air_redirect_run" && G::Distance2d(To(plain), self) >= 14.0f
            && A::ArenaFloor::Solid(self.X, self.Y))
        {
            waypoint = To(plain);
            break;
        }
    }
    assert(G::Distance2d(waypoint, self) >= 14.0f);
    // A marker 2 yd ahead on the run: the runner stands in its zone.
    Vector3 const ahead = G::PointAt(self, G::Bearing(self, waypoint), 2.0f, 75.0f);
    run.Summons.push_back(MakeUnit(A::SonarBombMarkerEntry, 960, ahead.X, ahead.Y, ActorKind::Summon));
    AdaptiveAtramedesPlan const out = Plan(run, Hunter);
    assert(Mechanic(out) == "air_redirect_run");
    assert(G::Distance2d(To(out), ahead) >= D::BombClearYards);
    // Out the near side (4 yd of blast), not on through the marker (8 yd).
    assert(BlastSeconds(run, self, To(out)) <= 4.0f / 7.0f + 0.1f);

    // The gong owner at its relay station with a marker 1.5 yd beside it.
    Blackboard relay = AirBoard();
    A::Facts const facts = A::BuildFacts(relay);
    A::ShieldFact const shield = A::RelayShields(facts).front();
    Vector3 const station = A::AirStationPoint(shield);
    Member(relay, Hunter).Position = station;
    Vector3 const beside = G::PointAt(station, G::Bearing(station, shield.Position), 1.5f, 75.0f);
    relay.Summons.push_back(MakeUnit(A::SonarBombMarkerEntry, 961, beside.X, beside.Y, ActorKind::Summon));
    AdaptiveAtramedesPlan const step = Plan(relay, Hunter);
    assert(Mechanic(step) == "air_relay_hazard_step");
    assert(G::Distance2d(To(step), beside) >= D::BombClearYards);
    // The radial way out (0.64 s of blast) leaves click reach; the escape
    // keeps reach for a sideways walk that is still out long before the bomb
    // lands (2.5 s after the marker).
    assert(G::Distance3d(A::ArenaFloor::OnFloor(To(step)), shield.Position) <= A::ShieldClickDistance);
    assert(BlastSeconds(relay, station, To(step)) <= 1.0f);
}

static void RunRules()
{
    TestBombEscapeGeometry();
    TestRunnerAndRelayLeaveABombFirst();
    TestBombExitAvoidsTheNextZone();
    TestFireTrailExitLeavesTheBand();
    TestMeleeDodgesEveryLaneInRange();
    TestTankAndMeleeHoldMaxRange();
    TestFlamePathAndRunner();
    TestRedirectUsesTheStruckShieldsRuntimeIdentity();
    TestDetoursProgressAndSlotsAvoidFire();
    std::puts("raid sound rules ok");
}
"""

DRIVER = r'''
int main()
{
#ifdef RAID_SOUND_ASSERT
    RunRules();
#endif
    SoundBook const book = RunBook(false);
    book.Print("dodge");
    SoundBook const still = RunBook(true);
    still.Print("static");
#ifdef RAID_SOUND_ASSERT
    RaidSoundAssertions(book, still);
#endif
    std::puts("raid sound replay ok");
    return 0;
}
'''

ASSERTIONS = r'''
static void RaidSoundAssertions(SoundBook const& book, SoundBook const& still)
{
    // Negative control: without the dodges the ground hazards land.
    assert(still.Of("ground", "all").Mean() >= 10.0);
    assert(still.Of("ground", "melee").Mean() >= 6.0 && still.Of("ground", "ranged").Mean() >= 6.0);
    // Ground: every role near 0 Sound (the tank and melee dodge the disks
    // around the boss at maximum melee range, everyone else steps out of
    // lanes, beam and fire), and the Sonic Breath kiter keeps the beam behind.
    for (char const* role : { "tank", "melee", "ranged", "healer", "gong_relay", "ice_mage" })
    {
        RoleTally const tally = book.Of("ground", role);
        std::printf("ground %s mean=%.2f max=%u\n", role, tally.Mean(), tally.Max);
        assert(tally.Samples > 0 && tally.Mean() <= GROUND_ROLE_MEAN && tally.Max <= GROUND_ROLE_MAX);
    }
    assert(book.Of("ground", "all").Mean() <= GROUND_ALL_MEAN);
    assert(book.Of("ground", "kiter_total").Max <= GROUND_KITER_MAX);
    // The cost: melee (and the tank) dodge inside melee range.
    auto const range = book.Sources.at("ground").at("melee_out_of_range_pct");
    assert(double(range.first) / double(range.second) <= MELEE_OUT_OF_RANGE_PCT);
    // Air (bombs and fire on, first and second phases): bystanders near 0.
    for (char const* phase : { "air_spawn7", "air_spawn3", "air2_spawn7", "air2_spawn3" })
    {
        for (char const* role : { "tank", "melee", "ranged", "healer", "gong_relay", "ice_mage" })
        {
            RoleTally const tally = book.Of(phase, role);
            assert(tally.Samples > 0 && tally.Mean() <= AIR_ROLE_MEAN);
        }
        assert(book.Of(phase, "all").Mean() <= AIR_ALL_MEAN);
        assert(book.Of(phase, "all").Max <= AIR_ALL_MAX);
        // Round 4: no bomb lands on anyone but the chased player (round 3:
        // 0.67-1.33 Sound per phase, the redirect runner and gong relays).
        assert(book.Sources.at(phase).at("bomb_bystander").first == 0);
    }
}
'''

# After-change bounds, a little above the measured values (the dossier's before/after table; before this change
# the same replay gave per-role ground means 1.8-15.1 with a tank at 100 Sound, air means 2.1-18.3, all
# roles 8.2-11.7 per air phase).
BOUNDS = {
    "GROUND_ROLE_MEAN": "2.0",
    "GROUND_ROLE_MAX": "12u",
    "GROUND_ALL_MEAN": "0.5",
    "GROUND_KITER_MAX": "6u",
    "AIR_ROLE_MEAN": "2.5",
    "AIR_ALL_MEAN": "1.0",
    "AIR_ALL_MAX": "25u",
    "MELEE_OUT_OF_RANGE_PCT": "3.0",
}


def build_program(assertions: bool) -> str:
    defines = "".join(f"#define {key} {value}\n" for key, value in BOUNDS.items())
    body = HARNESS + METRIC
    if assertions:
        body += "#define RAID_SOUND_ASSERT 1\n" + defines + RULES + ASSERTIONS
    return body + DRIVER


def compile_and_run(tmp_path: Path, include_first: list[str] | None = None, assertions: bool = True) -> str:
    source = tmp_path / "raid_sound.cpp"
    binary = tmp_path / "raid_sound"
    source.write_text(build_program(assertions), encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-O1",
                    *(include_first or []), *INCLUDES, str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    print(result.stdout)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    return result.stdout


def test_atramedes_raid_wide_sound_near_zero(tmp_path: Path) -> None:
    output = compile_and_run(tmp_path)
    assert "raid sound replay ok" in output


def _header_constant(text: str, name: str) -> float:
    match = re.search(rf"inline constexpr float {name} = ([0-9.]+)f;", text)
    assert match, name
    return float(match.group(1))


def test_shield_reserve_floor_is_derived_from_the_tier11_references() -> None:
    """The next-Searing-Flame reserve assumes a raid-DPS floor; it must not exceed any matched T11 kill."""
    gong = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/"
            "BotAtramedesGongPolicy.h").read_text(encoding="utf-8")
    floor = _header_constant(gong, "ReserveRaidDpsFloor")
    health = _header_constant(gong, "NativeHealth10N")
    reference = json.loads((ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/"
                            "atramedes_wcl_dps_reference_v1.json").read_text(encoding="utf-8"))
    target = json.loads((ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_atramedes.json")
                        .read_text(encoding="utf-8"))
    matched = {item["id"]: item for item in reference["references"]}
    raid_dps = [matched[identity]["raid_dps"] for identity in target["matched_reference_ids"]]
    band = reference["item_level_band"]
    assert len(raid_dps) == 7
    assert all(band["min"] <= matched[identity]["average_item_level"] <= band["max"]
               for identity in target["matched_reference_ids"])
    # Negative control: the old 150k floor (measured at ~409 gear) is above the slowest T11 kill.
    assert 150000.0 > min(raid_dps)
    assert floor <= min(raid_dps) and floor >= 0.95 * min(raid_dps) - 5000.0
    # The thresholds follow from the floor (82 s from the ground, 51 s from the air to the next Searing Flame).
    assert health == 26111168.0
    assert "100.0f * ReserveRaidDpsFloor * NextSearingSecondsFromGround / NativeHealth10N" in gong
    assert abs(100.0 * floor * 82.0 / health - 40.83) < 0.01 and abs(100.0 * floor * 51.0 / health - 25.39) < 0.01


def test_dodge_is_wired_and_bounded() -> None:
    folder = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes"
    dodge = (folder / "BotAtramedesDodge.h").read_text(encoding="utf-8")
    assert "user raid experience 2026-09-30" in dodge
    movement = (folder / "BotAtramedesMovementPolicy.h").read_text(encoding="utf-8")
    for exit_name in ("SonarPulseExit", "NearestFootprintExit", "FlameExit", "SonicBreathBeamExit"):
        body = movement[movement.index(f"inline std::optional<MoveProposal> {exit_name}("):]
        body = body[:body.index("\n}\n")]
        assert "Dodge::" in body, exit_name
    for path in folder.glob("*.h"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path.name
