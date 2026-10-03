# Manual quest interaction qualification, October 3

The private 60895 client can manually accept quest 52, Protect the Frontier,
display its two named kill objectives, collapse and expand its zone, cancel
abandonment and then abandon it. Declining the offered quest has a separate
trial. These use stock buttons and owned keyboard/mouse input, with native quest,
inventory, money and pose restoration. Objective progress, completion, rewards,
sharing and persistence remain open.

The batch is `client_interactions_20261003_ui23`. Its evidence is checkpointed in
[`442_interactions_20261003_24.tar.gz.dvc`](../../artifacts/client_harness/442_interactions_20261003_24.tar.gz.dvc).
New trials use the code controller under the current AGENTS.md; no Laya/Jev call
or learned questing result is claimed. Both owned clients use observer v31 and
verified HDMI-1 windows. The owned native worldserver supervisor keeps PID 3428101 and start ticks
15075252 throughout the batch. Only the independent C++ bridge is rebuilt and
restarted; the observer also has a reload-only deployment.

## Repairs and retained failures

Native questgiver status uses a 64-bit GUID and 32-bit Classic status flags.
Modern Classic uses its packed 128-bit GUID and 64-bit flags. The adapter keeps
the Classic flag meanings, translates single/multiple responses and requires
visible questgiver identity. It rejects unknown bits, duplicates and malformed
lengths. Tracked-query semantics remain unimplemented. The native greeting list
also receives a separate modern-layout adapter, including explicit repeatable
and title-length fields.

The enabled Accept click in `manual_quest_accept_06` reaches native opcode 27447,
but raises a ByteBufferException. The bridge sends 13 bytes while the native
reader requires 16: `QuestGiverAcceptQuest::StartCheat` is `uint32`, whereas
`QuestGiverQueryQuest::RespondToGiver` is a one-byte bool. Both arrive as bits
from the modern client. The corrected translation preserves these different
native widths. The regression includes the captured Guard Thomas request,
both bit values, all truncated prefixes, trailing bytes and identity guards.

`manual_quest_accept_07` then accepts quest 52 natively, but the original oracle
fails because Elwynn Forest is collapsed. The public `C_QuestLog.IsOnQuest(52)`
probe now checks acceptance independently of the visible log rows. Expanding
and reading those rows remain separate physical-input checks. Trial 08 passes
acceptance, display and normal abandonment with complete restoration.

The log initially renders the second objective as `slain: 0/5`. The captured
client template query is `36030000` for Young Forest Bear, entry 822. The bridge
fabricates a negative response because the bear is unseen. Native
`HandleCreatureQueryOpcode` serves public static templates by entry without
requiring a spawned GUID. Public creature queries now reach that native
authority, retaining a visible GUID when available and using zero otherwise.
Invalid IDs, nonexact bodies and more than 256 outstanding entries are rejected.
Responses still require an outstanding query. This does not grant interaction
with an unseen creature. Trial 11 verifies the displayed wolf 0/8 and named
Young Forest Bear 0/5 objectives on the repaired bridge.

Other retained failures distinguish runner mistakes from protocol defects:
the all-races eligibility mask was initially misread; a fixed NPC point became
stale after the camera moved; quest details require asynchronous settling;
stock quest-text animation temporarily disables Accept; and the abandonment
dialog labels cancellation `No`. Fresh screenshot-bound point reviews, waits
without repeated input and observed button labels correct those checks. Trial
09 stops before cancellation because it expects `Cancel`; trial 10 passes the
corrected `No` path. Failed trials preserve explicit fixture cleanup receipts.
The final passing flow uses normal abandonment without fallback cleanup.

The list-deployment scout reconnect failure remains in its original receipt.
Mouse attempts leave the disconnect popup unchanged and emit no login traffic;
an observed Return confirmation recovers it. `interaction_bridge_deploy
reconnect --keyboard-modal` now supports this ordinary default-button path.
The final deployment verifies both clients' original resources, equipment,
group/profile state, sessions and observer version.

## Validation and reproduction

`public_template_full.xml` reports **673 passing world/auth tests**. The earlier
focused quest packet group passes 21 checks under ASan/UBSan; the final public
template/mail/quest group passes 41 selected sanitizer checks. These are protocol
checks, not counts of fully qualified gameplay features. Live episode receipts
retain every earlier failed attempt and the passing trials.

Commit changes and build only the bridge when its protocol code changes:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.world.control build
```

For an observer-only change, use `interaction_observer_deploy --output
<new-deployment-directory> --version <expected-version>`. It copies the committed
read-only addon to both clients, uses `/reload`, verifies both actor baselines
and checks that neither server process nor session changed.

Run each physical trial separately inside a newly initialized evidence batch:

```bash
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_quest_accept --output <batch>/manual_accept --review-point-file <new-review-file>
```

After staging, inspect `manual_giver_staged.png` and its `episode.json` receipt.
Within the 60-second review window, create the new review JSON with the staged
`guid`, exact `frame_sha256`, bounded client-pixel `point: [x, y]`, and a short
`source` describing that review. The runner rejects an existing review file,
the wrong actor/frame or an out-of-bounds point. Use `--action decline` and a
different output/review file for the separate decline trial. `--stage-only`
captures and restores the fixture without qualifying an interaction.

The fixture requires primary actor Harnessone, native Guard Thomas and quest 52
absent from active/rewarded state. It rejects source items, auto-accept flags and
unsupported eligibility. Wider quest variants require separate contracts and
fresh evidence. Follow the [runbook](README.md#evidence-and-publication) to commit,
checkpoint, verify cloud hashes and remove only verified local frames/archives.
