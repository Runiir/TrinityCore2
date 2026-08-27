# Magmaw Canary91: first boss death is Pillar of Flame

Canary91 used exact source `af1ff054dc1a46553880d91dc8049cd308b64f27`,
gate-bearing build receipt `89c5733dfc1869c9cb317bcc2548d5da7226819319ad0c01232a2ab514665b91`,
and worldserver binary `a20479fa267568bbe3cc2780915c41399ff3fb699db5fbd2c5e87d9ac05faf02`.
Fresh provisioning and DB readback passed for the exact offline, unleased 2/3/5
Magmaw roster with zero group, instance, ghost-aura, corpse, or corpse-phase
residue.

The completion-watchdog run lasted 520.555 seconds. It cleared the entrance,
Chainwielder, and both Drudges, then reached Magmaw. This proves the Canary90
same-level hazard-floor repair advanced the route. Canary91 stopped fail-closed
at three deaths during Magmaw; it did not kill the boss and is not accepted
evidence.

## First causal edge

The first death was ranged Hunter `Mgwdpsd` (`30009`) at
`1787871985853`. Pillar of Flame entry `41843`, spell `77971`, hit at
`1787871985349` and `1787871985852` for `123434` total damage. Recorded
distance was `0.132` yards. The second hit landed one millisecond before the
death event. This is a direct ranged hazard-escape failure.

The bounded repair is: when an alive ranged bot is inside the active Pillar of
Flame hazard, submit the existing high-priority hazard movement candidate
through the decision queue and native movement planner. Ranged should stage at
the room rear before Pillar, keep mobile damage active while moving, and focus
Lava Parasites when present. Outside-hazard ranged, melee, and tanks must not
churn movement.

Do not teleport, force target or success, alter enemy health/damage, shrink the
hazard, suppress the watchdog, or special-case a GUID or recorded coordinate.

## Other observed deaths

- Blood DK `Mgwtankb` (`30002`) died at `1787872049803` after four terminal
  Mangle ticks totaling `151484` from `1787872043796` through
  `1787872049801`. Healer diagnosis near this window frequently reported
  `no_valid_profile_action`; this is a separate healer/precast review.
- Fire Mage `Mgwdpsa` (`30006`) died at `1787872051922` after sustained Magma
  Spit and parasite contact, Infectious Vomit at `1787872049949`, and Massive
  Crash for `53886` at `1787872051311`. Parasite escape/add focus remains a
  later edge if it persists after the first repair.

## DPS and HPS signal

The Magmaw encounter window was 166 active damage seconds: party DPS
`174092.801`, party HPS `32710.783`. Affliction averaged `36154.614` DPS with
`1808060` pet damage, `0.301260` pet share, and `0.469880` pet uptime. A live
`botauto diagnose` snapshot directly returned `210149.654` party DPS and
`31547.252` party HPS plus per-bot DPS/HPS and pet share. This proves the new
diagnostic response contract works; it is not the authoritative isolated
300-second Affliction calibration.

## Evidence limitations

Combat-log transport passed (`294/294` chunks, `3611951` bytes), identity and
cleanup passed, and forbidden assistance was absent. Final evidence demux did
not pass because the forced trace response reported a delta gap and the run
ended before a ready-check event. Preserve the raw batch until the bounded
repair and capture-tool review complete.

Evidence paths:

- report: `/tmp/trinity-magmaw-af1ff054dc-canary91.EfqWQC/canary91-report.json`
- normalized raw: `/tmp/trinity-magmaw-af1ff054dc-canary91.EfqWQC/canary91-raw.jsonl`
- worldserver log: `/tmp/trinity-magmaw-af1ff054dc-canary91.EfqWQC/canary91-worldserver.log`

Report canonical SHA-256 is
`c8174089d41ff6ec4deeba5d9790722f446e687824419bbea227368e6ae8e127`;
report file SHA-256 is
`dd4b829fb046e5ef184b5361b823723c7780a6e08f7855be76f20a6a6cd55955`.
