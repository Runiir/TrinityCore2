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
