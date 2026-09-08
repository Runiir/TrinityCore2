"""Compile the production acquisition function with native-shaped observations."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_elemental_acquires_native_owner_helper_only_without_victim(tmp_path):
    text = (ROOT / "src/server/scripts/Pet/pet_shaman.cpp").read_text()
    start = text.index("bool AcquireShamanOwnerVictim(")
    end = text.index("\nenum ShamanSpells", start)
    function = text[start:end]
    source = tmp_path / "elemental_owner.cpp"
    source.write_text(r'''
#include <cassert>
#include <initializer_list>
constexpr int TYPEID_PLAYER = 4;
constexpr int UNIT_FIELD_FLAGS = 1;
constexpr int UNIT_FLAG_PLAYER_CONTROLLED = 8;
struct Totem;
struct Unit {
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
    int flags = 0;
    struct Controller { int attacks = 0; Unit* target = nullptr;
        void AttackStart(Unit* unit) { ++attacks; target = unit; } } ai;
    TempSummon* ToTempSummon() { return summon; }
    Controller* AI() { return &ai; }
    void SetFlag(int field, int flag) { assert(field == UNIT_FIELD_FLAGS); flags |= flag; }
};
struct TempSummon : Creature {
    Unit* summoner = nullptr;
    TempSummon() { summon = this; }
    Unit* GetSummoner() const { return summoner; }
};
''' + function + r'''
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
}
''')
    binary = tmp_path / "elemental_owner"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
