import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/scripts/Spells/spell_generic_vengeance.cpp"
FIXTURE = ROOT / "tests/fixtures/vengeance_434_contract.json"


def _production_state_source(source: str) -> str:
    start = source.index("uint32 InitialVengeanceAttackPower(")
    end = source.index("// 93098 - 93099 - 84839 - 84840 - Vengeance", start)
    return source[start:end]


def _method_body(source: str, class_name: str, signature: str) -> str:
    class_start = source.index(f"class {class_name}")
    start = source.index("{", source.index(signature, class_start))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_actual_vengeance_recurrence_preserves_gain_decay_floor_and_cap(tmp_path):
    contract = json.loads(FIXTURE.read_text())
    cases = contract["cases"]
    source = SOURCE.read_text()
    cpp = tmp_path / "vengeance.cpp"
    cpp.write_text(
        """
#include <algorithm>
#include <cassert>
#include <cstdint>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
constexpr uint32 IN_MILLISECONDS = 1000;
"""
        + _production_state_source(source)
        + f"""
int main()
{{
    constexpr uint32 cap = {cases['initial_hit']['cap']};
    assert(InitialVengeanceAttackPower({cases['initial_hit']['damage']}, cap)
        == {cases['initial_hit']['expected_attack_power']});

    auto recurrence = UpdateVengeanceAttackPower(
        {cases['hit_update']['prior_attack_power']},
        {cases['hit_update']['prior_recent_max']},
        {cases['hit_update']['damage']},
        {cases['hit_update']['damage']}, cap);
    assert(recurrence.AttackPower == {cases['hit_update']['expected_attack_power']});
    assert(recurrence.RecentMaxAttackPower == {cases['hit_update']['prior_recent_max']});

    VengeanceState state;
    state.Initialize({cases['initial_hit']['expected_attack_power']}, 1000);
    assert(state.Update({cases['first_periodic_boundary']['timestamp_ms']}, cap)
        == {cases['first_periodic_boundary']['expected_attack_power']});
    assert(state.Update({cases['no_hit_update']['timestamp_ms']}, cap)
        == {cases['no_hit_update']['expected_attack_power']});

    VengeanceState capped;
    capped.Initialize({cases['cap_update']['initial_attack_power']}, 1000);
    capped.RecordDamage({cases['cap_update']['damage']}, 2500);
    assert(capped.Update(3000, {cases['cap_update']['cap']})
        == {cases['cap_update']['expected_attack_power']});
}}
"""
    )
    binary = tmp_path / "vengeance"
    result = subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(binary)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True)


def test_actual_passive_and_triggered_callbacks_keep_first_hit_and_decay(tmp_path):
    source = SOURCE.read_text()
    passive = _method_body(source, "spell_gen_vengeance", "void HandleEffectProc(")
    apply = _method_body(source, "spell_gen_vengeance_triggered", "void HandleEffectApply(")
    proc = _method_body(source, "spell_gen_vengeance_triggered", "void HandleEffectProc(")
    periodic = _method_body(source, "spell_gen_vengeance_triggered", "void HandleEffectPeriodic(")
    cpp = tmp_path / "callbacks.cpp"
    cpp.write_text(
        """
#include <algorithm>
#include <cassert>
#include <cstdint>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using int32 = std::int32_t;
using AuraEffectHandleModes = int;
constexpr uint32 IN_MILLISECONDS = 1000;
constexpr uint32 SPELL_VENGEANCE_TRIGGERED = 76691;
constexpr int STAT_STAMINA = 3;
constexpr int SPELLVALUE_BASE_POINT1 = 1;
constexpr int SPELLVALUE_BASE_POINT2 = 2;
namespace GameTime { uint32 now = 0; uint32 GetGameTimeMS() { return now; } }
struct CastSpellExtraArgs {
    int32 bp[3] = {0, 0, 0};
    explicit CastSpellExtraArgs(bool) { }
    CastSpellExtraArgs& AddSpellBP0(int32 value) { bp[0] = value; return *this; }
    CastSpellExtraArgs& AddSpellMod(int index, int32 value) { bp[index] = value; return *this; }
};
struct Unit {
    uint32 createHealth = 400000;
    uint32 stamina = 10000;
    bool hasAura = false;
    uint32 castSpell = 0;
    int32 castBP[3] = {0, 0, 0};
    uint32 GetCreateHealth() const { return createHealth; }
    uint32 GetStat(int) const { return stamina; }
    uint32 GetGUID() const { return 1; }
    void* GetAura(uint32, uint32) { return hasAura ? this : nullptr; }
    void CastSpell(Unit*, uint32 spell, CastSpellExtraArgs const& args) {
        hasAura = true; castSpell = spell;
        for (int i = 0; i < 3; ++i) castBP[i] = args.bp[i];
    }
};
template<class T> T CalculatePct(T value, uint32 pct) { return T((uint64(value) * pct) / 100); }
struct DamageInfo { uint32 damage; uint32 GetDamage() const { return damage; } };
struct ProcEventInfo { DamageInfo* info; DamageInfo* GetDamageInfo() { return info; } };
struct AuraEffect { int32 amount; int32 GetAmount() const { return amount; } };
"""
        + _production_state_source(source)
        + "\nstruct PassiveHarness {\n"
        + "Unit* target; bool prevented = false; Unit* GetTarget() { return target; } "
          "void PreventDefaultAction() { prevented = true; }\n"
        + "void HandleEffectProc(void const*, ProcEventInfo& eventInfo) "
        + passive
        + "\n};\nstruct TriggeredHarness {\n"
        + "Unit* target; bool removed = false; VengeanceState _vengeance; "
          "Unit* GetTarget() { return target; } void Remove() { removed = true; }\n"
        + "void HandleEffectApply(AuraEffect const* aurEff, AuraEffectHandleModes) "
        + apply
        + "\nvoid HandleEffectProc(void const*, ProcEventInfo& eventInfo) "
        + proc
        + "\nvoid HandleEffectPeriodic(void const*) "
        + periodic
        + r'''
};
int main() {
    Unit tank; DamageInfo firstDamage{30000}; ProcEventInfo firstEvent{&firstDamage};
    PassiveHarness passive{&tank}; passive.HandleEffectProc(nullptr, firstEvent);
    assert(passive.prevented && tank.castSpell == 76691);
    assert(tank.castBP[0] == 10000 && tank.castBP[1] == 10000 && tank.castBP[2] == 10000);

    TriggeredHarness triggered{}; triggered.target = &tank; AuraEffect effect{tank.castBP[0]};
    GameTime::now = 1000; triggered.HandleEffectApply(&effect, 0);
    GameTime::now = 3000; triggered.HandleEffectPeriodic(nullptr);
    assert(!triggered.removed && tank.castBP[0] == 9000);
    GameTime::now = 5000; triggered.HandleEffectPeriodic(nullptr);
    assert(tank.castBP[0] == 8000);

    DamageInfo laterDamage{6000}; ProcEventInfo laterEvent{&laterDamage};
    GameTime::now = 5500; triggered.HandleEffectProc(nullptr, laterEvent);
    GameTime::now = 6000; triggered.HandleEffectPeriodic(nullptr);
    assert(tank.castBP[0] == 7900);

    for (uint32 now = 8001; now <= 26001 && !triggered.removed; now += 2000) {
        GameTime::now = now; triggered.HandleEffectPeriodic(nullptr);
    }
    assert(triggered.removed);
}
'''
    )
    binary = tmp_path / "callbacks"
    result = subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(binary)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True)


def test_native_handlers_use_the_state_machine_and_preserve_script_identity():
    contract = json.loads(FIXTURE.read_text())
    source = SOURCE.read_text()
    assert "InitialVengeanceAttackPower(eventInfo.GetDamageInfo()->GetDamage(), healthCap)" in source
    assert "_vengeance.Initialize(aurEff->GetAmount(), GameTime::GetGameTimeMS())" in source
    assert "_vengeance.RecordDamage(eventInfo.GetDamageInfo()->GetDamage(), GameTime::GetGameTimeMS())" in source
    assert "_vengeance.Update(GameTime::GetGameTimeMS(), healthCap)" in source
    assert "AURA_EFFECT_HANDLE_REAL" in source
    assert source.count("RegisterSpellScript(spell_gen_vengeance);") == 1
    assert source.count("RegisterSpellScript(spell_gen_vengeance_triggered);") == 1
    assert len(source.splitlines()) < 1000

    assert contract["passive_spell_ids"] == [93098, 93099, 84839, 84840]
    assert contract["triggered_spell_id"] == 76691
    assert contract["wowsims_revision"] == "70d87383a9b92f30fb9e370c4676d3ce33b6e6b6"
    assert contract["wowsims_source_sha256"] == "9739ed0b6a7c4b140dc1948d966836efc50e93a8c6a0c4a364b790a52d7544e5"


def test_pinned_wowsims_source_hash_when_checkout_is_available():
    contract = json.loads(FIXTURE.read_text())
    checkout = ROOT.parent / "trinity-shared-instance-validation-03cb01db0b" / "wowsims-source-70d87383"
    source = checkout / contract["wowsims_source"]
    if source.exists():
        assert hashlib.sha256(source.read_bytes()).hexdigest() == contract["wowsims_source_sha256"]
