# Supervised live archaeology

Runiir's Whitemane client is owned by its existing Gamescope supervisor on
HDMI-1. Laya selects gameplay actions. Code verifies the observations and
executes calculated physical inputs in that client's private input session.

## Public observation without screenshots

The observer reads normal addon APIs and sends prefix `WMLF1` addon messages
addressed only to Runiir. The existing passive bearing reader reconstructs
these authenticated outbound messages without saving raw captures or chat.
The relay sends heading, world position and movement mode at approximately
10 Hz; inventory/archaeology facts update more slowly. Journal, route, flight
map and other visible UI controls update when they change. Fragmented UI
updates are assembled atomically and cannot replace a complete generation
with a partial one. Movement has a separate channel and a bounded queue.

After installing the observer and reloading through a recorded Laya choice,
restart the reader once in the supervising terminal:

```sh
bash tools/live_whitemane/start_bearing_feed.sh
```

When the reader is ready and a complete UI generation has arrived, verify and
activate the relay (read-only game inspection; this changes local transport):

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml \
  python -m tools.live_whitemane.addon_relay --activate
```

Relay mode does not take screenshots or silently fall back to pixels. Loss
of current own-reader identity or fresh movement data releases input.
The passive reader stops after 30 minutes of actual gameplay inactivity;
telemetry messages do not reset that timer.

## Decisions and held input

The archaeology and travel heads share the frozen GPU encoder with the
original UI head on localhost port 8004. Head identity and complete token
budgets are checked on each request; all original action options remain
available. CUDA warms before the service announces readiness.

In relay mode, waypoint movement requests a new retained-head Laya decision
on fresh movement samples at a target period of 100 ms. Accepted movement
stays held until replaced, arrived, interrupted, or its decision lease
expires. A separate input watchdog releases held keys after 350 ms without
an accepted decision, even if inference blocks. Turn duration follows the
turn-rate calculation; short approach pulses account for the measured feed
age. Route emergency bounds derive from distance and travel speed.

The existing marker-first rule, telescope fallback, digsite boundary margin,
calculated flight clearance and 150-fragment solve batches remain active.
Normal loot-window buttons are exposed and chosen by Laya if interaction
does not auto-loot the find.

## Validation boundary

The October 5 GPU replay made 100 original-head UI decisions at 10 Hz:
24.4 ms median, 28.7 ms 95th percentile, 51.3 ms maximum. Whole-GPU load
averaged 26.0%; this includes games and desktop rendering. A separate replay
of retained-head waypoint states passed 27 of 27 cases. These are inference
replays, not proof of the complete live farm loop. The broad original-head
movement prompt failed 9 of 12 replay cases and is not used for control.

The initial live travel and four Night Elf solves succeeded. The first find
interaction did not confirm fragments, and no complete model-driven digsite
or repeating farm loop has yet been established. The relay and continuous
controller require live qualification after the reader restart.

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
