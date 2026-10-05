# Supervised live archaeology

Runiir's Whitemane client is owned by its existing Gamescope supervisor on
HDMI-1. Laya selects gameplay actions. Code verifies the observations and
executes calculated physical inputs in that client's private input session.

## Local public observation

The observer encodes normal addon APIs in local telemetry tiles. The controller
reads a small region of the exact owned Gamescope window on HDMI-1, decodes
its checksums and passes structured facts to Laya. No image vision or per-frame
PNG files are needed. The relay is disabled by default and sends zero server
telemetry messages. Its historical opt-in implementation remains on disk.

Freshness follows newly displayed M, A and UI generations using the host's
monotonic clock. Startup requires every channel to advance. A frozen tile ages
and stops input. Wine's GetTime can pause or catch up across loading screens,
so it is not treated as the host clock. Movement targets stay in public world
coordinates, with the original marker preference and inward boundary margin.

After installing the observer and reloading through a recorded Laya choice,
restart the reader once in the supervising terminal:

```sh
bash tools/live_whitemane/start_bearing_feed.sh
```

Activate local tiles after the recorded addon reload:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml \
  python -m tools.live_whitemane.telemetry_tiles --activate
```

The passive feed still provides authenticated owned height and telescope
facts. Local tile mode does not silently fall back to another transport.
The passive reader stops after 30 minutes of actual gameplay inactivity;
telemetry messages do not reset that timer.

For agent-managed capture restarts, Runiir can install the fixed command once:

```sh
sudo bash tools/live_whitemane/install_capture_permission.sh
```

The installer writes a root-owned wrapper and an argument-free sudoers rule.
Only `51.255.74.57:8085` traffic can be captured, to stdout, without promiscuous
mode. Tcpdump drops to Runiir after opening capture. No editable repository
script, arbitrary tcpdump options, output path or shell receives passwordless
sudo. The existing feed script uses the installed command with `sudo -n`.
To revoke this permission, remove `/etc/sudoers.d/whitemane-owned-capture` and
`/usr/local/libexec/whitemane-owned-capture` with sudo.

## Decisions and held input

The archaeology and travel heads share the frozen GPU encoder with the
original UI head on localhost port 8004. Head identity and complete token
budgets are checked on each request; all original action options remain
available. CUDA warms before the service announces readiness.

In local tile mode, waypoint movement requests a new retained-head Laya decision
on fresh movement samples at a target period of 100 ms. Accepted movement
stays held until replaced, arrived, interrupted, or its decision lease
expires. A separate input watchdog releases held keys after 350 ms without
an accepted decision, even if inference blocks. Turn duration follows the
turn-rate calculation; short approach pulses account for the measured feed
age. Route emergency bounds derive from distance and travel speed.

The existing marker-first rule, telescope fallback, digsite boundary margin,
calculated flight clearance and 150-fragment solve batches remain active.
Mounting and grounded dismounting use Runiir's Shift+Space toggle. Each toggle
is sent once and its resulting mounted state is checked before continuing.
Survey cooldowns are local readiness waits with no model request or gameplay
input; a spell cooldown does not change character availability.
Normal loot-window buttons are exposed and chosen by Laya if interaction
does not auto-loot the find.

An out-of-range interaction keeps the same find pending. Both "Out of range."
and "You are too far away." enter recovery. Distance-derived forward probes
shrink toward half a yard because this realm has a small gathering radius.
Laya retries interaction until the gathering cast starts, then waits for a
fragment gain. Pending pickup is included in its activity-selection state.
The latch survives addon reloads and site replacement. Minimap disappearance
alone cannot clear it.

Saved GatherMate rings remain history. Local minimap candidates become live
finds only after normal native-tooltip confirmation. The current live find
test was detected by its normal soft-interact name; minimap-only detection
missed that find and is not qualified as a complete detector. A named find
also blocks minimap clearance. Pointer/tooltip checks can fail in a background
window; they never create a false confirmed artifact.

The passive
reader admits a visible find's CreateObject position only within eight seconds
of Runiir's own Survey, with the exact owned character as creator and a known
archaeology-find entry. Other objects and owners are ignored. The position
expires after 20 seconds and must match the current reader, client and world.
It is a rendered find position, not a server-side hidden dig destination.
Laya receives its bearing through the existing waypoint schema; loot becomes
available at a close measured approach. After pickup, the pending observation
is discarded.

## Persisted farm graph

`whitemane_farm_graph_v1.json` names the recorded states and completion events.
Each run keeps `graph.json` with a bounded transition history and interrupted
state. It covers Survey, marker/telescope approach, gathering, pickup
verification, solve batches, Tol Barad teleport, Orgrimmar portal, taxi or
Ramkahen travel, flight, landing and combat. Key-1 combat checks the current
hostile target, action readiness and cooldown, then resumes the interrupted
activity. If combat interrupts flight, Laya first lands at the observed current
position and dismounts with Shift+Space. This recovery cannot ascend or travel
horizontally. A fresh "Target needs to be in front of you" error lets Laya
choose a half-turn timed from the owned turn calibration before retrying key 1.
Two unsuccessful facing corrections stop the run. No target switching or extra
combat abilities are used.

Laya selects farm activities from the current public state and available
actions. The graph records its choices rather than requiring the historical
stage order. Retained-head actions are accepted without comparison to an
expert label. The marker, pickup and solve rules are decision context; actual
cooldowns, owned-client identity and complete telemetry are still checked.

Start a fresh supervised run that stops with an unopened Canopic Jar:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml \
  python -m tools.live_whitemane.farm_loop \
  --output /home/runiir/.local/share/trinity-whitemane-live/evidence/farm_graph_01 \
  --stop-on canopic_jar
```

The 30-minute inactivity rule and resource bounds remain active. `--stop-on
recipe` retains the later jar-opening and recipe-search workflow.

Local movement stalls, missed interactions and transport attempts return to
fresh observations. Laya receives the failure and recent recovery history,
then chooses a retry, wait, landing or fresh Survey when applicable. Recovery
preserves pending finds and the travel destination. It does not reset the
30-minute gameplay inactivity timer. Client identity, telemetry attribution,
digsite boundaries and resource limits remain enforced.

## Validation boundary

The October 5 GPU replay made 100 original-head UI decisions at 10 Hz:
24.4 ms median, 28.7 ms 95th percentile, 51.3 ms maximum. Whole-GPU load
averaged 26.0%; this includes games and desktop rendering. A separate replay
of retained-head waypoint states passed 27 of 27 cases. These are inference
replays, not proof of the complete live farm loop. The broad original-head
movement prompt failed 9 of 12 replay cases and is not used for control.

The initial live travel and four Night Elf solves succeeded. Later, Laya
approached a supervisor-discovered Night Elf find and collected six fragments
(20 to 26) after two range recoveries. The two earlier skipped finds were
collected by the supervisor. No complete model-driven digsite or Canopic Jar
has yet been established.

The direct live observation replay subsequently completed 100 requests without
screenshots or gameplay input. Observation plus inference took 30.9 ms median,
36.0 ms at the 95th percentile and 109.6 ms maximum. Movement sample age was
53.9 ms median and 144.6 ms maximum. At the owned client's 15 FPS idle rate,
68 distinct movement generations were observed in those 100 request cycles.
This does not claim a guaranteed new observation every 100 ms.

The local-tile replay completed 100 requests with no input or server telemetry:
32.4 ms median total, 43.2 ms at the 95th percentile, 151.8 ms maximum, with
98 distinct movement generations. Extra minimap fields degraded the retained
steering prompt in replay and were removed. The original-head pickup-priority
question receives the signal separately, only for confirmed or pending finds.

Closed public evidence is checkpointed with DVCLive and DVC. Batch 04 stores
travel and solve evidence; batch 05 stores the stopped dig trial, GPU replay
and relay installation. Large local screenshot copies are removed only
after the exact archive has been pushed and its remote status checked.

## Resource limits

The farm checks its own hot directory and process memory every five seconds.
Closed phases are checkpointed at action boundaries once hot data reaches
64 MiB. The controller stops before further input at 256 MiB or with less than
2 GiB free disk. A failed upload preserves the unsynced files and stops the
farm. Only unchanged files listed in the verified archive manifest are pruned;
shared DVC objects and other threads' services are not collected.

Hot histories retain 16 farm phases, 40 dig decisions and 40 movement decisions.
Step indices remain monotonic after pruning. Full movement decisions stream to
closed evidence; the latest eight observation files are reused. Action logs
rotate at 1 MiB. Memory limits are 512 MiB controller RSS, 128 MiB reader RSS,
3 GiB model RSS and 3.5 GiB model VRAM, with a 1 GiB host-memory reserve.
Resource interruption releases the owned input sender and never closes a game
or stops another thread's model service.

The resource regression first exposed a failed budget check being hidden by
its five-second cache. The cache now keeps that failure fatal until a fresh
check confirms recovery. All 44 Python checks and the Lua sender/boundary
checks pass with the fix.

Checks use the client environment:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml \
  python -m pytest tools/live_whitemane -q
lua tools/live_whitemane/test_relay.lua
lua tools/live_whitemane/test_boundary.lua
```

The root Pixi environment lacks Pillow and Xlib and cannot collect the live
controller suite. This is an environment limitation, not a passing test run.
