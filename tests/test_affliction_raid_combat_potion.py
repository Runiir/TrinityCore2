"""Affliction's raid profile uses its reserved Volcanic Potion in execute."""

from pathlib import Path
import sqlite3
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_09_06_affliction_combat_potion.sql"


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def _database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute(
        """CREATE TABLE bot_rotation_profile(
            id INTEGER PRIMARY KEY, class_id, spec_tag, role, version,
            source_note, scope_note
        )"""
    )
    db.execute(
        """CREATE TABLE bot_rotation_action(
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id, sort_order,
            spell_id, category, mechanic_tags, damage_weight, survival_weight,
            priority_bucket, min_enemies, max_enemies,
            min_target_health_pct, max_target_health_pct, target_selector,
            movement_directive, auto_attack_mode, min_range, max_range,
            maintain_aura_id, min_mana_pct, max_mana_pct,
            max_hostile_target_health_pct, enabled
        )"""
    )
    db.executemany(
        "INSERT INTO bot_rotation_profile VALUES(?,?,?,?,?,?,?)",
        [
            (1, 9, "affliction_warlock", "dps", 3, "old", "old"),
            (2, 9, "demonology_warlock", "dps", 3, "other", "other"),
            (3, 9, "affliction_warlock", "tank", 3, "other", "other"),
            (4, 8, "affliction_warlock", "dps", 3, "other", "other"),
        ],
    )
    # Two stale Affliction rows prove duplicate cleanup; the adjacent profile
    # row proves the migration does not broaden beyond Affliction DPS.
    db.executemany(
        """INSERT INTO bot_rotation_action(
            profile_id,sort_order,spell_id,category,mechanic_tags,
            damage_weight,survival_weight,priority_bucket,min_enemies,
            max_enemies,min_target_health_pct,max_target_health_pct,
            target_selector,movement_directive,auto_attack_mode,min_range,
            max_range,maintain_aura_id,min_mana_pct,max_mana_pct,
            max_hostile_target_health_pct,enabled
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (1, 3, 79476, "use_item", "stale", 0, 0, 9, 1, 0, 0, 1,
             "self", "ranged", "none", 0, 0, 0, 0, 1, 0, 1),
            (1, 4, 79476, "use_item", "duplicate", 0, 0, 9, 1, 0, 0, 1,
             "self", "ranged", "none", 0, 0, 0, 0, 1, 0, 1),
            (1, 80, 1120, "execute", "drain_soul", 1, 0, 8, 1, 1, 0, .25,
             "enemy", "ranged", "none", 12, 35, 0, 0, 1, 0, 1),
            (2, 25, 79476, "use_item", "other_spec", 1, 0, 1, 1, 0, 0, 1,
             "self", "ranged", "none", 0, 0, 0, 0, 1, 0, 1),
        ],
    )
    return db


def test_migration_is_scoped_idempotent_and_ranks_before_drain_soul() -> None:
    db = _database()
    migration = MIGRATION.read_text(encoding="utf-8")

    for _ in range(2):
        db.executescript(migration)
        rows = db.execute(
            """SELECT sort_order,spell_id,category,mechanic_tags,damage_weight,
                      survival_weight,priority_bucket,min_enemies,max_enemies,
                      min_target_health_pct,max_target_health_pct,target_selector,
                      movement_directive,auto_attack_mode,min_range,max_range,
                      maintain_aura_id,min_mana_pct,max_mana_pct,
                      max_hostile_target_health_pct,enabled
               FROM bot_rotation_action
               WHERE profile_id=1 AND spell_id=79476"""
        ).fetchall()
        assert rows == [
            (
                75, 79476, "use_item",
                "volcanic_potion,combat_potion,execute_25,pinned_apl",
                1.1, 0.0, 7, 1, 0, 0.0, 1.0, "self", "ranged", "none",
                0.0, 0.0, 0, 0.0, 1.0, 0.25, 1,
            )
        ]

    profile = db.execute(
        "SELECT version,source_note FROM bot_rotation_profile WHERE id=1"
    ).fetchone()
    assert profile == (4, "wowsims_affliction_apl_player_actions_v2")
    assert db.execute(
        "SELECT mechanic_tags FROM bot_rotation_action WHERE profile_id=2 AND spell_id=79476"
    ).fetchone() == ("other_spec",)
    assert db.execute(
        "SELECT priority_bucket FROM bot_rotation_action WHERE profile_id=1 AND spell_id=1120"
    ).fetchone() == (8,)


def test_missing_affliction_profile_does_not_create_or_retarget_a_row() -> None:
    db = _database()
    db.execute("DELETE FROM bot_rotation_action WHERE profile_id=1")
    db.execute("DELETE FROM bot_rotation_profile WHERE id=1")
    db.executescript(MIGRATION.read_text(encoding="utf-8"))
    assert db.execute(
        "SELECT COUNT(*) FROM bot_rotation_action WHERE spell_id=79476"
    ).fetchone() == (1,)
    assert db.execute(
        "SELECT profile_id FROM bot_rotation_action WHERE spell_id=79476"
    ).fetchone() == (2,)


def test_native_item_lifecycle_health_ranking_and_reservation(tmp_path: Path) -> None:
    candidates = (
        ROOT / "src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp"
    ).read_text(encoding="utf-8")
    profile_header = (
        ROOT / "src/server/game/Bots/BotClassSpecActionProfile.h"
    ).read_text(encoding="utf-8")
    resolver = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
    ).read_text(encoding="utf-8")
    reservation_header = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
    ).read_text(encoding="utf-8")
    player_source = (
        ROOT / "src/server/game/Entities/Player/Player.cpp"
    ).read_text(encoding="utf-8")
    spell_history = (
        ROOT / "src/server/game/Spells/SpellHistory.cpp"
    ).read_text(encoding="utf-8")

    item_eligibility = _between(
        candidates, "Item* FindOnUseItemForSpell", "bool HasEnoughPowerForProfileSpell"
    )
    hostile_health = _between(
        profile_header, "inline bool ValidHostileTargetHealthRange", "struct BotActionCandidate"
    )
    comparator_begin = resolver.index("    auto candidatePreferred =")
    comparator = resolver[
        comparator_begin : resolver.index("\n    };", comparator_begin) + 7
    ]
    reservation = _between(
        reservation_header, "namespace BotRaidCooldownReservation", "#endif"
    )
    potion_cooldown = _between(
        player_source, "void Player::UpdatePotionCooldown", "void Player::SetResurrectRequestData"
    )

    # Bind the fixture to the production lifecycle owner: potion casts set the
    # marker, and only the out-of-combat update path clears it.
    assert "player->SetLastPotionId(itemID);" in spell_history
    assert "if (!m_lastPotionId || IsInCombat())" in potion_cooldown
    assert "m_lastPotionId = 0;" in potion_cooldown
    # A self-target action still evaluates its separate hostile target gate.
    assert "Unit const* actionTarget = selfTarget ?" in candidates
    assert "MeetsHostileTargetHealthGate(" in candidates
    assert "float(hostileHealthTarget->GetHealth()) / float(hostileHealthTarget->GetMaxHealth())" in candidates

    program = r'''
#include <array>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <initializer_list>
#include <string_view>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using int32 = std::int32_t;
constexpr uint8 INVENTORY_SLOT_ITEM_START = 0;
constexpr uint8 INVENTORY_SLOT_ITEM_END = 2;
constexpr uint8 INVENTORY_SLOT_BAG_START = 2;
constexpr uint8 INVENTORY_SLOT_BAG_END = 3;
constexpr uint8 INVENTORY_SLOT_BAG_0 = 0;
constexpr int ITEM_SPELLTRIGGER_ON_USE = 1;
constexpr int ITEM_CLASS_CONSUMABLE = 0;

enum class BotCombatActionCategory {
    Wait, UseItem, Defensive, Mitigation, HealEfficient, HealFast, HealAoe,
    ExternalDefensive, ResurrectRecover, DispelCleanse, OffensiveCooldown
};
struct Unit;
struct BotActionProfileSpell {
    float MinHostileTargetHealthPct = 0.0f;
    float MaxHostileTargetHealthPct = 0.0f;
    uint8 PriorityBucket = 5;
    uint32 SortOrder = 0;
};
struct BotActionCandidate {
    BotActionProfileSpell Profile;
    float Score = 0.0f;
    uint32 ActionId = 0;
};

struct ItemEffect { int32 SpellID = 0; int Trigger = 0; int32 Charges = 0; };
struct ItemTemplate {
    bool Potion = false;
    int Class = ITEM_CLASS_CONSUMABLE;
    std::vector<ItemEffect> Effects;
    bool IsPotion() const { return Potion; }
    int GetClass() const { return Class; }
};
struct Item {
    ItemTemplate* Proto = nullptr;
    uint32 Count = 0;
    std::array<int32, 3> Charges{};
    ItemTemplate const* GetTemplate() const { return Proto; }
    bool IsPotion() const { return Proto && Proto->IsPotion(); }
    int32 GetSpellCharges(uint8 index) const { return Charges[index]; }
    uint32 GetCount() const { return Count; }
};
struct Bag {
    std::vector<Item*> Items;
    uint32 GetBagSize() const { return Items.size(); }
    Item* GetItemByPos(uint32 slot) const { return Items.at(slot); }
};
struct SpellInfo { uint32 Id = 79476; };
struct Spell {
    SpellInfo const* m_spellInfo = nullptr;
    bool IgnoreCooldowns = false;
    bool IsIgnoringCooldowns() const { return IgnoreCooldowns; }
};
struct SpellHistory {
    uint32 CooldownEvents = 0;
    void SendCooldownEvent(SpellInfo const*, uint32, Spell* = nullptr) { ++CooldownEvents; }
};
struct ObjectMgr {
    ItemTemplate const* Potion = nullptr;
    ItemTemplate const* GetItemTemplate(uint32 id) const { return id == 58091 ? Potion : nullptr; }
};
struct SpellMgr {
    SpellInfo const* Potion = nullptr;
    SpellInfo const* GetSpellInfo(int32 id) const { return id == 79476 ? Potion : nullptr; }
};
ObjectMgr* sObjectMgr = nullptr;
SpellMgr* sSpellMgr = nullptr;
struct Player {
    uint32 m_lastPotionId = 0;
    bool InCombat = false;
    std::array<Item*, 2> Inventory{};
    Bag* PotionBag = nullptr;
    SpellHistory History;
    uint32 GetLastPotionId() const { return m_lastPotionId; }
    void SetLastPotionId(uint32 id) { m_lastPotionId = id; }
    bool IsInCombat() const { return InCombat; }
    SpellHistory* GetSpellHistory() { return &History; }
    Item* GetItemByPos(uint8, uint8 slot) const { return Inventory[slot]; }
    Bag* GetBagByPos(uint8 slot) const { return slot == 2 ? PotionBag : nullptr; }
    void UpdatePotionCooldown(Spell* spell = nullptr);
};

HOSTILE_HEALTH
ITEM_ELIGIBILITY
POTION_COOLDOWN
RESERVATION

int main() {
    ItemTemplate volcanic;
    volcanic.Potion = true;
    volcanic.Effects.push_back({79476, ITEM_SPELLTRIGGER_ON_USE, -1});
    Item potion{&volcanic, 1};
    SpellInfo potionSpell;
    ObjectMgr objectMgr{&volcanic};
    SpellMgr spellMgr{&potionSpell};
    sObjectMgr = &objectMgr;
    sSpellMgr = &spellMgr;
    Spell prepotSpell{&potionSpell};
    Player player;

    // SpellHistory sets this during the prepot. Out of combat, the real
    // lifecycle immediately emits its cooldown and clears LastPotionId.
    player.SetLastPotionId(58091);
    player.UpdatePotionCooldown(&prepotSpell);
    assert(player.GetLastPotionId() == 0);
    assert(player.History.CooldownEvents == 1);

    player.Inventory[0] = &potion;
    assert(FindOnUseItemForSpell(&player, 79476) == &potion);
    player.Inventory[0] = nullptr;
    assert(FindOnUseItemForSpell(&player, 79476) == nullptr);
    player.Inventory[0] = &potion;
    player.SetLastPotionId(58091);
    assert(FindOnUseItemForSpell(&player, 79476) == nullptr);

    // In-combat use retains LastPotionId until exit and cannot be bypassed.
    player.InCombat = true;
    player.UpdatePotionCooldown(&prepotSpell);
    assert(player.GetLastPotionId() == 58091);
    player.InCombat = false;
    player.UpdatePotionCooldown();
    assert(player.GetLastPotionId() == 0);
    assert(player.History.CooldownEvents == 2);

    BotActionProfileSpell potionProfile;
    potionProfile.MaxHostileTargetHealthPct = 0.25f;
    potionProfile.PriorityBucket = 7;
    potionProfile.SortOrder = 75;
    assert(MeetsHostileTargetHealthGate(potionProfile, 0.25f, true));
    assert(!MeetsHostileTargetHealthGate(potionProfile, 0.2501f, true));
    assert(!MeetsHostileTargetHealthGate(potionProfile, 0.20f, false));

    BotActionCandidate potionCandidate{potionProfile, 0.89f, 1};
    BotActionCandidate drainSoul;
    drainSoul.Profile.PriorityBucket = 8;
    drainSoul.Profile.SortOrder = 80;
    drainSoul.Score = 0.76f;
    drainSoul.ActionId = 2;
NATIVE_COMPARATOR
    assert(candidatePreferred(potionCandidate, &drainSoul));
    assert(!candidatePreferred(drainSoul, &potionCandidate));

    using namespace BotRaidCooldownReservation;
    CandidateContext potionContext{BotCombatActionCategory::UseItem,
        "volcanic_potion,combat_potion,execute_25,pinned_apl"};
    RouteContext staging{true, true, false, false, "boss", "prepull", "prepull"};
    RouteContext trash{true, true, false, false, "trash", "trash", ""};
    RouteContext bossCombat{true, true, true, false, "boss", "boss", "combat"};
    assert(std::string_view(ReservationReason(staging, potionContext)) ==
        "raid_combat_potion_reserved");
    assert(std::string_view(ReservationReason(trash, potionContext)) ==
        "raid_combat_potion_reserved");
    assert(ReservationReason(bossCombat, potionContext) == nullptr);
}
'''
    program = (
        program.replace("HOSTILE_HEALTH", hostile_health)
        .replace("ITEM_ELIGIBILITY", item_eligibility)
        .replace("POTION_COOLDOWN", potion_cooldown)
        .replace("RESERVATION", reservation)
        .replace("NATIVE_COMPARATOR", comparator)
    )
    source = tmp_path / "affliction_potion.cpp"
    binary = tmp_path / "affliction_potion"
    source.write_text(program, encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", str(source), "-o", str(binary)], check=True
    )
    subprocess.run([str(binary)], check=True)


def test_raid_potion_health_owner_actual_callers_and_gate(tmp_path):
    bots = ROOT / "src/server/game/Bots"
    header = (bots / "BotClassSpecActionProfile.h").read_text()
    health = _between(header, "inline bool ValidHostileTargetHealthRange", "struct BotActionCandidate")
    owner = _between((bots / "BotRaidCombatPotionHealthOwner.h").read_text(),
                     "namespace BotRaidCombatPotionHealthOwner", "#endif")
    candidates = (bots / "BotClassSpecActionProfileCandidates.cpp").read_text()
    tags = _between(candidates, "bool HasMechanicTag(", "\n}\n") + "\n}"
    selection = _between(candidates, "        bool const requiresPotionHealthOwner", "        bool const interruptsCurrentChanneledSpell")
    gate = _between(candidates, "        else if ((requiresPotionHealthOwner", "        else if (profile.Role")
    gate = gate.replace("else if", "if", 1)
    callers = []
    downstream = []
    for name in ("BotWorldPopulationMgrCombatResolver.cpp", "BotWorldPopulationMgrCombatSpell.cpp"):
        text = (bots / name).read_text()
        callers.append(_between(text, "    auto const potionHealthOwner =", "    BotRaidCooldownReservation::RouteContext"))
        downstream.append(_between(text, "        if (!BotRaidCombatPotionHealthOwner::MeetsHostileTargetHealthGate", "        float selfHealthPct"))
    # The multidot rebuild must carry the same boss owner despite a different damage target.
    assert "BuildCandidates(bot, spreadTarget, profile, potionHealthOwner)" in (bots / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    program = r'''
#include <cassert>
#include <cmath>
#include <string>
#include <vector>
using uint32 = unsigned;
struct Unit {
    unsigned Entry=1, Health=19, MaxHealth=100; bool Alive=true, Phase=true;
    unsigned GetEntry() const { return Entry; }
    unsigned GetHealth() const { return Health; }
    unsigned GetMaxHealth() const { return MaxHealth; }
    bool IsAlive() const { return Alive; }
};
struct Player : Unit {
    unsigned GetMapId() const { return 669; }
    unsigned GetInstanceId() const { return 42; }
    bool IsInMap(Unit const*) const { return true; }
    bool IsInPhase(Unit const* u) const { return u->Phase; }
};
Unit const* engagedBoss=nullptr;
namespace ObjectAccessor { Unit const* GetUnit(Player const&, unsigned guid) { return guid==7 ? engagedBoss : nullptr; } }
enum class BotCombatActionCategory { UseItem, Damage };
struct BotActionProfileSpell {
    float MinHostileTargetHealthPct=0, MaxHostileTargetHealthPct=.25f;
    BotCombatActionCategory Category=BotCombatActionCategory::UseItem;
    std::string MechanicTags="volcanic_potion,combat_potion", TargetSelector="self";
};
HEALTH
OWNER
TAGS
struct BotActionCandidate { std::string RejectReason; Unit const* ActionTarget; BotActionProfileSpell Profile; };
using BotClassSpecActionProfile=BotActionProfileSpell;
struct BotClassSpecActionProfileStore {
static std::vector<BotActionCandidate> BuildCandidates(Player const* bot, Unit const* target,
    BotClassSpecActionProfile const& spell, BotCombatPotionHealthOwner potionHealthOwner) {
    bool selfTarget=spell.TargetSelector=="self";
    BotActionCandidate candidate{"", selfTarget ? bot : target, spell};
SELECTION
GATE
    return {candidate};
}
};
struct Config { bool ValidationRouteEnable=true; std::string ValidationRouteKind="boss"; unsigned ValidationRouteTargetEntry=41570; };
struct Raid { bool RaidInstance=true, EncounterInProgress=true; };
struct CohortState { ::Config Config; ::Raid Raid; bool CalibrationActive=false; };
struct PartyState { unsigned ValidationRouteEngagedBossGeneration=3, ValidationRouteGeneration=3,
    ValidationRouteEngagedBossMapId=669, ValidationRouteEngagedBossInstanceId=42,
    ValidationRouteEngagedBossGuid=7; };
struct Caller {
    CohortState cohort; PartyState party;
    CohortState const& Cohort() { return cohort; }
    PartyState const& Party() { return party; }
    std::vector<BotActionCandidate> Resolve(Player* bot, Unit* target, BotClassSpecActionProfile profile) {
CALLER0
        for (auto& candidate : candidates) {
DOWNSTREAM0
        }
        return candidates;
    }
    std::vector<BotActionCandidate> Select(Player* bot, Unit* target, BotClassSpecActionProfile profile) {
CALLER1
        for (auto& candidate : candidates) {
DOWNSTREAM1
        }
        return candidates;
    }
};
int main() {
    Player bot; Unit add, head; Unit boss; boss.Entry=41570; boss.Health=66; engagedBoss=&boss;
    Caller caller; BotClassSpecActionProfile potion;
    for (auto call : {&Caller::Resolve, &Caller::Select}) {
        auto check=[&](Unit* target, bool allowed) {
            auto result=(caller.*call)(&bot,target,potion);
            assert(result[0].RejectReason.empty()==allowed);
            assert(result[0].ActionTarget==&bot);
        };
        check(&add,false); check(&head,false);
        boss.Health=25; check(&add,true);
        add.Health=26; check(&add,true); head.Health=90; check(&head,true);
        boss.Health=26; check(&add,false); add.Health=19;
        engagedBoss=nullptr; check(&add,false); engagedBoss=&boss;
        caller.party.ValidationRouteEngagedBossGeneration=2; check(&add,false);
        caller.party.ValidationRouteEngagedBossGeneration=3;
        caller.party.ValidationRouteEngagedBossInstanceId=43; check(&add,false);
        caller.party.ValidationRouteEngagedBossInstanceId=42;
        boss.Alive=false; check(&add,false); boss.Alive=true;
        boss.Phase=false; check(&add,false); boss.Phase=true;
        caller.cohort.CalibrationActive=true; check(&add,true); caller.cohort.CalibrationActive=false;
        caller.cohort.Raid.RaidInstance=false; check(&add,true); caller.cohort.Raid.RaidInstance=true;
        auto damage=potion; damage.Category=BotCombatActionCategory::Damage; damage.TargetSelector="enemy";
        auto result=(caller.*call)(&bot,&add,damage);
        assert(result[0].RejectReason.empty() && result[0].ActionTarget==&add);
    }
}
'''
    for name, value in {"HEALTH": health, "OWNER": owner, "TAGS": tags,
                        "SELECTION": selection, "GATE": gate,
                        "CALLER0": callers[0], "CALLER1": callers[1],
                        "DOWNSTREAM0": downstream[0], "DOWNSTREAM1": downstream[1]}.items():
        program = program.replace(name, value)
    source = tmp_path / "raid_potion_owner.cpp"
    source.write_text(program)
    binary = tmp_path / "raid_potion_owner"
    subprocess.run(["g++", "-std=c++17", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
