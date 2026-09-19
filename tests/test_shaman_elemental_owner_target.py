"""Compile the production acquisition function with native-shaped observations."""
from pathlib import Path
import subprocess
from test_warlock_doomguard_guardian import function as extract_function

ROOT = Path(__file__).resolve().parents[1]


def nth_function(source: str, signature: str, occurrence: int) -> str:
    start = -1
    for _ in range(occurrence + 1):
        start = source.index(signature, start + 1)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_elemental_acquires_native_owner_helper_only_without_victim(tmp_path):
    text = (ROOT / "src/server/scripts/Pet/pet_shaman.cpp").read_text()
    start = text.index("Unit* ShamanElementalOwner(")
    end = text.index("\nenum ShamanSpells", start)
    function = text[start:end]
    native_spells = (ROOT / "src/server/game/Entities/Object/WorldObjectSpells.cpp").read_text()
    reaction_start = native_spells.index("            if (selfPlayerOwner && targetPlayerOwner)")
    reaction_end = native_spells.index("            // check FFA_PVP", reaction_start)
    native_reaction_block = native_spells[reaction_start:reaction_end]
    friendly_start = native_spells.index("    // PvP, PvC, CvP case")
    friendly_end = native_spells.index("    Player const* playerAffectingAttacker", friendly_start)
    native_friendly_rejection = native_spells[friendly_start:friendly_end]
    assert "selfPlayerOwner->IsInRaidWith(targetPlayerOwner)" in native_reaction_block
    assert "selfPlayerOwner->duel->opponent" in native_reaction_block
    assert "if (IsFriendlyTo(target) || target->IsFriendlyTo(this))" in native_friendly_rejection
    attack = nth_function(text, "void AttackStart(Unit* target) override", 0)
    attack_second = nth_function(text, "void AttackStart(Unit* target) override", 1)
    reset = nth_function(text, "void Reset() override", 0)
    reset_second = nth_function(text, "void Reset() override", 1)
    update = nth_function(text, "void UpdateAI(uint32 diff) override", 0)
    update_second = nth_function(text, "void UpdateAI(uint32 diff) override", 1)
    assert attack == attack_second
    assert reset.startswith("void Reset() override\n            {")
    assert reset_second.startswith("void Reset() override\n            {")
    assert "InitializeShamanElementalPlayerControlled(me);" in reset
    assert "InitializeShamanElementalPlayerControlled(me);" in reset_second
    assert "InitializeShamanElementalPlayerControlled(me);" in update
    assert "InitializeShamanElementalPlayerControlled(me);" in update_second
    assert "target && me->IsValidAttackTarget(target)" in text
    victim_update = extract_function((ROOT / "src/server/game/AI/CreatureAI.cpp").read_text(), "bool CreatureAI::UpdateVictim()")
    assert text.count("StopShamanProtectedVictim(me);") == 2
    assert "IsInSameRaidWith" not in text
    assert text.count("SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED)") == 1
    assert "SetTargetMap" not in text
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
constexpr int UNIT_STATE_CASTING = 1;
enum ReputationRank { REP_HATED = 0, REP_HOSTILE = 1, REP_UNFRIENDLY = 2,
    REP_NEUTRAL = 3, REP_FRIENDLY = 4 };
struct Player;struct Totem;struct Creature;struct Unit;
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
    Player* affectingPlayer = nullptr;
    bool alive = true, valid = true, engaged = true, totem = false, hostile = false;
    int type = TYPEID_UNIT, helperCalls = 0, raidId = 0, flags = 0;
    bool IsTotem() const { return totem; }
    Totem* ToTotem();
    // Base owner access is nonvirtual; Totem hides it with its native owner.
    Unit* GetOwner() const { return owner; }
    Unit* GetCharmerOrOwner() const { return owner; }
    Unit* GetVictim() const { return victim; }
    Unit* getAttackerForHelper() { ++helperCalls; return engaged ? helper : nullptr; }
    bool IsAlive() const { return alive; }
    bool HasFlag(int field, int flag) const { return field == UNIT_FIELD_FLAGS && (flags & flag) == flag; }
    void SetFlag(int field, int flag) { assert(field == UNIT_FIELD_FLAGS); flags |= flag; }
    Player* GetCharmerOrOwnerPlayerOrPlayerItself() const;
    Player* GetAffectingPlayer() const;
    ReputationRank GetReactionTo(Unit const* target) const;
    bool IsFriendlyTo(Unit const* target) const { return GetReactionTo(target) >= REP_FRIENDLY; }
    bool IsValidAttackTarget(Unit const* target) const;
    int GetTypeId() const { return type; }
};
struct Player : Unit {
    struct DuelInfo { Player* opponent; int startTime; };
    DuelInfo* duel = nullptr;
    Player() { type = TYPEID_PLAYER; affectingPlayer = this; }
    bool IsInRaidWith(Player const* other) const { return other && raidId && raidId == other->raidId; }
};
Player* Unit::GetCharmerOrOwnerPlayerOrPlayerItself() const { return affectingPlayer; }
Player* Unit::GetAffectingPlayer() const { return affectingPlayer; }
ReputationRank Unit::GetReactionTo(Unit const* target) const {
    if (this == target)
        return REP_FRIENDLY;
    Player const* selfPlayerOwner = GetAffectingPlayer();
    Player const* targetPlayerOwner = target->GetAffectingPlayer();
    Unit const* unit = this;
    Unit const* targetUnit = target;
    if (unit && unit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED)
        && targetUnit && targetUnit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
    {
''' + native_reaction_block + r'''
    }
    return hostile || target->hostile ? REP_HOSTILE : REP_NEUTRAL;
}
bool Unit::IsValidAttackTarget(Unit const* target) const {
    if (!target || !target->alive || !target->valid)
        return false;
''' + native_friendly_rejection + r'''
    return true;
}
struct Totem : Unit {
    Unit* nativeOwner = nullptr;
    Totem() { totem = true; type = 3; }
    Unit* GetOwner() const { return nativeOwner; }
};
Totem* Unit::ToTotem() { return static_cast<Totem*>(this); }
struct TempSummon;
struct Creature : Unit {
    Creature() { hostile = true; }
    TempSummon* summon = nullptr;
    Unit* selected=nullptr;
    bool HasReactState(int)const{return false;}
    bool IsInCombat()const{return true;}
    Unit* SelectVictim(){return selected;} // native selection boundary: protected helper can be selected

    int interrupts=0,stops=0,casts=0,melee=0;bool casting=false;Unit* lastCastTarget=nullptr;uint32 lastSpell=0;
    uint32 GetSpawnId()const{return 0;}
    void InterruptNonMeleeSpells(bool){++interrupts;casting=false;}
    void AttackStop(){++stops;victim=nullptr;}
    bool HasUnitState(int state)const{return state == UNIT_STATE_CASTING && casting;}
    void ApplySpellImmune(int, int, int, bool){}
    bool CanStartAttack(Unit*, bool) const { return true; }
    struct Controller {Creature* parent;int attacks=0;Unit* target=nullptr;bool reject=false;std::function<void(Unit*)> dispatch{};
        void AttackStart(Unit* unit){if(dispatch){dispatch(unit);return;}++attacks;if(!reject){target=unit;parent->victim=unit;}}} ai{this};
    TempSummon* ToTempSummon() { return summon; }
    Controller* AI() { return &ai; }
};
Creature const* Unit::ToCreature()const{return dynamic_cast<Creature const*>(this);}
struct TempSummon : Creature {
    Unit* summoner = nullptr;
    TempSummon() { summon = this; }
    Unit* GetSummoner() const { return summoner; }
};
''' + function + r'''
enum ShamanSpells {
    SPELL_SHAMAN_ANGEREDEARTH = 36213,
    SPELL_SHAMAN_FIREBLAST = 57984,
    SPELL_SHAMAN_FIRENOVA = 12470,
    SPELL_SHAMAN_FIRESHIELD = 13376
};
enum ShamanEvents {
    EVENT_SHAMAN_ANGEREDEARTH = 1,
    EVENT_SHAMAN_FIRENOVA = 1,
    EVENT_SHAMAN_FIRESHIELD = 2,
    EVENT_SHAMAN_FIREBLAST = 3
};
constexpr int REACT_PASSIVE=0,EVADE_REASON_NO_HOSTILES=0;
constexpr int IMMUNITY_SCHOOL=0,SPELL_SCHOOL_MASK_NATURE=1,SPELL_SCHOOL_MASK_FIRE=2;
struct EventMap {
    std::vector<uint32> ready;
    void Reset(){ready.clear();}
    void ScheduleEvent(uint32 id,uint32 delay){if(delay==0)ready.push_back(id);}
    void Update(uint32){}
    uint32 ExecuteEvent(){if(ready.empty())return 0;uint32 id=ready.front();ready.erase(ready.begin());return id;}
};
uint32 urand(uint32 min,uint32){return min;}
struct ScriptedAI {
 Creature* me;explicit ScriptedAI(Creature* value):me(value){}
 virtual ~ScriptedAI()=default;
 virtual void Reset(){}
 virtual void UpdateAI(uint32){}
 virtual void AttackStart(Unit* target){me->victim=target;}
 bool IsEngaged()const{return me->engaged;}void EngagementOver(){me->engaged=false;}
 void EnterEvadeMode(int){me->AttackStop();}
 void DoCastVictim(uint32 spell){++me->casts;me->lastSpell=spell;me->lastCastTarget=me->GetVictim();}
 void DoMeleeAttackIfReady(){++me->melee;}
 bool UpdateVictim();
};
''' + victim_update.replace('CreatureAI::', 'ScriptedAI::') + r'''
struct ActualEarthElementalAI : ScriptedAI {
 using ScriptedAI::ScriptedAI;
''' + reset + r'''
''' + attack + r'''
''' + update + r'''
 private:
 EventMap _events;
};
struct ActualFireElementalAI : ScriptedAI {
 using ScriptedAI::ScriptedAI;
''' + reset_second + r'''
''' + attack_second + r'''
''' + update_second + r'''
 private:
 EventMap _events;
};
'''+r'''
static void Reject(Creature& elemental, bool playerOwned = false) {
    assert(!AcquireShamanOwnerVictim(&elemental));
    assert(elemental.ai.attacks == 0);
    assert(elemental.flags == (playerOwned ? UNIT_FLAG_PLAYER_CONTROLLED : 0));
}
int main() {
    Player player;
    Unit target, different;
    Unit nearbyHostile;
    target.hostile = different.hostile = nearbyHostile.hostile = true;
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
        Reject(rejected, true);
        assert(player.helperCalls == 0); // no fallback from invalid/dead victim
    }
    target.alive = target.valid = true; player.victim = nullptr;
    for (int failure = 0; failure < 4; ++failure) {
        player.helper = failure == 0 ? nullptr : &target;
        player.engaged = failure != 1;
        target.alive = failure != 2; target.valid = failure != 3;
        Creature rejected; rejected.owner = &player;
        Reject(rejected, true);
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
    // The native reaction contract rejects a same-raid controlled wolf, while
    // its duel state remains a lawful hostile exception.
    totem.nativeOwner=&player;
    Player wolfOwner;player.raidId=17;wolfOwner.raidId=17;
    Unit wolf;wolf.hostile=true;wolf.flags=UNIT_FLAG_PLAYER_CONTROLLED;wolf.affectingPlayer=&wolfOwner;
    TempSummon nativeFire;nativeFire.summoner=&totem;nativeFire.affectingPlayer=&player;
    InitializeShamanElementalPlayerControlled(&nativeFire);
    assert(nativeFire.GetReactionTo(&wolf)==REP_FRIENDLY);
    assert(!nativeFire.IsValidAttackTarget(&wolf));
    Player::DuelInfo playerDuel{&wolfOwner,1},wolfDuel{&player,1};
    player.duel=&playerDuel;wolfOwner.duel=&wolfDuel;
    assert(nativeFire.GetReactionTo(&wolf)==REP_HOSTILE);
    assert(nativeFire.IsValidAttackTarget(&wolf));
    player.duel=nullptr;wolfOwner.duel=nullptr;

    // Execute both production Reset/UpdateAI bodies.  A pre-existing lawful
    // victim exercises the UpdateVictim short circuit; a same-raid victim is
    // stopped by native validity before it can receive a spell.
    TempSummon chainedUpdate;chainedUpdate.summoner=&totem;chainedUpdate.affectingPlayer=&player;
    chainedUpdate.victim=&wolf;chainedUpdate.selected=&wolf;
    ActualEarthElementalAI earth(&chainedUpdate);
    chainedUpdate.ai.dispatch=[&](Unit* target){earth.AttackStart(target);};
    earth.Reset();assert(chainedUpdate.flags==UNIT_FLAG_PLAYER_CONTROLLED);
    player.helper=&body;bodyRef.suppressed=false;player.victim=nullptr;
    earth.UpdateAI(1);
    assert(chainedUpdate.victim==&body&&chainedUpdate.lastCastTarget==&body);
    assert(chainedUpdate.melee==1);

    TempSummon fireSummon;fireSummon.summoner=&totem;fireSummon.affectingPlayer=&player;
    fireSummon.victim=&nearbyHostile;fireSummon.selected=&nearbyHostile;
    ActualFireElementalAI fire(&fireSummon);
    fireSummon.ai.dispatch=[&](Unit* target){fire.AttackStart(target);};
    fire.Reset();assert(fireSummon.flags==UNIT_FLAG_PLAYER_CONTROLLED);
    fire.UpdateAI(1);
    assert(fireSummon.lastSpell==SPELL_SHAMAN_FIRESHIELD);
    assert(fireSummon.lastCastTarget==&nearbyHostile);
    fire.AttackStart(nullptr);assert(fireSummon.victim==&nearbyHostile);

    // Existing friendly victim, protected target, and offense suppression all
    // fail closed; ordinary hostile acquisition remains available.
    fireSummon.victim=&wolf;fireSummon.selected=&wolf;fireSummon.casts=0;fireSummon.melee=0;
    player.helper=&nearbyHostile;player.victim=nullptr;fire.Reset();
    fire.UpdateAI(1);
    assert(fireSummon.victim==&nearbyHostile&&fireSummon.lastCastTarget==&nearbyHostile);
    assert(fireSummon.interrupts==1);
    fire.AttackStart(&wolf);assert(fireSummon.victim==&nearbyHostile);
    SetProtectedEncounterEntries(key,{0});
    fire.AttackStart(&nearbyHostile);assert(fireSummon.victim==&nearbyHostile);
    SetAllOffenseSuppressed(key,true);fire.AttackStart(&nearbyHostile);
    assert(fireSummon.victim==&nearbyHostile);
    Clear(key);

    // NPC-owned elementals retain the native non-player path and do not gain
    // the player-controlled classification.
    TempSummon npcSummon;npcSummon.summoner=&npc;npcSummon.helper=&target;
    ActualEarthElementalAI npcEarth(&npcSummon);npcEarth.Reset();
    assert(npcSummon.flags==0);
    Clear(key);
}
''')
    binary = tmp_path / "elemental_owner"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    "-I", str(ROOT / "src/server/game/Entities/Object"), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
