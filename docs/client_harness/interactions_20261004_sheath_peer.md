# Weapon cycles and the owner view

UI57 corrects the observed weapon cycles. The geared primary visits native
states 1, 2 and 0; the scout visits 1 and 0. All five probes pass 55 native,
public, peer-update, position, idle, main-bar and UI checks. The selected cycle,
input and cleanup tests pass 21 checks. The worldserver, bridge and both client
lifetimes stay unchanged. Inputs and captures verify HDMI-1.

The characters stand four yards apart. Ten reviewed early and settled frames
show that the scout's sword draws in the peer view and returns to its back.
The scout's owner view keeps the sword on its back. The heavy primary's peer
views are retained without a precise weapon-position claim. This narrows the
open defect to owner rendering. Movement.sheath remains unqualified and the
checklist stays at 317/916.

All 20 character restoration checks pass and the original party is removed.
The original cohort still reports a temporary teleport cleanup failure:
MySQL FLOAT/text storage rounds the new orientation from 3.14159265 to 3.14159,
which fails the helper's exact-row comparison. An independent cleanup verifies
the original positions and complete owned rows, removes the one remaining
teleport, confirms the other three are absent and reloads only game_tele.
The helper now records each inserted row's database read-back value so future
cleanup retains its exact identity guard. This recovery does not turn the
original failed cohort into a pass.

The remotely synchronized DVC57 archive is 370303747 bytes, SHA256
bd3d8c893c1a5d62434f7a31e2ba0c4b24bcb2dad6fbf7a225d405594e2bbabb.
The original failure, exact scene frames, native update proof and independent
cleanup remain attributable. Remaining movement contracts continue separately.
