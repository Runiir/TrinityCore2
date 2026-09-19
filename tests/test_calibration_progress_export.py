"""Exercise the production exporter body with native metric values."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_progress_uses_same_clock_and_totals_without_serializing_details(tmp_path):
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()
    start = source.index("std::string BotWorldPopulationMgr::GetCombatCalibrationJson(")
    end = source.index("\n// UpdateBot", start)
    body = source[start:end]
    harness = r'''
#include <cstdint>
#include <functional>
#include <iostream>
#include <map>
#include <sstream>
using uint64 = uint64_t;
using uint32 = uint32_t;
uint64 NowMs() { return 310000; }
namespace BotCalibrationFixtureContractGenerated {
struct SpecContract {};
SpecContract const* FindSpec(std::string const&) { return nullptr; }
}
struct CalibrationMetrics {
    uint64 WindowStartedMs = 10000, WindowEndedMs = 310000;
    uint64 Damage = 9600000, PetDamage = 900000, EffectiveHealing = 300000;
};
struct BotWorldPopulationMgr {
    struct State { std::string CalibrationTargetSpec = "fire_mage"; } state;
    State const& Cohort() const { return state; }
    mutable unsigned detailCalls = 0;
    std::string GetCombatCalibrationJson(bool includeBotDetails = true) const;
    void AppendCombatCalibrationBotRowsJson(std::ostringstream& out,
        std::map<uint32, CalibrationMetrics> const&, uint64,
        BotCalibrationFixtureContractGenerated::SpecContract const*, bool) const {
        ++detailCalls;
        out << "[{\"native_details\":true}]";
    }
    void AppendCombatCalibrationSummaryJson(std::ostringstream& out, uint64,
        std::function<void(std::map<uint32, CalibrationMetrics> const&, bool)> const& write) const {
        out << "{\"server_epoch\":71,\"scored_seconds\":300,\"bots\":";
        write({{17, CalibrationMetrics{}}}, true);
        out << '}';
    }
};
'''
    harness += body + r'''
int main() {
    BotWorldPopulationMgr manager;
    std::cout << manager.GetCombatCalibrationJson(false) << '\n';
    if (manager.detailCalls) return 1;
    std::cout << manager.GetCombatCalibrationJson() << '\n';
    return manager.detailCalls == 1 ? 0 : 2;
}
'''
    cpp, binary = tmp_path / "export.cpp", tmp_path / "export"
    cpp.write_text(harness)
    subprocess.run(["g++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    progress, full = map(json.loads, subprocess.check_output([str(binary)], text=True).splitlines())
    assert progress["detail_level"] == "progress"
    assert progress["server_epoch"] == full["server_epoch"] == 71
    assert progress["scored_seconds"] == full["scored_seconds"] == 300
    assert progress["bots"] == [dict(guid=17, details_included=False, damage=9600000,
        pet_damage=900000, effective_healing=300000, dps=32000, effective_hps=1000)]
    assert "detail_level" not in full
    assert full["bots"] == [{"native_details": True}]
