# Extra action-bar forwarding failures

UI52 adds no qualification; the checklist remains306/916. Scout01 reads the
automatic action-bar diagnostic while Settings is visible. That diagnostic is
only visible in the world, so the read times out. The adapter now checks the
Settings value and native request while the panel is open, then reads the bar
after closing it. The cleanup-only episode restores the original grid, search,
panels and native state.

Scout02 exposes a bridge gap. The stock Action Bar2 checkbox enables and
disables locally, but the running bridge reports the modern one-byte
`CMSG_SET_ACTION_BAR_TOGGLES` as unmapped. Neither case forwards the native
`CMSG_SET_ACTIONBAR_TOGGLES`; the native player mask remains0 throughout.
Both cases remain failed. A second cleanup-only episode restores the remaining
empty-grid setting and all original settings, bar visibility and native
resources. Neither cleanup episode qualifies the operation.

The repair maps the exact one-byte body to the native opcode, rejects malformed
bodies, and preserves the existing harmless pre-world zero initialization.
Its candidate build and live validation follow in a separate batch. The
adapter also continues grid, search and panel restoration when its native
restore oracle fails, while retaining the original failure. An injected native
enable/restore failure regression passes and verifies that cleanup behavior.

The bridge build defaults to one job and requires6GiB of available memory.
The native worldserver is not rebuilt. Both clients stay on HDMI-1 and retain
their lifetimes during this batch.

DVC52 is synchronized: archive249800516bytes, SHA256
819bc736aa5dc5e63818a5aedaa7f32a52441cc823eeb79ba63d6a21df4e2b24.
All selected JSON receipts and their attributed frames undergo archive digest
verification before exact local frame and archive/cache pruning.
