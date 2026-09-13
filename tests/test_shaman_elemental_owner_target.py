"""Compile the production acquisition function with native-shaped observations."""
from pathlib import Path
import subprocess
from test_warlock_doomguard_guardian import function as extract_function

ROOT = Path(__file__).resolve().parents[1]


def test_elemental_acquires_native_owner_helper_only_without_victim(tmp_path):
    text = (ROOT / "src/server/scripts/Pet/pet_shaman.cpp").read_text()
    start = text.index("Unit* ShamanElementalOwner(")
    end = text.index("\nenum ShamanSpells", start)
    function = text[start:end]
    attack = extract_function(text, "void AttackStart(Unit* target) override")
    assert text.count(attack) == 2
    update = extract_function((ROOT / "src/server/game/AI/CreatureAI.cpp").read_text(), "bool CreatureAI::UpdateVictim()")
    assert text.count("StopShamanProtectedVictim(me);") == 2
    source = tmp_path / "elemental_owner.cpp"
    source.write_text(r'''
#include <cassert>
#include <initializer_list>
#include <algorithm>
#include <tuple>
#include <vector>
#include <functional>
#include "Bots/BotRaidAreaAuthority.h"
#include "ObjectGuid.h"
constexpr int UNIT_FIELD_FLAGS = 1;
constexpr int UNIT_FLAG_PLAYER_CONTROLLED = 8;
struct Totem;struct Creature;struct Unit;
struct CombatRef {Unit* target;bool suppressed=false;Unit* GetOther(Unit const*)const{return target;}bool IsSuppressedFor(Unit const*)const{return suppressed;}};
struct CombatManager {std::vector<std::pair<int,CombatRef*>> pve,pvp;
 auto const& GetPvECombatRefs()const{return pve;}auto const& GetPvPCombatRefs()const{return pvp;}};
struct Unit {
    virtual ~Unit()=default;
    ObjectGuid guid{HighGuid::Player,30010u};uint32 entry=0;CombatManager combat;
    ObjectGuid GetGUID()const{return guid;}uint32 GetEntry()const{return entry;}
    Creature const* ToCreature()const;
    CombatManager& GetCombatManager(){return combat;}
    Unit* owner = nullptr;
    Unit* victim = nullptr;
    Unit* helper = nullptr;
    bool alive = true, valid = true, engaged = true, totem = false;
    int type = TYPEID_PLAYER, helperCalls = 0;
    bool IsTotem() const { return totem; }
    Totem* ToTotem();
    // Base owner access is nonvirtual; Totem hides it with its native owner.
    Unit* GetOwner() const { return owner; }
    Unit* GetCharmerOrOwner() const { return owner; }
    Unit* GetVictim() const { return victim; }
    Unit* getAttackerForHelper() { ++helperCalls; return engaged ? helper : nullptr; }
    bool IsAlive() const { return alive; }
    bool IsValidAttackTarget(Unit* target) const { return target->valid; }
    int GetTypeId() const { return type; }
};
struct Totem : Unit {
    Unit* nativeOwner = nullptr;
    Totem() { totem = true; type = 3; }
    Unit* GetOwner() const { return nativeOwner; }
};
Totem* Unit::ToTotem() { return static_cast<Totem*>(this); }
struct TempSummon;
struct Creature : Unit {
    TempSummon* summon = nullptr;
    Unit* selected=nullptr;
    bool HasReactState(int)const{return false;}
    bool IsInCombat()const{return true;}
    Unit* SelectVictim(){return selected;} // native selection boundary: protected helper can be selected

    int flags = 0,interrupts=0,stops=0;bool casting=false;
    uint32 GetSpawnId()const{return 0;}
    void InterruptNonMeleeSpells(bool){++interrupts;casting=false;}
    void AttackStop(){++stops;victim=nullptr;}
    struct Controller {Creature* parent;int attacks=0;Unit* target=nullptr;bool reject=false;std::function<void(Unit*)> dispatch{};
        void AttackStart(Unit* unit){if(dispatch){dispatch(unit);return;}++attacks;if(!reject){target=unit;parent->victim=unit;}}} ai{this};
    TempSummon* ToTempSummon() { return summon; }
    Controller* AI() { return &ai; }
    void SetFlag(int field, int flag) { assert(field == UNIT_FIELD_FLAGS); flags |= flag; }
};
Creature const* Unit::ToCreature()const{return dynamic_cast<Creature const*>(this);}
struct TempSummon : Creature {
    Unit* summoner = nullptr;
    TempSummon() { summon = this; }
    Unit* GetSummoner() const { return summoner; }
};
''' + function + r'''
constexpr int REACT_PASSIVE=0,EVADE_REASON_NO_HOSTILES=0;
struct ScriptedAI {
 Creature* me;explicit ScriptedAI(Creature* value):me(value){}
 virtual ~ScriptedAI()=default;
 virtual void AttackStart(Unit* target){me->victim=target;}
 bool IsEngaged()const{return true;}void EngagementOver(){}
 void EnterEvadeMode(int){me->AttackStop();}
 bool UpdateVictim();
};
''' + update.replace('CreatureAI::', 'ScriptedAI::') + r'''
struct ActualElementalAI : ScriptedAI {
 using ScriptedAI::ScriptedAI;
''' + attack + r'''
};
'''+r'''
static void Reject(Creature& elemental) {
    assert(!AcquireShamanOwnerVictim(&elemental));
    assert(elemental.ai.attacks == 0 && elemental.flags == 0);
}
int main() {
    Unit player, target, different;
    player.helper = &target;
    Creature direct;
    direct.owner = &player;
    assert(AcquireShamanOwnerVictim(&direct));
    assert(direct.ai.attacks == 1 && direct.ai.target == &target);
    assert(direct.flags == UNIT_FLAG_PLAYER_CONTROLLED && player.helperCalls == 1);

    // An existing victim always wins, even if the helper would choose another.
    player.victim = &target; player.helper = &different; player.helperCalls = 0;
    Creature current; current.owner = &player;
    assert(AcquireShamanOwnerVictim(&current));
    assert(current.ai.attacks == 1 && current.ai.target == &target);
    assert(player.helperCalls == 0);
    for (bool dead : {false, true}) {
        target.alive = !dead; target.valid = dead;
        Creature rejected; rejected.owner = &player;
        Reject(rejected);
        assert(player.helperCalls == 0); // no fallback from invalid/dead victim
    }
    target.alive = target.valid = true; player.victim = nullptr;
    for (int failure = 0; failure < 4; ++failure) {
        player.helper = failure == 0 ? nullptr : &target;
        player.engaged = failure != 1;
        target.alive = failure != 2; target.valid = failure != 3;
        Creature rejected; rejected.owner = &player;
        Reject(rejected);
    }
    player.engaged = target.alive = target.valid = true;
    player.helper = &target;
    Totem totem; totem.nativeOwner = &player;
    assert(static_cast<Unit*>(&totem)->GetOwner() == nullptr);
    assert(totem.GetOwner() == &player);
    TempSummon chained; chained.summoner = &totem;
    assert(AcquireShamanOwnerVictim(&chained));
    assert(chained.ai.attacks == 1 && chained.ai.target == &target);
    assert(chained.flags == UNIT_FLAG_PLAYER_CONTROLLED);
    TempSummon summoned; summoned.summoner = &player;
    assert(AcquireShamanOwnerVictim(&summoned));
    assert(summoned.ai.attacks == 1);
    Creature ownerless; Reject(ownerless);
    TempSummon orphan; Reject(orphan);
    totem.nativeOwner = nullptr;
    TempSummon ownerlessTotem; ownerlessTotem.summoner = &totem; Reject(ownerlessTotem);
    assert(!AcquireShamanOwnerVictim(nullptr));
    Unit npc; npc.type = 3; npc.helper = &target;
    Creature npcElemental; npcElemental.owner = &npc;
    assert(AcquireShamanOwnerVictim(&npcElemental));
    assert(npcElemental.ai.attacks == 1 && npcElemental.flags == 0);

    // No acquisition claim on an actual AI binding refusal.
    Creature refused;refused.owner=&player;refused.ai.reject=true;
    assert(!AcquireShamanOwnerVictim(&refused)&&!refused.victim);
    using namespace BotRaidAreaAuthority;
    auto key=player.GetGUID().GetRawValue();player.victim=nullptr;
    Creature parasite,body,head,allowed;
    parasite.entry=41806;parasite.guid=ObjectGuid(HighGuid::Unit,41806u,191u);
    body.entry=41570;body.guid=ObjectGuid(HighGuid::Unit,41570u,39u);
    head.entry=42347;head.guid=ObjectGuid(HighGuid::Unit,42347u,76u);
    allowed.entry=42321;allowed.guid=ObjectGuid(HighGuid::Unit,42321u,192u);
    CombatRef parasiteRef{&parasite},bodyRef{&body},headRef{&head},allowedRef{&allowed};
    player.helper=&parasite;player.combat.pve={{0,&parasiteRef},{1,&allowedRef},{2,&headRef},{3,&bodyRef}};
    Creature evolving;evolving.owner=&player;
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&parasite);evolving.casting=true;
    SetCurrentEncounterRestrictions(key,{41806,42321},{allowed.guid.GetRawValue()});
    StopShamanProtectedVictim(&evolving);assert(!evolving.victim&&!evolving.casting&&evolving.interrupts==1);
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&body);
    // Reverse reference iteration: same ordinary winner by raw GUID, not hash order.
    std::reverse(player.combat.pve.begin(),player.combat.pve.end());evolving.AttackStop();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&body);
    SetProtectedEncounterEntries(key,{41570});evolving.AttackStop();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&head);
    SetProtectedEncounterEntries(key,{41570,42347});evolving.AttackStop();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&allowed);
    // Explicit legal owner victim still wins over fallback refs.
    SetProtectedEncounterEntries(key,{});player.victim=&allowed;evolving.AttackStop();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&allowed);player.victim=nullptr;
    // Suppressed refs provide no authority; all illegal refs fail closed.
    bodyRef.suppressed=headRef.suppressed=allowedRef.suppressed=true;evolving.AttackStop();
    assert(!AcquireShamanOwnerVictim(&evolving)&&!evolving.victim);
    bodyRef.suppressed=false;player.combat.pvp={{1,&bodyRef}};player.combat.pve.clear();
    assert(AcquireShamanOwnerVictim(&evolving)&&evolving.victim==&body);
    SetAllOffenseSuppressed(key,true);evolving.casting=true;StopShamanProtectedVictim(&evolving);
    assert(!evolving.victim&&!evolving.casting&&!AcquireShamanOwnerVictim(&evolving));
    Clear(key);
    // Actual CreatureAI::UpdateVictim plus both production AttackStart overrides.
    // The native selection boundary intentionally keeps returning a protected helper.
    totem.nativeOwner=&player;TempSummon chainedUpdate;chainedUpdate.summoner=&totem;
    ActualElementalAI actual(&chainedUpdate);
    chainedUpdate.ai.dispatch=[&](Unit* target){actual.AttackStart(target);};
    chainedUpdate.selected=&parasite;player.helper=&parasite;player.victim=nullptr;
    player.combat.pvp.clear();player.combat.pve={{0,&parasiteRef},{1,&bodyRef}};
    bodyRef.suppressed=false;SetCurrentEncounterRestrictions(key,{41806},{});
    assert(!actual.UpdateVictim()&&!chainedUpdate.victim);
    assert(AcquireShamanOwnerVictim(&chainedUpdate)&&chainedUpdate.victim==&body);
    assert(actual.UpdateVictim()&&chainedUpdate.victim==&body);
    assert(actual.UpdateVictim()&&chainedUpdate.victim==&body);
    SetCurrentEncounterRestrictions(key,{41806},{parasite.guid.GetRawValue()});
    assert(actual.UpdateVictim()&&chainedUpdate.victim==&parasite);
    SetCurrentEncounterRestrictions(key,{41806},{});chainedUpdate.casting=true;
    StopShamanProtectedVictim(&chainedUpdate);
    assert(!actual.UpdateVictim()&&!chainedUpdate.victim&&!chainedUpdate.casting);
    assert(AcquireShamanOwnerVictim(&chainedUpdate)&&actual.UpdateVictim()&&chainedUpdate.victim==&body);
    Clear(key);assert(actual.UpdateVictim()&&chainedUpdate.victim==&parasite);
}
''')
    binary = tmp_path / "elemental_owner"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    "-I", str(ROOT / "src/server/game/Entities/Object"), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
