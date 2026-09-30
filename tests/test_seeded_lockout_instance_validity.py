"""Round 2 (BWD 10N, Nefarian): the homebind pin loop of seeded-lockout members.

Raid-shard provisioning writes every character at the raid's start (map 669)
with instance_id 0. Player::LoadFromDB creates a fresh, unbound instance of
the raid for the ungrouped bot and clears m_InstanceValid; Group::AddMember
re-evaluates it against that stray instance before BotMgrLoading moves the bot
into its seeded instance, and nothing evaluates it there. Once the 60 s
homebind timer runs out, Player::UpdateHomebindTime calls RepopAtGraveyard on
every update: the graveyard teleport is refused for a bot, and on Nefarian's
platform the `|| GetTransport()` clause revives every member at 50% each tick.

VerifyAdmission now re-evaluates the flag natively in the seeded instance and
fails closed when it stays invalid; an admitted attempt fails closed on the
first member that reads invalid again; diagnose and the raid-runtime roster
export instance_valid, homebind_timer_ms and min_durability_fraction.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
HEADER = BOTS / "BotMemberInstanceState.h"
COHORT_CONTEXT = BOTS / "BotRaidLockoutCohortContext.cpp"
COHORT_GROUP = BOTS / "BotWorldPopulationMgrValidationCohortGroup.cpp"
ADMISSION = BOTS / "BotWorldPopulationMgrValidationAdmission.cpp"
STATUS = BOTS / "BotWorldPopulationMgrStatus.cpp"
RAID_RUNTIME = BOTS / "BotWorldPopulationMgrRaidRuntime.cpp"
LOADING = BOTS / "BotMgrLoading.cpp"
PLAYER = ROOT / "src/server/game/Entities/Player/Player.cpp"
GROUP = ROOT / "src/server/game/Groups/Group.cpp"
INCLUDES = ["src/server/game", "src/common"]


def _run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


def _body(text: str, signature: str) -> str:
    body = text[text.index(signature):]
    return body[:body.index("\n}\n")]


PREDICATES = r'''
#include "Bots/BotMemberInstanceState.h"
#include <cstdio>
#include <string>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

using namespace BotMemberInstanceState;

static ActiveFacts Admitted(bool inInstance, bool valid)
{
    ActiveFacts facts;
    facts.LockoutAttached = true;
    facts.LockoutAdmitted = true;
    facts.LockoutAttemptId = 3;
    facts.CohortAttemptId = 3;
    facts.InOriginalInstance = inInstance;
    facts.InstanceValid = valid;
    return facts;
}

int main()
{
    // Admission: the native re-evaluation in the seeded instance decides.
    CHECK(AdmissionFailure(true, 11005009).empty(), "a revalidated member is admitted");
    CHECK(AdmissionFailure(false, 11005009) == "seeded_lockout_member_instance_invalid:11005009",
        "a member still invalid in its seeded instance fails admission, typed with its guid");

    // Active attempt.
    CHECK(EvaluateActive(Admitted(true, true)) == ActiveVerdict::Valid, "valid member passes");
    CHECK(ActiveFailureReason(EvaluateActive(Admitted(true, true))) == nullptr, "no reason when valid");
    // Adversarial: the pin-loop state inside the seeded instance.
    ActiveVerdict const pinned = EvaluateActive(Admitted(true, false));
    CHECK(pinned == ActiveVerdict::InstanceInvalid, "an invalid member in the seeded instance fails");
    CHECK(std::string(ActiveFailureReason(pinned))
        == "validation_active_seeded_lockout_member_instance_invalid", "typed active reason");
    // A member in a typed recovery transit (graveyard map) is owned by those checks.
    CHECK(EvaluateActive(Admitted(false, false)) == ActiveVerdict::Valid,
        "outside the original instance the flag is not this check's evidence");
    // Missing evidence fails closed: no verified admission for this attempt.
    ActiveFacts stale = Admitted(true, true);
    stale.LockoutAttemptId = 2;
    CHECK(EvaluateActive(stale) == ActiveVerdict::AdmissionMissing, "a previous attempt's admission is stale");
    ActiveFacts unverified = Admitted(true, true);
    unverified.LockoutAdmitted = false;
    CHECK(EvaluateActive(unverified) == ActiveVerdict::AdmissionMissing, "an unverified admission fails closed");
    ActiveFacts zero = Admitted(true, true);
    zero.LockoutAttemptId = 0;
    zero.CohortAttemptId = 0;
    CHECK(EvaluateActive(zero) == ActiveVerdict::AdmissionMissing, "attempt 0 is never an admission");
    CHECK(std::string(ActiveFailureReason(ActiveVerdict::AdmissionMissing))
        == "validation_active_seeded_lockout_admission_missing", "typed missing-admission reason");
    // Negative control: a cohort without a seeded lockout (Stonecore,
    // calibration, legacy Magmaw b5) is never touched, whatever the flag reads.
    ActiveFacts fresh;
    fresh.InOriginalInstance = true;
    fresh.InstanceValid = false;
    CHECK(EvaluateActive(fresh) == ActiveVerdict::NotApplicable, "no lockout: not applicable");
    CHECK(ActiveFailureReason(EvaluateActive(fresh)) == nullptr, "no lockout: never a failure");

    // Durability: the lowest current/max over worn items; unworn items skipped.
    float fraction = -1.0f;
    CHECK(!MinDurabilityFraction({}, fraction) && fraction == -1.0f, "nothing worn: no reading");
    CHECK(!MinDurabilityFraction({ { 0, 0 }, { 5, 0 } }, fraction), "rings and trinkets never count");
    CHECK(MinDurabilityFraction({ { 160, 160 }, { 60, 120 }, { 0, 0 } }, fraction) && fraction == 0.5f,
        "lowest fraction");
    CHECK(MinDurabilityFraction({ { 0, 95 }, { 95, 95 } }, fraction) && fraction == 0.0f, "a broken item reads 0");
    CHECK(MinDurabilityFraction({ { 200, 160 } }, fraction) && fraction == 1.0f, "never above 1");

    // Export: an unread member is null everywhere, never a default "valid".
    Reading missing;
    CHECK(FieldsJson(missing)
        == ",\"instance_valid\":null,\"homebind_timer_ms\":null,\"min_durability_fraction\":null",
        "unloaded member exports nulls");
    Reading pinnedReading;
    pinnedReading.Loaded = true;
    pinnedReading.InstanceValid = false;
    pinnedReading.HomebindTimerMs = 60000;
    CHECK(FieldsJson(pinnedReading)
        == ",\"instance_valid\":false,\"homebind_timer_ms\":60000,\"min_durability_fraction\":null",
        "no worn item: durability null");
    Reading valid;
    valid.Loaded = true;
    valid.InstanceValid = true;
    valid.DurabilityKnown = true;
    valid.MinDurability = 0.625f;
    CHECK(ObjectJson(valid)
        == "{\"instance_valid\":true,\"homebind_timer_ms\":0,\"min_durability_fraction\":0.6250}",
        "diagnose object");
    std::printf("%s\n", ObjectJson(pinnedReading).c_str());
    return failures ? 1 : 0;
}
'''


# The core's own sequence, driven by the same predicates. The member is
# evaluated where the loading path evaluates it (the stray instance) and,
# with the fix, again in the seeded instance; UpdateHomebindTime and
# RepopAtGraveyard's transport clause then run for 70 seconds of updates.
PIN_LOOP = r'''
#include "Bots/BotMemberInstanceState.h"
#include <cstdio>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

using namespace BotMemberInstanceState;

// Player::CheckInstanceValidity for a raid instance and a grouped member
// (the other-group loop never fires: the cohort is one group).
static bool CheckInstanceValidity(bool raidGroup, uint32 groupBoundInstance, uint32 mapInstance)
{
    return raidGroup && groupBoundInstance && groupBoundInstance == mapInstance;
}

struct Member
{
    bool InstanceValid = true;   // Player constructor
    uint32 HomebindTimer = 0;
    float Health = 1.0f;
    uint32 Revives = 0;
    bool OnTransport = true;     // standing on Nefarian's platform
};

// Player::UpdateHomebindTime, then RepopAtGraveyard's revive clause (the
// graveyard teleport itself is refused for a bot session in a dungeon).
static void Update(Member& member, uint32 diff)
{
    if (member.InstanceValid)
    {
        member.HomebindTimer = 0;
        return;
    }
    if (member.HomebindTimer > 0)
    {
        if (diff >= member.HomebindTimer)
        {
            if (member.OnTransport)
            {
                member.Health = 0.5f;
                ++member.Revives;
            }
        }
        else
            member.HomebindTimer -= diff;
    }
    else
        member.HomebindTimer = 60000;
}

static Member Admit(bool revalidate, std::string& failure)
{
    uint32 const seeded = 7;
    uint32 const stray = 11;  // LoadFromDB: CreateMap(669, bot, 0) with no bind or group
    Member member;
    member.InstanceValid = false;  // LoadFromDB: raid map, no raid group
    // Group::AddMember against the stray instance (the group is bound to the seeded one).
    member.InstanceValid = CheckInstanceValidity(true, seeded, stray);
    // BotMgrLoading: SetMap(seeded) and AddPlayerToMap leave the flag alone.
    if (revalidate)
    {
        member.InstanceValid = CheckInstanceValidity(true, seeded, seeded);
        failure = AdmissionFailure(member.InstanceValid, 11005009);
        if (failure.empty())
            member.HomebindTimer = 0;
    }
    return member;
}

static uint32 RunSeventySeconds(Member& member)
{
    for (uint32 t = 0; t < 70000; t += 50)
    {
        member.Health = 0.9f;  // healed or damaged in between
        Update(member, 50);
    }
    return member.Revives;
}

static ActiveFacts Facts(Member const& member)
{
    ActiveFacts facts;
    facts.LockoutAttached = true;
    facts.LockoutAdmitted = true;
    facts.LockoutAttemptId = 1;
    facts.CohortAttemptId = 1;
    facts.InOriginalInstance = true;
    facts.InstanceValid = member.InstanceValid;
    return facts;
}

int main()
{
    // Negative control: without the admission re-evaluation the member stays
    // invalid and is revived at 50% on every update after 60 s ...
    std::string failure;
    Member before = Admit(false, failure);
    CHECK(!before.InstanceValid, "the loading path leaves the member invalid");
    uint32 const pinned = RunSeventySeconds(before);
    CHECK(pinned > 100 && before.Health == 0.5f, "the pin loop revives the member every update");
    // ... and the active check reports it on the first observation.
    CHECK(EvaluateActive(Facts(before)) == ActiveVerdict::InstanceInvalid, "active check fails closed");

    // With the fix: admitted valid, never pinned, never failed.
    Member after = Admit(true, failure);
    CHECK(failure.empty() && after.InstanceValid && after.HomebindTimer == 0, "revalidated at admission");
    CHECK(RunSeventySeconds(after) == 0 && after.Health == 0.9f, "no repop, no pin");
    CHECK(EvaluateActive(Facts(after)) == ActiveVerdict::Valid, "active check passes");
    std::printf("pinned_revives=%u\n", pinned);
    return failures ? 1 : 0;
}
'''


def test_member_instance_state_predicates(tmp_path: Path) -> None:
    output = _run(tmp_path, PREDICATES)
    reading = json.loads(output.strip())
    assert reading == {"instance_valid": False, "homebind_timer_ms": 60000, "min_durability_fraction": None}


def test_pin_loop_needs_the_admission_revalidation(tmp_path: Path) -> None:
    output = _run(tmp_path, PIN_LOOP)
    assert int(re.search(r"pinned_revives=(\d+)", output).group(1)) > 100


def test_the_core_chain_the_diagnosis_relies_on() -> None:
    player = PLAYER.read_text(encoding="utf-8")
    load = _body(player, "bool Player::LoadFromDB(")
    # LoadFromDB: the saved map and instance id choose the map; validity is
    # evaluated there with the bot still ungrouped.
    assert "map = sMapMgr->CreateMap(mapId, this, instanceId);" in load
    assert load.index("SetMap(map);") < load.index("if (!CheckInstanceValidity(true) && !IsInstanceLoginGameMasterException())")
    homebind = _body(player, "void Player::UpdateHomebindTime(uint32 time)")
    assert "if (m_InstanceValid || IsGameMaster())" in homebind
    assert re.search(r"if \(time >= m_HomebindTimer\)\s*\{\s*// teleport to nearest graveyard\s*RepopAtGraveyard\(\);", homebind)
    repop = _body(player, "void Player::RepopAtGraveyard()")
    assert "|| GetTransport() ||" in repop and "ResurrectPlayer(0.5f);" in repop
    # The bot-session refusal of a cross-map teleport out of a dungeon.
    teleport = _body(player, "bool Player::TeleportTo(uint32 mapid,")
    assert "GetSession()->IsBotSession() && GetMap() && GetMap()->IsDungeon() && mapid != GetMapId()" in teleport
    group = GROUP.read_text(encoding="utf-8")
    add = _body(group, "bool Group::AddMember(Player* player)")
    assert "player->m_InstanceValid = player->CheckInstanceValidity(false);" in add
    loading = _body(LOADING.read_text(encoding="utf-8"), "Player* BotMgr::LoadCharacterAsBotSession(")
    # Membership (and its validity evaluation) precedes the destination map.
    assert loading.index("prejoinedGroup->AddMember(bot)") < loading.index("bot->SetMap(destinationMap);")
    assert loading.index("seed->Create(bot)") < loading.index("bot->SetMap(destinationMap);")
    assert "m_InstanceValid" not in loading
    # Raid-shard provisioning places characters on the raid map, instance 0.
    sql = (ROOT / "tools/raid_program/raid_loadout_sql.py").read_text(encoding="utf-8")
    columns = re.search(r"INSERT INTO `characters`\.`characters` \"\s*\"\(([^)]*)\)", sql).group(1)
    assert "`map`" in columns and "`instance_id`" not in columns


def test_admission_revalidates_in_the_seeded_instance_and_fails_closed() -> None:
    verify = _body(COHORT_CONTEXT.read_text(encoding="utf-8"), "std::string CohortContext::VerifyAdmission(")
    bind = verify.index('return fail("seeded_lockout_group_bind_mismatch");')
    revalidate = verify.index("bot->m_InstanceValid = bot->CheckInstanceValidity(false);")
    failure = verify.index("BotMemberInstanceState::AdmissionFailure(bot->m_InstanceValid,")
    fail_closed = verify.index("return fail(invalid);")
    timer = verify.index("bot->m_HomebindTimer = 0;")
    readback = verify.index("Readback const readback = ReadbackLockout(record);")
    # After the member is proven in the seeded instance through the bound
    # group, before the live readback and before any bot acts.
    assert verify.index("bot->GetInstanceId() != record.InstanceId") < bind < revalidate < failure < fail_closed < timer < readback
    admission = ADMISSION.read_text(encoding="utf-8")
    assert admission.index("BotRaidLockout::CohortContext::VerifyAdmission(*this);") \
        < admission.index("Cohort().ValidationAdmissionBatchSealed = true;")
    # Only the seeded-lockout context touches the flag; the shared loading
    # path (Stonecore, calibration, legacy Magmaw b5) is unchanged.
    for path in BOTS.glob("*.cpp"):
        if "m_InstanceValid =" in path.read_text(encoding="utf-8", errors="replace"):
            assert path == COHORT_CONTEXT, path
    arm = _body(COHORT_CONTEXT.read_text(encoding="utf-8"), "std::string CohortContext::ArmAdmission(")
    assert arm.index('if (!Registry::Find(cohort.Id, record))\n        return "";') < arm.index("lockout.Attached = true;")
    assert "if (!lockout.Attached)\n        return \"\";" in verify


def test_active_attempt_fails_closed_on_an_invalid_member() -> None:
    group = COHORT_GROUP.read_text(encoding="utf-8")
    active = group[group.index("if (activeObservationOnly)\n    {"):]
    active = active[:active.index("if (invalidReason)")]
    check = active.index("BotRaidLockout::CohortContext::ActiveMemberFailure(\n                    *this, bot, inOriginalInstance))")
    assert active.index("bool const inOriginalInstance = bot->GetMapId() == state.ValidationCohortMapId") < check
    assert "invalidate(state, bot, seededFailure);" in active[check:]
    context = _body(COHORT_CONTEXT.read_text(encoding="utf-8"), "char const* CohortContext::ActiveMemberFailure(")
    for fact in ("facts.LockoutAttached = lockout.Attached;", "facts.LockoutAdmitted = lockout.Admitted;",
                 "facts.LockoutAttemptId = lockout.AttemptId;", "facts.CohortAttemptId = cohort.AttemptId;",
                 "facts.InOriginalInstance = bot && inOriginalInstance;",
                 "facts.InstanceValid = bot && bot->m_InstanceValid;"):
        assert fact in context


def test_readings_are_exported_in_diagnose_and_both_rosters() -> None:
    status = STATUS.read_text(encoding="utf-8")
    diagnose = _body(status, "std::string BotWorldPopulationMgr::GetBotDiagnosisJson(")
    assert '<< ",\\"instance_state\\":" << BotMemberInstanceState::MemberObjectJson(bot)' in diagnose
    runtime = RAID_RUNTIME.read_text(encoding="utf-8")
    assert runtime.count("BotMemberInstanceState::RosterFieldsJson(guid)") == 2
    assert len(runtime.splitlines()) < 1000
    reader = (BOTS / "BotMemberInstanceState.cpp").read_text(encoding="utf-8")
    assert "reading.InstanceValid = bot->m_InstanceValid;" in reader
    assert "reading.HomebindTimerMs = bot->m_HomebindTimer;" in reader
    assert "ITEM_FIELD_MAXDURABILITY" in reader and "EQUIPMENT_SLOT_END" in reader
