"""Passive range selection preserves execution diagnostic ownership."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_actual_resolver_publication_and_passive_call_sites(tmp_path):
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp").read_text()
    start = source.index("    if (publishDiagnostics)")
    publication = source[start:source.index("    if (!best || !best->SpellId)", start)]
    fallback = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text()
    calls = []
    for marker in ("ResolvedCombatAction profileAction = ResolveProfileCombatAction(",
                   "ResolvedCombatAction const preview = ResolveProfileCombatAction("):
        start = fallback.index(marker)
        calls.append(fallback[start:fallback.index(";", start) + 1])
    program = r'''
#include <cassert>
#include <map>
#include <string>
#include <sstream>
#include <vector>
using uint32=unsigned;
struct Guid {uint32 GetCounter()const{return 1;}};
struct Bot {Guid GetGUID(){return {};}};
struct BotActionCandidate {unsigned SpellId=0;std::string RejectReason;int Category=0;};
struct Saturation {int RecommendedBalanceMode=0;float ExperimentConfidence=0;std::string ToJson(){return "saturation";}};
struct PartyState {
std::map<unsigned,std::string> LastCombatRejectsByBot,LastCombatMaskByBot,LastChosenCombatByBot,LastActionCategoryByBot;
std::map<unsigned,Saturation> LastSaturationByBot;
} party;
PartyState& Party(){return party;}
std::string JsonEscape(std::string value){return value;}
namespace BotCombatMaskEvaluation {
std::string Quote(std::string v){return v;}
std::string Append(std::string a,int,std::string b){return a+b;}
}
namespace BotRoleSaturationPolicy {char const* ToString(int){return "balance";}}
namespace BotCombatActionCatalog {char const* ToString(int v){return v==1?"execution":"preview";}}
namespace BotClassSpecActionProfileStore {
std::string CandidateMaskJson(std::vector<BotActionCandidate> const& c,int,char const*,char const*){return std::to_string(c[0].SpellId);}
std::string ChosenActionJson(BotActionCandidate const* c,int,char const*,char const*,float){return std::to_string(c->SpellId);}
}
struct ResolvedCombatAction {unsigned SpellId;};
ResolvedCombatAction ResolveProfileCombatAction(Bot* bot,void*,unsigned hostileCount=0,bool densityOnly=false,
unsigned excludedSpellId=0,bool areaOnly=false,bool selfCenteredOnly=false,bool forbidArea=false,
bool allowMultidot=true,bool hostileTargetOnly=false,bool movementCompatibleOnly=false,
char const* specTagOverride=nullptr,bool publishDiagnostics=true){
// Different resolved results emulate execution contract and passive preview.
std::vector<BotActionCandidate> candidates={{forbidArea?101u:202u,forbidArea?"execution_reject":"preview_reject",forbidArea?1:2}};
auto best=&candidates[0];int profile=0,maskEvaluation=0;std::string roleGoal="tank";
Saturation saturation;saturation.ExperimentConfidence=forbidArea?1:2;
unsigned requestedHostileCount=hostileCount;
ResolvedCombatAction action{best->SpellId};
''' + publication + r'''
return action;
}
int main(){Bot bot;int unit;auto target=&unit;
struct {Bot* Bot;void* Target;} context{&bot,target};
struct {bool ForbidAreaDamage=false,AllowMultidot=true;} magmawProfile;
auto execution=ResolveProfileCombatAction(&bot,target,0,false,0,false,false,true);
assert(execution.SpellId==101);
auto previous=party;
''' + '\n'.join(calls) + r'''
assert(profileAction.SpellId==202);assert(preview.SpellId==202);
assert(party.LastCombatRejectsByBot==previous.LastCombatRejectsByBot);
assert(party.LastCombatMaskByBot==previous.LastCombatMaskByBot);
assert(party.LastChosenCombatByBot==previous.LastChosenCombatByBot);
assert(party.LastActionCategoryByBot==previous.LastActionCategoryByBot);
assert(party.LastSaturationByBot.at(1).ExperimentConfidence==previous.LastSaturationByBot.at(1).ExperimentConfidence);
auto normal=ResolveProfileCombatAction(&bot,target);
assert(party.LastCombatRejectsByBot!=previous.LastCombatRejectsByBot);
assert(party.LastCombatMaskByBot!=previous.LastCombatMaskByBot);
assert(normal.SpellId==202);assert(party.LastChosenCombatByBot.at(1)=="202");
assert(party.LastActionCategoryByBot.at(1)=="preview");
assert(party.LastSaturationByBot.at(1).ExperimentConfidence==2);
}
'''
    # Keep production call-site member spelling without a C++ type/member clash.
    program = program.replace("struct Bot {", "struct PlayerStub {").replace("Bot*", "PlayerStub*").replace("Bot bot;", "PlayerStub bot;")
    cpp = tmp_path / "preview.cpp"
    cpp.write_text(program)
    binary = tmp_path / "preview"
    subprocess.run(["g++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
