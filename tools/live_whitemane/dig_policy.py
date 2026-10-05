"""Marker preference with a latched telescope fallback and per-race solve batches.

This module selects guidance sources and affordable projects. It never generates
hidden find positions, learns from unconfirmed finds, or sends game input.
"""
from dataclasses import dataclass, field


@dataclass
class DigProgress:
    site_id: int | None = None
    looted_finds: int = 0
    telescope_fallback: bool = False
    marker_attempts: dict = field(default_factory=dict)
    last_decision: tuple | None = None
    repetitions: int = 0

    def guidance(self, *, site_id, looted_finds, visible_marker=None):
        if site_id != self.site_id or looted_finds > self.looted_finds:
            self.site_id, self.looted_finds = site_id, looted_finds
            self.telescope_fallback = False
            self.marker_attempts.clear()
            self.last_decision, self.repetitions = None, 0
        if site_id is None:
            return 'outside_digsite'
        if self.telescope_fallback or visible_marker is None:
            return 'telescope'
        return 'gathermate_minimap_marker'

    def failed_marker_survey(self, marker_id):
        count = self.marker_attempts.get(marker_id, 0) + 1
        self.marker_attempts[marker_id] = count
        if count >= 2:
            self.telescope_fallback = True
        return self.telescope_fallback

    def decision_outcome(self, *, action, position, progress):
        key = (action, tuple(position))
        self.repetitions = self.repetitions + 1 if key == self.last_decision and not progress else 0
        self.last_decision = key
        if self.repetitions >= 2:
            self.telescope_fallback = True
        return self.telescope_fallback


@dataclass
class SolveBatches:
    active_races: set = field(default_factory=set)

    def next_project(self, race):
        """Re-read current project and bag state before every solve; keystones give 12."""
        index = race['index']
        if race['fragments'] >= 150:
            self.active_races.add(index)
        if index not in self.active_races:
            return None
        stones = min(race['sockets'], race['keystones_in_bags'])
        required = max(0, race['cost'] - stones * 12)
        if race['cost'] <= 0 or race['fragments'] < required:
            self.active_races.discard(index)
            return None
        return {'race': index, 'project_spell': race['project_spell'],
                'keystones': stones, 'fragments_required': required}
