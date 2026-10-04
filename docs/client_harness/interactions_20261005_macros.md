# Macro editor controls

UI66 adds eight scoped contracts, taking reviewed coverage to **357/916**.
The parent objective remains open.

`macro_controls02` is a fresh whole-pass trial. It creates two disposable account
macros and one character macro, switches stock banks, saves a changed name and
observed icon, cancels deletion and verifies reload persistence. Stock
confirmation acceptance removes one owned macro during cleanup. Both banks then
restore to zero after reload, and all ten native/public restoration checks pass.
Actual rendered dialog, bank, saved-edit, selection and restoration frames were
reviewed.

Selection qualification uses the physical change after reload from TC442B at
index 1 to TC442Renamed at index 2, with unchanged counts. The earlier click on
an already-selected A is excluded. The harness now requires both name and index
changes for a selection test.

The installed macro UI selected slot 1 even in an empty bank and displayed the
previous macro's details. The compatibility addon's bounded UI hook hides those
details and disables deletion/editing when the selected bank contains no macros.
The fresh trial verifies the empty body field is hidden and Delete disabled,
then creates a character macro and verifies normal details return. The observer
remains read-only and uses a separate bounded macro page.

The initial inspection failed because Escape did not close the editor; its
settings and all ten native checks subsequently restored. The first mutation
trial passed its edits and reload but hit a diagnostic deadline during cleanup,
leaving one owned character macro. Recovery attempt 1 rejected a mismatched
numeric/formatted GUID comparison before macro input. Corrected recovery attempt
2 removes the exact source-attributed macro and restores zero banks and all ten
checks. All failures remain failures in the archive. Later trials use stock Exit,
fresh targeted control pages and bounded polling with varied sampling intervals;
they never replay an input while waiting for an observation.

The scope is the owned primary with originally empty banks, empty macro bodies
and an unused action probe. Generic popup checks cover the stock macro deletion
dialog. Other actors, existing custom macros and capacity variants remain open.
Macro-only trials keep their native verification within the macro interface;
binding/settings trials still preserve their original settings layout.

The DVC archive is
`artifacts/client_harness/442_interactions_20261005_66.tar.gz.dvc`,
1020882946 bytes, SHA256
`eb0746bb3542d2c9d9838c1ffcbdd0c18fa3723f13e3839de2a70ea9fb6cdd8b`.
Remote review verifies all 18 JSON receipts and 654 attributed frames before
local pruning and exact archive/cache eviction. No native rebuild or server/client
restart was required; both client windows remain on HDMI-1. Work stays sequential
after the reported OOM, with no additional client or model process.
