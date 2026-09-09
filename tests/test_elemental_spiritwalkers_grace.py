from __future__ import annotations

import json
import sqlite3
import subprocess
from copy import deepcopy
from pathlib import Path

from tools.bot_ml.build_all_spec_phase1_catalogs import (
    ACTION_PROFILES_PATH,
    RUNTIME_ACTION_SPELL_IDS,
    TARGET_CATALOG_PATH,
    reconcile_elemental_runtime_action_catalogs,
)
from tools.bot_ml.build_validation_provisioning import (
    bot_known_spell_ids,
    build_character_insert_sql,
    load_config_with_bwd_diagnostic_shards,
)
from tools.bot_ml.validation_profile_manifests import load_action_profile_manifest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_09_05_elemental_spiritwalkers_grace.sql"
ROLLBACK = ROOT / "sql/custom/rollback/world/2026_09_09_05_elemental_spiritwalkers_grace_rollback.sql"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"


def test_scoped_idempotent_rotation_migration_and_rollback() -> None:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER, spec_tag TEXT,
            role TEXT, enabled INTEGER
        );
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER,
            sort_order INTEGER, spell_id INTEGER, category TEXT,
            mechanic_tags TEXT, damage_weight REAL, priority_bucket INTEGER,
            min_enemies INTEGER, target_selector TEXT,
            movement_directive TEXT, auto_attack_mode TEXT,
            requires_moving INTEGER, enabled INTEGER DEFAULT 1
        );
        INSERT INTO bot_rotation_profile VALUES
            (1, 7, 'elemental_shaman', 'dps', 1),
            (2, 7, 'elemental_shaman', 'dps', 0),
            (3, 7, 'enhancement', 'dps', 1),
            (4, 8, 'elemental_shaman', 'dps', 1),
            (5, 7, 'elemental_shaman', 'healer', 1);
        INSERT INTO bot_rotation_action
            (profile_id, sort_order, spell_id, category, mechanic_tags,
             damage_weight, priority_bucket, min_enemies, target_selector,
             movement_directive, auto_attack_mode, requires_moving)
        VALUES
            (1, 15, 51505, 'builder', 'existing_lava_burst', 1, 1, 1, 'enemy', 'ranged', 'none', 0),
            (2, 99, 79206, 'buff', 'disabled_profile', 0, 9, 1, 'self', 'ranged', 'none', 0),
            (3, 99, 79206, 'buff', 'other_spec', 0, 9, 1, 'self', 'melee', 'none', 0),
            (4, 99, 79206, 'buff', 'other_class', 0, 9, 1, 'self', 'ranged', 'none', 0),
            (5, 99, 79206, 'buff', 'other_role', 0, 9, 1, 'self', 'healer_support', 'none', 0);
        """
    )
    untouched_before = db.execute(
        "SELECT profile_id, sort_order, mechanic_tags FROM bot_rotation_action WHERE profile_id != 1 ORDER BY profile_id"
    ).fetchall()
    for _ in range(2):
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
    rows = db.execute(
        "SELECT sort_order, category, mechanic_tags, damage_weight, priority_bucket, min_enemies, "
        "target_selector, movement_directive, auto_attack_mode, requires_moving "
        "FROM bot_rotation_action WHERE profile_id = 1 AND spell_id = 79206"
    ).fetchall()
    assert rows == [(16, "offensive_cooldown", "unblock_moving_lava_burst", 1.0, 1, 1,
                     "self", "ranged", "none", 1)]
    assert db.execute(
        "SELECT mechanic_tags FROM bot_rotation_action WHERE profile_id = 1 AND spell_id = 51505"
    ).fetchone() == ("existing_lava_burst",)
    assert db.execute(
        "SELECT profile_id, sort_order, mechanic_tags FROM bot_rotation_action WHERE profile_id != 1 ORDER BY profile_id"
    ).fetchall() == untouched_before
    db.executescript(ROLLBACK.read_text(encoding="utf-8"))
    assert db.execute(
        "SELECT COUNT(*) FROM bot_rotation_action WHERE profile_id = 1 AND spell_id = 79206"
    ).fetchone() == (0,)
    assert db.execute(
        "SELECT profile_id, sort_order, mechanic_tags FROM bot_rotation_action WHERE profile_id != 1 ORDER BY profile_id"
    ).fetchall() == untouched_before


def test_catalog_reconciliation_and_character_spell_provisioning() -> None:
    targets = json.loads(TARGET_CATALOG_PATH.read_text(encoding="utf-8"))
    actions = json.loads(ACTION_PROFILES_PATH.read_text(encoding="utf-8"))
    target = next(row for row in targets["targets"]
                  if row["spec_target_id"] == "elemental_shaman")
    assert RUNTIME_ACTION_SPELL_IDS["elemental_shaman"] == [79206]
    assert 79206 in target["action_profile_spell_ids"]
    assert 79206 in actions["action_profile_spells_by_spec"]["elemental_shaman"]

    before_targets, before_actions = deepcopy((targets, actions))
    target["action_profile_spell_ids"].remove(79206)
    actions["action_profile_spells_by_spec"]["elemental_shaman"].remove(79206)
    old_targets, old_actions = deepcopy((targets, actions))
    new_targets, new_actions = reconcile_elemental_runtime_action_catalogs(
        targets, actions)
    assert (targets, actions) == (old_targets, old_actions)
    assert reconcile_elemental_runtime_action_catalogs(new_targets, new_actions) == (
        new_targets, new_actions)
    for old, new in zip(old_targets["targets"], new_targets["targets"]):
        if old["spec_target_id"] == "elemental_shaman":
            assert set(new["action_profile_spell_ids"]) - set(old["action_profile_spell_ids"]) == {79206}
        else:
            assert old == new
    for spec, old in old_actions["action_profile_spells_by_spec"].items():
        if spec == "elemental_shaman":
            assert set(new_actions["action_profile_spells_by_spec"][spec]) - set(old) == {79206}
        else:
            assert old == new_actions["action_profile_spells_by_spec"][spec]
    assert (new_targets, new_actions) == (before_targets, before_actions)

    manifest = load_action_profile_manifest(ACTION_PROFILES_PATH)
    config = load_config_with_bwd_diagnostic_shards(
        ROOT / "experiments/configs/validation_provisioning_cata_001.json",
        ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json",
    )
    elemental_bots = [
        (scenario, bot)
        for scenario in config["scenarios"]
        for bot in scenario["bots"]
        if bot.get("class_spec") == "elemental_shaman"
    ]
    assert elemental_bots
    for scenario, bot in elemental_bots:
        assert 79206 in bot_known_spell_ids(bot, manifest)
        one_bot = {**config, "scenarios": [{**scenario, "bots": [bot]}]}
        sql = build_character_insert_sql(one_bot, manifest)
        assert (
            f"SELECT c.`guid`, 79206, 1, 0 FROM `characters`.`characters` c "
            f"WHERE c.`name` = '{bot['name']}'"
        ) in sql


def test_native_opportunity_gate_is_order_independent_and_spell_specific(tmp_path: Path) -> None:
    resolver_source = RESOLVER.read_text(encoding="utf-8")
    comparator_start = resolver_source.index("    auto candidatePreferred =")
    comparator_end = resolver_source.index("\n    };", comparator_start) + 7
    comparator = resolver_source[comparator_start:comparator_end].replace(
        "BotActionCandidate", "Candidate"
    )
    source = tmp_path / "elemental_swg.cpp"
    binary = tmp_path / "elemental_swg"
    program = r'''
#include "Bots/BotCastWhileMoving.h"
#include "Bots/BotElementalSpiritwalkersGrace.h"

#include <algorithm>
#include <cassert>
#include <string>
#include <utility>
#include <vector>

class SpellInfo { public: unsigned Id = 0; };
enum class Capability { None, LightningBoltGlyph, SpiritwalkersGrace };
struct Caster
{
    Capability Active = Capability::None;
    bool HasAuraTypeWithAffectMask(AuraType auraType, SpellInfo const* spell) const
    {
        if (auraType != SPELL_AURA_CAST_WHILE_WALKING || !spell)
            return false;
        if (Active == Capability::LightningBoltGlyph)
            return spell->Id == 403;
        return Active == Capability::SpiritwalkersGrace;
    }
};
struct Candidate
{
    Candidate(unsigned spellId, std::string rejection = {},
        std::string laterRejection = {}, bool castTime = false)
        : SpellId(spellId), RejectReason(std::move(rejection)),
          LaterFilterRejection(std::move(laterRejection)), CastTime(castTime) { }
    unsigned SpellId = 0;
    std::string RejectReason;
    std::string LaterFilterRejection;
    bool CastTime = false;
    struct { unsigned PriorityBucket = 1; unsigned SortOrder = 16; } Profile;
    float Score = 1.0f;
    unsigned ActionId = 0;
};

void Evaluate(std::vector<Candidate>& candidates, Caster const& caster)
{
    BotElementalSpiritwalkersGrace::EvaluateGraceAfterDamageOpportunities(candidates);
    for (Candidate& candidate : candidates)
    {
        SpellInfo info{ candidate.SpellId };
        bool rejectedByMovement = BotCastWhileMoving::RejectMovingCandidate(
            &caster, &info, true, candidate.CastTime, false);
        bool defer = BotElementalSpiritwalkersGrace::DeferLavaBurstMovementRejection(
            "elemental_shaman", candidate.SpellId, rejectedByMovement);
        if (rejectedByMovement && !defer)
        {
            candidate.RejectReason = "movement_requires_instant_action";
            continue;
        }
        if (!candidate.RejectReason.empty())
            continue;
        if (!candidate.LaterFilterRejection.empty())
        {
            candidate.RejectReason = candidate.LaterFilterRejection;
            continue;
        }
        if (defer)
        {
            candidate.RejectReason = std::string(
                BotElementalSpiritwalkersGrace::MovementRejection);
            continue;
        }
        if (candidate.SpellId == BotElementalSpiritwalkersGrace::SpiritwalkersGraceSpellId
            && !BotElementalSpiritwalkersGrace::HasMovementBlockedLavaBurst(candidates))
            candidate.RejectReason = "no_movement_blocked_lava_burst";
    }
}

Candidate const& Find(std::vector<Candidate> const& candidates, unsigned spell)
{
    return *std::find_if(candidates.begin(), candidates.end(), [spell](auto const& row)
        { return row.SpellId == spell; });
}

unsigned SelectedSpell(std::vector<Candidate> const& candidates)
{
NATIVE_CANDIDATE_COMPARATOR
    Candidate const* selected = nullptr;
    for (Candidate const& candidate : candidates)
        if (candidate.RejectReason.empty()
            && candidatePreferred(candidate, selected))
            selected = &candidate;
    return selected ? selected->SpellId : 0;
}

int main()
{
    for (std::vector<Candidate> rows : {
            std::vector<Candidate>{{79206, "", "", false}, {51505, "", "", true}},
            std::vector<Candidate>{{51505, "", "", true}, {79206, "", "", false}}})
    {
        Evaluate(rows, {Capability::None});
        assert(Find(rows, 51505).RejectReason == "movement_requires_instant_action");
        assert(Find(rows, 79206).RejectReason.empty());
        assert(SelectedSpell(rows) == 79206);
    }

    for (std::string blocker : {"global_cooldown", "cooldown_not_ready",
            "insufficient_resource", "missing_required_target_aura"})
    {
        std::vector<Candidate> rows{{79206, "", "", false}, {51505, blocker, "", true}};
        Evaluate(rows, {Capability::None});
        assert(Find(rows, 51505).RejectReason == blocker);
        assert(Find(rows, 79206).RejectReason == "no_movement_blocked_lava_burst");
    }
    for (std::string blocker : {"enemy_count_too_high", "target_immune", "max_range_exceeded"})
    {
        std::vector<Candidate> rows{{79206, "", "", false}, {51505, "", blocker, true}};
        Evaluate(rows, {Capability::None});
        assert(Find(rows, 51505).RejectReason == blocker);
        assert(Find(rows, 79206).RejectReason == "no_movement_blocked_lava_burst");
    }

    std::vector<Candidate> missingLava{{79206, "", "", false}};
    Evaluate(missingLava, {Capability::None});
    assert(Find(missingLava, 79206).RejectReason == "no_movement_blocked_lava_burst");

    std::vector<Candidate> stationary{{79206, "movement_gate", "", false}, {51505, "", "", true}};
    Evaluate(stationary, {Capability::None});
    assert(Find(stationary, 79206).RejectReason == "movement_gate");

    std::vector<Candidate> graceActive{{79206, "", "", false}, {51505, "", "", true}};
    Evaluate(graceActive, {Capability::SpiritwalkersGrace});
    assert(Find(graceActive, 51505).RejectReason.empty());
    assert(Find(graceActive, 79206).RejectReason == "no_movement_blocked_lava_burst");

    // Glyph 101052's native family mask covers Lightning Bolt 403, not Lava
    // Burst 51505. The exact LvB probe therefore remains movement-blocked.
    std::vector<Candidate> glyphRows{{79206, "", "", false}, {403, "", "", true}, {51505, "", "", true}};
    Evaluate(glyphRows, {Capability::LightningBoltGlyph});
    assert(Find(glyphRows, 403).RejectReason.empty());
    assert(Find(glyphRows, 51505).RejectReason == "movement_requires_instant_action");
    assert(Find(glyphRows, 79206).RejectReason.empty());

    for (std::string blocker : {"global_cooldown", "cooldown_not_ready"})
    {
        std::vector<Candidate> unavailableGrace{{79206, blocker, "", false}, {51505, "", "", true}};
        Evaluate(unavailableGrace, {Capability::None});
        assert(Find(unavailableGrace, 79206).RejectReason == blocker);
        assert(SelectedSpell(unavailableGrace) == 0);
    }
}
'''
    source.write_text(
        program.replace("NATIVE_CANDIDATE_COMPARATOR", comparator),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Spells/Auras"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)

    resolver = resolver_source
    assert "EvaluateGraceAfterDamageOpportunities" in resolver
    assert "DeferLavaBurstMovementRejection" in resolver
    assert "HasMovementBlockedLavaBurst" in resolver
    assert resolver.index("EvaluateGraceAfterDamageOpportunities") < resolver.index(
        "for (BotActionCandidate& candidate : candidates)")
    deferred = resolver.index("if (deferLavaBurstMovementRejection)")
    assert resolver.index('candidate.RejectReason = "max_range_exceeded"') < deferred
    assert deferred < resolver.index("HasMovementBlockedLavaBurst")
