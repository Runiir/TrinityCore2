"""Spellbook of a two-spec loadout character before login.

A native dual-spec character knows the active group's talents, its primary
tree spells and everything those teach (SPELL_EFFECT_LEARN_SPELL), plus every
trainable class spell. Player::ActivateSpec removes the other group's talent
and tree spells (and their taught spells) and learns them only when that
group becomes active. The provisioned spellbook follows the same rule:

    inactive_only = LEARN closure(inactive talents + inactive tree spells)
                  + inactive spec's talent-gated action-profile spells
                  - LEARN closure(active talents + active tree spells)
                  - the active spec's single-spec spellbook
    known         = active single-spec spellbook
                  + every group's baseline action-profile spells
                  - inactive_only
                  + the dual-spec switch spells 63644/63645

An action-profile spell is talent-gated when no class trainer teaches it (nor
a trainer spell's LEARN closure) and it is not a class-wide or proficiency
spell; e.g. Sunfire 93402 exists only through the Balance talent 93401
(spell_druid.cpp:116, 231-234). Trainer data is the world_knowledge extract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from tools.bot_ml.build_validation_provisioning import (
    DEFAULT_ACTION_PROFILES,
    NATIVE_SELF_SETUP_SPELL_IDS,
    bot_known_spell_ids,
    bot_primary_tree_spell_ids,
    bot_spell_ids,
    load_wdbc_values,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRAINERS = REPO_ROOT / "dataset/world_knowledge/trainers.jsonl"
SPELL_EFFECT_FMT = "nifiiiffiiiiiifiifiiiiiiiix"
SPELL_EFFECT_LEARN_SPELL = 36
SPELL_EFFECT_FIELD = 1
TRIGGER_SPELL_FIELD = 21
SPELL_ID_FIELD = 24
# Activating Secondary Spec / Activating Primary Spec (SPELL_EFFECT_TALENT_SPEC_SELECT),
# taught natively by 63680 when a character buys dual specialization.
DUAL_SPEC_SWITCH_SPELL_IDS = (63644, 63645)
CLASS_TRAINER_TYPE = 0
MAX_TRAINER_LEVEL = 85
CLASS_TRAINER_NAMES = {1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
                       6: "Death Knight", 7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid"}
_LEARN_CACHE: dict[Path, dict[int, list[int]]] = {}
_BASELINE_CACHE: dict[tuple[Path, int], frozenset[int]] = {}


class LoadoutSpellError(ValueError):
    pass


def spell_learn_map(dbc_dir: Path) -> dict[int, list[int]]:
    """spell -> spells it teaches through SPELL_EFFECT_LEARN_SPELL (SpellEffect.dbc)."""
    dbc_dir = Path(dbc_dir).resolve()
    cached = _LEARN_CACHE.get(dbc_dir)
    if cached is not None:
        return cached
    mapping: dict[int, list[int]] = {}
    for row in load_wdbc_values(dbc_dir / "SpellEffect.dbc", SPELL_EFFECT_FMT):
        if int(row[SPELL_EFFECT_FIELD]) == SPELL_EFFECT_LEARN_SPELL and int(row[TRIGGER_SPELL_FIELD]) > 0:
            mapping.setdefault(int(row[SPELL_ID_FIELD]), []).append(int(row[TRIGGER_SPELL_FIELD]))
    _LEARN_CACHE[dbc_dir] = mapping
    return mapping


def learn_closure(spells: Iterable[int], learn_map: dict[int, list[int]]) -> set[int]:
    result: set[int] = set()
    pending = [int(spell) for spell in spells]
    while pending:
        spell = pending.pop()
        if spell in result:
            continue
        result.add(spell)
        pending.extend(learn_map.get(spell, ()))
    return result


def class_trainer_baseline(class_id: int, learn_map: dict[int, list[int]],
                           trainers_path: Path = DEFAULT_TRAINERS) -> frozenset[int]:
    """Spells a class trainer teaches without a prerequisite ability, with their LEARN closure."""
    key = (Path(trainers_path).resolve(), int(class_id))
    cached = _BASELINE_CACHE.get(key)
    if cached is not None:
        return cached
    name = CLASS_TRAINER_NAMES.get(int(class_id))
    offers: dict[int, set[int]] = {}
    if name and Path(trainers_path).is_file():
        with Path(trainers_path).open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if str(row.get("subname") or "") != f"{name} Trainer":
                    continue
                for spell in row.get("trainer_spells") or []:
                    if (int(spell.get("trainer_type", -1)) == CLASS_TRAINER_TYPE
                            and int(spell.get("req_level") or 0) <= MAX_TRAINER_LEVEL):
                        offers.setdefault(int(spell["spell_id"]), set()).add(int(spell.get("req_ability1") or 0))
    # A trainer spell is baseline when some offer needs no ability or needs an
    # ability that is itself baseline (e.g. Maul requires Bear Form); an offer
    # that requires a talent stays talent-gated.
    known: set[int] = set()
    changed = True
    while changed:
        changed = False
        for spell, requirements in offers.items():
            if spell not in known and any(not req or req in known for req in requirements):
                known |= learn_closure([spell], learn_map)
                changed = True
    result = frozenset(known)
    _BASELINE_CACHE[key] = result
    return result


def _view(bot: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    return {"class": bot["class"], "class_spec": group["class_spec"], "spells": bot.get("spells", []),
            "primary_talent_tree_id": group["primary_talent_tree_id"], "talents": group["talents"]}


def specialization_closure(group: dict[str, Any], learn_map: dict[int, list[int]]) -> set[int]:
    seeds = {int(talent["spell_id"]) for talent in group["talents"]} | set(bot_primary_tree_spell_ids(group))
    return learn_closure(seeds, learn_map)


def talent_gated_profile_spells(class_id: int, class_spec: str, baseline: frozenset[int],
                                action_profiles: dict[str, Any]) -> set[int]:
    spec_spells = {int(spell) for spell in action_profiles.get("action_profile_spells_by_spec", {}).get(class_spec, [])}
    class_wide = {int(spell) for spell in action_profiles["action_profile_spells_by_class"].get(int(class_id), [])}
    proficiency = {int(spell) for spell in action_profiles["proficiency_spells_by_class"].get(int(class_id), [])}
    return spec_spells - set(baseline) - class_wide - proficiency


def loadout_known_spells(bot: dict[str, Any], dbc_dir: Path, action_profiles: dict[str, Any] | None = None,
                         trainers_path: Path = DEFAULT_TRAINERS) -> dict[str, list[int]]:
    action_profiles = action_profiles or DEFAULT_ACTION_PROFILES
    loadout = bot["loadout"]
    groups = loadout["groups"]
    active = groups[int(loadout["active_talent_group"])]
    learn_map = spell_learn_map(dbc_dir)
    single_active = set(bot_known_spell_ids(_view(bot, active), action_profiles))
    inactive = [group for group in groups
                if group is not active and group.get("mirrors_talent_group") is None
                and group["class_spec"] != active["class_spec"]]
    inactive_only: set[int] = set()
    if inactive:
        baseline = class_trainer_baseline(int(bot["class"]), learn_map, trainers_path)
        if not baseline:
            raise LoadoutSpellError(f"class_trainer_baseline_missing:{bot['class']}:{trainers_path}")
        for group in inactive:
            inactive_only |= specialization_closure(group, learn_map)
            inactive_only |= talent_gated_profile_spells(int(bot["class"]), str(group["class_spec"]),
                                                        baseline, action_profiles)
        inactive_only -= specialization_closure(active, learn_map) | single_active
    known = set(single_active)
    for group in groups:
        known.update(bot_spell_ids(_view(bot, group), action_profiles))
        known.update(NATIVE_SELF_SETUP_SPELL_IDS.get(str(group["class_spec"]), ()))
    known -= inactive_only
    if int(loadout.get("talent_groups_count") or 0) > 1:
        known.update(DUAL_SPEC_SWITCH_SPELL_IDS)
    missing_active = sorted(single_active - known)
    if missing_active:
        raise LoadoutSpellError(f"active_single_spec_spells_dropped:{bot.get('name')}:{missing_active}")
    return {"known_spell_ids": sorted(known), "inactive_only_spell_ids": sorted(inactive_only),
            "dual_spec_switch_spell_ids": sorted(DUAL_SPEC_SWITCH_SPELL_IDS)
            if int(loadout.get("talent_groups_count") or 0) > 1 else []}
