# Native warrior stance round trip

UI51 qualifies the stance bar and combat stance in complete primary04. The
checklist reaches306/916 scoped variants. Ordinary clicks select Defensive,
Berserker and the original Battle Stance. Stock active/checked buttons, native
spell completions71/2458/2457, native form bytes18/19/17, effective pages8/9/7
and all12 main-bar assignments agree. The original stance and bar, zero rage,
health, integer stats, native weapon damage, inventory, money and saved spell
and action rows restore. Five exact frames receive visual review.

Three earlier attempts remain failed and unqualified:

- Primary01 requires every stance in persisted spell rows. Starter Battle2457
  is absent there, but the native login known-spell packet contains all three
  stances. The corrected preflight uses that packet and exact SpellEffect
  shapeshift contracts. No click occurs in primary01.
- Primary02 uses physical1280x720 dimensions to normalize UI coordinates. The
  game UI basis is1365.3333740234x768, so the click254,654 misses Defensive Stance
  and generates no cast. Observer73 uses the established scaled UI coordinate
  basis. A read-only geometry episode verifies centers203,658;238,658;272,658
  against the rendered buttons before another click. Primary02 preserves its
  native resources and original layout.
- Primary03 passes all three native stance cases but fails its final stat guard.
  Weapon damage changes8146.9990234375/10121.939453125 to
  7406.3623046875/9201.76171875, an exact10% extra multiplier loss. The fixture
  separately knows unrestricted passive7381, the Berserker10% damage boost.
  Native passive learning applies it without a form restriction; leaving
  Berserker removes that boost. The intermediate damage values, native DBC and
  unchanged native source support this explanation. The initial weapon damage
  is not restored and the failed run remains explicit. Other stats, inventory,
  money, saved spells and action rows do restore.

Primary04 starts from the resulting Battle baseline and restores native weapon
damage exactly. Its guard allows only1e-6 relative/.002 absolute float rounding,
while integer stats remain exact. A regression using primary03's actual values
still rejects the10% change. Stance observation, restoration and latency Lua
tests pass3/3. Python compilation and Lua parsing pass. Native C++ source is
unchanged in this batch.

Both observer72 and73 deployments complete on the primary without a timeout.
The native worldserver, bridge and game lifetimes remain unchanged; presenters
stay on HDMI-1. DVC51 is synchronized, with15 JSON receipts and42 attributed
images verified. Exact local frames and archive/cache objects are pruned only
after remote and digest verification.

This is one idle zero-rage warrior. Other classes, combat and nonzero-rage
retention remain open. Reconnect persistence also remains open: learned7381
stays in the fixture's saved spell rows and may reapply on login.
