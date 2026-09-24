#include "Bots/BotWorldPopulationMgrPlay.h"

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotPlayPullTimer.h"
#include "Bots/BotPlaySession.h"
#include "Bots/BotRaidRoleResolver.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Config.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupMgr.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "WorldSession.h"

#include <algorithm>
#include <chrono>
#include <limits>
#include <optional>
#include <sstream>

namespace BotWorldPopulationMgrPlay
{
namespace
{
// Same persisted recovery state the validation reset clears
// (tools/bot_ml/run_live_bot_validation.py build_bot_pool_reset_sql).
constexpr uint32 GhostCharacterFlag = 0x2000;
constexpr uint32 ResurrectAtLoginFlag = 0x0100;
constexpr uint32 GhostAuraId = 8326;

std::string Escape(std::string const& value)
{
    std::string escaped;
    for (char c : value)
    {
        if (c == '"' || c == '\\')
            escaped += '\\';
        escaped += c;
    }
    return escaped;
}

std::string Result(char const* action, bool ok, std::string const& reason,
    std::string const& extra = "")
{
    std::ostringstream json;
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_play_" << action << "\"" << extra
         << ",\"failure_reason\":"
         << (ok ? std::string("null") : "\"" + Escape(reason) + "\"") << '}';
    return json.str();
}

bool IsHuman(Player const* player)
{
    return player && player->GetSession() && !player->GetSession()->IsBotSession();
}

// Monotonic milliseconds; GameTime's uint32 counter wraps after 49 days.
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

// A human within this range of the next node's anchor has arrived there.
constexpr float AdvanceArrivalRange = 45.0f;

// Templates: the route node type is private to the manager; only the friend
// Context names it.
template <typename Node>
Position NodeAnchor(Node const& node)
{
    bool const navigation = node.NavigationAnchorX != 0.0f || node.NavigationAnchorY != 0.0f;
    return Position(navigation ? node.NavigationAnchorX : node.X,
        navigation ? node.NavigationAnchorY : node.Y,
        navigation ? node.NavigationAnchorZ : node.Z);
}

template <typename Node>
bool IsNodeCreature(Node const& node, Unit const* unit)
{
    Creature const* creature = unit ? unit->ToCreature() : nullptr;
    if (!creature)
        return false;
    uint32 const entry = creature->GetEntry();
    auto in = [entry](std::vector<uint32> const& entries)
    {
        return std::find(entries.begin(), entries.end(), entry) != entries.end();
    };
    return entry == node.TargetEntry || entry == node.OpenerTargetEntry
        || in(node.AlternateTargetEntries) || in(node.AddTargetEntries)
        || in(node.PackTargetEntries) || in(node.ScriptedEventEntries);
}

uint8 LfgRoleMask(std::string const& role)
{
    if (role == "tank")
        return BotRaidRole::TankMask;
    if (role == "healer")
        return BotRaidRole::HealerMask;
    return BotRaidRole::DamageMask;
}

BotPlayExternal Register(Player* human, Group* group, std::string const& slotId)
{
    BotRaidRole::Resolution const resolution = BotRaidRole::Resolve(
        group ? group->GetLfgRoles(human->GetGUID()) : 0,
        human->GetPrimaryTalentTree(human->GetActiveSpec()));
    BotPlayExternal external;
    external.Guid = human->GetGUID();
    external.Name = human->GetName();
    external.Role = resolution.Role;
    external.ClassSpec = resolution.ClassSpec;
    external.RoleSource = resolution.Source;
    external.RoleAmbiguous = resolution.Ambiguous;
    external.SlotId = slotId;
    external.RegisteredAtMs = GameTime::GetGameTimeMS();
    // Bots read the group role first (GetDungeonRole), so a human never
    // falls back to the class guess that calls every Warrior a tank.
    if (group)
        group->SetLfgRoles(human->GetGUID(), LfgRoleMask(external.Role));
    return external;
}
}

std::string Context::Fill(BotWorldPopulationMgr& mgr, Player* leader)
{
    char const* action = "fill";
    if (!sConfigMgr->GetBoolDefault("BotWorld.PlayMode.Enable", false))
        return Result(action, false, "play_mode_disabled");
    if (!IsHuman(leader))
        return Result(action, false, "leader_must_be_an_online_player");
    if (leader->IsGameMaster())
        return Result(action, false, "gm_mode_on_type_gm_off");
    for (auto const& [id, cohort] : mgr._cohorts)
        if (cohort->Active)
            return Result(action, false, id == CohortId
                ? "play_session_already_active" : "another_cohort_active:" + id);

    Group* group = leader->GetGroup();
    if (!group)
    {
        group = new Group();
        if (!group->Create(leader))
        {
            delete group;
            return Result(action, false, "group_create_failed");
        }
        sGroupMgr->AddGroup(group);
    }
    if (group->GetLeaderGUID() != leader->GetGUID())
        return Result(action, false, "only_the_raid_leader_can_fill");
    if (!group->isRaidGroup())
        group->ConvertToRaid();
    if (group->GetRaidDifficulty() != RAID_DIFFICULTY_10MAN_NORMAL)
        return Result(action, false, "set_raid_difficulty_to_10_player_normal");

    std::vector<Player*> humans;
    for (Group::MemberSlot const& slot : group->GetMemberSlots())
    {
        Player* member = ObjectAccessor::FindConnectedPlayer(slot.guid);
        if (!member)
            return Result(action, false, "offline_member:" + slot.name);
        if (!IsHuman(member))
            return Result(action, false, "bot_already_in_group:" + slot.name);
        humans.push_back(member);
    }

    mgr.CreateCohort(CohortId);
    BotWorldPopulationMgr::CohortRuntime* cohort = mgr.FindCohort(CohortId);
    if (!cohort)
        return Result(action, false, "play_cohort_missing");
    std::string const previous = mgr._selectedCohortId;
    mgr._selectedCohortId = CohortId;
    cohort->Purpose = CohortPurpose::Play;
    cohort->Play = BotPlaySession();
    auto abandon = [&mgr, cohort, &previous](std::string const& reason)
    {
        cohort->Purpose = CohortPurpose::Validation;
        cohort->Play = BotPlaySession();
        cohort->Play.LastEvent = "fill_failed:" + reason;
        mgr._selectedCohortId = previous;
        return Result("fill", false, reason);
    };

    // Load the trained roster of the scenario to choose which bots stay out.
    std::string const selected = mgr.SelectRuntimeProfile(Scenario);
    if (selected.find("\"ok\":true") == std::string::npos)
        return abandon("play_profile_unavailable");
    mgr.LoadConfig(Scenario, nullptr);
    if (mgr.Party().ValidationRouteManifest.empty())
        return abandon("play_route_manifest_missing");
    std::vector<BotPlayRoster::TemplateSlot> roster;
    for (auto const& identity : mgr.Party().ValidationRouteManifest.front().ExpectedRoster)
        roster.push_back({ identity.RosterSlotId, identity.Role, identity.ClassSpec });

    std::vector<BotPlayExternal> externals;
    std::vector<std::string> roles;
    for (Player* human : humans)
    {
        externals.push_back(Register(human, group, ""));
        roles.push_back(externals.back().Role);
    }
    std::string failure;
    std::vector<std::string> const slots = BotPlayRoster::ChooseExternalSlots(
        roster, roles, BotPlayRoster::DisruptionOrder(Scenario), &failure);
    if (slots.size() != humans.size())
        return abandon(failure.empty() ? "play_slot_choice_failed" : failure);

    BotPlaySession& session = cohort->Play;
    session.Active = true;
    session.StartedAtMs = GameTime::GetGameTimeMS();
    session.SessionId = "play-" + std::to_string(leader->GetGUID().GetCounter())
        + "-" + std::to_string(GameTime::GetGameTime());
    session.LeaderGuid = leader->GetGUID();
    session.GroupGuid = group->GetGUID();
    session.Scenario = Scenario;
    for (size_t index = 0; index < externals.size(); ++index)
    {
        externals[index].SlotId = slots[index];
        session.ExternalSlotIds.insert(slots[index]);
        session.Externals[externals[index].Guid.GetRawValue()] = externals[index];
    }
    session.LastEvent = "filling";
    // Each human takes the subgroup of the trained slot it replaces, so the
    // bots' trained subgroups stay at five members each.
    for (size_t index = 0; index < roster.size(); ++index)
        for (BotPlayExternal const& external : externals)
            if (external.SlotId == roster[index].SlotId
                && group->GetMemberGroup(external.Guid) != uint8(index / MAXGROUPSIZE))
                group->ChangeMembersGroup(external.Guid, uint8(index / MAXGROUPSIZE));
    mgr._selectedCohortId = previous;

    TC_LOG_INFO("server", "BotWorld play fill session=%s leader=%s group=%s humans=%u",
        session.SessionId.c_str(), leader->GetName().c_str(),
        group->GetGUID().ToString().c_str(), uint32(humans.size()));
    bool const autonomyStarted = mgr.StartAutonomyForCohort(CohortId);

    mgr._selectedCohortId = CohortId;
    // StartAutonomy reports Cohort().Active, which a failed admission leaves
    // set; success is an active admission of exactly the planned bots on the
    // Magmaw scenario (a configured runtime profile must not replace it).
    uint32 const expectedBots = uint32(roster.size() - session.ExternalSlotIds.size());
    // Config.Name is renamed by an auto recording window; the selected
    // profile and route scenario are the immutable identity.
    bool const started = autonomyStarted
        && mgr.Cohort().ValidationAdmission == ValidationAdmissionPhase::Active
        && mgr.Cohort().ValidationRaidAdmissionComplete
        && mgr.Party().Bots.size() == expectedBots
        && mgr.Cohort().SelectedProfileName == Scenario
        && mgr.Cohort().Config.ValidationRouteScenarioId == Scenario;
    std::ostringstream extra;
    extra << ",\"session_id\":\"" << Escape(session.SessionId) << "\""
          << ",\"bots\":" << mgr.Party().Bots.size()
          << ",\"external_slots\":[";
    bool first = true;
    for (std::string const& slot : session.ExternalSlotIds)
    {
        extra << (first ? "" : ",") << '"' << Escape(slot) << '"';
        first = false;
    }
    extra << ']';
    std::string reason = !mgr.Cohort().ValidationAttemptFailureReason.empty()
        ? mgr.Cohort().ValidationAttemptFailureReason
        : mgr.Cohort().LastPopulationFailureReason;
    if (reason.empty() && mgr.Cohort().SelectedProfileName != Scenario)
        reason = "play_profile_replaced:" + mgr.Cohort().SelectedProfileName;
    mgr._selectedCohortId = previous;
    if (!started)
    {
        // Leave nothing half-started, so the leader can simply fill again.
        mgr.StopAutonomyForCohort(CohortId);
        cohort->Play = BotPlaySession();
        cohort->Play.LastEvent = "fill_failed:" + reason;
        cohort->Purpose = CohortPurpose::Validation;
        return Result(action, false, reason.empty() ? "play_start_failed" : reason, extra.str());
    }
    session.LastEvent = "holding_at_entrance";
    return Result(action, true, "", extra.str());
}

std::string Context::Go(BotWorldPopulationMgr& mgr, Player* invoker)
{
    char const* action = "go";
    BotWorldPopulationMgr::CohortRuntime* cohort = mgr.FindCohort(CohortId);
    if (!cohort || !cohort->Active || !cohort->Play.Active)
        return Result(action, false, "no_active_play_session");
    if (IsHuman(invoker))
    {
        Group* group = invoker->GetGroup();
        if (!group || group->GetGUID() != cohort->Play.GroupGuid
            || (!group->IsLeader(invoker->GetGUID())
                && !group->IsAssistant(invoker->GetGUID())))
            return Result(action, false, "only_the_raid_leader_or_assistant_can_go");
    }
    std::string const previous = mgr._selectedCohortId;
    mgr._selectedCohortId = CohortId;
    uint64 const current = mgr.Party().ValidationRouteGeneration;
    cohort->Play.PermittedGeneration = std::max(cohort->Play.PermittedGeneration, current + 1);
    cohort->Play.LastEvent = "go";
    std::ostringstream extra;
    extra << ",\"route_generation\":" << current
          << ",\"permitted_generation\":" << cohort->Play.PermittedGeneration
          << ",\"node\":\"" << Escape(mgr.Cohort().Config.ValidationRouteNodeId) << "\"";
    mgr._selectedCohortId = previous;
    return Result(action, true, "", extra.str());
}

std::string Context::Stop(BotWorldPopulationMgr& mgr, Player* invoker)
{
    char const* action = "stop";
    BotWorldPopulationMgr::CohortRuntime* cohort = mgr.FindCohort(CohortId);
    if (!cohort || cohort->Purpose != CohortPurpose::Play)
        return Result(action, false, "no_play_cohort");
    if (IsHuman(invoker) && cohort->Play.Active)
    {
        Group* group = invoker->GetGroup();
        if (!group || group->GetGUID() != cohort->Play.GroupGuid
            || !group->IsLeader(invoker->GetGUID()))
            return Result(action, false, "only_the_raid_leader_can_stop");
    }
    // Despawning removes each bot from the human's raid (BotMgr cleanup
    // re-reads the bot's group every time). A raid left with one human is
    // disbanded by the core.
    std::string const stopped = mgr.StopAutonomyForCohort(CohortId);
    cohort->Play = BotPlaySession();
    cohort->Play.LastEvent = "stopped";
    cohort->Purpose = CohortPurpose::Validation;
    return Result(action, true, "", ",\"stop\":" + stopped);
}

std::string Context::Status(BotWorldPopulationMgr& mgr)
{
    BotWorldPopulationMgr::CohortRuntime* cohort = mgr.FindCohort(CohortId);
    if (!cohort)
        return Result("status", false, "no_play_cohort");
    std::string const previous = mgr._selectedCohortId;
    mgr._selectedCohortId = CohortId;
    uint32 alive = 0;
    for (auto const& state : mgr.Party().Bots)
        if (Player* bot = mgr.GetLoadedBot(state))
            alive += bot->IsAlive() ? 1 : 0;
    std::ostringstream extra;
    extra << ",\"active\":" << (cohort->Active ? "true" : "false")
          << ",\"event\":\"" << Escape(cohort->Play.LastEvent) << "\""
          << ",\"bots\":" << mgr.Party().Bots.size() << ",\"bots_alive\":" << alive
          << ",\"node\":\"" << Escape(mgr.Cohort().Config.ValidationRouteNodeId) << "\""
          << ",\"route_generation\":" << mgr.Party().ValidationRouteGeneration
          << ",\"permitted_generation\":" << cohort->Play.PermittedGeneration
          << ",\"ready_check_pending\":" << (cohort->Raid.NativeReadyCheckPending ? "true" : "false")
          << ",\"ready_check_responses\":" << cohort->Raid.NativeReadyCheckResponseCount
          << ",\"wipe_state\":\"" << Escape(cohort->Raid.WipeState) << "\""
          << ",\"pull_in_ms\":" << (cohort->Play.PullAtMs
              ? int64(cohort->Play.PullAtMs) - int64(NowMs()) : 0)
          << ",\"pull_source\":\"" << Escape(cohort->Play.PullSource) << "\""
          << ",\"admission\":\"" << Escape(mgr.Cohort().ValidationAttemptFailureReason.empty()
              ? mgr.Cohort().LastPopulationFailureReason
              : mgr.Cohort().ValidationAttemptFailureReason) << "\"";
    extra << StatusFieldsJson(mgr);
    mgr._selectedCohortId = previous;
    return Result("status", true, "", extra.str());
}

bool Context::IsExternalSlot(BotWorldPopulationMgr const& mgr, std::string const& slotId)
{
    return mgr.Cohort().Purpose == CohortPurpose::Play
        && mgr.Cohort().Play.ExternalSlotIds.count(slotId) != 0;
}

uint32 Context::ExternalSlotCount(BotWorldPopulationMgr const& mgr)
{
    return mgr.Cohort().Purpose == CohortPurpose::Play
        ? uint32(mgr.Cohort().Play.ExternalSlotIds.size()) : 0;
}

uint32 Context::ExpectedBotCount(BotWorldPopulationMgr const& mgr, uint32 declaredRosterSize)
{
    uint32 const external = ExternalSlotCount(mgr);
    return declaredRosterSize > external ? declaredRosterSize - external : declaredRosterSize;
}

bool Context::ResetBotPool(BotWorldPopulationMgr& mgr, char const* reason)
{
    // A configured BotWorld.RuntimeProfile must not replace the play
    // scenario between fill and admission.
    if (mgr.Cohort().SelectedProfileName != Scenario
        || mgr.Cohort().Config.ValidationRouteScenarioId != Scenario)
    {
        mgr.Cohort().LastPopulationFailureReason = "play_profile_replaced";
        return false;
    }
    std::string tag = mgr.Cohort().Config.PoolTagFilter;
    CharacterDatabase.EscapeString(tag);
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT `guid` FROM `character_bot_pool` WHERE `enabled` = 1 AND `experiment_tags` = '%s' ORDER BY `guid`",
        tag.c_str());
    if (!result)
    {
        mgr.Cohort().LastPopulationFailureReason = "play_pool_empty";
        return false;
    }
    std::ostringstream list;
    bool first = true;
    std::vector<uint32> guids;
    do
    {
        guids.push_back(result->Fetch()[0].GetUInt32());
        list << (first ? "" : ",") << guids.back();
        first = false;
    } while (result->NextRow());
    {
        std::lock_guard<std::mutex> guard(mgr._leaseMutex);
        for (uint32 guid : guids)
            if (mgr._guidLeases.count(guid))
            {
                mgr.Cohort().LastPopulationFailureReason = "play_pool_guid_leased";
                return false;
            }
    }
    std::string const in = "(" + list.str() + ")";
    uint32 const seed = std::numeric_limits<uint32>::max();
    // Bot-owned rows only: a human's group keeps its rows; only the bots'
    // memberships and bot-led groups are removed.
    std::vector<std::string> const statements = {
        "UPDATE `character_bot_pool` SET `in_use` = 0 WHERE `guid` IN " + in,
        "UPDATE `characters` SET `online` = 0, `health` = " + std::to_string(seed)
            + ", `power1` = " + std::to_string(seed)
            + ", `characterFlags` = `characterFlags` & ~" + std::to_string(GhostCharacterFlag)
            + ", `at_login` = `at_login` & ~" + std::to_string(ResurrectAtLoginFlag)
            + " WHERE `guid` IN " + in,
        "DELETE FROM `character_instance` WHERE `guid` IN " + in,
        "DELETE FROM `corpse_phases` WHERE `OwnerGuid` IN " + in,
        "DELETE FROM `corpse` WHERE `guid` IN " + in,
        "DELETE FROM `character_aura` WHERE `guid` IN " + in + " AND `spell` = " + std::to_string(GhostAuraId),
        "DELETE FROM `character_spell_cooldown` WHERE `guid` IN " + in,
        "DELETE gi FROM `group_instance` gi JOIN `groups` g ON g.`guid` = gi.`guid` WHERE g.`leaderGuid` IN " + in,
        "DELETE gm FROM `group_member` gm WHERE gm.`memberGuid` IN " + in
            + " OR gm.`guid` IN (SELECT g.`guid` FROM `groups` g WHERE g.`leaderGuid` IN " + in + ")",
        "DELETE FROM `groups` WHERE `leaderGuid` IN " + in,
        "DELETE pc FROM `pet_spell_cooldown` pc JOIN `character_pet` cp ON cp.`id` = pc.`guid` WHERE cp.`owner` IN " + in,
        "DELETE pa FROM `pet_aura` pa JOIN `character_pet` cp ON cp.`id` = pa.`guid` WHERE cp.`owner` IN " + in,
        "DELETE FROM `mail_items` WHERE `receiver` IN " + in,
        "DELETE FROM `mail` WHERE `receiver` IN " + in,
    };
    for (std::string const& statement : statements)
        CharacterDatabase.DirectExecute(statement.c_str());
    TC_LOG_INFO("server", "BotWorld play reset pool tag=%s bots=%u session=%s reason=%s",
        mgr.Cohort().Config.PoolTagFilter.c_str(), uint32(guids.size()),
        mgr.Cohort().Play.SessionId.c_str(), reason ? reason : "");
    return true;
}

Player* Context::AdmissionAnchor(BotWorldPopulationMgr& mgr)
{
    BotPlaySession const& session = mgr.Cohort().Play;
    auto anchored = [&session](Player* player)
    {
        return IsHuman(player) && player->GetGroup()
            && player->GetGroup()->GetGUID() == session.GroupGuid;
    };
    Player* leader = ObjectAccessor::FindConnectedPlayer(session.LeaderGuid);
    if (anchored(leader))
        return leader;
    for (auto const& [raw, external] : session.Externals)
        if (Player* human = ObjectAccessor::FindConnectedPlayer(external.Guid))
            if (anchored(human))
                return human;
    return nullptr;
}

bool Context::NativeGroupAdmits(BotWorldPopulationMgr& mgr, Group* group,
    std::set<ObjectGuid> const& botGuids)
{
    BotPlaySession& session = mgr.Cohort().Play;
    if (!group || group->GetGUID() != session.GroupGuid
        || group->GetMembersCount() > mgr.Cohort().Config.RaidSize)
        return false;
    std::set<ObjectGuid> members;
    for (Group::MemberSlot const& slot : group->GetMemberSlots())
        members.insert(slot.guid);
    for (ObjectGuid const& bot : botGuids)
        if (!members.count(bot))
            return false;
    for (ObjectGuid const& member : members)
    {
        if (botGuids.count(member))
            continue;
        Player* player = ObjectAccessor::FindConnectedPlayer(member);
        // A foreign bot is never a human; an offline human keeps its entry.
        if (player && !IsHuman(player))
            return false;
        if (player && !session.Externals.count(member.GetRawValue()))
        {
            session.Externals[member.GetRawValue()] = Register(player, group, "");
            session.LastEvent = "human_joined:" + player->GetName();
        }
    }
    return true;
}

bool Context::PermitRouteAdvance(BotWorldPopulationMgr& mgr, uint64 prospectiveGeneration)
{
    BotPlaySession& session = mgr.Cohort().Play;
    if (prospectiveGeneration <= session.PermittedGeneration)
        return true;
    auto const& manifest = mgr.Party().ValidationRouteManifest;
    size_t const targetIndex = size_t(prospectiveGeneration - 1);
    // Generation past the last node completes the route; nothing to follow.
    if (targetIndex == 0 || targetIndex >= manifest.size())
        return true;
    auto const& current = manifest[targetIndex - 1];
    auto const& next = manifest[targetIndex];

    // Read the raid like a human raider: follow the humans toward the next
    // pack or boss, join a fight they start there, and walk to the boss when
    // the leader starts a pull timer.
    uint64 const now = NowMs();
    std::string reason = BotPlayPullTimer::Running(session.PullAtMs, now)
            || BotPlayPullTimer::Released(session.PullAtMs, now)
        ? "pull_timer" : "";
    Position const currentAnchor = NodeAnchor(current);
    Position const nextAnchor = NodeAnchor(next);
    auto const& raid = mgr.Cohort().Raid;
    for (auto const& [raw, external] : session.Externals)
    {
        if (!reason.empty())
            break;
        Player* human = ObjectAccessor::FindConnectedPlayer(external.Guid);
        if (!IsHuman(human) || !human->IsInWorld() || !human->IsAlive()
            || human->GetMapId() != raid.MapId || human->GetInstanceId() != raid.InstanceId)
            continue;
        float const toNext = human->GetExactDist(&nextAnchor);
        if (toNext <= AdvanceArrivalRange)
            reason = "human_at_next:" + human->GetName();
        else if (toNext < human->GetExactDist(&currentAnchor))
            reason = "human_moving_ahead:" + human->GetName();
        else if (IsNodeCreature(next, human->GetVictim()))
            reason = "human_engaged:" + human->GetName();
        else
            for (Unit* attacker : human->getAttackers())
                if (IsNodeCreature(next, attacker))
                {
                    reason = "human_engaged:" + human->GetName();
                    break;
                }
    }
    if (reason.empty())
    {
        // Written once per hold, so status keeps showing pull and ready-check
        // events that happen while the bots wait.
        std::string const holding = "following_raid_to:" + next.NodeId;
        if (session.LastHoldEvent != holding)
            session.LastEvent = session.LastHoldEvent = holding;
        return false;
    }
    session.PermittedGeneration = prospectiveGeneration;
    session.LastHoldEvent.clear();
    session.LastEvent = "advance:" + next.NodeId + ":" + reason;
    TC_LOG_INFO("server", "BotWorld play advance session=%s node=%s reason=%s",
        session.SessionId.c_str(), next.NodeId.c_str(), reason.c_str());
    return true;
}

bool Context::PullPermitted(BotWorldPopulationMgr& mgr)
{
    BotPlaySession& session = mgr.Cohort().Play;
    if (session.PullAtMs && mgr.Cohort().Raid.WipeGeneration != session.PullWipeGeneration)
    {
        session.PullAtMs = 0;
        session.LastEvent = "pull_timer_consumed_by_wipe";
    }
    // Open only from zero until the release window closes: a timer from an
    // earlier pull never lets the bots pull the boss on arrival.
    return BotPlayPullTimer::Released(session.PullAtMs, NowMs());
}

std::string Context::Pull(BotWorldPopulationMgr& mgr, Player* invoker, bool cancel,
    uint32 seconds, std::string const& source)
{
    char const* action = "pull";
    BotWorldPopulationMgr::CohortRuntime* cohort = mgr.FindCohort(CohortId);
    if (!cohort || !cohort->Active || !cohort->Play.Active)
        return Result(action, false, "no_active_play_session");
    if (IsHuman(invoker))
    {
        Group* group = invoker->GetGroup();
        if (!group || group->GetGUID() != cohort->Play.GroupGuid
            || (!group->IsLeader(invoker->GetGUID())
                && !group->IsAssistant(invoker->GetGUID())))
            return Result(action, false, "only_the_raid_leader_or_assistant_can_pull");
    }
    BotPlaySession& session = cohort->Play;
    session.PullSource = source;
    if (cancel)
    {
        session.PullAtMs = 0;
        session.LastEvent = "pull_cancelled:" + source;
    }
    else
    {
        seconds = std::min(seconds, BotPlayPullTimer::MaxSeconds);
        session.PullAtMs = NowMs() + uint64(seconds) * 1000;
        session.PullWipeGeneration = cohort->Raid.WipeGeneration;
        session.LastEvent = "pull_timer:" + std::to_string(seconds) + "s:" + source;
    }
    TC_LOG_INFO("server", "BotWorld play pull session=%s cancel=%u seconds=%u source=%s",
        session.SessionId.c_str(), uint32(cancel), seconds, source.c_str());
    return Result(action, true, "", ",\"cancel\":" + std::string(cancel ? "true" : "false")
        + ",\"seconds\":" + std::to_string(seconds));
}

bool Context::FromPlayLeadership(BotWorldPopulationMgr& mgr, Player* sender)
{
    BotWorldPopulationMgr::CohortRuntime* cohort = mgr.FindCohort(CohortId);
    Group* group = sender ? sender->GetGroup() : nullptr;
    return cohort && cohort->Active && cohort->Purpose == CohortPurpose::Play
        && cohort->Play.Active && IsHuman(sender) && group
        && group->GetGUID() == cohort->Play.GroupGuid
        && (group->IsLeader(sender->GetGUID()) || group->IsAssistant(sender->GetGUID()));
}

void OnAddonMessage(Player* sender, uint32 chatType, std::string const& prefix,
    std::string const& message)
{
    if ((chatType != CHAT_MSG_RAID && chatType != CHAT_MSG_PARTY)
        || !Context::FromPlayLeadership(*sBotWorldPopulationMgr, sender))
        return;
    std::optional<BotPlayPullTimer::Signal> const signal =
        BotPlayPullTimer::ParseAddon(prefix, message);
    if (!signal)
        return;
    Context::Pull(*sBotWorldPopulationMgr, sender, signal->Cancel, signal->Seconds,
        "addon:" + prefix);
}

void OnGroupChat(Player* sender, uint32 chatType, std::string const& message, Group* /*group*/)
{
    if (chatType != CHAT_MSG_RAID && chatType != CHAT_MSG_RAID_LEADER
        && chatType != CHAT_MSG_RAID_WARNING && chatType != CHAT_MSG_PARTY
        && chatType != CHAT_MSG_PARTY_LEADER)
        return;
    if (!Context::FromPlayLeadership(*sBotWorldPopulationMgr, sender))
        return;
    std::optional<BotPlayPullTimer::Signal> const signal = BotPlayPullTimer::ParseChat(message);
    if (!signal)
        return;
    Context::Pull(*sBotWorldPopulationMgr, sender, signal->Cancel, signal->Seconds, "chat");
}

bool Context::FrozenLeaderHolds(BotWorldPopulationMgr const& mgr, Group const* group,
    ObjectGuid frozenLeader)
{
    return mgr.Cohort().Purpose == CohortPurpose::Play
        || (group && group->GetLeaderGUID() == frozenLeader);
}

void Context::OnRaidReadyCheckStarted(BotWorldPopulationMgr& mgr, Group* group, Player* initiator)
{
    BotWorldPopulationMgr::CohortRuntime* cohort = mgr.FindCohort(CohortId);
    if (!group || !IsHuman(initiator) || !cohort || !cohort->Active
        || cohort->Purpose != CohortPurpose::Play || !cohort->Play.Active
        || group->GetGUID() != cohort->Play.GroupGuid)
        return;
    // Same arming as RequestNativeRaidReadyCheckForCohort, minus the request
    // packet the human leader already sent. Each bot answers from its own
    // update loop once it is independently ready (TryRespondNativeRaidReadyCheck).
    auto& raid = cohort->Raid;
    // A check already answered for this wipe and roster stays answered (a
    // pre-pull check must not reopen a completed wipe recovery), but the bots
    // still answer the new check.
    if (raid.NativeReadyCheckActionObserved
        && raid.NativeReadyCheckActionWipeGeneration == raid.WipeGeneration
        && raid.NativeReadyCheckAssignmentGeneration == raid.AssignmentGeneration)
    {
        ++raid.NativeReadyCheckActionGeneration;
        raid.NativeReadyCheckResponseCount = 0;
        raid.NativeReadyCheckResponders.clear();
        raid.NativeReadyCheckPending = true;
        cohort->Play.LastEvent = "ready_check:" + initiator->GetName();
        return;
    }
    ++raid.EvidenceSequence;
    ++raid.NativeReadyCheckActionGeneration;
    raid.NativeReadyCheckActionAttemptId = raid.AttemptId;
    raid.NativeReadyCheckActionWipeGeneration = raid.WipeGeneration;
    raid.NativeReadyCheckAssignmentGeneration = raid.AssignmentGeneration;
    raid.NativeReadyCheckActionEvidenceSequence = raid.EvidenceSequence;
    raid.NativeReadyCheckResponseCount = 0;
    raid.NativeReadyCheckResponders.clear();
    raid.NativeReadyCheckActionObserved = false;
    raid.NativeReadyCheckPending = true;
    cohort->Play.LastEvent = "ready_check:" + initiator->GetName();
}

void OnRaidReadyCheckStarted(Group* group, Player* initiator)
{
    Context::OnRaidReadyCheckStarted(*sBotWorldPopulationMgr, group, initiator);
}

void Context::PublishExternalPlayers(BotWorldPopulationMgr& mgr,
    BotEncounter::Blackboard& board, Player* observer,
    std::function<BotEncounter::ActorSnapshot(Unit*)> const& build,
    std::set<ObjectGuid>& seenUnits)
{
    Group* group = observer ? observer->GetGroup() : nullptr;
    BotPlaySession const& session = mgr.Cohort().Play;
    if (!group || group->GetGUID() != session.GroupGuid)
        return;
    for (Group::MemberSlot const& slot : group->GetMemberSlots())
    {
        if (seenUnits.count(slot.guid))
            continue;
        Player* human = ObjectAccessor::GetPlayer(*observer, slot.guid);
        if (!IsHuman(human) || !human->IsInWorld())
            continue;
        BotEncounter::ActorSnapshot actor = build(human);
        auto const external = session.Externals.find(slot.guid.GetRawValue());
        if (external != session.Externals.end())
        {
            actor.Role = external->second.Role;
            actor.ClassSpec = external->second.ClassSpec;
        }
        board.ExternalPlayers.push_back(std::move(actor));
        seenUnits.insert(slot.guid);
    }
}

std::string Context::StatusFieldsJson(BotWorldPopulationMgr const& mgr)
{
    if (mgr.Cohort().Purpose != CohortPurpose::Play || !mgr.Cohort().Play.Active)
        return "";
    BotPlaySession const& session = mgr.Cohort().Play;
    std::ostringstream json;
    json << ",\"play_session_id\":\"" << Escape(session.SessionId) << "\""
         << ",\"play_session\":{\"scenario\":\"" << Escape(session.Scenario) << "\""
         << ",\"leader_guid\":" << session.LeaderGuid.GetCounter()
         << ",\"permitted_generation\":" << session.PermittedGeneration
         << ",\"event\":\"" << Escape(session.LastEvent) << "\""
         << ",\"externals\":[";
    bool first = true;
    for (auto const& [raw, external] : session.Externals)
    {
        json << (first ? "" : ",") << "{\"guid\":" << external.Guid.GetCounter()
             << ",\"name\":\"" << Escape(external.Name) << "\""
             << ",\"role\":\"" << Escape(external.Role) << "\""
             << ",\"class_spec\":\"" << Escape(external.ClassSpec) << "\""
             << ",\"role_source\":\"" << Escape(external.RoleSource) << "\""
             << ",\"slot\":\"" << Escape(external.SlotId) << "\"}";
        first = false;
    }
    json << "]}";
    return json.str();
}
}
