"""Native item-use restrictions of phase gear against the character who wears it.

Loading a character's inventory equips every saved item through
``Player::CanEquipItem`` (Player.cpp:17609, ``not_loading`` false), which calls
``Player::CanUseItem(Item*)`` (Player.cpp:10451) and so
``Player::CanUseItem(ItemTemplate const*)`` (Player.cpp:10846-10879); an item
that fails stays unequipped. ``item_use_failures`` mirrors those checks, in
the core's order:

* ITEM_FLAG2_FACTION_HORDE / ITEM_FLAG2_FACTION_ALLIANCE (ItemTemplate.h:190-191)
  against the character's team (Player.cpp:10853-10855); the team is
  ``Player::TeamForRace`` (Player.cpp:6138): ChrRaces.dbc BaseLanguage 1 is
  Horde, 7 is Alliance;
* AllowableClass & classMask and AllowableRace & raceMask, a zero result
  refusing the item (Player.cpp:10857-10858; the masks are
  ``1 << (class - 1)`` and ``1 << (race - 1)``, Unit.h:774-776), so a mask of
  0 refuses every character;
* RequiredSkill: skill value 0 or below RequiredSkillRank (Player.cpp:10860-10866);
* RequiredSpell the character must know (Player.cpp:10868-10869);
* RequiredLevel (Player.cpp:10871-10872);
* HolidayID: an event item refuses outside its holiday (Player.cpp:10875-10876);
* RequiredReputationFaction/Rank (``CanUseItem(Item*)``, Player.cpp:10837-10838).

The pipeline cannot prove a spell, a holiday or a reputation the provisioning
does not grant, so it fails closed on them: a RequiredSpell item is refused, a
holiday item is refused, and a reputation-gated item is refused unless the
character is declared to hold the rank (the canonical raid provisioning writes
no ``character_reputation`` rows, so every character holds only its default
standing; see ``item_policy.required_reputation`` in the phase config). Skills
are the professions the character is provisioned with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.build_validation_gear_profiles import load_wdbc

ITEM_FLAG2_FACTION_HORDE = 0x00000001
ITEM_FLAG2_FACTION_ALLIANCE = 0x00000002
TEAM_HORDE, TEAM_ALLIANCE = "horde", "alliance"
BASE_LANGUAGE_TEAMS = {1: TEAM_HORDE, 7: TEAM_ALLIANCE}  # Player::TeamForRace
CHR_RACES_FMT = "niixiixixxxxixsxxxxxixxx"  # DBCfmt.h ChrRacesEntryfmt
CHR_RACES_BASE_LANGUAGE_FIELD = 7
REPUTATION_POLICY_EXCLUDED = "excluded_unless_provisioned"


class EquipRestrictionError(ValueError):
    pass


@dataclass(frozen=True)
class CharacterView:
    """What the core checks an item against: race, class, level, team, skills, granted reputation ranks."""
    race: int
    class_id: int
    level: int
    team: str
    skills: Mapping[int, int] = field(default_factory=dict)
    reputation_ranks: Mapping[int, int] = field(default_factory=dict)

    def key(self) -> str:
        return f"race{self.race}/class{self.class_id}/{self.team}"


def load_race_teams(dbc_dir: Path) -> dict[int, str]:
    """{race: team} from ChrRaces.dbc BaseLanguage, as ``Player::TeamForRace``."""
    path = Path(dbc_dir) / "ChrRaces.dbc"
    if not path.is_file():
        raise EquipRestrictionError(f"equip_restriction_oracle_missing:{path.name}")
    teams = {}
    for row in load_wdbc(path, CHR_RACES_FMT):
        team = BASE_LANGUAGE_TEAMS.get(int(row["values"][CHR_RACES_BASE_LANGUAGE_FIELD]))
        if team:
            teams[int(row["values"][0])] = team
    if not teams:
        raise EquipRestrictionError("equip_restriction_oracle_empty:ChrRaces.dbc")
    return teams


def profession_skills(setup: Mapping[str, Any] | None) -> dict[int, int]:
    """{skill: provisioned value} of a profession setup (``merge_profession_skills``)."""
    return {int(row["native_skill_id"]): int(row.get("provisioned_value") or 0)
            for row in (setup or {}).get("requirements") or []}


def character_view(bot: Mapping[str, Any], teams: Mapping[int, str], skills: Mapping[int, int] | None = None,
                   reputation_ranks: Mapping[int, int] | None = None) -> CharacterView:
    race = int(bot["race"])
    if race not in teams:
        raise EquipRestrictionError(f"equip_restriction_race_unknown:{race}")
    return CharacterView(race=race, class_id=int(bot["class"]), level=int(bot.get("level", 85)), team=teams[race],
                         skills=dict(skills or {}), reputation_ranks=dict(reputation_ranks or {}))


def _mask_allows(mask: int, value: int) -> bool:
    return bool(int(mask) & (1 << (int(value) - 1)))


def item_use_failures(fact: Mapping[str, Any] | None, character: CharacterView) -> list[str]:
    """Why ``Player::CanUseItem`` refuses the item for the character (empty when it may wear it)."""
    if not fact:
        return ["item_template_unknown"]
    failures = []
    flags2 = int(fact.get("flags2") or 0)
    if (flags2 & ITEM_FLAG2_FACTION_HORDE and character.team != TEAM_HORDE) \
            or (flags2 & ITEM_FLAG2_FACTION_ALLIANCE and character.team != TEAM_ALLIANCE):
        failures.append(f"faction_restricted:{'horde' if flags2 & ITEM_FLAG2_FACTION_HORDE else 'alliance'}")
    if not _mask_allows(int(fact.get("allowable_class", -1)), character.class_id):
        failures.append("class_restricted")
    if not _mask_allows(int(fact.get("allowable_race", -1)), character.race):
        failures.append("race_restricted")
    skill = int(fact.get("required_skill") or 0)
    if skill:
        value = int(character.skills.get(skill) or 0)
        if value == 0 or value < int(fact.get("required_skill_rank") or 0):
            failures.append(f"skill_required:{skill}:{int(fact.get('required_skill_rank') or 0)}")
    if int(fact.get("required_spell") or 0):
        failures.append(f"spell_required:{int(fact['required_spell'])}")
    if character.level < int(fact.get("required_level") or 0):
        failures.append("level_required")
    if int(fact.get("holiday_id") or 0):
        failures.append(f"holiday_item:{int(fact['holiday_id'])}")
    faction = int(fact.get("required_reputation_faction") or 0)
    if faction and int(character.reputation_ranks.get(faction, -1)) < int(fact.get("required_reputation_rank") or 0):
        failures.append(f"reputation_required:{faction}:{int(fact.get('required_reputation_rank') or 0)}")
    return failures


def restricted_items(item_ids: Iterable[int], facts: Mapping[int, Mapping[str, Any]],
                     characters: Iterable[CharacterView]) -> dict[int, list[str]]:
    """{item_id: reasons} for the items any of the characters cannot wear."""
    characters = list(characters)
    if not characters:
        raise EquipRestrictionError("equip_restriction_characters_missing")
    result = {}
    for item_id in sorted({int(value) for value in item_ids}):
        reasons = sorted({f"{character.key()}:{reason}" for character in characters
                          for reason in item_use_failures(facts.get(item_id), character)})
        if reasons:
            result[item_id] = reasons
    return result


def check_reputation_policy(config: Mapping[str, Any]) -> None:
    policy = (config.get("item_policy") or {}).get("required_reputation")
    if policy != REPUTATION_POLICY_EXCLUDED:
        raise EquipRestrictionError(f"phase_required_reputation_policy_unsupported:{policy}")
