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

Later book probes exposed stale partial chat observations and a pending glyph
that Escape cancels before closing its panel. Chat submission now waits before
checking the text or completing normal name entry. Observer v37 records pending
glyphs while their panel is visible and interleaves normal state between control
pages. Background text entry uses longer key holds and gaps. The first full
rerun had four chat-test failures because their fixtures assumed immediate
completion; the tests now distinguish delayed observation from deadline-expired
name completion, and the next full rerun passed 696 checks. Failed live book and
reload receipts remain failed; cleanup of the exact unused book passed separately.

## Cold login query burst

The fresh primary login sent 316 unique public creature queries in 44 ms. Native
had answered 59 when the 256-outstanding-query guard closed the connection. This
was an actual bridge failure, independent of desktop focus.

The bridge now forwards at most 64 creature queries at once, queues at most 4,096
distinct pending entries, coalesces duplicates and releases the next queued entry
after an authoritative native reply. Queued reads receive no invented missing
template response. Logout resets the active and waiting state. Regression cases
cover a 400-entry burst, duplicate and unsolicited replies, the pending bound and
release of capacity. The first full rerun retained two mail-test failures caused
by the corrected native opcode name and duplicate coalescing; their expectations
are updated without weakening the malformed-mail checks.

If a disconnected primary cannot pass a deployment's normal UI precheck,
`interaction_bridge_deploy restart --unavailable-primary-source <recovery.json>`
can use a closed failed owned-reentry receipt. It checks client/server lifetimes
and the exact native inventory, money, spells and talents before carrying the
previous public baseline forward. The initial public precheck stays deferred and
failed in its receipt. Both actors must pass fresh public checks after reconnect.
