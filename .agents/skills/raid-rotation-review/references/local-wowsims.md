# Local WoWSims server bridge

The downloaded Cataclysm binary is both a static web UI and a native simulation
HTTP server. Treat it as an exploratory tool until its exact build identity is
bound.

## Inspect without disturbing an existing server

Use read-only checks first:

```bash
sha256sum /path/to/wowsimcata-amd64-linux
ss -ltnp | rg 'wowsim|:3333'
curl -fsS http://127.0.0.1:3333/version
curl -fsSL http://127.0.0.1:3333/cata/ | head
```

Do not stop a user-started server, start a competing listener, or submit a long
simulation without authorization. The server exposes protobuf endpoints such
as `/computeStats`, `/raidSim`, `/raidSimAsync`, `/statWeights`, and
`/asyncProgress`; they are not JSON REST endpoints.

## Use the UI for exploration

The UI exposes spec presets for:

- APL rotations and strict sequences;
- gear, enchants, gems, reforges, and stat weights;
- talents, glyphs, consumes, race, spec options, and pet options;
- target count/stats/distance and encounter duration/execute proportions;
- detailed damage, resource, aura, and iteration results.

`RaidSimResult` has two complementary evidence surfaces:

- aggregate `ActionMetrics`, `AuraMetrics`, and `ResourceMetrics` for the full
  iteration cohort;
- a textual first-iteration debug log used by the UI to reconstruct casts,
  completions, landed effects, resources, auras, cooldowns, movement, and the
  timeline.

The log is empty unless the request enables `simOptions.debugFirstIteration`
(or equivalent UI debugging). Keep a diagnostic debug/timeline run separate
from the large statistical result and do not promote it as a qualification
denominator. Log timestamps are formatted with limited precision; line index is
the authoritative order for same-time events.

Use `CLI Export` to save a complete `RaidSimRequest` JSON. Hash the exported
bytes immediately. Prefer pinned source APL files when reviewing source policy;
the served minified JavaScript is useful for discovery but poor review authority.

Pass exported/native result JSON to `review_rotation_mechanics.py` with
`--wowsims-result`. The tool accepts a direct `RaidSimResult` or a wrapper with
`result`/`finalRaidResult`, normalizes per-iteration action metrics, and parses
the optional debug log into an ordered event timeline.

## Use pinned execution for reproducibility

For a deterministic or qualifying comparison, use the repository's pinned
WoWSims source revision and `run_wowsims_exact_references.py` lifecycle. Require
the request, binary/build receipt, result, transport, and DVC reconstruction
bindings. Record the local UI version/hash only as diagnostic provenance.

The local UI can suggest a rotation or reveal gear/stat behavior. It cannot by
itself prove that Trinity used matching gear, race, talents, pet/setup, target,
buffs, resources, execute schedule, or movement conditions.
