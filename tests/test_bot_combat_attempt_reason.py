"""Nonspell combat attempts cannot fail an unobserved spell resource gate."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_actual_combat_attempt_reason_selection(tmp_path):
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatDiagnostics.cpp").read_text()
    start = source.index("    if (reason && *reason)", source.index("void BotWorldPopulationMgr::RecordCombatAttempt"))
    end = source.index("    diagnostic.DetailJson", start)
    selector = source[start:end]
    program = r'''
#include <cassert>
#include <string>
struct Diagnostic {
 unsigned SpellId=0;
 bool TargetAlive=true,TargetAttackable=true,LineOfSight=true,InRange=true;
 bool Casting=false,GlobalCooldown=false,CooldownReady=false,HasPower=false;
 std::string Reason,DiagnosticReason;
};
Diagnostic select(Diagnostic diagnostic,void const* spellInfo,void const* actionTarget,
                  char const* reason=nullptr,char const* diagnosticReason=nullptr) {
''' + selector + r'''
 return diagnostic;
}
int main() {
 int token=1;auto target=&token;
 // Native successful melee fallback: spellId0 and absent spell metadata leave
 // both spell gate observations false; neither is evidence of failure.
 Diagnostic melee;
 auto result=select(melee,nullptr,target);
 assert(result.Reason.empty());assert(result.DiagnosticReason.empty());
 // Explicit outcome and retry overrides retain their independent authority.
 result=select(melee,nullptr,target,"native_outcome","retry_override");
 assert(result.Reason=="native_outcome");assert(result.DiagnosticReason=="retry_override");
 result=select(melee,nullptr,target,"explicit_reason");
 assert(result.Reason=="explicit_reason");assert(result.DiagnosticReason=="explicit_reason");
 // Real spell failures remain ordered: cooldown before power, then success.
 Diagnostic spell;spell.SpellId=49998;
 result=select(spell,&token,target);assert(result.Reason=="cooldown");
 spell.CooldownReady=true;
 result=select(spell,&token,target);assert(result.Reason=="no_power");
 spell.HasPower=true;
 result=select(spell,&token,target);assert(result.Reason.empty());
 result=select(spell,nullptr,target);assert(result.Reason=="bad_spell");
 // Absent metadata never masks applicable nonspell target failures.
 melee.InRange=false;
 result=select(melee,nullptr,target);assert(result.Reason=="out_of_range");
 result=select(melee,nullptr,nullptr);assert(result.Reason=="target_missing");
}
'''
    cpp = tmp_path / "reason.cpp"
    binary = tmp_path / "reason"
    cpp.write_text(program)
    subprocess.run(["g++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
