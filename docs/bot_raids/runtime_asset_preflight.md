# Reusable runtime asset checks

Launch through `tools.bot_ml.run_live_bot_validation` or the dummy-batch runner.
Do not reconstruct a temporary source asset tree or manually choose BWD merely
because its historical contract is familiar. The live runner derives the asset
map from its selected route, or map 0 for the existing calibration fixture. A
conflicting explicit map is rejected before verification or provisioning.
Missing closure arguments are filled from the selected checkout, configuration
DataDir and run output. Explicit custom roots remain supported and verified.
The derived bundle directory is created before verification. Route input changes
during verification are rejected; the runner then uses the retained route objects.
Child runs preserve explicit full-hash and strict-mode options.

Runtime navigation readers open files read-only. Their asset check requires
readable regular files with the expected bytes, sizes and membership, rather than
requiring an offline copy at mode 0444 and a native copy at mode 0664. Observed modes
remain in the receipt; `mode_policy=readable_runtime_input` identifies this
comparison. The generated route, gear and runtime-profile inputs use the same
read-access policy, avoiding irrelevant 0644/0664 differences. Other asset classes
retain exact mode requirements. No chmod or copy is performed. Historical extraction/archive manifests are unchanged.
The standalone closure verifier remains strict for sealed replay; the live CLI
also supports `--runtime-asset-strict-modes` when exact archived modes are needed.

Map patterns filter files before hashing. The regular-file walker reuses SHA256
values in a local SQLite cache under `$XDG_CACHE_HOME/trinity-cata` (otherwise
`~/.cache/trinity-cata`). Device, inode, mode, size, nanosecond mtime and ctime must
all match, and entries are scoped to the current boot. Files are reopened without
following symlinks; path and read-race checks remain active. Directory listings
are fresh so added/deleted members are still detected. Manifest, provenance,
configuration and expected hashes are verified on every run.

This cache is trusted local performance state, not a signed authority or portable
receipt. It is not intended to defend against an attacker who can rewrite both
the local cache and runtime files as the same OS user. `--runtime-asset-full-hash`
on the live CLI bypasses persistent reuse for an audit. Missing/corrupt cache
falls back to hashing. Never hydrate or promote this cache through DVC.

Inspect `hash_reuse.hits`, `misses` and `bytes_hashed` to measure benefit. An
unrelated sibling changing an ancestor directory timestamp does not invalidate a
file; replacement/type/permission changes and scanned-directory changes still do.
Do not interpret a passing asset check as class, boss or performance acceptance.
