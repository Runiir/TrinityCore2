from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RaidAssignment:
    type: str
    mechanic_event_id: str
    mechanic_family: str
    assigned_to_guid: int
    eta: float
    target_guid: int | None = None
    cooldown: str | None = None
    subgroup: int | None = None
    target_enemy_guid: int | None = None
    priority: int = 0

    def as_frame_value(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "mechanic_event_id": self.mechanic_event_id,
            "mechanic_family": self.mechanic_family,
            "assigned_to_guid": self.assigned_to_guid,
            "eta": self.eta,
            "priority": self.priority,
        }
        if self.target_guid is not None:
            payload["target_guid"] = self.target_guid
        if self.cooldown is not None:
            payload["cooldown"] = self.cooldown
        if self.subgroup is not None:
            payload["subgroup"] = self.subgroup
        if self.target_enemy_guid is not None:
            payload["target_enemy_guid"] = self.target_enemy_guid
        return payload


class RaidAssignmentScheduler:
    def __init__(self, raid_members: list[dict[str, Any]]) -> None:
        self.raid_members = raid_members
        self._tank_index = 0
        self._interrupt_index = 0
        self._healer_index = 0
        self._soak_index = 0
        self._assignments: list[RaidAssignment] = []

    def next_tank(self, event_id: str, mechanic_family: str, eta: float) -> RaidAssignment:
        tanks = self._members_for_role("tank")
        assignment = self._assign("tank_swap", event_id, mechanic_family, tanks[self._tank_index % len(tanks)], eta, priority=20)
        self._tank_index += 1
        return assignment

    def next_interrupt(self, event_id: str, mechanic_family: str, eta: float, target_enemy_guid: int) -> RaidAssignment:
        candidates = self._members_for_roles({"melee_dps", "ranged_dps", "tank"})
        assignment = self._assign(
            "interrupt",
            event_id,
            mechanic_family,
            candidates[self._interrupt_index % len(candidates)],
            eta,
            target_enemy_guid=target_enemy_guid,
            priority=18,
        )
        self._interrupt_index += 1
        return assignment

    def next_healer_cooldown(self, event_id: str, mechanic_family: str, eta: float, cooldown: str) -> RaidAssignment:
        healers = self._members_for_role("healer")
        assignment = self._assign("healer_cooldown", event_id, mechanic_family, healers[self._healer_index % len(healers)], eta, cooldown=cooldown, priority=16)
        self._healer_index += 1
        return assignment

    def next_soak(self, event_id: str, mechanic_family: str, eta: float) -> RaidAssignment:
        candidates = self._members_for_roles({"tank", "healer", "melee_dps", "ranged_dps"})
        assignment = self._assign("soak", event_id, mechanic_family, candidates[self._soak_index % len(candidates)], eta, priority=14)
        self._soak_index += 1
        return assignment

    def subgroup_move(self, event_id: str, mechanic_family: str, eta: float, subgroup: int) -> list[RaidAssignment]:
        assignments = []
        for member in self.raid_members:
            if int(member.get("subgroup", 1)) == subgroup:
                assignments.append(self._assign("subgroup_move", event_id, mechanic_family, member, eta, subgroup=subgroup, priority=12))
        return assignments

    def add_target(self, event_id: str, eta: float, target_enemy_guid: int) -> RaidAssignment:
        candidates = self._members_for_roles({"melee_dps", "ranged_dps"})
        return self._assign("target_switch", event_id, "add_wave", candidates[0], eta, target_enemy_guid=target_enemy_guid, priority=15)

    def frame_state(self) -> dict[str, Any]:
        ordered = sorted(self._assignments, key=lambda item: (-item.priority, item.eta, item.assigned_to_guid))
        return {"assignments": [item.as_frame_value() for item in ordered]}

    def _assign(self, assignment_type: str, event_id: str, family: str, member: dict[str, Any], eta: float, **kwargs: Any) -> RaidAssignment:
        assignment = RaidAssignment(
            type=assignment_type,
            mechanic_event_id=event_id,
            mechanic_family=family,
            assigned_to_guid=int(member["guid"]),
            eta=round(float(eta), 3),
            **kwargs,
        )
        self._assignments.append(assignment)
        return assignment

    def _members_for_role(self, role: str) -> list[dict[str, Any]]:
        members = [member for member in self.raid_members if member.get("role") == role]
        if not members:
            raise ValueError(f"raid_missing_role:{role}")
        return members

    def _members_for_roles(self, roles: set[str]) -> list[dict[str, Any]]:
        members = [member for member in self.raid_members if member.get("role") in roles]
        if not members:
            raise ValueError(f"raid_missing_roles:{sorted(roles)}")
        return members

