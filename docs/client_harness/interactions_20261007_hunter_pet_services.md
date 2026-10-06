# Owned Hunter control and pet-service prerequisites

UI142 continues the complete player-interaction objective, with441/916 qualified
operations and475 still open. These prerequisites add no new qualification.

The fresh ordinary retained Hunter entry passes its9 admission checks. The stock
trainer now displays Control Pet after the UI141 metadata repair. One ordinary
purchase passes all9 checks: native parent79682, learned dependent93321, matching
modern delivery, exact native relation, normal saved parent row, and646 copper
charged. Money changes9354→8708; the native saved spells are1515 and79682. All five
prior actors remain frozen. The retained starting Wolf is pet4/entry42717/owner6,
created by79597; it is not a tame result.

The native control catalog and modern delivery agree exactly, with10 public action
rows and a visible Attack button. Menu diagnostics expose two harness issues and
one compatibility gap. `hunter_pet_menu_recon01` fails its exact pet-row check
because only native `savetime` advances during normal autosave; the failed receipt
stays failed. The new check permits only a monotonic save clock and compares every
other saved pet field exactly. Native `Player::SaveToDB` calls `SavePetToDB`, which
writes the current game time. Regression checks reject name, owner, slot, health,
level, action-bar and identity changes.

`hunter_pet_menu_recon02` completes catalog/restoration diagnostics but opens the
player menu. The stock PetFrame has asymmetric mouse insets7/66/6/7, placing its
visual center outside its clickable region. This receipt supplies no owned pet
menu acceptance. Passive observer139 reads the current unit/GUID and mouse
rectangle center without changing frame attributes or invoking game actions.
It is normally reloaded on the scout; the primary remains offline.

`hunter_pet_menu_recon03` opens the actual stock Wolf menu. Its title and owned
target agree, but Rename is absent, so the whole trial fails. All13 restoration
checks pass. The native pet's bytes2 value196609 contains pet flags3, meaning
rename and abandon are permitted. Both native and pinned4.4.2 definitions use
bits1/2 for these permissions. The bridge previously omitted the corresponding
PetFlags byte. Creation and sparse mask80 update paths now preserve that byte,
including permission removal to0.

The bounded capture helper retains only a configured session's exact owned
Hunter6/pet4, synthetic name `Harnesswolf`, complete packet shape, and at most120
seconds. It writes a separate private journal; general rename bodies remain
excluded from the global packet journal and checkpoint allowlist. No normal
Rename request has yet been captured or forwarded, and no Rename handler is
released. The bridge build871c43ee73 uses one job with17665176KiB memory available;
deployment and live menu acceptance are the next steps.

Validation retains both failures and fixes. The probe/privacy checks pass23 tests;
the passive frame/owned-pet checks pass44. The initial full run passes3411 and fails
two old complete-unit packet-order expectations because mask80 and its byte are
now present. Those expectations are updated to the pinned serializer order and
the full rerun passes3413 tests in47.01s. An initial build CLI invocation used an unsupported
`--jobs` argument and performed no compilation; the corrected `--build-jobs1`
invocations succeed. Logs retain every result.

The Hunter is normally logged out; Harnesstwo is selected and remains offline.
The closed preservation boundary passes16 checks, including all five prior actors,
the exact retained Hunter native/saved/pet rows, normal paid lessons, all13 failed
menu restoration checks, and unchanged worldserver/client lifetimes. Harnessone's
saved user pose remains protected. Custom scripts remain blocked, with the
accepted original softTargetInteract0 unrestored at1. The user's prior movement
and buzzard selection are recorded as user input; the separate later primary
logout remains unattributed.

The closed checkpoint is `artifacts/client_harness/442_interactions_20261007_142.tar.gz.dvc`,
332617598 bytes, MD5 `4bd40897b9752b070222108c221c2448`, SHA-256
`4751e5e2d06c7f724be21d1eb71b51cf54dfd7c9669a97e55c33565e1d2b6384`.
Actual remote streaming verifies all30 JSON records,181 PNG images and the3 exact
accepted native purchase/learn/modern-delivery packets for Control Pet. Only after
that proof are181 raw PNG files313111314 bytes and the exact archive/cache object
offloaded. DVC status intentionally reports not-in-cache; push reports up to date.
Two eviction CLI calls reject paths because the tool requires a basename and remove
nothing; the corrected basename invocation succeeds. All post-checkpoint reports
are copied into UI143. New paid-control continuity guards pass17 checks before
reentry on the changed bridge; they require the complete owned offline deployment
chain and never replay the purchase. UI143 continues live menu and Rename work.

UI143 deploys the missing native permission byte and the correct stock Wolf menu
passes all6 catalog,3 menu and13 restoration checks. Rename uses two dialogs. The
first capture helper incorrectly treats Accept, which opens the stock Yes/No
confirmation, as submission. That whole failed receipt stays excluded; no Rename
packet is sent and all13 restoration checks pass. Separate fresh image reviews
for both stages produce one actual25-byte `Harnesswolf` request, pet number4 and
the exact owned GUID. Native translation is absent during capture; Wolf stays
unchanged and all13 restoration checks pass. The private capture is disarmed.

The captured shape now drives a native Rename translator. It requires a current
Hunter, released native control catalog, matching pet number/owner/summon links
and native rename permission. It preserves the submitted ASCII name and GUID;
the native core owns validation, persistence and one-time permission removal.
General Rename bodies remain excluded. The one-job build a3866085fa uses
17260488KiB available memory,65 focused protocol checks pass, and the full
world/auth suite passes3515 tests in48.90s. Paid Control knowledge can cross
successive verified bridge deployments without another purchase. Its first
new test run has29 passed and1 failure because the synthetic two-change fixture
contains two source references instead of four; the failed log is retained. The
corrected fixture and explicit four-reference admission pass30 tests. Rename
acceptance/preservation guards pass62 tests. Both original actors remain offline
through the second bridge-only deployment. Live Rename acceptance passes all18 outcome checks,4 post-name menu checks and13 restoration checks. Native storage and public name replies retain `Harnesswolf`; native permission flags change3 to2 and Rename disappears while Abandon remains available. A stale125-second filled-dialog review is rejected before any confirmation input; a read-only fresh capture fixes it without relaxing the guard.

Normal logout and reentry retain the saved name, pet number4 and the removed one-time permission. The first persistence trial remains whole failed/excluded because its oracle incorrectly requires a new bridge transport session ID. All other13 persistence checks and all13 restoration checks pass; normal character reentry reuses that healthy connection. The corrected oracle requires a later offline-to-native-login epoch, and the existing new-runtime-GUID/same-saved-pet check remains. Its27 guards pass; fresh whole persistence02 passes14 persistence,4 menu and13 restoration checks. The earlier final guard selection passes113 tests. This adds no qualification until DVC143 actual remote verification and normal parking close. No Rename or paid Control purchase is repeated.
