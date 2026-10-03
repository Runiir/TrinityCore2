# Concurrent clients without desktop focus changes

The primary and scout clients use separate Gamescope displays, Wine prefixes,
client directories and input locks. Both visible windows remain on HDMI-1. They
share only the isolated lab's servers and databases. This is input and client
state isolation, not a separate operating system or worldserver per character.

Each input adapter connects an independent C++ libei sender to its actor's private
Gamescope socket. The sender checks the Unix socket peer's PID, UID and process
start ticks, then waits for its emulated device to resume. It releases its pressed
keys/buttons on normal closure. Lost devices fail the task; actions are not
automatically replayed. Host window placement checks are read-only during tasks.
Keyboard lookup and screenshots use the actor's private X display.

Build/start/status/stop commands are in the [lab runbook](README.md#actor-isolation-and-concurrent-tasks).
Only one task can own each actor. Two concurrent UI workers use the committed
`442_two_actor_isolated_ui_v1.json` config. The explicit `--use-laya` flag scopes
new Laya calls to the user's requested bounded isolation trial.

## Live result

UI26 `native_isolated_laya_ui_02` passed all six Laya-selected actions. Both actors
opened bags, character equipment and friends through ordinary inputs, then closed
their panels. Native resources, equipment, group state and raid profiles matched
their baselines. Both worker lifetimes overlapped.

The read-only desktop watcher recorded 2,158 samples over approximately 109.5
seconds. Host focus and pointer stayed unchanged, and both clients remained in
the background throughout. It records opaque window handles and pointer
coordinates, without desktop screenshots or keys. The native worldserver was
neither rebuilt nor restarted.

This qualifies the concurrent panel case. Long-running archaeology, arbitrary
screenshot reasoning, fleet recovery and more than two clients remain open.

## Delayed UI observations

The first native-input trial failed panel restoration. Cleanup sent Escape again
before the first close was observed, opening the game menu on the scout. Cleanup
now waits for a state change before sending another Escape. A timeout fails the
task instead of repeating the input. Two regression checks verify those cases.
Resources and equipment stayed unchanged in the failed trial, whose receipt is
retained alongside the successful retry.

Earlier talent trials were initially suspected of losing their first input. A
single N press followed by observation, without another input, showed the talent
panel at 6.76 seconds after an empty observation at 2.7 seconds. This supports a
delayed observation for that trace. It does not prove that every earlier failure
had the same cause. Panel actions and read-only diagnostic pages now wait for
their requested state or page with a bounded timeout.

The current regression suite passes 694 tests. The wrong-peer and reused-process
tests verify rejection before any input traffic. Those guards also passed with
the sanitizer build. The live success uses the optimized C++ sender whose build
receipt pins its source, executable and libei header hashes.
