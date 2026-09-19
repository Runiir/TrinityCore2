"""DPS-042: actual producer/consumer gates and native range data at the 433 head receipt.

Surrounding class/resource gates are outside this range-only fixture. The movement
adapter and arbiter are production headers; the pincer ownership case supplies an
already-admitted Movement claim, not a simulated native pincer execution.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / 'src/server/game/Bots'
FIXTURE = ROOT / 'tests/fixtures/magmaw_433_balance_min_range.json'


def between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def compile_fixture(tmp_path, revision=None):
    def read(name):
        path = BOTS / name
        if revision:
            return subprocess.check_output(['git', 'show', f'{revision}:{path.relative_to(ROOT)}'], cwd=ROOT, text=True)
        return path.read_text()
    producer = read('BotClassSpecActionProfileCandidates.cpp')
    missing = between(producer, '        else if (spell.SpellId && !spellInfo)', '        else if (spell.SpellId && spell.Category')
    ranged = between(producer, '        else if (spell.RequiresMeleeRange', '        else if (spellInfo && spellInfo->NeedsComboPoints()')
    resolver = read('BotWorldPopulationMgrCombatResolver.cpp')
    native = between(resolver, '    auto effectiveSpellMinRange =', '    auto effectiveSpellMaxRange =')
    gate = between(resolver, '        float distance = selfCenteredHostileAction', '        if (deferLavaBurstMovementRejection)')
    pre_rejected = between(resolver, '        if (!candidate.RejectReason.empty())\n        {\n            // Preserve the highest-priority', '        bool candidateIsMajorTankDefensive')
    controller = read('BotControllerCombat.cpp')
    control_gate = between(controller, '        if (candidate.Profile.RequiresMeleeRange', '        if (candidate.SpellId)')
    spell_header=(ROOT/'src/server/game/Spells/Spell.h').read_text()
    assert 'SPELL_RANGE_MELEE               = 1' in spell_header
    assert 'SPELL_RANGE_RANGED              = 2' in spell_header
    helper = (BOTS / 'BotSpellMinimumRange.h').read_text()
    helper = '\n'.join(line for line in helper.splitlines() if not line.startswith('#include "'))
    native_method = between((ROOT/'src/server/game/Entities/Object/WorldObjectSpells.cpp').read_text(), 'float WorldObject::GetSpellMinRangeForTarget', '\nfloat WorldObject::ApplyEffectModifiers').replace('WorldObject::', 'Unit::')
    melee_method = between((ROOT/'src/server/game/Entities/Unit/Unit.cpp').read_text(), 'float Unit::GetMeleeRange(Unit const* target) const', '\nbool Unit::IsWithinBoundaryRadius')
    evidence = json.loads(FIXTURE.read_text())
    assert evidence['incident']['event_target']['distance'] == 4.64954
    assert evidence['incident']['event_target']['line_of_sight'] is True
    assert evidence['incident']['native_actor']['moving'] is False
    rows = ','.join('{%d,%s,%d}' % (row['spell_id'], row['hostile_min'], row['range_flags']) for row in evidence['dbc']['spells'])
    cpp = r'''
#include "Bots/BotProfileCombatRangeCandidate.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <string>
#include <vector>
constexpr int SPELL_RANGE_MELEE=1, SPELL_RANGE_RANGED=2;
constexpr float NOMINAL_MELEE_RANGE=5.0f;
struct Range { float RangeMin[2]={0,0}; int Flags=0; };
struct SpellInfo { Range range; Range* RangeEntry=&range;
 float GetMinRange(bool friendly=false) const { return RangeEntry->RangeMin[friendly]; }
 float GetMaxRange(bool) const { return 40; }
};
struct Unit { float distance=4.64954f, reach=1.5f;
 float GetSpellMinRangeForTarget(Unit const*, SpellInfo const*) const;
 bool IsHostileTo(Unit const*) const { return true; }
 float GetMeleeRange(Unit const* target) const;
 float GetCombatReach() const { return reach; }
 float GetExactDist(Unit const*) const { return distance; }
 bool IsWithinMeleeRange(Unit const* target) const { return distance<=GetMeleeRange(target); }
};
''' + native_method + melee_method + helper + r'''
struct Profile { std::string TargetSelector="enemy"; int SpellId=8921; float MinRange=0,MaxRange=40;
 bool RequiresMeleeRange=false,RequiresRangedRange=true,RangeRecoveryRequired=false; };
struct BotActionCandidate { struct Profile Profile; int ResolvedSpellId=8921,SpellId=8921; std::string RejectReason; };
struct SpellMgr { SpellInfo info; bool missing=false;
 SpellInfo const* GetSpellInfo(int) { return missing?nullptr:&info; }
} store;
auto* sSpellMgr=&store;
std::string admit(float distance, float configured=0, bool controller=false, bool melee=false, bool ranged=true,
    bool* rangeRecovery=nullptr) {
 Unit actor, victim; actor.distance=distance;victim.reach=2.0f;
 Unit *bot=&actor,*target=&victim,*actionTarget=target;
 Profile profile,spell,action; spell.MinRange=configured;spell.RequiresMeleeRange=melee;spell.RequiresRangedRange=ranged;
 std::vector<BotActionCandidate> candidates(1);auto& candidate=candidates[0];candidate.Profile=spell;
 auto* spellInfo=sSpellMgr->GetSpellInfo(spell.SpellId);
 if(false) {}
''' + missing + ranged + r'''
 if(!candidate.RejectReason.empty()) return candidate.RejectReason;
 bool selfTarget=false,selfCenteredHostileAction=false;
''' + native + r'''
 auto effectiveSpellMaxRange=[](BotActionCandidate const&, float maximum) { return maximum; };
 bool densityOnly=false;
 for(auto& candidate:candidates) {
 if(controller) {float targetDistance=distance;
''' + control_gate + r'''
 } else {
''' + gate + r'''
 }
 }
 if(rangeRecovery) *rangeRecovery=action.RangeRecoveryRequired;
 return candidate.RejectReason;
}
// Run the production pre-rejected branch before handing its range envelope
// to the real movement lane. Keep max-range recovery and aggregation covered.
float rejectedEnvelope(float configured, float profileMinimum, float targetReach,
    float initialMinimum=0, std::string reason="", bool self=false) {
 Unit actor,victim;actor.distance=6;victim.reach=targetReach;
 Unit *bot=&actor,*target=&victim,*actionTarget=self?bot:target;
 Profile profile,spell,action;profile.MinRange=profileMinimum;spell.MinRange=configured;
 spell.TargetSelector=self?"self":"enemy";action.MinRange=initialMinimum;
 std::vector<BotActionCandidate> candidates(1);auto& candidate=candidates[0];candidate.Profile=spell;
 auto* spellInfo=sSpellMgr->GetSpellInfo(spell.SpellId);
 if(false) {}
''' + missing + ranged + r'''
 if(!reason.empty())candidate.RejectReason=reason;
 assert(!candidate.RejectReason.empty());
 bool densityOnly=false;BotActionCandidate const* bestRangeRecovery=nullptr;
 auto candidatePreferred=[](BotActionCandidate const&,BotActionCandidate const*){return true;};
 for(auto& candidate:candidates){
 auto* candidateSpellInfo=sSpellMgr->GetSpellInfo(candidate.ResolvedSpellId);
''' + pre_rejected + r'''
 }
 assert((bestRangeRecovery!=nullptr)==(reason=="out_of_range"&&!self));
 return action.MinRange;
}
void rejectedMovement() {
 store.info.range.Flags=0;
 float envelope=rejectedEnvelope(8,0,2);
 assert(envelope==8); // The old 2af propagation returned 5.
 assert(rejectedEnvelope(0,8,2)==8); // Profile fallback survives.
 assert(rejectedEnvelope(8,0,2,12)==12); // Existing larger minimum survives.
 assert(rejectedEnvelope(8,0,2,3,"out_of_range")==3);
 assert(rejectedEnvelope(8,0,2,3,"insufficient_resource")==3);
 store.info.range.Flags=SPELL_RANGE_RANGED;
 float hunterEnvelope=rejectedEnvelope(0,0,7);
 assert(std::abs(hunterEnvelope-(1.5f+7+1.3333334f))<0.00001f);
 // A self target must not inherit the unrelated enemy's large combat reach.
 assert(rejectedEnvelope(8,0,7,0,"",true)==8);
 for(float minimum:{envelope,hunterEnvelope}) {
 using namespace BotActionArbitration;
 Kernel kernel;kernel.Begin(2000);bool moved=false;
 BotProfileCombatRangeCandidate::Decision decision;
 decision.TargetPresent=decision.TargetInWorld=decision.TargetAlive=decision.TargetAttackable=decision.SameMap=decision.SameInstance=true;
 decision.Distance=6;decision.MinRange=minimum;
 decision.Move=[&moved](){moved=true;return true;};
 BotProfileCombatRangeCandidate::Request request;request.Observe=[decision](){return decision;};
 assert(kernel.Submit(BotProfileCombatRangeCandidate::Build(std::move(request))));
 auto result=kernel.Resolve();assert(moved&&result.AnyCommitted);
 assert(result.Trace[0].Reason=="profile_combat_min_range_reconciled");
 }
 store.info.range.Flags=0;
}
void movement(bool pincer) {
 using namespace BotActionArbitration;
 Kernel kernel;kernel.Begin(1789291131548ULL);bool moved=false,cast=false,pincerMoved=false;
 BotProfileCombatRangeCandidate::Decision decision;
 decision.TargetPresent=decision.TargetInWorld=decision.TargetAlive=decision.TargetAttackable=decision.SameMap=decision.SameInstance=true;
 decision.Distance=4.64954f;decision.MinRange=0;
 decision.Move=[&moved](){moved=true;return true;};
 BotProfileCombatRangeCandidate::Request request;
 request.Observe=[decision](){return decision;};
 assert(kernel.Submit(BotProfileCombatRangeCandidate::Build(std::move(request))));
 Candidate offense;offense.Key="world.profile_combat";offense.ActionPriority=Priority::TrainedDamage;
 offense.RequiredResources=Uses(Resource::Cast,Resource::GlobalCooldown,Resource::Target);
 offense.Attempt=[&cast](){if(!admit(4.64954f).empty())return Outcome::NotApplicable("range_rejected");cast=true;return Outcome::Submitted("cast_submitted");};
 assert(kernel.Submit(std::move(offense)));
 if(pincer) {Candidate owner;owner.Key="observed.pincer.movement";owner.ActionPriority=Priority::Survival;
 owner.RequiredResources=Uses(Resource::Movement);
 owner.Attempt=[&pincerMoved](){pincerMoved=true;return Outcome::Started("native_owner_retained");};assert(kernel.Submit(std::move(owner)));}
 auto result=kernel.Resolve();assert(cast&&!moved&&pincerMoved==pincer);
 if(!pincer) {bool seen=false;for(auto const& trace:result.Trace)if(trace.Key==BotProfileCombatRangeCandidate::Key){seen=true;assert(trace.Reason=="profile_min_range_satisfied");}assert(seen);}
}
int main(){
 struct Row {int id;float minimum;int flags;};
 for(Row row:std::vector<Row>{ROWS}){
 store.info.range.RangeMin[0]=store.info.range.RangeMin[1]=row.minimum;store.info.range.Flags=row.flags;
 for(bool controller:{false,true}){
 if(row.flags==0){assert(admit(4.64954f,0,controller).empty());assert(admit(0,0,controller).empty());}
 else {assert(!admit(4.64954f,0,controller).empty());assert(admit(5,0,controller).empty());}
 assert(!admit(4.64954f,8,controller).empty());assert(admit(8,8,controller).empty());
 assert(admit(4.64954f,8,controller,false,false)=="min_range_required");
 if(row.flags==2) assert(admit(4.64954f,0,controller,false,false)=="min_range_required");
 assert(admit(41,0,controller)=="max_range_exceeded");
 assert(admit(8,0,controller,true)=="melee_range_required");
 }}
 store.info.range.Flags=0;store.info.range.RangeMin[0]=store.info.range.RangeMin[1]=2;
 for(bool controller:{false,true}) {assert(admit(5,0,controller,false,false)=="min_range_required");assert(admit(5.5f,0,controller,false,false).empty());}
 assert(!admit(5).empty());assert(admit(5.5f).empty()); // Native positive minimum plus both reaches.
 store.info.range.RangeMin[0]=store.info.range.RangeMin[1]=0;
 store.missing=true;assert(admit(4.64954f)=="missing_spell_info");store.missing=false;
 movement(false);movement(true);rejectedMovement();
 bool maxRangeRecovery=false;
 assert(admit(41,0,false,false,true,&maxRangeRecovery)=="max_range_exceeded");
 assert(maxRangeRecovery);
}
'''.replace('ROWS',rows)
    path=tmp_path/('baseline.cpp' if revision else 'repaired.cpp');path.write_text(cpp)
    binary=path.with_suffix('')
    subprocess.run(['c++','-std=c++17','-I',str(ROOT/'src/server/game'),'-I',str(ROOT/'src/common'),'-I',str(ROOT/'src/server/game/Entities/Object'),str(path),'-o',str(binary)],check=True,capture_output=True,text=True)
    return subprocess.run([str(binary)],capture_output=True,text=True)


def test_recorded_producer_to_both_consumers_and_movement(tmp_path):
    result=compile_fixture(tmp_path)
    assert result.returncode==0,result.stderr


def test_frozen_433_producer_rejects_native_legal_recorded_point(tmp_path):
    result=compile_fixture(tmp_path,'4337116eeb')
    assert result.returncode!=0
    assert 'admit(4.64954f,0,controller).empty()' in result.stderr


def test_frozen_2af_rejected_candidate_loses_movement_envelope(tmp_path):
    result=compile_fixture(tmp_path,'2af61a1cef')
    assert result.returncode!=0
    assert 'envelope==8' in result.stderr
