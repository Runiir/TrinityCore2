# Bounded specialist work contract

Use this contract for every delegated raid specialist task. The user's latest
instruction always wins.

## Lock scope before acting

Write a compact scope lock containing:

- the immutable evidence path or exact source state;
- one first-broken edge and one implementation hypothesis;
- the owned behavior and expected observable change;
- allowed files or directories;
- explicitly excluded adjacent lanes and mutations;
- one focused validation command, plus any explicitly assigned build or live
  run;
- terminal conditions for success, failed verification, and out-of-scope
  handoff.

Record pre-existing dirty files and leave them untouched. Read-only inspection
outside the owned files is allowed only to resolve the admitted edge.

## Stay inside the lock

- Implement one hypothesis. Do not fix a newly discovered adjacent problem.
  Return its evidence and owning specialist instead.
- Do not regenerate DVC stages, build, provision, start or stop servers, mutate
  databases, publish evidence, or clean artifacts unless the scope lock assigns
  that action.
- Run the focused validation once. If the patch itself causes a focused failure,
  permit one correction cycle and rerun it. An unrelated or pre-existing failure
  is a handoff, not permission for repository-wide repair.
- Do not run broad discovery, a full test suite, repeated live canaries, or a
  second optimization after the expected signal passes.
- If the evidence disproves the hypothesis or identifies another owner, stop
  without a speculative patch.
- Preserve cross-lane ownership for raid cooldowns. A role unit may tag and
  submit a native cooldown candidate; shared runtime owns the default
  trash/regroup/pre-pull reservation; an encounter unit may expose only the
  reviewed boss phase that releases it; shard architecture validates the
  resulting bag item, cast, aura, target, and timing receipts. Do not duplicate
  the reservation or release policy in a class rotation or route fixture.
- Treat an admission receipt as a mutation boundary. Gear, talents, glyphs,
  pet row/spellbook/autocast state, roster leases, group identity, difficulty,
  map, and instance identity must reach their declared state before the
  receipt commits. After commit, decision and route code may observe them but
  must not repair or normalize them. A legitimate native gameplay transition
  must be represented explicitly in the receipt contract before it is allowed;
  never silence an identity-drift diagnostic to accommodate a late mutation.
- Keep each receipt-bound observer and canonicalizer in one shared production
  owner. Do not copy pet, gear, roster, or instance identity logic into
  calibration, route, and runtime functions. If multiple consumers need it,
  extract a value-only helper and test all consumers against the same result.
- Treat priority-queue candidates as deferred work. A submitter may return
  before `Candidate::Attempt` runs, so its callable must explicitly capture
  every value it owns and may reference only state whose lifetime spans queue
  resolution. Do not use blanket `[&]` captures in deferred candidates. When
  touching a submitter, audit sibling candidates in that submitter and keep a
  source-level lifetime guard in the focused regression suite; a later stack
  layout change must not be able to resurrect dangling-capture behavior.
- Separate stable identity from native lifecycle state. A pet row, owner,
  entry, and persisted spellbook/autocast are identity; alive, summoned,
  in-world, current victim, and combat references are lifecycle. Death,
  dismissal, revive, summon, release, and worldport need typed recovery facts,
  not a rewritten receipt or a misleading identity-drift reason.

## Return a bounded handoff

Report the scope lock, exact changed files, decisive before/after signal, test
command and result, untouched dirty files, and the next owner if any. Changed
files must be a subset of the declared ownership. The coordinator must reject
and split a handoff that crosses the lock, even when its extra changes appear
useful.
