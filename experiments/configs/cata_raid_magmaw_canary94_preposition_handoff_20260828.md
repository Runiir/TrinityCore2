# Canary94 Magmaw pincer preposition handoff

## Scope

- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Route node: `bwd.magmaw.encounter`, generation 4
- Runtime commit: `8f7a40d015368abcc55070c0a4a3a679011d46f4`
- Binary SHA-256: `81144af6c8873a1c1e13ab7115b7e6d7f8df80b680614ab1dd77bb51613d67a4`
- Gate-bearing build receipt semantic SHA-256: `44944093a0c721c213ea3d98e33a92abde081e216e3d244251aad090feb274e4`

## Accepted observations

Canary94 cleared the entrance regroup, Chainwielder, and Drudge nodes with all
10 bots alive, then engaged Magmaw. It stopped fail-closed on a 300-second
semantic-progress plateau at the boss. This was a watchdog stall threshold,
not a raid success timer. The Hunter and Protection Paladin died, leaving eight
bots alive. Cleanup, identity, and all 319 combat-log chunks passed. No
forbidden assistance was observed.

The two deterministic pincer assignees did submit and retain mechanic-owned
movement during Massive Crash. Database position samples prove both moved
toward the native four-yard spell-click destination. They began roughly 17 to
25 yards away, however, and the short native window closed before both could
complete the normal mount and hook flow. The first broken edge is therefore
late approach timing, not missing assignment, path rejection, or a forced
movement override.

The Hunter accumulated six separate Pillar of Flame hits across 46 seconds and
died to the last hit. The Protection Paladin died to Mangle 89773. Those are
later edges until the pincer flow is attempted from a viable native position.

## Diagnostic correction

The reported 218,398.818 party DPS and 43,687.606 Affliction DPS are not valid
originated-DPS values. Magmaw and both exposed-head entries each received the
same 20,025,492 shared-health amount, and the old metrics summed all three
native callbacks. Effective healing remains valid at 6,657,051 healing and
22,043.215 HPS.

Commit `c93529f796` marks generic `NODAMAGE` callbacks whose spell contains
`SPELL_AURA_SHARE_DAMAGE_PCT`, retains them as explicit raw-event evidence, and
excludes only those callbacks from party, actor, and pet DPS. It also carries
the selected mechanic identity into native movement planner diagnostics. This
uses engine provenance and contains no Magmaw entry or spell special case.

## Bounded repair and replay contract

Gameplay commit `6226d3c024` allows only the two deterministic living DPS hook
assignees to preposition at the existing native spell-click destination while
Mangle or Massive Crash provides the native warning. Immediate local Pillar
escape and Massive Crash survival keep higher priority. Native timers, damage,
interaction flags, vehicles, hook spells, target selection, and pathing remain
unchanged.

The next matched canary must verify:

1. both assigned DPS emit `pincer_preposition` before the interaction window;
2. planner diagnostics retain the exact movement mechanic reason;
3. both reach and use the native pincer interaction and launch both hooks;
4. the tank is not killed by indefinite Mangle;
5. `.botauto diagnose` reports originated party and actor DPS plus unchanged
   effective HPS, while the cleanup combat log retains raw-event damage;
6. the completion watchdog either observes a normal clear or stops on the first
   later trace-backed failure.

Forbidden shortcuts include removing or reducing Mangle, reducing encounter
damage, extending the pincer window, teleporting players, forcing vehicle
occupancy or boss state, suppressing the watchdog, or encoding captured GUIDs
and coordinates.

## Evidence locations

- Report: `/tmp/trinity-magmaw-8f7a-canary94.RQC8Ok/canary94-report.json`
  (`91a107b64c0ece5a15e6a03ecab39adfe898200a123f5ccd88b0029507438297`)
- Normalized telemetry: `/tmp/trinity-magmaw-8f7a-canary94.RQC8Ok/canary94-raw.jsonl`
  (`750236acf28417ab01f30a2a4cd19fd1190c1acb60b02586d21ff72004d56609`)
- Worldserver log: `/tmp/trinity-magmaw-8f7a-canary94.RQC8Ok/canary94-worldserver.log`
  (`a8f3d5d49642e6d43151b645574a18f68b22ade63c2598f8ccf8532b38327f97`)

Use a fresh provisioned ten-player roster, an exact coordinator build receipt,
and the completion watchdog. No fixed raid success timer is allowed.
