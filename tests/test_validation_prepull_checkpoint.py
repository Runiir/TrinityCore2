from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"


def test_validation_prepull_checkpoint_is_default_off_and_centrally_wired() -> None:
    config = (BOT_DIR / "BotWorldPopulationMgrConfig.h").read_text(encoding="utf-8")
    preparation = (
        BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
    ).read_text(encoding="utf-8")
    candidates = (
        BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
    ).read_text(encoding="utf-8")
    consumables = (
        BOT_DIR / "BotWorldPopulationMgrRaidConsumables.cpp"
    ).read_text(encoding="utf-8")
    readback = (
        BOT_DIR / "BotWorldPopulationMgrRaidConsumablesJson.cpp"
    ).read_text(encoding="utf-8")

    assert "bool ValidationPrepullCheckpointEnable = false;" in config
    assert preparation.index("ValidationPrepullCheckpoint.Configure") < preparation.index(
        "SubmitRaidPrepullConsumableCandidate(context);"
    )
    assert preparation.index("ValidationPrepullCheckpoint.Observe") < preparation.index(
        "InstallAdmissionPolicy"
    )
    assert "AdmissionClass::FormationMovement" in candidates
    assert "AdmissionClass::FriendlyHealing" in candidates
    assert "AdmissionClass::OffenseSuppression" in candidates
    assert "AdmissionClass::BagConsumable" in consumables
    assert '\\"validation_checkpoint\\"' in readback


def test_validation_prepull_checkpoint_crosses_production_kernel_boundary(
    tmp_path: Path,
) -> None:
    source = tmp_path / "validation_prepull_checkpoint.cpp"
    binary = tmp_path / "validation_prepull_checkpoint"
    source.write_text(
        r'''
#include "Bots/BotValidationPrepullCheckpoint.h"

#include <cassert>
#include <algorithm>
#include <string>
#include <vector>

using namespace BotActionArbitration;
using namespace BotValidationPrepullCheckpoint;

static void SubmitCandidate(Kernel& kernel, std::string key,
    AdmissionClass admission, std::string scope,
    std::vector<std::string>& attempts)
{
    Candidate candidate;
    candidate.Key = key;
    candidate.Source = "compiled_production_boundary";
    candidate.ActionPriority = Priority::Mechanic;
    candidate.Attempt = [&attempts, key]()
    {
        attempts.push_back(key);
        return Outcome::Committed("submitted");
    };
    kernel.SetCandidateAdmission(candidate.Key, admission, std::move(scope));
    assert(kernel.Submit(std::move(candidate)));
}

static std::vector<std::string> RunDisabled()
{
    Checkpoint checkpoint;
    checkpoint.Configure(false, {"raid", 9, 4, "magmaw"}, 10);
    Kernel kernel;
    std::vector<std::string> attempts;
    kernel.Begin(100);
    InstallAdmissionPolicy(kernel, checkpoint);
    SubmitCandidate(kernel, "hostile_player", AdmissionClass::Unknown,
        "wrong", attempts);
    SubmitCandidate(kernel, "pet_attack", AdmissionClass::Unknown,
        "wrong", attempts);
    Resolution const& result = kernel.Resolve();
    assert(result.CommittedCandidates.size() == 2);
    return attempts;
}

int main()
{
    Scope scope{"raid", 9, 4, "magmaw"};
    Checkpoint checkpoint;
    checkpoint.Configure(true, scope, 10);
    assert(checkpoint.CurrentPhase() == BotValidationPrepullCheckpoint::Phase::Staging);

    // Fail-before observation: without the checkpoint policy every hostile
    // attempt reaches the production Kernel callback.
    std::vector<std::string> const disabled = RunDisabled();
    assert(disabled.size() == 2);

    Kernel kernel;
    std::vector<std::string> attempts;
    kernel.Begin(100);
    InstallAdmissionPolicy(kernel, checkpoint);
    std::string const scopeKey = scope.Key();
    SubmitCandidate(kernel, "formation", AdmissionClass::FormationMovement,
        scopeKey, attempts);
    SubmitCandidate(kernel, "friendly_heal", AdmissionClass::FriendlyHealing,
        scopeKey, attempts);
    SubmitCandidate(kernel, "bag_flask_food_prepot", AdmissionClass::BagConsumable,
        scopeKey, attempts);
    SubmitCandidate(kernel, "offense_suppression", AdmissionClass::OffenseSuppression,
        scopeKey, attempts);
    SubmitCandidate(kernel, "hostile_player", AdmissionClass::Unknown,
        scopeKey, attempts);
    SubmitCandidate(kernel, "pet_attack", AdmissionClass::Unknown,
        scopeKey, attempts);
    SubmitCandidate(kernel, "taunt", AdmissionClass::Unknown,
        scopeKey, attempts);
    SubmitCandidate(kernel, "bossward_movement", AdmissionClass::Unknown,
        scopeKey, attempts);
    SubmitCandidate(kernel, "stale_formation", AdmissionClass::FormationMovement,
        "raid:8:4:magmaw", attempts);
    Resolution const& staged = kernel.Resolve();
    assert(staged.CommittedCandidates.size() == 4);
    assert(attempts.size() == 4);
    assert(std::find(attempts.begin(), attempts.end(), "formation") != attempts.end());
    assert(std::find(attempts.begin(), attempts.end(), "friendly_heal") != attempts.end());
    assert(std::find(attempts.begin(), attempts.end(), "bag_flask_food_prepot") != attempts.end());
    assert(std::find(attempts.begin(), attempts.end(), "offense_suppression") != attempts.end());

    Scope stale{"raid", 8, 4, "magmaw"};
    for (uint32_t guid = 1; guid <= 10; ++guid)
    {
        MemberReceipt ready{guid, true, true, true, true, true, true};
        assert(!checkpoint.Observe(stale, ready));
        assert(checkpoint.Observe(scope, ready));
    }
    assert(checkpoint.CurrentPhase() == BotValidationPrepullCheckpoint::Phase::Ready);
    assert(!checkpoint.Release(stale));
    assert(checkpoint.Release(scope));
    assert(!checkpoint.Release(scope));
    assert(checkpoint.CurrentPhase() == BotValidationPrepullCheckpoint::Phase::Released);
    assert(checkpoint.ReleaseCount() == 1);
    std::string const readback = checkpoint.ToJson();
    assert(readback.find("\"ready_count\":10") != std::string::npos);
    assert(readback.find("\"all_ready\":true") != std::string::npos);
    assert(readback.find("\"release_count\":1") != std::string::npos);

    // Pass-after observation: exact release removes the mask. The same
    // hostile/player and pet callbacks now reach production resolution once.
    attempts.clear();
    kernel.Begin(200);
    InstallAdmissionPolicy(kernel, checkpoint);
    SubmitCandidate(kernel, "hostile_player", AdmissionClass::Unknown,
        scopeKey, attempts);
    SubmitCandidate(kernel, "pet_attack", AdmissionClass::Unknown,
        scopeKey, attempts);
    Resolution const& released = kernel.Resolve();
    assert(released.CommittedCandidates.size() == 2);
    assert(attempts.size() == disabled.size());
    for (std::string const& key : disabled)
        assert(std::find(attempts.begin(), attempts.end(), key) != attempts.end());
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++20",
            "-O0",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/server/shared"),
            "-I",
            str(ROOT / "src/common"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
