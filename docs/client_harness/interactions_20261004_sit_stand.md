# Stock sit/stand binding

UI54 pose04 qualifies sit and stand through the installed X binding on both
owned human warriors. The checklist reaches 311/916 scoped operations. Modern
one-byte requests become native four-byte stand states; native one-byte replies
become modern state plus zero animation-kit ID. Native fields agree. Eight
reviewed settled frames show both standing and seated poses. Original AFK
status, seated pose, sheath, main bar, observed public position, native
health/power/stats, inventory, money and saved spell/action rows restore.

Pose01 fails before scored input because native creation omits zero stand and
power fields. Sparse getters now match the native field semantics. Pose02 also
fails before input because natural AFK had seated both clients. Those automatic
packets lie outside scoring windows and receive no binding qualification.
Pose03 passes native checks and restoration, but its early stand screenshots
still show seated paint. Its visual result remains unqualified. Pose04 waits
12 seconds passively after each input; no binding is replayed to settle paint.

The bridge build uses one job, takes 14.70 seconds and peaks at 523796 KiB RSS.
The 53 codec, observer and cleanup checks pass. The stance restoration regression
also passes after the sparse getter correction. Only the owned bridge restarts;
native worldserver and both client lifetimes stay unchanged on HDMI-1.

DVC54 archive is 199934098 bytes, SHA256
673b2384a21ee47e2de95b052b18d4b719a5f1e9b4266f10c45bdc9b6da06c6e.
Selected receipts and attributed frames pass archive digest verification.
Other races, chairs, combat, emotes, movement and persistence remain open.
