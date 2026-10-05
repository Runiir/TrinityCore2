# Supervised Whitemane archaeology

The owned official launcher/client stays on HDMI-1. Character Runiir is farming
for Recipe: Vial of the Sands. No recipe was found during the evidence below.
The packet helper stops after 30 minutes without authenticated own gameplay
activity, with no fixed session limit. Only tcpdump needs terminal sudo access.

## Inputs and movement

The public observer supplies visible GatherMate markers, Canopic Helper's line
endpoint, distance, facing, mount/flight/falling/swimming state, loot tooltip
checksum and fragment increases. Laya receives typed facts, not screenshots.
The retained archaeology head's legacy `telescope` slot now encodes the selected
public navigation guide. Exact marker source and endpoint remain in its receipt.
This conversion supplies bearing, color/distance band and numeric distance; it
does not supply a preferred action or hide any of the seven choices.

The controller keeps a waypoint until arrival. It holds movement along long
approaches, brakes before delayed public position readings reach the endpoint,
and settles between final corrections. Turn holds use the median measured
angular speed of earlier owned-client turns instead of a 0.3-second cap.
Laya selects flight phases. Landing holds descent and requires two grounded
observations. The public altitude API currently returns zero even in flight;
height above terrain is unknown and is never inferred from map coordinates.

The boundary extension clips the displayed telescope line at the first exit,
eight yards inside the public 60895 perimeter. It checks build, active site ID
and addon-visible POI blob ID before allowing a line. The polygons came from
the local reference client's hashed public DB2 tables; Whitemane's streamed
asset bytes have not been compared directly. The controller also clips local
routes and watches for leaving that perimeter. A boundary mismatch stops input.

Mouse Button 4 is X button 8 / BTN_SIDE. A loot click requires a visible
archaeology-find tooltip and a subsequent fragment increase. Final pickup can
run after the site is replaced. Existing GatherMate markers are attempted first;
two unsuccessful marker Surveys latch telescope search until confirmed pickup.

## Evidence and rejected changes

- The retained archaeology head is `archaeology-head-v2`, SHA-256
  `c9d97c846d8ff7c7b4c072c5bb8a61e95ea89c6755f368d9341c32f71c4d05b9`.
- The retained travel head is `travel-head-v3`, SHA-256
  `b9a058ab4c6ea77ffffca6e40e3650da65a699a051514738f6c5472774f0eb46`.
- A changed question and renamed guidance schema passed only 3/22 shadow cases.
  That experiment did not send its choices to the game.
- A new guidance-head training run was interrupted after epoch 10 validation
  accuracy 0.728571. Its partial checkpoint is rejected and is not served.
- With the original question, unchanged inputs passed 14/14, numeric distance
  passed 14/14, source text alone passed 11/14, and a larger context block passed
  4/14. The larger blocks were rejected.
- Additional numeric-distance edge cases passed 26/27. For the rejected 220.24
  yard red/aligned case, Laya proposed Survey. The controller records that
  rejected result and retries the existing compact distance-band representation;
  all actions remain available. A disagreement in both forms stops input.
- Earlier Laya step 38 right-click completed as an input but did not loot.
  Step 39 confirmed a Troll fragment reward after pointer settling and tooltip
  review. Input completion is not counted as successful pickup.
- The first held approach overshot its waypoint because public coordinates
  lagged movement. Braking replaced that loop. A later correction moved 1.9
  yards and reached within 3.6 yards of the recorded marker. The flight's held
  descent confirmed grounded state twice. This does not prove terrain planning.
- A launcher mount macro sometimes failed; local flight now casts the owned
  Blue Wind Rider explicitly and dismounts only after grounding.
- The old passive reader incorrectly treated temporary process-CWD changes
  during addon reload as an installation change. It now pins the already-owned
  process lifetime, name and host executable. An already-running old reader
  needs one restart to load that fix.

The complete Southmoon digsite and the recipe farm remain unaccepted until
fresh live evidence confirms completion. Per-race 150-fragment batches with
maximum bag keystones are specified in `dig_policy.py`; live solving and the
cross-zone travel loop are not implemented by this dig controller.

Batch 01 is checkpointed through DVCLive and
`artifacts/client_harness/whitemane_live_20261005_batch01.tar.gz.dvc`. DVC push
completed and cloud status confirmed synchronization. Closed screenshots and
the rejected partial head were then pruned after checking their archived
hashes. The local archive and its exact cache object were also removed to keep
the batch remote-only. Local DVC status therefore reports this output not in cache;
restore it with `pixi run dvc pull` targeting that `.dvc` file.
