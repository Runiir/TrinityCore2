from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Reservation:
    type: str
    assigned_to_guid: int
    expires_in: float
    target_enemy_slot: int | None = None
    spell_id: int | None = None
    target_guid: int | None = None
    priority: int = 0

    def as_frame_value(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "assigned_to_guid": self.assigned_to_guid,
            "expires_in": self.expires_in,
            "priority": self.priority,
        }
        if self.target_enemy_slot is not None:
            payload["target_enemy_slot"] = self.target_enemy_slot
        if self.spell_id is not None:
            payload["spell_id"] = self.spell_id
        if self.target_guid is not None:
            payload["target_guid"] = self.target_guid
        return payload


class ReservationStore:
    def __init__(self) -> None:
        self._reservations: list[Reservation] = []

    def reserve(
        self,
        reservation_type: str,
        assigned_to_guid: int,
        *,
        expires_in: float,
        target_enemy_slot: int | None = None,
        spell_id: int | None = None,
        target_guid: int | None = None,
        priority: int = 0,
    ) -> Reservation:
        reservation = Reservation(
            type=reservation_type,
            assigned_to_guid=assigned_to_guid,
            expires_in=expires_in,
            target_enemy_slot=target_enemy_slot,
            spell_id=spell_id,
            target_guid=target_guid,
            priority=priority,
        )
        self._reservations.append(reservation)
        return reservation

    def tick(self, elapsed_sec: float) -> None:
        remaining: list[Reservation] = []
        for reservation in self._reservations:
            expires_in = reservation.expires_in - elapsed_sec
            if expires_in > 0:
                remaining.append(Reservation(
                    type=reservation.type,
                    assigned_to_guid=reservation.assigned_to_guid,
                    expires_in=round(expires_in, 3),
                    target_enemy_slot=reservation.target_enemy_slot,
                    spell_id=reservation.spell_id,
                    target_guid=reservation.target_guid,
                    priority=reservation.priority,
                ))
        self._reservations = remaining

    def active(self, reservation_type: str | None = None) -> list[Reservation]:
        reservations = self._reservations
        if reservation_type is not None:
            reservations = [reservation for reservation in reservations if reservation.type == reservation_type]
        return sorted(reservations, key=lambda item: (-item.priority, item.expires_in))

    def frame_state(self) -> dict[str, Any]:
        return {
            "reservations": [reservation.as_frame_value() for reservation in self.active()],
            "reserved_actions": [reservation.as_frame_value() for reservation in self.active()],
        }

