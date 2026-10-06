# Owned native-backed Who search

UI104 `who_search01` qualifies only `friends.who_search` for one stock `n-Harnessone` query. One Refresh click produces one modern request, one native request and one response on each side. The bridge echoes request ID1 and enriches only the native-authorized row with its database identity. The native and modern results agree on GUID1, Harnessone, level85, Human Warrior and Badlands area3. Actual stock columns show Harnessone, Badlands,85,Warrior and "1 Person Found".

All21 action checks,8 checks against the pre-repair fixture,9 native restoration checks and12 friend restoration checks pass. The original empty query field and closed panels restore. The transient Who result cache remains at one row after this read; cleanup sends no second query. Original social rows, inventory/money, quest/header/selection, native quests, group, resources, stats, spells, actions, pose, AFK and position are preserved. The scout remains offline at Harnesstwo level1 character selection. Both existing owned clients stay on HDMI-1; only the bridge restarts. Script permission remains blocked, and the historical original `softTargetInteract=0` remains unrestored at stock-disabled1.

The bridge implements the pinned [modern Who packet layout](https://raw.githubusercontent.com/TrinityCore/TrinityCore/6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2/src/server/game/Server/Packets/WhoPackets.cpp) and the checkout's native Who layout. Native visibility remains authoritative. One unanswered request cannot be replaced because native replies carry no request ID. Asynchronous identity enrichment is bound to the same actor, state pointer and request serial. WHOIS/account-name packets are excluded from raw capture. The new observer reads public Who getters and stock labels without submitting queries or selecting rows.

Verification retains every earlier failure:

- `who_probe01` failed at an unmapped41-byte modern request and is excluded. Its empty query and all21 restoration checks passed.
- Two C++ builds failed at JSON/array type conversions; both were corrected before deployment. The successful build uses one job, with15,994,252KiB available memory before compilation. The existing unchanged mail.cpp:123 indentation warning remains recorded.
- New Who tests initially had46 fixture failures from omitted required arrays, then4 failures from the independent reader's missing byte alignment. Corrected focused tests pass46 in0.13s; the full codec-bound suite passes1786 in44.38s.
- The old packet-history priming regression failed once, retaining2500 synthetic records. Streaming priming peaks at no more than two, discards old records and preserves the next owned boundary. The additional lobby/entry readers stream history too; the full foundation suite passes1740 in44.50s.

No race-filter, cross-realm, enemy, arena, addon, non-ASCII exact-name, sorting, selection, invitation, whisper, missing-name or long-list variant is accepted by this record. Guild/other filter codec coverage is synthetic and does not qualify live UI behavior.

DVC pointer: `artifacts/client_harness/442_interactions_20261006_104.tar.gz.dvc`. The234,109,479-byte archive has SHA-256 `8ce675926dc3bb09d79ea76c52516012267b42d8a3313d0d61d79946782be313` and DVC MD5 `9d41b6c8beb8a60d3e7a665bfc66ccc2`. Cloud verification and archive review pass for31 JSON receipts and116 attributed images. Whole-pass, failed-probe, memory, build/test, deployment and runtime closure receipts are retained. Generated frames and the local archive/cache are removed only after this proof.
