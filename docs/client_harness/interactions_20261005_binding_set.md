# Character-specific bindings

UI65 adds `keybindings.per_character_toggle`, taking reviewed coverage to
**349/916**. The parent objective remains open.

`primary_binding_set02` switches the stock checkbox from account set 1 to
character set 2, saves and reloads, then accepts the stock warning when returning
to account set 1 and reloads again. All four persistence checks, the original
settings and all ten native/public restoration checks pass. Four actual frames
show the checked checkbox, the deletion warning, the unchecked checkbox and the
original seated character after cleanup.

The fixture had no character-specific bindings file. The original account
bindings file remains byte-identical and the generated character file is absent
afterward. Existing custom character bindings, other actors, warning cancellation
and conflicting assignments remain open.

The first trial failed in panel cleanup before any checkbox mutation case. All
ten restoration checks and original settings pass. Its initial inner exception
was masked by the old cleanup; the retained failure review does not invent that
cause. The revised trial clears the editor filter, handles the stock confirmation
and records inner operation failures separately.

The batch initializer used the Python environment without DVCLive and failed
before creating metadata. The first checkpoint attempt then failed on the missing
`native_server_before.json`. Both failures are retained. Metadata was explicitly
recovered from the first trial's recorded pre-input runtime, timestamp and source
commit; both trials and the current native process have the same identity. This
is a recovered initialization, not a successful initializer invocation.

The DVC archive is
`artifacts/client_harness/442_interactions_20261005_65.tar.gz.dvc`:
293709105 bytes, SHA256
`dc656404919082a01575e0edca8c1f21b308c34996297a4a3d2744159cce089e`.
Remote review verifies all 15 JSON receipts and 183 attributed frames before
local-frame pruning and exact archive/cache eviction. Qualification tests pass
all three checks. The native worldserver and both clients retain their lifetimes;
both client windows remain on HDMI-1. Further work uses already extracted client
sources and one input trial at a time after observed swap growth.
